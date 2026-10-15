#!/usr/bin/env python3
"""
Mount & Partition Agent
-----------------------
Natural language → lsblk / losetup / mount(2) via Gemini tool use.

Usage:
    sudo -E python3 mount_agent.py
    > Mount ~/Downloads/ubuntu.iso so I can look at the files inside
    > What's mounted right now?
    > List the files inside the ISO
    > Unmount it and clean up

Requires:
    - Linux OS
    - Root privileges (for losetup / mount)
    - pip install google-genai
    - GEMINI_API_KEY in environment (hence `sudo -E`)

Safety model (the LLM never gets a shell):
    * No shell=True anywhere; every command is a fixed argv list.
    * Mounts only land under MOUNT_ROOT (/mnt/agent/<name>).
    * Read-only by default; read-write requires explicit human confirmation.
    * Only loop devices can be attached/mounted/detached unless --allow-real-disks.
    * File browsing is confined to the mount point (symlinks resolved).
"""

import argparse
import ctypes
import ctypes.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL = "gemini-2.5-flash"
MOUNT_ROOT = Path("/mnt/agent")
MS_RDONLY = 1
ALLOW_REAL_DISKS = False  # overridden by --allow-real-disks CLI flag

# ---------------------------------------------------------------------------
# libc bindings for mount(2) / umount2(2)
# ---------------------------------------------------------------------------
libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
libc.mount.argtypes = [
    ctypes.c_char_p, ctypes.c_char_p,
    ctypes.c_char_p, ctypes.c_ulong, ctypes.c_char_p,
]
libc.umount2.argtypes = [ctypes.c_char_p, ctypes.c_int]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def run(argv: list[str], timeout: int = 30) -> dict:
    """Run a subprocess with a fixed argv list. Returns stdout/stderr/ok."""
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return {
        "ok": p.returncode == 0,
        "stdout": p.stdout.strip(),
        "stderr": p.stderr.strip(),
    }


def err(msg: str) -> dict:
    return {"ok": False, "error": msg}


def is_loop(dev: str) -> bool:
    return re.fullmatch(r"/dev/loop\d+(p\d+)?", dev) is not None


def device_allowed(dev: str) -> bool:
    if not re.fullmatch(r"/dev/[A-Za-z0-9/_-]+", dev):
        return False
    return is_loop(dev) or ALLOW_REAL_DISKS


def mount_dir(name: str) -> Path | None:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", name) or name in (".", ".."):
        return None
    return MOUNT_ROOT / name


def confirm(question: str) -> bool:
    return input(f"\n[CONFIRM] {question} [y/N] ").strip().lower() == "y"


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def list_block_devices() -> dict:
    """Run lsblk and return all block devices as JSON."""
    r = run(["lsblk", "-J", "-o",
             "NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,RO,MOUNTPOINTS,PKNAME"])
    return json.loads(r["stdout"]) if r["ok"] else err(r["stderr"])


def list_loop_devices() -> dict:
    """Run losetup -l and return all active loop devices."""
    r = run(["losetup", "-J", "-l"])
    if not r["ok"]:
        return err(r["stderr"])
    return json.loads(r["stdout"]) if r["stdout"] else {"loopdevices": []}


def attach_loop(image_path: str, read_only: bool = True) -> dict:
    """
    Attach a disk image or ISO file to a free loop device via losetup.
    read_only=True (default) for safe browsing.
    """
    p = Path(image_path).expanduser().resolve()
    if not p.is_file():
        return err(f"{p} is not a regular file")
    if not read_only and not confirm(f"Attach {p} READ-WRITE?"):
        return err("User declined read-write attach")
    argv = ["losetup", "--find", "--show", "--partscan"]
    if read_only:
        argv.append("--read-only")
    r = run(argv + [str(p)])
    if not r["ok"]:
        return err(r["stderr"])
    dev = r["stdout"]
    run(["udevadm", "settle"])          # wait for partition nodes to appear
    return {
        "ok": True,
        "device": dev,
        "hint": "Call list_block_devices to see partitions (e.g. loop0p1).",
    }


