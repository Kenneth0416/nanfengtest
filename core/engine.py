"""The one agent engine: Pi Durable. The Copilot and the information agent both run on it."""
from __future__ import annotations

import json
import queue
import re
import sys
import threading

from . import coverage
from .pi_engine import Answer, PiDurableEngine


# Which playbook each information-agent tool belongs to, to show the chain of skills used.
TOOL_SKILL = {"follow_source": "check-terms", "fetch_source": "fetch-source", "dedupe_report": "dedupe",
              "find_matches": "dedupe", "pdf_overview": "read-pdf", "read_pdf_pages": "read-pdf",
              "pdf_page_text": "read-pdf", "read_table": "read-table", "save_series": "read-table",
              "classify_item": "read-article", "save_item": "read-article", "map_markets": "map-submarkets",
              "check_figures": "check-figures", "stage_figures": "check-figures", "save_figures": "check-figures"}


class AgentUnavailable(RuntimeError):
    """Anything that stops the agent answering. The message is plain language for the user;
    `detail` keeps the technical cause for the 'Technical details' expander and the logs."""
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


class PiNotReady(AgentUnavailable):
    """Pi cannot run here (no Node, no `npm install`, or no model key)."""


class AgentFailed(AgentUnavailable):
    """Pi started but the model API failed: budget, key, rate limit or outage."""


def _plain(err: Exception) -> str:
    t = str(err).lower()
    if "pi local run" in t or "timeout after" in t:
        # the Node process or its conversation store failed; the model API was not involved
        return ("The Copilot's run on this server failed before it reached the model (a local error, not the model "
                "API). Please ask again; if it keeps happening, tell whoever runs the server.")
    if any(w in t for w in ("credit", "billing", "quota", "insufficient", "budget", "balance")):
        why = "the model API budget has run out"
    elif any(w in t for w in ("401", "403", "authentication", "api key", "api_key", "permission")):
        why = "the model API key was refused"
    elif any(w in t for w in ("429", "rate limit", "rate_limit", "overloaded", "529")):
        why = "the model API is busy right now"
    elif any(w in t for w in ("connection error", "connecterror", "econnrefused", "enotfound", "network")):
        why = "this server can't reach the model API"
    elif "timeout" in t or "timed out" in t:
        why = "the model took too long to answer"
    else:
        why = "the model API returned an error"
    return (f"The agent couldn't finish this because {why}. "
            "Please try again later, or tell whoever runs the server.")


FOLLOW_UP = re.compile(r"(?:^|\n)\s*\**\s*Follow[ -]ups?\s*:?\**\s*:?\s*(.+?)\s*$", re.I | re.S)


def split_follow_ups(text: str) -> tuple[str, list[str]]:
    """The answer without its closing `Follow up: a | b | c` line, and those questions as a list (at most three).
    An answer without the line comes back unchanged with no questions."""
    m = FOLLOW_UP.search(text or "")
    if not m or "\n" in m.group(1).strip():
        return text, []
    qs = [q.strip(" -•*") for q in re.split(r"\s*[|｜]\s*", m.group(1)) if q.strip(" -•*")]
    return text[:m.start()].rstrip(), qs[:3]


class StreamingAnswer:
    """A Copilot answer being written: events() yields {"event": "delta", "text": ...} and tool events in order;
    when the generator finishes, `answer` holds the complete Answer (text, trace, sources) or `error` the failure."""

    def __init__(self, engine: "Engine", question: str, role: str, conversation: str | None = None):
        self.answer: Answer | None = None
        self.error: Exception | None = None
        self.coverage = coverage.note(question, engine.app.store)
        self._q: queue.Queue = queue.Queue()

        def run():
            try:
                self.answer = engine.ask(question, role, None, self._q.put, conversation)
            except Exception as e:  # noqa: BLE001  (surfaced to the page as .error)
                self.error = e
            finally:
                self._q.put(None)
        threading.Thread(target=run, daemon=True, name=f"copilot-{role}").start()

    def events(self):
        if self.coverage:
            yield {"event": "delta", "text": f"> **Coverage:** {self.coverage}\n\n"}
        while (e := self._q.get()) is not None:
            yield e

    def text(self):
        """Just the text pieces, for st.write_stream."""
        for e in self.events():
            if e["event"] == "delta":
                yield e["text"]


