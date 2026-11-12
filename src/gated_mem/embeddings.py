"""Embedding 提供者：本地优先 + 协议可插拔 + 零网络回退。

设计依据：GM-DIRECTIVE-P3-v2.2.0 议题 2（选项 C-Lite）。

铁律：
  1. 默认引擎必须是零依赖、断网可跑、确定性的（BuiltinHashEmbedder）。
  2. 可选引擎（FastEmbedProvider）缺失时必须优雅降级到 sys.stderr 提示，绝不抛异常打断主流程。
  3. model_id 必须随向量一起持久化；不同 model_id/dim 的向量严禁混算余弦。
"""
from __future__ import annotations

import hashlib
import math
import re
import struct
import sys
import unicodedata
from typing import Dict, List, Optional, Sequence

# 默认向量维度。384 与 bge-small 系列对齐，便于将来切换真实模型时不改库结构。
DEFAULT_DIM = 384

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_WORD_RE = re.compile(r"[a-zA-Z0-9_]+")


class EmbeddingProvider(object):
    """向量提供者抽象协议。

    任何实现都必须满足：
      - model_id 稳定不变（写入库的向量与其绑定）
      - dim 固定（维度不同的向量不可比较）
      - embed() 对同一输入返回完全相同的向量（确定性）
    """

    model_id: str = "abstract"
    dim: int = 0

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        """把一批文本编码为向量列表。"""
        raise NotImplementedError

    def embed_one(self, text: str) -> List[float]:
        """单条编码。"""
        return self.embed([text])[0]

    def _normalize(self, vec: List[float]) -> List[float]:
        """L2 归一化，保证余弦可直接用点积。"""
        norm = math.sqrt(sum(x * x for x in vec))
        if norm <= 0.0:
            return vec
        return [x / norm for x in vec]


# ---------------------------------------------------------------------------
# 技术概念词表（跨词汇桥接）
# ---------------------------------------------------------------------------
# BuiltinHashEmbedder 是纯字面的，无法把「持久层主库并发瓶颈」与
# 「MySQL 连接池打满」联系到一起。为了让零依赖兜底引擎在本工具的目标域
# （软件架构演进）内可用，这里内置一张人工维护的概念归并表：
# 每个词都能命中一组共享的 concept token，使同义/近义表达在向量空间靠近。
#
# 这是**人工整理的领域词典**，不是学习出来的语义模型。它的覆盖边界就是
# 这张表本身——表外的词仍然只能靠字面匹配。FastEmbedProvider 可用时不需要它。
CONCEPT_LEXICON = {
    # 持久化 / 数据库
    "database": ["数据库", "持久化", "持久层", "存储层", "db", "主库", "从库", "数据存储"],
    "pg": ["postgresql", "postgres", "pg", "大象"],
    "mysql": ["mysql", "mariadb"],
    "pool": ["连接池", "连接数", "连接", "pool", "pooling"],
    "bottleneck": ["瓶颈", "打满", "耗尽", "饱和", "压力", "不够用", "扛不住", "并发问题"],
    "concurrency": ["并发", "高并发", "并行", "吞吐", "qps", "tps"],
    "migration": ["迁移", "切换", "替换", "换掉", "废弃", "弃用", "改用", "migrate"],
    "cache": ["缓存", "cache", "redis", "memcached", "kv"],
    "queue": ["队列", "消息", "mq", "kafka", "rabbitmq", "rocketmq"],
    "auth": ["认证", "鉴权", "登录", "授权", "auth", "oauth", "jwt", "token", "会话", "session"],
    "build": ["构建", "打包", "编译", "build", "webpack", "vite", "rollup", "esbuild"],
    "test": ["测试", "单测", "用例", "test", "pytest", "jest", "mock", "断言"],
    "deploy": ["部署", "发布", "上线", "deploy", "release", "k8s", "kubernetes", "docker", "容器"],
    "frontend": ["前端", "页面", "组件", "frontend", "react", "vue", "ui"],
    "api": ["接口", "api", "rest", "grpc", "graphql", "端点", "endpoint"],
    "log": ["日志", "监控", "观测", "log", "metric", "trace", "告警", "apm"],
    "security": ["安全", "密钥", "加密", "权限", "安全约束", "secret", "key", "漏洞"],
    "performance": ["性能", "优化", "加速", "变慢", "耗时", "延迟", "latency", "快"],
    "reason": ["原因", "为什么", "为何", "理由", "why", "because", "动机"],
}

# 反向索引：子串/词 -> concept 名列表
_CONCEPT_INDEX = None


def _concept_tokens(text: str) -> List[str]:
    """把文本映射为一组 concept token（供向量器混入特征）。"""
    global _CONCEPT_INDEX
    if _CONCEPT_INDEX is None:
        idx = {}
        for concept, words in CONCEPT_LEXICON.items():
            for w in words:
                idx.setdefault(w.lower(), []).append(concept)
        _CONCEPT_INDEX = idx

    s = unicodedata.normalize("NFKC", text).lower()
    hits = set()
    for word, concepts in _CONCEPT_INDEX.items():
        if word in s:
            hits.update(concepts)
    return ["c:" + c for c in sorted(hits)]