def detect_filesystem(device: str) -> dict:
    """
    Probe a device or partition with blkid.
    Returns TYPE (iso9660, ext4, vfat, …), LABEL, UUID.
    If it fails, the device may hold a partition table — call list_block_devices.
    """
    if not device_allowed(device):
        return err(f"{device} not permitted")
    r = run(["blkid", "-p", "-o", "export", device])
    if not r["ok"]:
        return err(r["stderr"] or "no recognizable filesystem (partition table?)")
    return {
        "ok": True,
        **dict(line.split("=", 1) for line in r["stdout"].splitlines() if "=" in line),
    }


def mount_device(device: str, name: str,
                 fstype: str | None = None, read_only: bool = True) -> dict:
    """
    Mount a device/partition at /mnt/agent/<name>.
    fstype is auto-detected if omitted. Read-only by default.
    """
    if not device_allowed(device):
        return err(f"{device} not permitted (loop devices only by default)")
    target = mount_dir(name)
    if target is None:
        return err("name must match [A-Za-z0-9._-]{1,64}")
    if not read_only and not confirm(f"Mount {device} READ-WRITE at {target}?"):
        return err("User declined read-write mount")
    if not fstype:
        det = detect_filesystem(device)
        if not det.get("ok"):
            return det
        fstype = det.get("TYPE")
        if not fstype:
            return err("could not determine filesystem type")
    target.mkdir(parents=True, exist_ok=True)
    flags = MS_RDONLY if read_only else 0
    rc = libc.mount(
        device.encode(), str(target).encode(), fstype.encode(), flags, None
    )
    if rc != 0:
        e = ctypes.get_errno()
        try:
            target.rmdir()
        except OSError:
            pass
        return err(f"mount failed: {os.strerror(e)} (errno {e})")
    return {
        "ok": True,
        "mountpoint": str(target),
        "fstype": fstype,
        "read_only": read_only,
    }


def list_mounts() -> dict:
    """List all mounts this agent has made under /mnt/agent."""
    out = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        f = line.split()
        mp = f[4].replace("\\040", " ")
        if mp.startswith(str(MOUNT_ROOT) + "/"):
            sep = f.index("-")
            out.append({
                "mountpoint": mp,
                "fstype": f[sep + 1],
                "source": f[sep + 2],
                "options": f[5],
            })
    return {"mounts": out}


def unmount(name: str, detach_loop: bool = True) -> dict:
    """
    Unmount /mnt/agent/<name>, remove the directory,
    and (optionally) detach the backing loop device.
    """
    target = mount_dir(name)
    if target is None or not target.exists():
        return err(f"no mount named '{name}'")
    source = next(
        (m["source"] for m in list_mounts()["mounts"]
         if m["mountpoint"] == str(target)),
        None,
    )
    if libc.umount2(str(target).encode(), 0) != 0:
        e = ctypes.get_errno()
        return err(f"umount failed: {os.strerror(e)} (is it busy?)")
    try:
        target.rmdir()
    except OSError:
        pass
    res = {"ok": True, "unmounted": str(target)}
    if detach_loop and source and is_loop(source):
        base = re.sub(r"p\d+$", "", source)
        res["detach"] = run(["losetup", "-d", base])
    return res


def detach_loop_device(device: str) -> dict:
    """Detach a loop device that has no active mounts (cleanup after failure)."""
    if not is_loop(device):
        return err("only /dev/loopN devices can be detached")
    r = run(["losetup", "-d", device])
    return {"ok": r["ok"], "stderr": r["stderr"]}


