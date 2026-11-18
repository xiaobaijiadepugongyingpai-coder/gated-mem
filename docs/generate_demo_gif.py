"""Generate high-quality animated GIF demo for Gated-Mem README.

Produces docs/demo.gif with crisp typography, dark mode, and terminal styling.
"""
import os
from PIL import Image, ImageDraw, ImageFont

WIDTH = 880
HEIGHT = 500
FONT_DIR = os.path.join(os.environ.get("SystemRoot", ""), "Fonts")
FONT_PATH = os.path.join(FONT_DIR, "consola.ttf") if FONT_DIR else "consola.ttf"
FONT_SIZE = 15
LINE_HEIGHT = 22

# Color Palette (GitHub Dark / Catppuccin inspired)
BG_COLOR = (13, 17, 23)        # #0D1117
TERM_BG = (22, 27, 34)         # #161B22
BORDER_COLOR = (48, 54, 61)    # #30363D
TITLE_BAR = (30, 37, 46)       # #1E252E
TEXT_WHITE = (230, 237, 243)   # #E6EDF3
TEXT_GRAY = (139, 148, 158)    # #8B949E
GREEN = (63, 185, 80)          # #3FB950
CYAN = (88, 166, 255)          # #58A6FF
YELLOW = (210, 153, 34)        # #D29922
RED = (248, 81, 73)            # #F85149
PURPLE = (188, 140, 255)       # #BC8CFF

def get_font(size=FONT_SIZE, bold=False):
    try:
        bold_path = os.path.join(FONT_DIR, "consolab.ttf") if FONT_DIR else "consolab.ttf"
        path = bold_path if bold else FONT_PATH
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

