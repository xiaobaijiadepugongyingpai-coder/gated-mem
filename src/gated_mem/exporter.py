"""离线单文件 HTML 图谱导出器。

安全铁律（P3 §3.4，Gate 3 一票否决项）：
  1. 严禁 Python 字符串拼接把记忆内容塞进 HTML 标签。
  2. 快照数据一律 json.dumps 后把 "</" 替换成 "<\\/"（防止提前闭合 <script>）。
  3. 前端一律用 textContent 渲染文本，严禁 innerHTML 渲染 content / residual_diff。
  4. 零外部 CDN：不引用任何 http(s):// 资源，CSS 与 JS 全部内联。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from .storage import Store

STALE = ("superseded", "killed")

HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gated-Mem 记忆图谱</title>
<style>
:root{--bg:#0f1115;--fg:#e6e6e6;--muted:#8b949e;--active:#3fb950;--superseded:#f85149;
--killed:#6e7681;--pinned:#a371f7;--stale:#d29922;--edge:#30363d;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,
BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;display:flex;
height:100vh;overflow:hidden}
#graph{flex:1;position:relative;min-width:0}
canvas{display:block;width:100%;height:100%;cursor:grab}
canvas:active{cursor:grabbing}
#side{width:340px;border-left:1px solid var(--edge);padding:16px;overflow-y:auto;
background:#0b0d11;flex-shrink:0}
h1{font-size:15px;margin:0 0 12px;letter-spacing:.5px}
h2{font-size:12px;margin:16px 0 6px;color:var(--muted);text-transform:uppercase;
letter-spacing:1px;font-weight:600}
.item{border-left:3px solid var(--edge);padding:6px 0 6px 10px;margin-bottom:8px;
font-size:13px;word-break:break-word}
.item.active{border-color:var(--active)}
.item.superseded{border-color:var(--superseded)}
.item.killed{border-color:var(--killed)}
.item.pinned{border-color:var(--pinned);border-left-width:4px}
.item.stale{background:rgba(210,153,34,.08)}
.id{color:var(--muted);font-size:11px;font-family:ui-monospace,monospace}
.diff{color:var(--stale);font-size:12px;margin-top:4px}
.legend{display:flex;flex-wrap:wrap;gap:10px;font-size:11px;color:var(--muted);
margin-top:10px}
.legend span::before{content:"●";margin-right:4px}
.lg-active::before{color:var(--active)}.lg-superseded::before{color:var(--superseded)}
.lg-killed::before{color:var(--killed)}.lg-pinned::before{color:var(--pinned)}
.lg-stale::before{color:var(--stale)}
#empty{color:var(--muted);font-size:13px}
#slider{width:100%;margin-top:10px}
#stepLabel{color:var(--muted);font-size:12px}
</style>
</head>
<body>
<div id="graph"><canvas id="cv"></canvas></div>
<div id="side">
  <h1>Gated-Mem 记忆图谱</h1>
  <div class="legend">
    <span class="lg-active">active</span>
    <span class="lg-superseded">superseded</span>
    <span class="lg-killed">killed</span>
    <span class="lg-pinned">pinned</span>
    <span class="lg-stale">stale 祖先</span>
  </div>
  <h2>Step 时光机</h2>
  <input id="slider" type="range" min="0" max="100" value="100">
  <div id="stepLabel"></div>
  <h2>节点详情</h2>
  <div id="detail"><div id="empty">点击画布上的节点查看详情</div></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
  "use strict";
  var DATA = JSON.parse(document.getElementById("data").textContent);
  var canvas = document.getElementById("cv");
  var ctx = canvas.getContext("2d");
  var nodes = DATA.nodes.map(function(n, i){
    var a = (i / Math.max(1, DATA.nodes.length)) * Math.PI * 2;
    return { d: n, x: Math.cos(a) * 180 + 300, y: Math.sin(a) * 180 + 300,
             vx: 0, vy: 0 };
  });
  var byId = {};
  nodes.forEach(function(n){ byId[n.d.id] = n; });
  var edges = DATA.edges.filter(function(e){ return byId[e.source] && byId[e.target]; });

  var W = 0, H = 0, DPR = window.devicePixelRatio || 1;
  function resize(){
    var r = canvas.parentElement.getBoundingClientRect();
    W = r.width; H = r.height;
    canvas.width = Math.floor(W * DPR);
    canvas.height = Math.floor(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }
  window.addEventListener("resize", resize);

  var scale = 1, ox = 0, oy = 0, drag = null;
  canvas.addEventListener("wheel", function(ev){
    ev.preventDefault();
    scale *= (ev.deltaY < 0 ? 1.1 : 0.9);
    scale = Math.min(4, Math.max(0.2, scale));
  }, { passive: false });
  canvas.addEventListener("mousedown", function(ev){
    drag = { x: ev.clientX, y: ev.clientY, ox: ox, oy: oy, moved: false };
  });
  window.addEventListener("mousemove", function(ev){
    if(!drag) return;
    ox = drag.ox + (ev.clientX - drag.x);
    oy = drag.oy + (ev.clientY - drag.y);
    if(Math.abs(ev.clientX - drag.x) + Math.abs(ev.clientY - drag.y) > 3) drag.moved = true;
  });
  window.addEventListener("mouseup", function(ev){
    if(drag && !drag.moved){
      var hit = pick(ev);
      if(hit) showDetail(hit.d);
    }
    drag = null;
  });

  function pick(ev){
    var r = canvas.getBoundingClientRect();
    var mx = ev.clientX - r.left, my = ev.clientY - r.top;
    var best = null, bd = 900;
    nodes.forEach(function(n){
      var sx = n.x * scale + ox + W / 2, sy = n.y * scale + oy + H / 2;
      var d = (sx - mx) * (sx - mx) + (sy - my) * (sy - my);
      if(d < bd){ bd = d; best = n; }
    });
    return best;
  }

  function colorFor(n){
    if(n.d.stale) return "#d29922";
    if(n.d.pinned) return "#a371f7";
    if(n.d.status === "killed") return "#6e7681";
    if(n.d.status === "superseded") return "#f85149";
    return "#3fb950";
  }

  var stepMax = DATA.max_step || 0;
  var stepCur = stepMax;
  var slider = document.getElementById("slider");
  var stepLabel = document.getElementById("stepLabel");
  function applyStep(){
    stepLabel.textContent = "显示 step <= " + stepCur + " / " + stepMax;
  }
  slider.addEventListener("input", function(){
    stepCur = Math.round(stepMax * (parseInt(slider.value, 10) / 100));
    applyStep();
  });
  applyStep();

  function visible(n){ return n.d.created_step <= stepCur; }

  function tick(){
    // 简易力导向：斥力 + 边弹簧
    for(var i = 0; i < nodes.length; i++){
      for(var j = i + 1; j < nodes.length; j++){
        var a = nodes[i], b = nodes[j];
        var dx = b.x - a.x, dy = b.y - a.y;
        var d2 = dx * dx + dy * dy || 1;
        var d = Math.sqrt(d2);
        var f = 2200 / d2;
        var ux = dx / d, uy = dy / d;
        a.vx -= ux * f; a.vy -= uy * f;
        b.vx += ux * f; b.vy += uy * f;
      }
    }
    edges.forEach(function(e){
      var a = byId[e.source], b = byId[e.target];
      if(!a || !b) return;
      var dx = b.x - a.x, dy = b.y - a.y;
      var d = Math.sqrt(dx * dx + dy * dy) || 1;
      var f = (d - 120) * 0.008;
      var ux = dx / d, uy = dy / d;
      a.vx += ux * f; a.vy += uy * f;
      b.vx -= ux * f; b.vy -= uy * f;
    });
    nodes.forEach(function(n){
      n.vx += (-n.x) * 0.002;
      n.vy += (-n.y) * 0.002;
      n.vx *= 0.85; n.vy *= 0.85;
      n.x += n.vx; n.y += n.vy;
    });
  }

  function draw(){
    ctx.clearRect(0, 0, W, H);
    ctx.save();
    ctx.translate(W / 2 + ox, H / 2 + oy);
    ctx.scale(scale, scale);

    ctx.strokeStyle = "#30363d";
    ctx.lineWidth = 1 / scale;
    edges.forEach(function(e){
      var a = byId[e.source], b = byId[e.target];
      if(!a || !b || !visible(a) || !visible(b)) return;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      if(e.type === "SUPERSEDES"){ ctx.setLineDash([4 / scale, 4 / scale]); }
      else { ctx.setLineDash([]); }
      ctx.stroke();
    });
    ctx.setLineDash([]);

    nodes.forEach(function(n){
      if(!visible(n)) return;
      ctx.beginPath();
      ctx.arc(n.x, n.y, 7, 0, Math.PI * 2);
      ctx.fillStyle = colorFor(n);
      ctx.fill();
      if(n.d.pinned){
        ctx.strokeStyle = "#a371f7"; ctx.lineWidth = 2 / scale; ctx.stroke();
      }
      if(n.d.stale){
        ctx.beginPath();
        ctx.arc(n.x, n.y, 11, 0, Math.PI * 2);
        ctx.strokeStyle = "#d29922"; ctx.lineWidth = 1.5 / scale; ctx.stroke();
      }
      ctx.fillStyle = "#8b949e";
      ctx.font = (11 / scale) + "px ui-monospace,monospace";
      ctx.fillText(n.d.id, n.x + 10 / scale, n.y + 4 / scale);
    });
    ctx.restore();
  }

  function showDetail(d){
    var box = document.getElementById("detail");
    box.textContent = "";
    var wrap = document.createElement("div");
    wrap.className = "item " + d.status + (d.pinned ? " pinned" : "") +
                    (d.stale ? " stale" : "");
    var idEl = document.createElement("div");
    idEl.className = "id";
    idEl.textContent = d.id + "  ·  " + d.memory_type + "  ·  step " + d.created_step;
    var body = document.createElement("div");
    body.textContent = d.content;
    wrap.appendChild(idEl);
    wrap.appendChild(body);
    if(d.stale && d.stale_ancestors && d.stale_ancestors.length){
      var w = document.createElement("div");
      w.className = "diff";
      w.textContent = "⚠ 祖先已废弃: " + d.stale_ancestors.join(", ");
      wrap.appendChild(w);
    }
    if(d.residual_diff){
      var dd = document.createElement("div");
      dd.className = "diff";
      dd.textContent = d.residual_diff;
      wrap.appendChild(dd);
    }
    box.appendChild(wrap);
  }

  function loop(){ tick(); draw(); requestAnimationFrame(loop); }
  resize();
  loop();
})();
</script>
</body>
</html>
"""


