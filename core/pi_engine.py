"""Runs a question through the Pi Durable harness (pi_engine/agent.ts).

Pi Durable commits every model turn and tool call to SQLite before showing it,
so an interrupted run resumes where it stopped. Each person has their own
persistent conversation. Requires Node.js 22+ and `npm install` in pi_engine/.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .bridge import ToolBridge


@dataclass
class Answer:
    text: str
    trace: list[dict] = field(default_factory=list)   # [{tool, args, result}]
    engine: str = ""


def system_prompt(app, role: str = "team") -> str:
    """The Copilot's instructions: the rules plus every Python skill's SKILL.md (served to Pi by the bridge)."""
    team = app.config.get("team", {})
    skills = "\n\n".join(f"### Skill: {s.name}\n{s.description}\n{s.instructions}" for s in app.skills)
    return (
        "You are the London Office Market Agent, a shared AI tool for one business team.\n"
        f"Today is {date.today():%d %B %Y}. The team: {team.get('description', '')} Everyone on the team "
        "sees the same Home page, alerts and brief, so changes to focus or alerts apply to the whole team.\n\n"
        "Rules:\n- Use tools for every number; never invent figures.\n"
        "- Quote the period and publisher for each figure, and flag definition differences between sources.\n"
        "- Say how a figure reached the team library: open data collected automatically, or a report uploaded "
        "by a named colleague on a date (the sources' 'provenance' field).\n"
        "- If the question names a publisher or an area the library does not cover, the app already shows the "
        "user a coverage note above your answer. Do not repeat it and never present another publisher's or "
        "area's figures as if they answered the question; say whose and which area's figures you are using.\n"
        "- If a figure is marked ⚠ (flagged by a colleague and not yet checked), say so next to it.\n"
        "- Sources 'disagree' only when they give different values for the SAME period, market and metric. "
        "Figures from different periods are a change over time, never a disagreement.\n"
        "- Never promise what you have no tool for (adding an area, a feed or an alert you cannot create). "
        "Say instead that anyone on the team can follow a source or upload a report on the Sources page.\n"
        "- 🔵 Internal records (our own deals, from record_deal / list_our_deals) are confidential: cite them as "
        "'internal only' or 'quotable', never as market evidence, and never put an internal-only record in an IC "
        "paper or anything that leaves the company.\n"
        "- Lead with the answer in plain business English, then the evidence. Keep it short.\n"
        "- Explain why a change matters for rents, values, leasing risk or strategy.\n\n" + skills)


# A failure inside the local Pi process or its conversation store, as opposed to the model API.
STORE_ERROR = re.compile(r"PathError|unresolvable path|SQLITE_|SqliteError|not a database|malformed|database is locked|"
                         r"Unexpected (end of JSON|token)|ENOENT.*conversations", re.I)


class PiDurableEngine:
    """One Pi Durable store per person (data/pi/<name>.sqlite + .json), so two people asking at once never
    write the same file; the same person's requests are queued behind a lock. A store that will not load
    (a run killed mid-write, a corrupt conversation) is moved aside and the conversation starts again."""
    name = "pi-durable"

    def __init__(self, app):
        self.app = app
        self.dir = Path(os.getenv("PI_ENGINE_DIR", app.root / "pi_engine"))
        self.bridge: ToolBridge | None = None
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock(self, role: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(role, threading.Lock())

    def store_paths(self, role: str) -> tuple[Path, Path]:
        """(sqlite store, conversation map) for one person. PI_STORE / PI_CONVERSATIONS override both (tests)."""
        if os.getenv("PI_STORE") or os.getenv("PI_CONVERSATIONS"):
            return (Path(os.getenv("PI_STORE", str(self.app.root / "data" / "pi_durable.sqlite"))),
                    Path(os.getenv("PI_CONVERSATIONS", str(self.app.root / "data" / "pi_conversations.json"))))
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", role.strip()).strip("_") or "team"
        base = self.app.root / "data" / "pi"
        return base / f"{safe}.sqlite", base / f"{safe}.json"

    def reset_store(self, role: str) -> str:
        """Move a broken store aside (never deleted) so the next run starts a fresh conversation."""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        moved = []
        store, conv = self.store_paths(role)
        for f in [store, conv, *store.parent.glob(store.name + "-*")]:  # -wal, -shm, -journal
            if f.exists():
                target = f.with_name(f"{f.name}.broken-{stamp}")
                f.rename(target)
                moved.append(target.name)
        return ", ".join(moved)

    def available(self) -> tuple[bool, str]:
        if not shutil.which("node"):
            return False, "Node.js not found"
        if not (self.dir / "node_modules" / "@earendil-works" / "pi-durable").exists():
            return False, "run `npm install` in pi_engine/"
        if not (os.getenv("MIMO_API_KEY") or os.getenv("XIAOMI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
                or os.getenv("OPENAI_API_KEY") or os.getenv("PI_FAUX") == "1"):
            return False, "no MIMO_API_KEY, ANTHROPIC_API_KEY or OPENAI_API_KEY"
        return True, "ready"

    def _run(self, script: str, stdin: str, role: str, request_id: str | None) -> tuple[dict, str]:
        """One request through Pi, serialised per person. A store error resets that person's store once and
        runs again; the answer then comes from a fresh conversation (the person is told in the engine note)."""
        with self._lock(role):
            try:
                return self._run_once(script, stdin, role, request_id)
            except RuntimeError as e:
                if not STORE_ERROR.search(str(e)):
                    raise
                moved = self.reset_store(role)
                print(f"[agent] Pi store for {role!r} would not load and was moved aside ({moved}); starting a new "
                      f"conversation", file=sys.stderr)
                out, rid = self._run_once(script, stdin, role, None)
                out["store_reset"] = True
                return out, rid

    def _run_once(self, script: str, stdin: str, role: str, request_id: str | None) -> tuple[dict, str]:
        if self.bridge is None:
            self.bridge = ToolBridge(self.app)
        rid = request_id or uuid.uuid4().hex
        llm_cfg = self.app.config.get("llm", {})
        store, conv = self.store_paths(role)
        store.parent.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "BRIDGE_URL": self.bridge.url, "ROLE": role, "REQUEST_ID": rid,
               "PI_STORE": str(store), "PI_CONVERSATIONS": str(conv),
               "ANTHROPIC_MODEL": os.getenv("ANTHROPIC_MODEL", llm_cfg.get("anthropic_model", "claude-opus-5-5")),
               "OPENAI_MODEL": os.getenv("OPENAI_MODEL", llm_cfg.get("openai_model", "gpt-5.5")),
               "MIMO_MODEL": os.getenv("MIMO_MODEL", llm_cfg.get("mimo_model", "mimo-v2.6-flash"))}
        if os.getenv("MIMO_API_KEY") and not os.getenv("XIAOMI_API_KEY"):
            env["XIAOMI_API_KEY"] = os.environ["MIMO_API_KEY"]  # the name Pi's Xiaomi provider reads
        cmd = ["node", "--experimental-strip-types", "--no-warnings", str(self.dir / script)]
        last_err = ""
        limit = int(os.getenv("PI_TIMEOUT", self.app.config.get("agent", {}).get("timeout_seconds", 1800)))
        for _attempt in range(2):   # a retry with the same request ID resumes, it never re-asks
            try:
                proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env,
                                      cwd=self.dir, timeout=limit)
            except subprocess.TimeoutExpired:  # the durable run keeps its finished steps; one resume
                last_err = f"timeout after {limit} s"
                continue
            lines = [l for l in proc.stdout.splitlines() if l.startswith("{")]
            if proc.returncode == 0 and lines:
                out = json.loads(lines[-1])
                if out.get("failure"):  # the run settled without an answer, e.g. model_error
                    f = out["failure"]
                    raise RuntimeError(f"Pi {script} model {f.get('reason')}: {json.dumps(f.get('detail'))[:600]}")
                return out, rid
            err = (proc.stderr or proc.stdout).strip()
            # keep the head (the error itself) and the tail (where it happened) of a long stack trace
            last_err = (err if len(err) <= 1000 else err[:500] + " … " + err[-500:]) or f"exit code {proc.returncode}, no output"
        raise RuntimeError(f"Pi local run of {script} failed (not the model API): {last_err}")

    def ask(self, question: str, role: str, request_id: str | None = None) -> Answer:
        out, rid = self._run("agent.ts", question, role, request_id)
        return Answer(out.get("answer", ""), self.bridge.pop_trace(rid),
                      f"pi-durable:{out.get('model', '')} (conversation {out.get('conversation', '')})"
                      + (" · earlier conversation could not be loaded and was set aside; this is a new one"
                         if out.get("store_reset") else ""))

    def gather(self, instruction: str = "", role: str = "team", request_id: str | None = None) -> Answer:
        """One run of the Pi information agent (pi_engine/info_agent.ts), a durable conversation of its own:
        the daily round when there is no instruction, or one item (an upload, a link)."""
        out, rid = self._run("info_agent.ts", instruction, role, request_id)
        return Answer(out.get("answer", ""), self.bridge.pop_trace(rid), f"Pi information agent ({out.get('model', '')})")