def draw_window_frame(draw, title="gated-mem v1.0.0 — Git for Agent Memory"):
    # Window background & border
    draw.rounded_rectangle([10, 10, WIDTH - 10, HEIGHT - 10], radius=10, fill=TERM_BG, outline=BORDER_COLOR, width=1)
    
    # Title bar
    draw.rounded_rectangle([10, 10, WIDTH - 10, 42], radius=10, fill=TITLE_BAR)
    draw.rectangle([10, 32, WIDTH - 10, 42], fill=TITLE_BAR)  # square bottom corners of title bar
    draw.line([10, 42, WIDTH - 10, 42], fill=BORDER_COLOR, width=1)
    
    # Window controls (macOS style dots)
    draw.ellipse([26, 21, 38, 33], fill=(255, 95, 86))   # Red
    draw.ellipse([46, 21, 58, 33], fill=(255, 189, 46))  # Yellow
    draw.ellipse([66, 21, 78, 33], fill=(39, 201, 63))   # Green
    
    # Title text
    f_title = get_font(13)
    draw.text((WIDTH // 2 - 140, 20), title, font=f_title, fill=TEXT_GRAY)

def create_frame(lines):
    img = Image.new("RGB", (WIDTH, HEIGHT), color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw_window_frame(draw)
    
    font = get_font()
    y = 56
    for line in lines:
        if isinstance(line, list):
            # Formatted line parts [(text, color, is_bold), ...]
            x = 28
            for part in line:
                text = part[0]
                color = part[1] if len(part) > 1 else TEXT_WHITE
                bold = part[2] if len(part) > 2 else False
                f = get_font(FONT_SIZE, bold=bold)
                draw.text((x, y), text, font=f, fill=color)
                x += int(draw.textlength(text, font=f))
        elif isinstance(line, tuple):
            text, color = line
            draw.text((28, y), text, font=font, fill=color)
        else:
            draw.text((28, y), line, font=font, fill=TEXT_WHITE)
        y += LINE_HEIGHT
    return img

def main():
    script_steps = [
        # Step 0: Blank shell
        [
            [("$ ", CYAN), ("gated-mem setup --agent dsh", TEXT_WHITE)],
        ],
        # Step 1: setup result
        [
            [("$ ", CYAN), ("gated-mem setup --agent dsh", TEXT_WHITE)],
            [("✓ [P0] DeepSeek Harness adapter registered.", GREEN)],
            [("  Patched: ~/.dsh/profiles/desktop/cordis.patch.yml", TEXT_GRAY)],
            [("  Skill  : ~/.dsh/skills/gated-mem/SKILL.md", TEXT_GRAY)],
            [("$ ", CYAN), ("# Record architectural decision", TEXT_GRAY)],
        ],
        # Step 2: first remember
        [
            [("$ ", CYAN), ("gated-mem setup --agent dsh", TEXT_WHITE)],
            [("✓ [P0] DeepSeek Harness adapter registered.", GREEN)],
            [("$ ", CYAN), ("gated-mem remember \"Switch DB to MySQL\" --subject db", TEXT_WHITE)],
            [("✓ [EVENT #01] Decision saved (scope=global, vitality=1.00)", GREEN)],
        ],
        # Step 3: second remember (override)
        [
            [("$ ", CYAN), ("gated-mem remember \"Switch DB to MySQL\" --subject db", TEXT_WHITE)],
            [("✓ [EVENT #01] Decision saved (scope=global, vitality=1.00)", GREEN)],
            [("$ ", CYAN), ("gated-mem remember \"Migrate to PostgreSQL 16\" --subject db", TEXT_WHITE)],
            [("⚡ [EVENT #02] SUPERSEDES event #01 via slot (db, engine)", YELLOW)],
            [("   Residual diff saved: [Replaced: MySQL] pool saturated under write load", TEXT_GRAY)],
        ],
        # Step 4: log graph
        [
            [("$ ", CYAN), ("gated-mem remember \"Migrate to PostgreSQL 16\" --subject db", TEXT_WHITE)],
            [("⚡ [EVENT #02] SUPERSEDES event #01 via slot (db, engine)", YELLOW)],
            [("$ ", CYAN), ("gated-mem log --graph", CYAN, True)],
            [("┌── Memory Evolution Tree ──────────────────────────────────────┐", BORDER_COLOR)],
            [("│ ", BORDER_COLOR), ("● mem-02", GREEN, True), (" [ACTIVE]     PostgreSQL 16", TEXT_WHITE)],
            [("│ ", BORDER_COLOR), ("  └── [SUPERSEDES]", YELLOW), (" ──▶ ", TEXT_GRAY), ("● mem-01", RED), (" [SUPERSEDED] MySQL", TEXT_GRAY)],
            [("│ ", BORDER_COLOR), ("         └── trace: ", TEXT_GRAY), ("[Replaced: MySQL] pool saturated", CYAN)],
            [("│ ", BORDER_COLOR), ("● mem-03", GREEN, True), (" [ACTIVE]     Mock DB in unit tests (Anti-trap: safe)", TEXT_WHITE)],
            [("└── 2 active, 1 superseded, 0 cascade kills ───────────────────┘", BORDER_COLOR)],
        ],
        # Step 5: Causal undo
        [
            [("┌── Memory Evolution Tree ──────────────────────────────────────┐", BORDER_COLOR)],
            [("│ ", BORDER_COLOR), ("● mem-02", GREEN, True), (" [ACTIVE]     PostgreSQL 16", TEXT_WHITE)],
            [("│ ", BORDER_COLOR), ("  └── [SUPERSEDES]", YELLOW), (" ──▶ ", TEXT_GRAY), ("● mem-01", RED), (" [SUPERSEDED] MySQL", TEXT_GRAY)],
            [("└── 2 active, 1 superseded, 0 cascade kills ───────────────────┘", BORDER_COLOR)],
            [("$ ", CYAN), ("gated-mem undo 2", PURPLE, True)],
            [("↺ [UNDO] Atomically rolling back transaction event #02...", YELLOW)],
            [("✓ Restored: mem-01 [MySQL] is back to [ACTIVE].", GREEN)],
            [("✓ Cascade protection: mem-03 preserved without collateral damage.", GREEN)],
        ],
        # Step 6: Doctor & Bench
        [
            [("$ ", CYAN), ("gated-mem undo 2", PURPLE, True)],
            [("✓ Restored: mem-01 [MySQL] is back to [ACTIVE].", GREEN)],
            [("$ ", CYAN), ("gated-mem doctor", CYAN, True)],
            [("  [OK] Python 3.9+  ·  SQLite WAL mode  ·  FTS5 fulltext indexed", GREEN)],
            [("  [OK] Core dependencies: ZERO (Standard library only)", GREEN)],
            [("  [OK] Unit tests: 181/181 PASSED  (90% coverage)", GREEN)],
            [("  [OK] E3 Benchmark: +40.00pp net gain over single channels", CYAN, True)],
            [("$ ", CYAN), ("gated-mem export-html -o docs/demo_memory_graph.html", TEXT_WHITE)],
            [("✓ Exported zero-CDN interactive graph with time-scrubber.", PURPLE)],
        ],
    ]

    frames = []
    durations = []
    
    # Build frames with appropriate pacing
    for i, step in enumerate(script_steps):
        img = create_frame(step)
        # Duplicate frames for pause / pacing
        pause_count = 2 if i < 3 else (4 if i == 4 or i == 5 else 6)
        duration = 800 if i < 3 else (1400 if i == 4 or i == 5 else 2600)
        
        frames.append(img)
        durations.append(duration)
        
    os.makedirs("docs", exist_ok=True)
    out_path = "docs/demo.gif"
    
    # Save as animated GIF with adaptive palette
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True
    )
    print(f"Generated {out_path} ({os.path.getsize(out_path)} bytes, {len(frames)} keyframes)")

if __name__ == "__main__":
    main()