def build_snapshot(store: Store) -> Dict[str, Any]:
    """从 SQLite 构建导出快照。"""
    nodes: List[Dict[str, Any]] = []
    all_nodes = store.all_memories()
    max_step = 0
    for n in all_nodes:
        stale = [
            a for a, _d in store.ancestors_recursive(n.memory_id, max_depth=8)
            if (store.get_memory(a) is not None and store.get_memory(a).status.value in STALE)
        ]
        max_step = max(max_step, n.created_step)
        nodes.append({
            "id": n.memory_id,
            "content": n.content,
            "memory_type": n.memory_type.value,
            "subject": n.subject,
            "predicate": n.predicate,
            "scope": n.scope,
            "status": n.status.value,
            "pinned": bool(n.pinned),
            "created_step": n.created_step,
            "last_cited_step": n.last_cited_step,
            "residual_diff": n.residual_diff or "",
            "stale": bool(stale),
            "stale_ancestors": sorted(stale),
        })

    edges: List[Dict[str, Any]] = []
    for r in store.conn.execute(
        "SELECT source_id, target_id, edge_type FROM memory_edges"
        " WHERE project_id=? ORDER BY edge_id ASC",
        (store.project_id,),
    ).fetchall():
        edges.append({"source": r["source_id"], "target": r["target_id"], "type": r["edge_type"]})

    return {"nodes": nodes, "edges": edges, "max_step": max_step}


def safe_json(data: Any) -> str:
    """序列化并转义 </ —— 防止记忆内容提前闭合 <script> 标签。"""
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def render_html(snapshot: Dict[str, Any]) -> str:
    """把快照渲染成完整 HTML。"""
    return HTML_TEMPLATE.replace("__DATA__", safe_json(snapshot))


def export_html(store: Store, out_path: Path) -> Dict[str, Any]:
    """导出到文件，返回统计。"""
    snapshot = build_snapshot(store)
    html = render_html(snapshot)
    out = Path(out_path)
    if out.parent and str(out.parent) not in ("", "."):
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return {
        "nodes": len(snapshot["nodes"]),
        "edges": len(snapshot["edges"]),
        "bytes": len(html.encode("utf-8")),
    }
