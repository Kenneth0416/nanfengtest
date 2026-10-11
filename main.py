"""Command-line interface for the London Office Market Agent.

  python main.py refresh                 load seed data and pull live sources (scheduled daily on the server)
  python main.py gather                  the information agent's daily round: colleagues' links and tips, open
                                         data, new report titles (runs on Pi; scheduled daily)
  python main.py process "<link or instruction>"   hand one item to the information agent
  python main.py chat                    talk to the agent (Pi)
  python main.py brief [--pptx] [--theme t]  print the team brief (one brief for the board and the investment
                                         committee); --pptx builds the 6-slide deck under data/exports/ and prints
                                         its path (for a weekly timer)
  python main.py signals                 the team's top signals
  python main.py ingest path/to/report.pdf [--save]
  python main.py classify "Headline text"
"""
from __future__ import annotations

import argparse
import sys

from core.app import App
from core.engine import AgentUnavailable, Engine

def main(argv=None):
    p = argparse.ArgumentParser(description="London Office Market Agent")
    p.add_argument("command", choices=["refresh", "gather", "process", "chat", "ask", "brief", "signals", "ingest", "classify",
                                       "housekeep"])
    p.add_argument("text", nargs="?", help="question, file path or headline")
    p.add_argument("--user", default="cli", help="your name, for your own focus and team activity")
    p.add_argument("--pptx", action="store_true", help="brief: build the PowerPoint deck instead of printing markdown")
    p.add_argument("--theme", help="brief --pptx: navy-gold, editorial-cream, data-white, charcoal-amber or forest-cream")
    p.add_argument("--fixed", action="store_true", help="brief --pptx: skip the Copilot, rule-picked storyline only")
    p.add_argument("--save", action="store_true", help="ingest: store the extracted figures")
    p.add_argument("--offline", action="store_true", help="skip live connectors")
    a = p.parse_args(argv)

    app = App(live=not a.offline)
    if a.command == "refresh":
        for r in app.refresh():
            print(f"{r['connector']:>16}: {r.get('error') or r['counts']}")
        return
    if a.command == "housekeep":  # the daily tidy-up: states advance, live stories re-scored, today's digest
        from core.lifecycle import housekeep
        res = housekeep(app.store, app.config)
        moved = ", ".join(f"{n} {s}" for s, n in sorted(res["moved"].items())) or "nothing moved"
        print(f"housekeep: {moved}; digest of {len(res['digest']['picked'])} picks, "
              f"{sum(res['digest']['folded'].values())} folded")
        return
    app.ensure_data()
    try:
        return run(app, a)
    except AgentUnavailable as e:
        print(e)
        return 1


def show(ans):
    print(ans.text, f"\n\n[{ans.engine}; tools: {', '.join(t['tool'] for t in ans.trace) or 'none'}]")


def run(app, a):
    if a.command == "process":
        return show(Engine(app).gather(a.user, a.text or ""))
    if a.command == "gather":
        return show(Engine(app).gather(a.user if a.user != "cli" else "scheduler"))
    if a.command == "brief":
        if a.pptx:
            if not a.fixed:
                try:  # the Copilot plans the deck from this week's data; rules only when Pi is not running
                    built, ans = Engine(app).build_deck(a.theme, a.user)
                    if built:
                        print(ans.text)
                        print(f"Deck saved at {built['path']} (storyline by the Copilot)")
                        return 0
                    print("The Copilot did not produce a deck; falling back to the rule-picked storyline.")
                except AgentUnavailable as e:
                    print(f"Fallback, rule-picked storyline: {e}")
            out = app.call("build_brief_pptx", {"theme": a.theme}, a.user)
            print(out["summary"])
            return 0 if out["data"].get("path") else 1
        print(app.call("generate_brief", {}, a.user)["summary"])
    elif a.command == "signals":
        print(app.call("get_signals", {"limit": 8}, a.user)["summary"])
    elif a.command == "ingest":
        print(app.call("ingest_report", {"path": a.text, "save": a.save}, a.user)["summary"])
    elif a.command == "classify":
        print(app.call("classify_text", {"title": a.text or ""}, a.user)["summary"])
    elif a.command == "ask":
        show(Engine(app).ask(a.text or "", a.user))
    else:
        engine = Engine(app)
        engine._check()
        print(f"London Office Market Agent - {app.config['team']['name']}. Engine: {engine.status}")
        print("Try: " + " | ".join(app.config["team"]["questions"][:3]) + "\nType 'quit' to exit.\n")
        while True:
            try:
                q = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if q.lower() in ("quit", "exit"):
                break
            if not q:
                continue
            ans = engine.ask(q, a.user)
            print(f"\nagent> {ans.text}\n  [{ans.engine}; tools: {', '.join(t['tool'] for t in ans.trace) or 'none'}]\n")


if __name__ == "__main__":
    sys.exit(main())