def list_files(name: str, subpath: str = "", max_entries: int = 200) -> dict:
    """
    List a directory inside one of the agent's mounts.
    Browsing is confined to the mount point (no symlink escapes).
    """
    target = mount_dir(name)
    if target is None or not target.is_dir():
        return err(f"no mount named '{name}'")
    root = target.resolve()
    p = (root / subpath.lstrip("/")).resolve()
    if root != p and root not in p.parents:
        return err("path escapes the mount point")
    if not p.is_dir():
        return err(f"'{subpath or '/'}' is not a directory")
    entries = []
    for i, child in enumerate(sorted(p.iterdir())):
        if i >= max_entries:
            entries.append("... (truncated)")
            break
        kind = "d" if child.is_dir() else "l" if child.is_symlink() else "f"
        size = child.stat().st_size if kind == "f" else None
        entries.append({"name": child.name, "type": kind, "size": size})
    return {"ok": True, "path": str(p), "entries": entries}


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------
TOOLS_IMPL = {
    "list_block_devices": list_block_devices,
    "list_loop_devices": list_loop_devices,
    "attach_loop": attach_loop,
    "detect_filesystem": detect_filesystem,
    "mount_device": mount_device,
    "list_mounts": list_mounts,
    "unmount": unmount,
    "detach_loop_device": detach_loop_device,
    "list_files": list_files,
}

# Gemini function declarations
TOOLS = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="list_block_devices",
            description=(
                "Run lsblk and return all block devices, partitions, "
                "filesystems and mountpoints as JSON."
            ),
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        ),
        types.FunctionDeclaration(
            name="list_loop_devices",
            description=(
                "Run losetup -l: lists which loop devices exist "
                "and which image files back them."
            ),
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        ),
        types.FunctionDeclaration(
            name="attach_loop",
            description=(
                "Attach a disk image or ISO file to a free loop device "
                "(losetup --find --partscan). Returns the loop device path. "
                "Read-only by default."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "image_path": types.Schema(
                        type=types.Type.STRING,
                        description="Absolute or ~ path to the image file.",
                    ),
                    "read_only": types.Schema(
                        type=types.Type.BOOLEAN,
                        description="Attach read-only (default: true).",
                    ),
                },
                required=["image_path"],
            ),
        ),
        types.FunctionDeclaration(
            name="detect_filesystem",
            description=(
                "Probe a device or partition with blkid and return its TYPE "
                "(iso9660, ext4, vfat, ...), LABEL, UUID. If it fails, the "
                "device may hold a partition table: call list_block_devices "
                "to find its partitions."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "device": types.Schema(
                        type=types.Type.STRING,
                        description="Block device path, e.g. /dev/loop0.",
                    ),
                },
                required=["device"],
            ),
        ),
        types.FunctionDeclaration(
            name="mount_device",
            description=(
                "mount(2) a device/partition at /mnt/agent/<name>. "
                "fstype is auto-detected if omitted. Read-only by default."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "device": types.Schema(
                        type=types.Type.STRING,
                        description="Block device path, e.g. /dev/loop0 or /dev/loop0p1.",
                    ),
                    "name": types.Schema(
                        type=types.Type.STRING,
                        description="Short directory name, e.g. 'ubuntu-iso'.",
                    ),
                    "fstype": types.Schema(
                        type=types.Type.STRING,
                        description="Filesystem type; auto-detected if omitted.",
                    ),
                    "read_only": types.Schema(
                        type=types.Type.BOOLEAN,
                        description="Mount read-only (default: true).",
                    ),
                },
                required=["device", "name"],
            ),
        ),
        types.FunctionDeclaration(
            name="list_mounts",
            description="List all mounts this agent has made under /mnt/agent.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        ),
        types.FunctionDeclaration(
            name="unmount",
            description=(
                "Unmount /mnt/agent/<name>, remove the directory, "
                "and detach its backing loop device."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(
                        type=types.Type.STRING,
                        description="The mount name given when mount_device was called.",
                    ),
                    "detach_loop": types.Schema(
                        type=types.Type.BOOLEAN,
                        description="Also detach the backing loop device (default: true).",
                    ),
                },
                required=["name"],
            ),
        ),
        types.FunctionDeclaration(
            name="detach_loop_device",
            description=(
                "Detach a loop device with no active mounts "
                "(cleanup after a failed mount attempt)."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "device": types.Schema(
                        type=types.Type.STRING,
                        description="Loop device path, e.g. /dev/loop3.",
                    ),
                },
                required=["device"],
            ),
        ),
        types.FunctionDeclaration(
            name="list_files",
            description=(
                "List a directory inside one of the agent's mounts. "
                "Browsing is confined to the mount point."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(
                        type=types.Type.STRING,
                        description="The mount name.",
                    ),
                    "subpath": types.Schema(
                        type=types.Type.STRING,
                        description="Subdirectory inside the mount to list (default: root).",
                    ),
                    "max_entries": types.Schema(
                        type=types.Type.INTEGER,
                        description="Maximum entries to return (default: 200).",
                    ),
                },
                required=["name"],
            ),
        ),
    ])
]

