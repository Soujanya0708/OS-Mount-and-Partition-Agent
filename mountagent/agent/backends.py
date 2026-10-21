"""
backends.py - The "brain" that turns a sentence into tool calls.

  claude   Claude API with native tool use (multi-step, remembers the conversation)
  ollama   Local LLM via Ollama that returns a single JSON tool call
  offline  Regex rules from heuristic.py, no network needed

Every backend gets an `execute(name, args) -> dict` callback from the terminal, which
handles confirmation and rendering, so backends never touch the system directly.
"""

import json
import os
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from .. import config
from ..core.session import Session
from . import heuristic
from .tools import TOOL_NAMES, TOOL_SPECS

Executor = Callable[[str, Dict[str, Any]], Dict[str, Any]]

SYSTEM_PROMPT = """You are the Mount & Partition Agent, running inside a terminal.
You translate the user's plain-English requests into block-device operations using your tools.

This machine: {platform}

Rules:
- Image files are attached and mounted by the mount tool in one step.
- Mount read-only unless the user clearly asks for write access.
- Leave mount_point empty to use the default location.
- When the user wants to look inside something, mount it and then call list_files on the mount point.
- If a tool fails, explain the error in one or two sentences and suggest the fix (e.g. run with sudo).
- Reply in short plain text suitable for a terminal: no markdown headings or tables."""


class Backend:
    name = "base"

    def respond(self, prompt: str, execute: Executor) -> str:
        raise NotImplementedError

    def reset(self):
        pass


# ---------------------------------------------------------------- offline / ollama

class PlanBackend(Backend):
    """Backends that produce a fixed plan up front, then run it step by step."""

    def __init__(self, session: Session, platform: str):
        self.session = session
        self.system_prompt = SYSTEM_PROMPT.format(platform=platform)

    def make_plan(self, prompt: str) -> Optional[heuristic.Plan]:
        return heuristic.parse(prompt, self.session)

    def respond(self, prompt: str, execute: Executor) -> str:
        plan = self.make_plan(prompt)
        if plan is None:
            return ("I couldn't map that to a mount operation. Try e.g. "
                    "\"mount ubuntu.iso\", \"show partitions\", \"unmount ubuntu\" or type 'help'.")

        print(f"  thought: {plan.thought}")
        previous: Dict[str, Any] = {}
        summaries = []
        for tool, args in plan.steps:
            args = {k: previous.get(v[1:], v) if isinstance(v, str) and v.startswith("@") else v
                    for k, v in args.items()}
            result = execute(tool, args)
            if not result.get("ok"):
                return f"Stopped: {result.get('error')}"
            summaries.append(_summarize(tool, result))
            previous = result
        return " ".join(s for s in summaries if s)


class OfflineBackend(PlanBackend):
    name = "offline"


class OllamaBackend(PlanBackend):
    name = "ollama"

    def __init__(self, session: Session, platform: str,
                 model: str = config.OLLAMA_MODEL, host: str = config.OLLAMA_HOST):
        super().__init__(session, platform)
        self.model, self.host = model, host.rstrip("/")

    def make_plan(self, prompt: str) -> Optional[heuristic.Plan]:
        tools = "\n".join(f"- {t['name']}: {t['description']} params={json.dumps(t['input_schema']['properties'])}"
                          for t in TOOL_SPECS)
        mounted = ", ".join(m.mount_point for m in self.session.mounts) or "none"
        ask = (f"{self.system_prompt}\n\nTools:\n{tools}\n\nCurrently mounted this session: {mounted}\n\n"
               'Answer with JSON only: {"thought": "...", "tool": "<tool name>", "parameters": {...}}\n\n'
               f"User request: {prompt}")
        try:
            data = _post_json(f"{self.host}/api/generate",
                              {"model": self.model, "prompt": ask, "stream": False, "format": "json"},
                              timeout=60)
            decision = json.loads(data.get("response", "{}"))
            tool = decision.get("tool")
            if tool not in TOOL_NAMES:
                raise ValueError(f"model chose unknown tool {tool!r}")
            steps = [(tool, decision.get("parameters") or {})]
            if tool == "mount":
                steps.append(("list_files", {"path": "@mount_point"}))
            return heuristic.Plan(decision.get("thought", ""), steps)
        except Exception as e:
            print(f"  (ollama unavailable: {e}; using offline parser)")
            return super().make_plan(prompt)