class Engine:
    def __init__(self, app):
        self.app = app
        self.pi = PiDurableEngine(app)
        self.ready, self.why = self.pi.available()
        self.status = "Pi Durable (durable conversations)" if self.ready else f"Pi Durable not ready: {self.why}"

    def _check(self):
        if not self.ready:
            raise PiNotReady("The Copilot isn't available on this server right now. Ask whoever runs it to finish "
                             "the setup ('Running the agent' in the README).", f"{self.why}")

    def _run(self, fn, *args):
        """Every Pi call goes through here, so an API failure reaches the user as one plain sentence."""
        self._check()
        try:
            return fn(*args)
        except AgentUnavailable:
            raise
        except Exception as e:
            print(f"[agent] Pi call failed: {str(e)[-600:]}", file=sys.stderr)
            raise AgentFailed(_plain(e), str(e)[-600:]) from None

    def ask(self, question: str, role: str, history: list[dict] | None = None, on_event=None,
            conversation: str | None = None) -> Answer:
        """A Copilot question. Pi keeps the conversation itself, so history is not passed; `conversation` names
        which of the person's saved chats this continues (their one default chat when not given).
        `on_event` gets each streamed piece of the answer and each tool start as it happens."""
        gap = coverage.note(question, self.app.store)
        ans = self._run(self.pi.ask, f"{question}\n\n(Coverage note shown to the user: {gap})" if gap else question, role,
                        None, on_event, conversation)
        if gap:
            ans.text = f"> **Coverage:** {gap}\n\n{ans.text}"
        return ans

    def ask_streaming(self, question: str, role: str, conversation: str | None = None) -> "StreamingAnswer":
        """The same question, answered while the person watches: Pi runs in a thread and every piece of text
        (and each tool start) is handed over as it arrives. Iterate `.events()`; `.answer` or `.error` is set when
        the iteration ends."""
        return StreamingAnswer(self, question, role, conversation)

    @staticmethod
    def deck_ask(fmt: str, theme: str | None) -> str:
        return (f"Build this week's team brief deck as a {'IC' if fmt == 'ic' else 'board'} pack"
                + (f" on the {theme} theme" if theme else "") + ". Call brief_deck_data first and read the ranked stories: "
                "decide yourself which of them deserve a slide this week (1-4 content slides; leave out anything that did "
                "not move or does not matter to the person asking), which layout and chart or table each gets, the theme "
                "if none was given, and the order. Write one finding per title, a so_what where the layout takes one, "
                "speaker notes, and a `why` on every slide saying what in this week's data earned it. Call "
                "brief_deck_guide('storyline') if you need the rules. Then call build_brief_pptx with format and spec; "
                "if it refuses or lists problems, fix exactly those and build again. Finish with one line per slide "
                "and its why.")

    @staticmethod
    def deck_edit_ask(fmt: str, theme: str, spec: dict, instruction: str) -> str:
        """An edit to a built deck: the current spec travels with the request so the Copilot changes only what
        was asked and builds the whole deck again from the revised spec."""
        return (f"The team is editing the {'IC' if fmt == 'ic' else 'board'} deck in the slide editor. Its current spec "
                f"(theme {theme}, {len(spec.get('slides', []))} slides) is:\n```json\n{json.dumps(spec, ensure_ascii=False)}\n```\n"
                f"They ask: {instruction}\n"
                "Rules: do exactly what was asked and nothing else. Never remove, replace or merge a slide unless the "
                "instruction asks for that; if you cannot do what was asked without removing one, do not build: explain "
                "why and ask. The editor allows up to 12 slides, so adding never requires dropping one. To add a slide "
                "(or N slides), call brief_deck_data and take the best-ranked stories that are not already in the deck "
                "(or the topic named), with a layout from brief_deck_guide('layouts'), a `why`, and figures only as the "
                "data gives them; keep the cover first and the sources slide last and renumber the eyebrows. Then call "
                "build_brief_pptx with format, theme and the full revised spec; if it refuses or lists problems, fix "
                "those and build again (never by dropping slides). Finish with one or two lines, in the language of "
                "the instruction, that describe the deck exactly as the last successful build returned it: which slides "
                "were added, changed or moved, and the final slide count. Do not claim anything the build did not do, "
                "and do not refer to a 'next message'.")

    @staticmethod
    def built_deck(ans: Answer) -> dict | None:
        return next((t["result"].get("data") for t in reversed(ans.trace)
                     if t["tool"] == "build_brief_pptx" and (t["result"].get("data") or {}).get("path")), None)

    def build_deck(self, fmt: str, theme: str | None, user: str) -> tuple[dict | None, Answer]:
        """The Copilot plans the deck from this week's data: reads brief_deck_data (the ranked stories), decides
        which deserve a slide, which layouts and charts, writes titles, so-whats and a `why` per slide, builds,
        fixes anything the check reports. Returns (build result data, the Copilot's answer)."""
        ans = self._run(self.pi.ask, self.deck_ask(fmt, theme), user)
        return self.built_deck(ans), ans

    def build_deck_streaming(self, fmt: str, theme: str | None, user: str, conversation: str | None = None) -> "StreamingAnswer":
        """The same plan, watched: tool starts and the Copilot's words arrive as events; `built_deck(.answer)`
        gives the build once the events end."""
        self._check()
        return StreamingAnswer(self, self.deck_ask(fmt, theme), user, conversation)

    def edit_deck_streaming(self, fmt: str, theme: str, spec: dict, instruction: str, user: str,
                            conversation: str | None = None) -> "StreamingAnswer":
        self._check()
        return StreamingAnswer(self, self.deck_edit_ask(fmt, theme, spec, instruction), user, conversation)

    def read_upload(self, path, user: str) -> tuple[dict | None, list[str], str]:
        """A colleague's PDF upload, read by the information agent for their review.
        Returns (analysis staged for review, skill chain used, the agent's note)."""
        ans = self._run(self.pi.gather, f"{user} uploaded the report at {path} for the team. Process it for their "
                             "review: follow your playbooks (dedupe, read-pdf, map-submarkets, check-figures) "
                             "and finish with stage_figures. If it is a duplicate, stop and say so.", user)
        chain = list(dict.fromkeys(TOOL_SKILL.get(t["tool"], t["tool"]) for t in ans.trace if t["tool"] in TOOL_SKILL))
        staged = self.app.store.staged(str(path))
        return (staged, chain, ans.engine) if staged else (None, chain, ans.text)  # e.g. a duplicate

    def gather(self, user: str = "team", instruction: str = "") -> Answer:
        """A gathering round (the team inbox, open data, new report titles), or one item when given."""
        return self._run(self.pi.gather, instruction, user)
