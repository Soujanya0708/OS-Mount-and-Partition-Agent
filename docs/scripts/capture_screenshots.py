"""
capture_screenshots.py - Runs real terminal sessions of the agent and saves them as PNG
"screenshots" for Review 3, Chapter 7 (docs/screenshots/).

Each session is executed for real (python -m mountagent with the inputs piped in); the captured
output is then drawn in a terminal-style window. Typed input is re-inserted after each prompt,
because piped input is not echoed.

Run from the repository root:   python docs/scripts/capture_screenshots.py
Windows sessions mount samples/test.iso for real; "--platform linux" sessions are simulated.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "screenshots"

SESSIONS = [
    ("01_windows_devices", "windows", ["-b", "offline"],
     ["show me all disks and partitions", "exit"]),
    ("02_windows_mount_iso", "windows", ["-b", "offline"],
     ["mount samples/test.iso so I can look at the files inside", "y",
      "which images are attached?", "unmount it", "y", "exit"]),
    ("03_linux_mount_iso", "any", ["-b", "offline", "--platform", "linux"],
     ["Mount this ubuntu.iso file so I can look at the files inside.", "which loop devices are in use?",
      "unmount it", "exit"]),
    ("04_linux_devices", "any", ["-b", "offline", "--platform", "linux"],
     ["show me all disks and partitions", "mount /dev/sdb1 read-write at /mnt/usb", "mounts", "exit"]),
    ("05_safety_linux", "any", ["-b", "offline", "--platform", "linux"],
     ["Delete everything on my drive", "mount ubuntu.iso at /etc", "mount ubuntu.iso at /mnt/../root",
      "unmount /", "exit"]),
    ("06_safety_windows", "any", ["-b", "offline", "--platform", "windows", "--dry-run"],
     ["unmount C:", "mount rootfs.img", "mount backup.iso into /etc", "exit"]),
    ("07_help", "any", ["-b", "offline", "--dry-run"], ["help", "exit"]),
]

# Non-interactive commands captured the same way
COMMANDS = [
    ("08_unit_tests", [sys.executable, "-m", "unittest", "discover", "-v", "tests"]),
    ("09_evaluation", [sys.executable, "eval/evaluate.py"]),
]

BG, FG, DIM = (12, 16, 28), (214, 222, 235), (120, 132, 156)
GREEN, CYAN, YELLOW, RED, BLUE, WHITE = (74, 222, 128), (56, 189, 248), (250, 204, 21), (248, 113, 113), \
    (96, 165, 250), (255, 255, 255)
MAX_COLS = 118


def run_session(args, inputs):
    env = dict(os.environ, NO_COLOR="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-m", "mountagent", *args], input="\n".join(inputs) + "\n",
                          capture_output=True, text=True, encoding="utf-8", cwd=ROOT, env=env, timeout=300)
    out = proc.stdout + proc.stderr
    # Re-insert the typed text after each prompt
    pieces, pos, i = [], 0, 0
    for m in re.finditer(r"mount-agent> |\[Y/n\] ", out):
        pieces.append(out[pos:m.end()])
        typed = inputs[i] if i < len(inputs) else ""
        i += 1
        pieces.append(typed + "\n")
        pos = m.end()
    pieces.append(out[pos:])
    return "".join(pieces).rstrip() + "\n"


def run_command(cmd):
    env = dict(os.environ, NO_COLOR="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=ROOT, env=env, timeout=600)
    return (proc.stdout + proc.stderr).rstrip() + "\n"


def color_for(line):
    s = line.strip()
    if s.startswith(("+---", "|")) and "Agent" in line or s.startswith("+---"):
        return CYAN
    if s.startswith("->"):
        return CYAN
    if s.startswith("thought:") or s.startswith("commands run:") or s.startswith(("$ ", "PS> ")):
        return DIM
    if s.startswith("x "):
        return RED
    if "[Y/n]" in line or s.startswith(("Not running", "This machine", "Note:")):
        return YELLOW
    if s.startswith(("FAIL", "ERROR", "Traceback")):
        return RED
    if s.endswith(("... ok", "OK")) or s.startswith("OK"):
        return GREEN
    if s.endswith("/") and " " not in s:
        return BLUE
    if re.match(r"^[A-Z][A-Z /-]{2,}\s{2,}[A-Z]", s):
        return WHITE
    return FG


def wrap(text):
    lines = []
    for line in text.splitlines():
        line = line.rstrip().replace("\t", "    ")
        while len(line) > MAX_COLS:
            lines.append(line[:MAX_COLS])
            line = "    " + line[MAX_COLS:]
        lines.append(line)
    return lines


def load_font(size, bold=False):
    candidates = (["consolab.ttf", "DejaVuSansMono-Bold.ttf"] if bold else ["consola.ttf", "DejaVuSansMono.ttf"])
    for name in candidates:
        for base in ("C:/Windows/Fonts", "/usr/share/fonts/truetype/dejavu", ""):
            try:
                return ImageFont.truetype(str(Path(base) / name) if base else name, size)
            except OSError:
                continue
    return ImageFont.load_default()


def render(title, command_line, text, path):
    font, bold = load_font(15), load_font(15, bold=True)
    lines = [command_line] + wrap(text)
    char_w = font.getbbox("M")[2]
    line_h = 20
    width = max(820, min(MAX_COLS, max(len(l) for l in lines)) * char_w + 40)
    height = 44 + len(lines) * line_h + 24

    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, width, 30], fill=(30, 36, 52))
    for i, c in enumerate([(248, 113, 113), (250, 204, 21), (74, 222, 128)]):
        d.ellipse([12 + i * 20, 9, 24 + i * 20, 21], fill=c)
    d.text((80, 7), title, font=font, fill=DIM)

    y = 42
    for n, line in enumerate(lines):
        x = 20
        if n == 0:
            d.text((x, y), line, font=bold, fill=GREEN)
        elif line.startswith("mount-agent> "):
            d.text((x, y), "mount-agent> ", font=bold, fill=GREEN)
            d.text((x + 13 * char_w, y), line[13:], font=bold, fill=WHITE)
        elif line.startswith("agent: "):
            d.text((x, y), "agent:", font=bold, fill=GREEN)
            d.text((x + 7 * char_w, y), line[7:], font=font, fill=FG)
        else:
            d.text((x, y), line, font=font, fill=color_for(line))
        y += line_h
    img.save(path)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    on_windows = os.name == "nt"
    prompt = f"PS {ROOT}>" if on_windows else f"{os.getenv('USER', 'user')}@{os.uname().nodename}:~/{ROOT.name}$"

    for name, needs, args, inputs in SESSIONS:
        if needs == "windows" and not on_windows:
            print(f"skip {name} (needs Windows)")
            continue
        text = run_session(args, inputs)
        cmd = "python -m mountagent " + " ".join(args)
        render(f"Terminal - {cmd}", f"{prompt} {cmd}", text, OUT / f"{name}.png")
        print(f"saved {name}.png")

    for name, cmd in COMMANDS:
        text = run_command(cmd)
        shown = "python " + " ".join(cmd[1:])
        render(f"Terminal - {shown}", f"{prompt} {shown}", text, OUT / f"{name}.png")
        print(f"saved {name}.png")


if __name__ == "__main__":
    main()