class BuiltinHashEmbedder(EmbeddingProvider):
    """内置确定性字符 N-gram 特征哈希向量器。

    原理：把文本拆成中文字符 2/3-gram 与英文词元，用带符号的特征哈希
    投影到固定维度，再做 L2 归一化。整个过程无随机数、无外部依赖、无网络。

    它不追求语义精度，只保证：
      - 确定性（同输入必同输出）
      - 局部性（字面相近的文本向量相近）
      - 中英文都可用（中文走 n-gram，英文走词元 + 词根共享）
    """

    def __init__(self, dim: int = DEFAULT_DIM, seed: int = 0x5EED) -> None:
        if dim <= 0:
            raise ValueError("dim 必须为正")
        self.dim = dim
        self.seed = seed
        self.model_id = "builtin-hash-%d" % dim

    def _features(self, text: str) -> List[str]:
        """提取特征串：中文 2-gram/3-gram + 英文整词与词根。"""
        s = unicodedata.normalize("NFKC", text).lower()
        feats: List[str] = []

        for run in _CJK_RE.findall(s):
            # 单字也入特征，保证极短文本可用
            feats.extend(list(run))
            for n in (2, 3):
                if len(run) >= n:
                    for i in range(len(run) - n + 1):
                        feats.append(run[i : i + n])

        for w in _WORD_RE.findall(s):
            feats.append("w:" + w)
            # 简易词根共享：去掉常见英文后缀，让 migrate/migration 落到同一特征
            for suf in ("ing", "tion", "ed", "es", "s"):
                if len(w) > len(suf) + 3 and w.endswith(suf):
                    feats.append("w:" + w[: -len(suf)])
                    break

        # 概念桥接：让跨词汇的近似表达落到共享特征上
        feats.extend(_concept_tokens(s))
        return feats

    def _bucket(self, feat: str) -> (int, float):
        """带符号哈希：同一特征永远落到同一桶与同一符号。"""
        h = hashlib.sha256((feat + "\x00" + str(self.seed)).encode("utf-8")).digest()
        idx = struct.unpack("<I", h[:4])[0] % self.dim
        sign = 1.0 if (h[4] & 1) == 0 else -1.0
        return idx, sign

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            feats = self._features(text)
            if not feats:
                out.append(vec)
                continue
            # 用 1/sqrt(n) 缩放，避免长文本范数爆炸
            weight = 1.0 / math.sqrt(len(feats))
            for feat in feats:
                idx, sign = self._bucket(feat)
                vec[idx] += sign * weight
            out.append(self._normalize(vec))
        return out


class FastEmbedProvider(EmbeddingProvider):
    """可选的本地 ONNX 向量引擎（fastembed）。

    未安装 fastembed 时构造会抛 ImportError，由 get_default_provider()
    捕获并降级到 BuiltinHashEmbedder，同时向 stderr 打印一行提示。
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5") -> None:
        try:
            from fastembed import TextEmbedding  # type: ignore
        except Exception as exc:  # pragma: no cover - 取决于环境
            raise ImportError("fastembed 未安装：%s" % exc)
        self._model = TextEmbedding(model_name=model_name)
        self.model_id = "fastembed-%s" % model_name
        self.dim = self._probe_dim()

    def _probe_dim(self) -> int:  # pragma: no cover - 依赖真实模型
        vec = next(iter(self._model.embed(["维度探测"])))
        return len(list(vec))

    def embed(self, texts: Sequence[str]) -> List[List[float]]:  # pragma: no cover
        return [self._normalize([float(x) for x in v]) for v in self._model.embed(list(texts))]


def get_default_provider(prefer: Optional[str] = None, dim: int = DEFAULT_DIM) -> EmbeddingProvider:
    """按优先级构造 provider。

    prefer:
      - "builtin" / None：内置哈希
      - "fastembed" / "auto"：尝试 fastembed，失败则降级并提示到 stderr
    """
    if prefer in ("fastembed", "auto"):
        try:
            return FastEmbedProvider()
        except Exception as exc:
            sys.stderr.write(
                "[gated-mem] fastembed 不可用（%s），已降级到 BuiltinHashEmbedder(%d 维)。\n"
                % (exc, dim)
            )
            return BuiltinHashEmbedder(dim=dim)
    return BuiltinHashEmbedder(dim=dim)


class EmbeddingModelMismatch(RuntimeError):
    """库内向量模型与当前 provider 不一致。"""


def assert_model_consistency(stored_model_ids: Sequence[str], provider: EmbeddingProvider) -> None:
    """校验库内已有向量的 model_id 与当前 provider 一致。

    不同模型/维度的向量混算余弦是静默的灾难（分数毫无意义但不会报错），
    所以这里必须显式拦截。
    """
    distinct = {m for m in stored_model_ids if m}
    if not distinct:
        return
    if distinct != {provider.model_id}:
        raise EmbeddingModelMismatch(
            "库内向量模型 %r 与当前 provider %r 不一致。"
            "请调用 rebuild_embeddings() 全量重建，或改用匹配的 provider。"
            % (sorted(distinct), provider.model_id)
        )


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """余弦相似度。维度不等直接抛错，绝不静默截断。"""
    if len(a) != len(b):
        raise ValueError("向量维度不一致：%d vs %d" % (len(a), len(b)))
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / math.sqrt(na * nb)


def non_negative_cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """非负截断余弦。负相关一律视为 0（有界校准融合要求 s_vec ∈ [0,1]）。"""
    c = cosine(a, b)
    return c if c > 0.0 else 0.0
