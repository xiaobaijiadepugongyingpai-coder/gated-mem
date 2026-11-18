"""Generate high-impact README media assets for Gated-Mem.

Produces:
  1. docs/demo_screenshot.png — High-res capture of the Interactive Graph Studio
  2. docs/demo.gif            — Dual-act hero GIF (Terminal CLI + Live Time-Travel Graph Studio)
  3. docs/social_preview.png  — 1280x640 GitHub Social Preview OpenGraph banner
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
HTML_PATH = DOCS / "demo_memory_graph.html"

# Unified 1400:820 aspect ratio scaled cleanly for crisp GitHub README rendering
OUT_W = 1120
OUT_H = 656
FONT_DIR = os.path.join(os.environ.get("SystemRoot", ""), "Fonts")
FONT_MONO = os.path.join(FONT_DIR, "consola.ttf") if FONT_DIR else "consola.ttf"
FONT_MONO_B = os.path.join(FONT_DIR, "consolab.ttf") if FONT_DIR else "consolab.ttf"
FONT_SANS = os.path.join(FONT_DIR, "segoeui.ttf") if FONT_DIR else "segoeui.ttf"
FONT_SANS_B = os.path.join(FONT_DIR, "segoeuib.ttf") if FONT_DIR else "segoeuib.ttf"

# Color Palette (GitHub Dark / Graph Studio harmonized)
BG_COLOR = (7, 9, 14)         # #07090E
TERM_BG = (13, 17, 23)        # #0D1117
CARD_BG = (22, 27, 34)        # #161B22
BORDER_COLOR = (38, 44, 54)   # #262C36
TITLE_BAR = (22, 27, 34)      # #161B22
TEXT_WHITE = (230, 237, 243)  # #E6EDF3
TEXT_GRAY = (139, 148, 158)   # #8B949E
GREEN = (63, 185, 80)         # #3FB950
CYAN = (88, 166, 255)         # #58A6FF
YELLOW = (210, 153, 34)       # #D29922
RED = (248, 81, 73)           # #F85149
PURPLE = (163, 113, 247)      # #A371F7

FONT_SIZE = 19
LINE_HEIGHT = 29


def get_font(size: int = FONT_SIZE, bold: bool = False, sans: bool = False):
    candidates = (
        [FONT_SANS_B if bold else FONT_SANS, FONT_MONO_B if bold else FONT_MONO]
        if sans
        else [FONT_MONO_B if bold else FONT_MONO, "DejaVuSansMono.ttf"]
    )
    for path in candidates:
        try:
            if path and os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def find_browser() -> Optional[str]:
    pf = os.environ.get("ProgramFiles", "")
    pf86 = os.environ.get("ProgramFiles(x86)", "")
    candidates = [
        os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe") if pf else "",
        os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe") if pf86 else "",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("msedge"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


class _SimpleWS:
    """Minimal stdlib-only WebSocket client for Chrome DevTools Protocol."""

    def __init__(self, url: str) -> None:
        rest = url[5:]
        host_port, path = rest.split("/", 1)
        host, port = host_port.split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=15)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET /{path} HTTP/1.1\r\n"
            f"Host: {host_port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        self.extra = buf.split(b"\r\n\r\n", 1)[1]
        self._id = 0

    def _recv_exact(self, n: int) -> bytes:
        out = bytearray()
        if self.extra:
            take = min(n, len(self.extra))
            out.extend(self.extra[:take])
            self.extra = self.extra[take:]
        while len(out) < n:
            chunk = self.sock.recv(n - len(out))
            if not chunk:
                raise EOFError("WebSocket closed")
            out.extend(chunk)
        return bytes(out)

    def send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        mask = os.urandom(4)
        header = bytearray([0x81])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", n))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", n))
        header.extend(mask)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def recv_text(self) -> str:
        while True:
            b1, b2 = self._recv_exact(2)
            opcode = b1 & 0x0F
            masked = b2 & 0x80
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else b""
            data = self._recv_exact(length)
            if masked:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if opcode == 0x8:
                raise EOFError("Close frame")
            if opcode == 0x9:
                continue
            if opcode == 0x1:
                return data.decode("utf-8")

    def call(self, method: str, params=None) -> dict:
        self._id += 1
        cid = self._id
        self.send_text(json.dumps({"id": cid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.recv_text())
            if msg.get("id") == cid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def close(self) -> None:
        self.sock.close()


def draw_terminal_frame(
    lines: list,
    title: str = "gated-mem v1.0.0  —  Git for Agent Memory (Zero Dependencies)",
    badge_text: Optional[str] = None,
    badge_color: Tuple[int, int, int] = GREEN,
) -> Image.Image:
    img = Image.new("RGB", (OUT_W, OUT_H), color=BG_COLOR)
    draw = ImageDraw.Draw(img)

    pad = 24
    # Outer terminal frame
    draw.rounded_rectangle(
        [pad, pad, OUT_W - pad, OUT_H - pad],
        radius=14,
        fill=TERM_BG,
        outline=BORDER_COLOR,
        width=2,
    )
    # Title bar
    draw.rounded_rectangle([pad, pad, OUT_W - pad, pad + 46], radius=14, fill=TITLE_BAR)
    draw.rectangle([pad, pad + 32, OUT_W - pad, pad + 46], fill=TITLE_BAR)
    draw.line([pad, pad + 46, OUT_W - pad, pad + 46], fill=BORDER_COLOR, width=1)

    # Traffic lights
    draw.ellipse([pad + 18, pad + 16, pad + 32, pad + 30], fill=(255, 95, 86))
    draw.ellipse([pad + 42, pad + 16, pad + 56, pad + 30], fill=(255, 189, 46))
    draw.ellipse([pad + 66, pad + 16, pad + 80, pad + 30], fill=(39, 201, 63))

    f_title = get_font(15, sans=True)
    tw = draw.textlength(title, font=f_title)
    draw.text(((OUT_W - tw) / 2, pad + 13), title, font=f_title, fill=TEXT_GRAY)

    if badge_text:
        f_badge = get_font(13, bold=True, sans=True)
        bw = int(draw.textlength(badge_text, font=f_badge)) + 22
        bx = OUT_W - pad - bw - 16
        by = pad + 10
        draw.rounded_rectangle(
            [bx, by, bx + bw, by + 26],
            radius=13,
            fill=(22, 34, 28) if badge_color == GREEN else (22, 30, 46),
            outline=badge_color,
            width=1,
        )
        draw.text((bx + 11, by + 5), badge_text, font=f_badge, fill=badge_color)

    y = pad + 72
    for line in lines:
        if isinstance(line, list):
            x = pad + 28
            for part in line:
                text = part[0]
                color = part[1] if len(part) > 1 else TEXT_WHITE
                bold = part[2] if len(part) > 2 else False
                f = get_font(FONT_SIZE, bold=bold)
                draw.text((x, y), text, font=f, fill=color)
                x += int(draw.textlength(text, font=f))
        elif isinstance(line, tuple):
            text, color = line
            draw.text((pad + 28, y), text, font=get_font(FONT_SIZE), fill=color)
        else:
            draw.text((pad + 28, y), line, font=get_font(FONT_SIZE), fill=TEXT_WHITE)
        y += LINE_HEIGHT

    return img


def add_caption_pill(img: Image.Image, text: str, accent: Tuple[int, int, int] = CYAN) -> Image.Image:
    out = img.copy()
    draw = ImageDraw.Draw(out, "RGBA")
    f = get_font(15, bold=True, sans=True)
    tw = int(draw.textlength(text, font=f))
    bw = tw + 30
    bh = 34
    bx = int((out.width - 320 - bw) / 2)
    by = 14
    draw.rounded_rectangle(
        [bx, by, bx + bw, by + bh],
        radius=17,
        fill=(13, 17, 23, 232),
        outline=(accent[0], accent[1], accent[2], 210),
        width=2,
    )
    draw.ellipse([bx + 11, by + 12, bx + 21, by + 22], fill=accent)
    draw.text((bx + 27, by + 7), text, font=f, fill=TEXT_WHITE)
    return out


def capture_graph_studio_frames() -> Optional[dict]:
    browser = find_browser()
    if not browser or not HTML_PATH.exists():
        return None

    tmp_dir = tempfile.mkdtemp(prefix="gm_demo_cdp_")
    port = 9247
    proc = subprocess.Popen(
        [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={tmp_dir}",
            "--window-size=1400,820",
            HTML_PATH.as_uri(),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    captured = {}
    try:
        ws_url = None
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as r:
                    tabs = json.loads(r.read().decode())
                    for t in tabs:
                        if "demo_memory_graph.html" in t.get("url", ""):
                            ws_url = t["webSocketDebuggerUrl"]
                            break
                if ws_url:
                    break
            except Exception:
                time.sleep(0.25)
        if not ws_url:
            return None

        ws = _SimpleWS(ws_url)
        ws.call("Emulation.setDeviceMetricsOverride", {
            "width": 1400, "height": 820, "deviceScaleFactor": 1, "mobile": False
        })
        time.sleep(2.2)

        def eval_js(expr: str):
            return ws.call("Runtime.evaluate", {"expression": expr, "returnByValue": True})

        def snap_pil() -> Image.Image:
            res = ws.call("Page.captureScreenshot", {"format": "png"})
            from io import BytesIO
            return Image.open(BytesIO(base64.b64decode(res["data"]))).convert("RGB")

        def set_step(prefix: str, select_node: Optional[str] = None, clear_sel: bool = False):
            eval_js(
                f"Array.from(document.querySelectorAll('#stepChips .step-chip'))"
                f".find(el => el.textContent.startsWith('{prefix}'))?.click();"
            )
            time.sleep(0.95)
            if select_node:
                eval_js(
                    f"Array.from(document.querySelectorAll('#nodeList .ledger-item'))"
                    f".find(el => el.querySelector('.ledger-id')?.textContent === '{select_node}')?.click();"
                )
                time.sleep(0.45)
            elif clear_sel:
                eval_js("window.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}));")
                time.sleep(0.3)
            eval_js("document.getElementById('btnResetView').click();")
            time.sleep(0.45)

        set_step("s130", clear_sel=True)
        captured["s130"] = snap_pil()

        set_step("s140", select_node="M5")
        captured["s140"] = snap_pil()

        set_step("s210", select_node="M10")
        captured["s210"] = snap_pil()

        set_step("s260", select_node="M12")
        captured["s260"] = snap_pil()

        set_step("s340", clear_sel=True)
        captured["s340_overview"] = snap_pil()

        set_step("s340", select_node="M1")
        captured["s340_m1"] = snap_pil()

        ws.close()
        return captured
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(tmp_dir, ignore_errors=True)


def generate_social_preview(graph_img: Image.Image) -> None:
    """Create a 1280x640 GitHub Social Preview banner."""
    W, H = 1280, 640
    banner = Image.new("RGB", (W, H), color=(7, 9, 14))
    draw = ImageDraw.Draw(banner)

    # Subtle dot matrix background
    for gx in range(28, W, 36):
        for gy in range(28, H, 36):
            draw.ellipse([gx - 1, gy - 1, gx + 1, gy + 1], fill=(32, 40, 54))

    # Left hero copy
    lx = 58
    f_tag = get_font(15, bold=True, sans=True)
    draw.rounded_rectangle([lx, 56, lx + 275, 88], radius=16, fill=(18, 38, 28), outline=GREEN, width=1)
    draw.text((lx + 16, 63), "ZERO CORE DEPENDENCIES · MCP", font=f_tag, fill=GREEN)

    f_h1 = get_font(56, bold=True, sans=True)
    draw.text((lx, 112), "Gated-Mem", font=f_h1, fill=TEXT_WHITE)

    f_sub = get_font(27, bold=True, sans=True)
    draw.text((lx, 184), "Git for Agent Memory", font=f_sub, fill=CYAN)

    f_desc = get_font(18, sans=True)
    desc_lines = [
        "Stop coding agents from recalling deleted",
        "MySQL configs 3 weeks after migrating.",
    ]
    for idx, line in enumerate(desc_lines):
        draw.text((lx, 236 + idx * 27), line, font=f_desc, fill=TEXT_GRAY)

    # 3 metric pills
    metrics = [
        ("100%", "Current-state accuracy (vs 20% RAG)", GREEN),
        ("0 / 40", "Stale-state leakage into prompt body", CYAN),
        ("+40pp", "Cross-module symbol disambiguation", PURPLE),
    ]
    my = 326
    f_mval = get_font(22, bold=True)
    f_mlbl = get_font(16, sans=True)
    for val, lbl, col in metrics:
        draw.rounded_rectangle([lx, my, lx + 505, my + 52], radius=10, fill=(16, 21, 29), outline=(42, 50, 64), width=1)
        draw.text((lx + 16, my + 13), val, font=f_mval, fill=col)
        draw.text((lx + 114, my + 16), lbl, font=f_mlbl, fill=TEXT_WHITE)
        my += 64

    # Footer agents
    f_ft = get_font(15, sans=True)
    draw.text((lx, 548), "Native adapters: DeepSeek Harness (dsh) · Claude Code · Cursor", font=f_ft, fill=TEXT_GRAY)

    # Right framed Graph Studio preview
    card_w, card_h = 620, 363
    cx, cy = 606, 138
    preview = graph_img.resize((card_w, card_h), Image.Resampling.LANCZOS)
    draw.rounded_rectangle([cx - 6, cy - 6, cx + card_w + 6, cy + card_h + 6], radius=14, fill=(22, 27, 34), outline=CYAN, width=2)
    banner.paste(preview, (cx, cy))

    f_cap = get_font(14, sans=True)
    draw.text((cx, cy + card_h + 16), "Offline Single-File HTML Graph Studio · Time-Travel & Causal Diff", font=f_cap, fill=TEXT_GRAY)

    out_path = DOCS / "social_preview.png"
    banner.save(out_path, optimize=True)
    print(f"Saved {out_path} ({out_path.stat().st_size} bytes)")


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    captured = capture_graph_studio_frames()

    if captured and "s340_m1" in captured:
        ss_path = DOCS / "demo_screenshot.png"
        captured["s340_m1"].save(ss_path, optimize=True)
        print(f"Saved {ss_path} ({ss_path.stat().st_size} bytes)")
        generate_social_preview(captured["s340_m1"])

    # Act 1: Crisp Terminal CLI (Git-like Memory Workflow, Consola-safe glyphs)
    cli_steps = [
        (
            [
                [("$ ", CYAN, True), ("pip install \"git+https://github.com/.../gated-mem.git\"", TEXT_WHITE)],
                [("$ ", CYAN, True), ("gated-mem setup", TEXT_WHITE), ("   # auto-mounts dsh / claude / cursor", TEXT_GRAY)],
                [("[OK] [P0] DeepSeek Harness adapter registered.", GREEN)],
                [("     Patched: ~/.dsh/profiles/desktop/cordis.patch.yml", TEXT_GRAY)],
                [("     Skill  : ~/.dsh/skills/gated-mem/SKILL.md", TEXT_GRAY)],
                [("", TEXT_WHITE)],
                [("$ ", CYAN, True), ("gated-mem remember \"Use MySQL 8.0\" --subject db --predicate engine", TEXT_WHITE)],
                [("[OK] [EVENT #01] Saved mem-01 (status=ACTIVE, vitality=1.00)", GREEN)],
                [("$ ", CYAN, True), ("gated-mem remember \"Migrate to PostgreSQL 16\" --subject db --predicate engine", TEXT_WHITE)],
                [("[>>] [EVENT #02] SUPERSEDES mem-01 via slot (db, engine)", YELLOW, True)],
                [("     Residual diff: [Replaced: MySQL] write pool saturated", CYAN)],
            ],
            "STEP 1/3 · SLOT OVERRIDE",
            CYAN,
            1900,
        ),
        (
            [
                [("$ ", CYAN, True), ("gated-mem log --graph", CYAN, True)],
                [("+-- Memory Evolution Tree --------------------------------------------------+", BORDER_COLOR)],
                [("| ", BORDER_COLOR), ("* mem-02", GREEN, True), (" [ACTIVE]      Migrate to PostgreSQL 16", TEXT_WHITE)],
                [("| ", BORDER_COLOR), ("  +-- [SUPERSEDES]", YELLOW), (" --> ", TEXT_GRAY), ("x mem-01", RED), (" [SUPERSEDED] Use MySQL 8.0", TEXT_GRAY)],
                [("| ", BORDER_COLOR), ("         +-- trace: ", TEXT_GRAY), ("[Replaced: MySQL] write pool saturated", CYAN)],
                [("| ", BORDER_COLOR), ("* mem-03", GREEN, True), (" [ACTIVE]      Unit tests must mock DB ", TEXT_WHITE), ("[! STALE_PARENT]", YELLOW)],
                [("+-- 2 active · 1 superseded · 0 cascade kills (rules preserved!) -----------+", BORDER_COLOR)],
                [("", TEXT_WHITE)],
                [("$ ", CYAN, True), ("gated-mem undo 2", PURPLE, True), ("   # atomic cross-table rollback", TEXT_GRAY)],
                [("[<<] Rolled back event #02 -> mem-01 [MySQL 8.0] restored to ACTIVE.", GREEN)],
            ],
            "STEP 2/3 · ZERO-CASCADE & UNDO",
            YELLOW,
            2200,
        ),
        (
            [
                [("$ ", CYAN, True), ("gated-mem doctor", CYAN, True)],
                [("  [OK] Python >=3.9 · SQLite WAL + FTS5 + recursive CTE ready", GREEN)],
                [("  [OK] Core runtime dependencies: ZERO (100% Python stdlib)", GREEN, True)],
                [("  [OK] Unit tests: 191 / 191 PASSED (91% coverage)", GREEN)],
                [("  [OK] Phase-5 E3: 90% Top-1 (+40.00pp over best single channel)", CYAN, True)],
                [("", TEXT_WHITE)],
                [("$ ", CYAN, True), ("gated-mem export-html -o docs/demo_memory_graph.html", TEXT_WHITE)],
                [("[OK] Exported 46 KB Zero-CDN Interactive Graph Studio -> launching...", PURPLE, True)],
            ],
            "STEP 3/3 · VERIFIED & EXPORTED",
            GREEN,
            1900,
        ),
    ]

    frames: List[Image.Image] = []
    durations: List[int] = []

    for lines, badge, col, dur in cli_steps:
        frames.append(draw_terminal_frame(lines, badge_text=badge, badge_color=col))
        durations.append(dur)

    # Act 2: Real Interactive Graph Studio Time-Travel (from Chrome CDP)
    if captured:
        studio_sequence = [
            ("s130", "GRAPH STUDIO · step 130 — All 9 initial decisions ACTIVE", GREEN, 1300),
            ("s140", "TIME-TRAVEL · step 140 — M5 supersedes M1 ([Replaced: MySQL])", RED, 1700),
            ("s210", "TIME-TRAVEL · step 210 — OAuth 2.1 replaces Session Cookie", YELLOW, 1400),
            ("s260", "TIME-TRAVEL · step 260 — Vite 5 replaces webpack 5", YELLOW, 1400),
            ("s340_overview", "GRAPH STUDIO · step 340 — 15 nodes, 9 edges, 0 cascade kills", CYAN, 1700),
            ("s340_m1", "1-HOP CAUSAL AUDIT · M5→M1 SUPERSEDES & stale-parent warnings", PURPLE, 2400),
        ]
        for key, caption, accent, dur in studio_sequence:
            if key in captured:
                scaled = captured[key].resize((OUT_W, OUT_H), Image.Resampling.LANCZOS)
                frames.append(add_caption_pill(scaled, caption, accent=accent))
                durations.append(dur)

    out_gif = DOCS / "demo.gif"
    # Quantize consistently for crisp text + small file size
    pal_frames = [f.convert("P", palette=Image.Palette.ADAPTIVE, colors=256) for f in frames]
    pal_frames[0].save(
        out_gif,
        save_all=True,
        append_images=pal_frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    print(f"Generated {out_gif} ({out_gif.stat().st_size} bytes, {len(frames)} keyframes)")


if __name__ == "__main__":
    main()