SYSTEM = """\
You are a Linux storage assistant that mounts disk images and partitions for the user.

Standard workflow for an image file:
1. attach_loop (read-only by default)
2. list_block_devices — check whether the image has partitions
3. detect_filesystem on the right node (the loop device itself for ISOs)
4. mount_device — mounts it at /mnt/agent/<name>
5. list_files — show the user what's inside

For ISOs the loop device itself is usually iso9660.
For full disk images, mount the relevant partition (ask the user which if several are plausible).

Always default to read-only. Clean up after failures (detach loop devices you attached).
Be concise and report the mountpoint once the mount succeeds.
"""


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------
def chat() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY not set. Export it before running with sudo -E.")

    client = genai.Client(api_key=api_key)
    history: list[types.Content] = []

    print("Mount & Partition Agent  (Ctrl-D or Ctrl-C to quit)")
    print(f"  Model      : {MODEL}")
    print(f"  Mount root : {MOUNT_ROOT}")
    print(f"  Real disks : {'allowed' if ALLOW_REAL_DISKS else 'blocked (pass --allow-real-disks)'}")
    print()

    while True:
        try:
            user_text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return
        if not user_text:
            continue

        history.append(types.Content(role="user", parts=[types.Part(text=user_text)]))

        # Agentic loop: keep going until the model stops calling tools
        while True:
            response = client.models.generate_content(
                model=MODEL,
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM,
                    tools=TOOLS,
                    temperature=0,
                ),
            )

            # Collect all parts from this turn
            candidate = response.candidates[0]
            history.append(types.Content(role="model", parts=candidate.content.parts))

            tool_calls = [
                p for p in candidate.content.parts
                if p.function_call is not None
            ]

            # Print any text parts
            for part in candidate.content.parts:
                if part.text and part.text.strip():
                    print(part.text)

            if not tool_calls:
                break   # model is done

            # Execute every tool call and collect results
            function_responses = []
            for part in tool_calls:
                fc = part.function_call
                print(f"  [tool] {fc.name}({json.dumps(dict(fc.args))})")
                try:
                    result = TOOLS_IMPL[fc.name](**dict(fc.args))
                except Exception as exc:
                    result = err(f"{type(exc).__name__}: {exc}")
                function_responses.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=fc.name,
                            response=result,
                        )
                    )
                )

            history.append(
                types.Content(role="user", parts=function_responses)
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Natural-language Linux mount/partition agent powered by Gemini."
    )
    ap.add_argument(
        "--allow-real-disks",
        action="store_true",
        help="Permit mounting non-loop block devices (/dev/sdX, nvme...)",
    )
    args = ap.parse_args()
    ALLOW_REAL_DISKS = args.allow_real_disks

    if sys.platform != "linux":
        sys.exit("This agent requires Linux (needs losetup and mount(2)).")
    if os.geteuid() != 0:
        sys.exit("Run as root:  sudo -E python3 mount_agent.py")

    MOUNT_ROOT.mkdir(parents=True, exist_ok=True)
    chat()
