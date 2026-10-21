"""
shell.py - The interactive terminal (REPL).
Reads a line, handles built-in commands, otherwise hands the sentence to the agent backend
and renders every tool call, its result and the exact commands that ran.
"""

import os
from typing import Any, Dict, List

from .. import config
from ..agent.backends import Backend
from ..agent.tools import MUTATING_TOOLS, ToolBox
from ..core.platforms import Platform
from ..core.session import Session
from . import render

try:
    import readline  # arrow-key history on Linux/macOS
except ImportError:
    readline = None


class Shell:
    def __init__(self, backend: Backend, platform: Platform, session: Session,
                 confirm: bool = True, show_trace: bool = True):
        self.backend = backend
        self.platform = platform
        self.runner = platform.r
        self.session = session
        self.toolbox = ToolBox(platform, session)
        self.confirm = confirm
        self.show_trace = show_trace
        self.history: List[str] = []

    # ------------------------------------------------------------ main loop

    def loop(self):
        self._load_history()
        render.banner(self.platform.name, self.backend.name, self.runner.dry_run, config.is_admin())
        while True:
            try:
                line = input(render.bold(config.PROMPT)).strip()
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                continue
            if not line:
                continue
            self.history.append(line)
            if self.builtin(line) is False:
                break
        self._save_history()
        if self.session.mounts:
            print(render.yellow(f"Note: {len(self.session.mounts)} filesystem(s) are still mounted:"))
            render.mounts_table(self.session.mounts)

    def run_once(self, line: str):
        self.handle(line)

    # ------------------------------------------------------------ commands

    def builtin(self, line: str):
        """Returns False to exit; None when the line was handled here or by the agent."""
        cmd, _, arg = line.partition(" ")
        cmd, arg = cmd.lower(), arg.strip().lower()

        if cmd in ("exit", "quit", "q"):
            return False
        if cmd in ("help", "?"):
            render.help_text(self.platform.name)
        elif cmd == "clear":
            os.system("cls" if os.name == "nt" else "clear")
        elif cmd == "mounts" and not arg:
            render.mounts_table(self.session.mounts)
        elif cmd == "history" and not arg:
            for i, h in enumerate(self.history[:-1], 1):
                print(f"  {i:3}  {h}")
        elif cmd == "reset" and not arg:
            self.backend.reset()
            print("  conversation cleared")
        elif cmd in ("dryrun", "trace", "confirm") and arg in ("on", "off"):
            self._toggle(cmd, arg == "on")
        else:
            self.handle(line)
        return None

    def _toggle(self, name: str, value: bool):
        if name == "dryrun":
            if not value and self.platform.name != config.HOST_PLATFORM:
                render.error(f"this machine can't run {self.platform.name} commands; staying in dry-run")
                return
            self.runner.dry_run = value
        elif name == "trace":
            self.show_trace = value
        else:
            self.confirm = value
        print(f"  {name} {'on' if value else 'off'}")

    # ------------------------------------------------------------ agent

    def handle(self, line: str):
        self.runner.take_trace()
        try:
            text = self.backend.respond(line, self.execute)
        except KeyboardInterrupt:
            text = "cancelled"
        render.reply(text)

    def execute(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Called by the backend for every tool call."""
        render.tool_call(name, args)
        if name in MUTATING_TOOLS and self.confirm and not self.runner.dry_run:
            try:
                answer = input(render.yellow(f"     run {name}? [Y/n] ")).strip().lower()
            except EOFError:
                answer = "n"
            if answer not in ("", "y", "yes"):
                return {"ok": False, "error": "user declined this action"}

        res = self.toolbox.call(name, args)
        render.result(name, res)
        trace = self.runner.take_trace()
        if self.show_trace:
            render.trace(trace)
        return res

    # ------------------------------------------------------------ history file

    def _load_history(self):
        if readline and config.HISTORY_FILE.exists():
            try:
                readline.read_history_file(str(config.HISTORY_FILE))
            except OSError:
                pass

    def _save_history(self):
        if readline:
            try:
                readline.write_history_file(str(config.HISTORY_FILE))
            except OSError:
                pass
