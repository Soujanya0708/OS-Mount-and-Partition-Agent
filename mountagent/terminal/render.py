"""
render.py - Turns tool results into readable terminal output (colors, tables, trees).
"""

import json
import os
import sys
from typing import Any, Dict, List

_COLOR = sys.stdout.isatty() and not os.getenv("NO_COLOR")
if _COLOR and os.name == "nt":
    os.system("")  # enables ANSI escape codes in the Windows console


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def bold(t): return _c("1", t)
def dim(t): return _c("2", t)
def red(t): return _c("31", t)
def green(t): return _c("32", t)
def yellow(t): return _c("33", t)
def blue(t): return _c("34", t)
def cyan(t): return _c("36", t)


def banner(platform: str, backend: str, dry_run: bool, admin: bool):
    print(bold(cyan("+----------------------------------------------------+")))
    print(bold(cyan("|        Mount & Partition Agent  -  terminal         |")))
    print(bold(cyan("+----------------------------------------------------+")))
    mode = yellow("DRY-RUN (simulated, nothing is mounted)") if dry_run else green("LIVE")
    if platform == "windows":
        priv = green("administrator") if admin else yellow("standard user (ISO mounts ok; partitions/VHD need admin)")
    else:
        priv = green("root") if admin else yellow("not root - mounting needs sudo")
    print(f"  os: {bold(platform)}   brain: {bold(backend)}   mode: {mode}")
    print(f"  privileges: {priv}")
    print(dim("  Type a request in plain English, or 'help'. Ctrl-D or 'exit' to quit.\n"))


def help_text(platform: str):
    if platform == "windows":
        examples = """  mount this ubuntu.iso so I can look at the files inside
  mount C:\\Users\\me\\Downloads\\backup.vhdx
  mount partition 1 of disk 1        (admin terminal)
  what filesystem is ubuntu.iso?
  show me all disks and partitions
  which images are attached?
  show files in D:
  unmount ubuntu            (or: unmount it / unmount D:)"""
    else:
        examples = """  mount this ubuntu.iso so I can look at the files inside
  mount /dev/sdb1 read-write at /mnt/usb
  mount disk.img partition 2
  what filesystem is backup.img?
  show me all disks and partitions
  which loop devices are in use?
  show files in /mnt/agent/ubuntu
  unmount ubuntu            (or: unmount it)"""
    print(f"""
{bold('Ask in plain English')}, for example:
{examples}

{bold('Built-in commands')}
  help              this screen
  mounts            what this session has mounted
  dryrun on|off     simulate commands instead of running them
  trace on|off      show the exact commands/syscalls after each request
  confirm on|off    ask before mount/unmount
  reset             forget the conversation (Claude backend)
  history           previous requests
  clear             clear the screen
  exit / quit       leave (Ctrl-D also works)
""")


def tool_call(name: str, args: Dict[str, Any]):
    shown = ", ".join(f"{k}={v!r}" for k, v in args.items())
    print(f"  {cyan('->')} {bold(name)}({shown})")


def error(msg: str):
    print(f"  {red('x')} {msg}")


def reply(text: str):
    if text:
        print(f"\n{green('agent:')} {text}\n")


def trace(lines: List[str]):
    if lines:
        print(dim("  commands run:"))
        for line in lines:
            print(dim(f"    {line}" if line.startswith("PS> ") else f"    $ {line}"))


def result(name: str, res: Dict[str, Any]):
    if not res.get("ok"):
        error(res.get("error", "unknown error"))
        return
    if name == "list_block_devices":
        _devices(res["devices"])
    elif name == "list_attached_images":
        _images(res["images"])
    elif name == "list_files":
        _files(res["path"], res["entries"])
    elif name == "mount":
        _kv([("source", res["source"]), ("loop device", res.get("loop_device") or "-"),
             ("device", res["device"]), ("filesystem", res["filesystem"]),
             ("mount point", res["mount_point"]),
             ("access", "read-only" if res["read_only"] else "read-write"),
             ("via", res["method"])])
    elif name == "unmount":
        _kv([("unmounted", res.get("mount_point") or "-"),
             ("released", res.get("released") or "-")])
    elif name == "inspect_filesystem":
        _kv([("path", res["path"]), ("filesystem", res["filesystem"])])
    else:
        print(json.dumps(res, indent=2))


def mounts_table(records):
    if not records:
        print(dim("  nothing mounted in this session"))
        return
    rows = [(r.mount_point, r.source, r.loop_device or r.device, r.filesystem, "ro" if r.read_only else "rw")
            for r in records]
    _table(["MOUNT POINT", "SOURCE", "DEVICE", "FS", "MODE"], rows)


# ---------------------------------------------------------------- helpers

def _kv(pairs):
    width = max(len(k) for k, _ in pairs)
    for k, v in pairs:
        print(f"     {dim(k.ljust(width))}  {v}")


def _table(headers, rows):
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]
    print("     " + bold("  ".join(h.ljust(w) for h, w in zip(headers, widths))))
    for row in rows:
        print("     " + "  ".join(str(x).ljust(w) for x, w in zip(row, widths)))


def _devices(devices):
    rows = []

    def walk(devs, prefix, is_child):
        for i, d in enumerate(devs):
            last = i == len(devs) - 1
            branch = ("`-" if last else "|-") if is_child else ""
            mount = d.get("mountpoint") or ", ".join(m for m in (d.get("mountpoints") or []) if m) or ""
            rows.append((prefix + branch + d["name"], d.get("size") or "", d.get("type") or "",
                         d.get("fstype") or "", mount, d.get("label") or d.get("model") or ""))
            child_prefix = prefix + (("  " if last else "| ") if is_child else "")
            walk(d.get("children", []), child_prefix, True)

    walk(devices, "", False)
    _table(["NAME", "SIZE", "TYPE", "FSTYPE", "MOUNTPOINT", "LABEL/MODEL"], rows)


def _images(images):
    if not images:
        print(dim("     no image files attached"))
        return
    _table(["DEVICE", "BACKING FILE", "RO"],
           [(i.get("name"), i.get("back-file") or "", "yes" if i.get("ro") else "no") for i in images])


def _files(path, entries):
    if not entries:
        print(dim(f"     {path} is empty"))
        return
    print(dim(f"     {path}:"))
    for e in entries:
        if e["is_dir"]:
            print(f"       {blue(e['name'] + '/')}")
        else:
            print(f"       {e['name']}  {dim(_size(e['size']))}")


def _size(n: int) -> str:
    for unit in ("B", "K", "M", "G"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}T"
