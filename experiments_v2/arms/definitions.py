"""实验臂定义。

7 个臂，全部通过开关组合，不复制检索逻辑。
只调用 src/gated_mem 的既有接口，不修改它。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Arm:
    """一个实验臂 = 一组检索开关。"""

    name: str
    use_slots: bool = False   # 是否做槽位覆盖（SUPERSEDES / 状态门控）
    lam: float = 0.0          # 生命力指数；0.0 = 关闭
    fusion: bool = False      # 是否 FTS + 向量融合
    wrapper: bool = False     # True = 无存储，纯 prompt 现算
    kind: str = "store"       # "store" | "wrapper" | "none"

    def describe(self) -> str:
        bits = []
        bits.append("slots" if self.use_slots else "no-slots")
        bits.append("lam=%.1f" % self.lam)
        bits.append("fusion" if self.fusion else "no-fusion")
        if self.wrapper:
            bits.append("WRAPPER")
        return "%s [%s]" % (self.name, ", ".join(bits))


ARMS: list[Arm] = [
    Arm("A0_nomem",       use_slots=False, lam=0.0, fusion=False, kind="none"),
    Arm("A1_vector",      use_slots=False, lam=0.0, fusion=False),
    Arm("A2_fts",         use_slots=False, lam=0.0, fusion=True),   # ← 新增：最强单通道候选
    Arm("A3_slot",        use_slots=True,  lam=0.0, fusion=False),
    Arm("A4_slot_fusion", use_slots=True,  lam=0.0, fusion=True),
    Arm("A5_full",        use_slots=True,  lam=0.3, fusion=True),
    Arm("A6_wrapper",     use_slots=False, lam=0.0, fusion=False,
        wrapper=True, kind="wrapper"),
]

# E4 桥接实验额外使用的第 8 臂（一行用户级指令修复）
ARM_ONE_LINE = Arm(
    "A7_one_line", use_slots=False, lam=0.0, fusion=False, kind="none"
)


def by_name(name: str) -> Arm:
    for a in ARMS:
        if a.name == name:
            return a
    if name == ARM_ONE_LINE.name:
        return ARM_ONE_LINE
    raise KeyError("unknown arm: %s" % name)


def store_arms() -> list[Arm]:
    """需要真正建库的臂。"""
    return [a for a in ARMS if a.kind == "store"]


if __name__ == "__main__":
    for a in ARMS:
        print(a.describe())
    print(ARM_ONE_LINE.describe(), "(E4 only)")
