"""
config.py - Defaults for the Mount & Partition Agent.
Every value can be overridden with an environment variable or a command-line flag.
"""

import os
import sys
from pathlib import Path

# Linux: where new mounts are created when the user does not name a mount point
MOUNT_ROOT = os.getenv("MOUNT_AGENT_ROOT", "/mnt/agent")

# Linux: the agent refuses to mount or unmount anything outside these directories
SAFE_MOUNT_PREFIXES = ("/mnt", "/media")

# LLM backends
CLAUDE_MODEL = os.getenv("MOUNT_AGENT_CLAUDE_MODEL", "claude-opus-5-5")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("MOUNT_AGENT_OLLAMA_MODEL", "llama3")

# Terminal
HISTORY_FILE = Path.home() / ".mount_agent_history"
PROMPT = "mount-agent> "

IS_LINUX = sys.platform.startswith("linux")
IS_WINDOWS = os.name == "nt"

# The platform this machine can really run commands for (None = simulate only, e.g. macOS)
HOST_PLATFORM = "linux" if IS_LINUX else "windows" if IS_WINDOWS else None


def is_admin() -> bool:
    """root on Linux, an elevated (Run as administrator) shell on Windows."""
    if IS_WINDOWS:
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0