# ---------------------------------------------------------------- claude

class ClaudeBackend(Backend):
    name = "claude"
    MAX_STEPS = 8

    def __init__(self, platform: str, model: str = config.CLAUDE_MODEL):
        import anthropic
        self.system_prompt = SYSTEM_PROMPT.format(platform=platform)
        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.history: List[Dict[str, Any]] = []

    def reset(self):
        self.history = []

    def respond(self, prompt: str, execute: Executor) -> str:
        checkpoint = len(self.history)
        self.history.append({"role": "user", "content": prompt})
        try:
            for _ in range(self.MAX_STEPS):
                resp = self.client.beta.messages.create(
                    model=self.model,
                    max_tokens=16000,
                    system=self.system_prompt,
                    tools=TOOL_SPECS,
                    messages=self.history,
                    output_config={"effort": "medium"},
                    cache_control={"type": "ephemeral"},
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                )
                # Keep the full content (thinking + tool_use blocks) so the next request is valid
                self.history.append({"role": "assistant", "content": resp.content})
                text = "\n".join(b.text for b in resp.content if b.type == "text").strip()

                if resp.stop_reason == "refusal":
                    return text or "Claude declined this request."
                if resp.stop_reason != "tool_use":
                    return text

                if text:
                    print(f"  claude: {text}")
                results = []
                for block in resp.content:
                    if block.type == "tool_use":
                        # Passed as-is: ToolBox validates it and returns a readable error the model can fix
                        out = execute(block.name, block.input)
                        results.append({"type": "tool_result", "tool_use_id": block.id,
                                        "content": json.dumps(out), "is_error": not out.get("ok", False)})
                self.history.append({"role": "user", "content": results})
            return "Stopped after too many tool calls."
        except self.anthropic.AuthenticationError:
            del self.history[checkpoint:]
            return "Claude API key is missing or invalid (set ANTHROPIC_API_KEY) - or restart with --backend offline."
        except self.anthropic.APIConnectionError:
            del self.history[checkpoint:]
            return "Could not reach the Claude API (no network?). Restart with --backend offline."
        except self.anthropic.APIStatusError as e:
            del self.history[checkpoint:]
            return f"Claude API error {e.status_code}: {e.message}"


# ---------------------------------------------------------------- selection

def _post_json(url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _ollama_running(host: str) -> bool:
    try:
        with urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=1):
            return True
    except Exception:
        return False


def _claude_available() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


def create_backend(choice: str, session: Session, platform: str) -> Backend:
    """`platform` is the OS backend's description, given to the LLM so it knows what it is driving."""
    if choice == "auto":
        if _claude_available():
            choice = "claude"
        elif _ollama_running(config.OLLAMA_HOST):
            choice = "ollama"
        else:
            choice = "offline"

    if choice == "claude":
        return ClaudeBackend(platform)
    if choice == "ollama":
        return OllamaBackend(session, platform)
    return OfflineBackend(session, platform)


def _summarize(tool: str, result: Dict[str, Any]) -> str:
    if tool == "mount":
        mode = "read-only" if result["read_only"] else "read-write"
        return f"Mounted {result['source']} at {result['mount_point']} ({result['filesystem']}, {mode})."
    if tool == "unmount":
        what = result.get("mount_point") or result.get("released")
        extra = f" and released {result['released']}" if result.get("released") and result.get("mount_point") else ""
        return f"Unmounted {what}{extra}."
    if tool == "inspect_filesystem":
        return f"{result['path']} is formatted as {result['filesystem']}."
    if tool == "list_block_devices":
        return f"Found {len(result['devices'])} top-level block device(s)."
    if tool == "list_attached_images":
        return f"{len(result['images'])} image(s) attached."
    return ""
