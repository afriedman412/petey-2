"""Edit ledger: which chat changed which file.

Claude Code runs this before and after every tool call a chat makes (see
.claude/settings.json). Before the call it snapshots the modified / untracked
files and their modification times; after the call, every file that changed
during the call is written to runs/edit_ledger/ledger.jsonl with the chat's id
and a label (its custom title, else its first message). Files that change
while no tool is running (review-page saves, hand edits) get no owner.

    python3 scripts/edit_ledger.py who      # uncommitted files by chat

Never fails a tool call: every error is swallowed and exits 0.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("PETEY_EDIT_LEDGER_ROOT") or Path(__file__).resolve().parent.parent)
LEDGER_DIR = ROOT / "runs" / "edit_ledger"
LEDGER = LEDGER_DIR / "ledger.jsonl"
STATE_DIR = LEDGER_DIR / "state"
OWN_PREFIX = "runs/edit_ledger/"
LABEL_MAX = 80
LABEL_REFRESH_S = 600


def _dirty_files():
    """Modified, added, deleted and untracked paths, relative to ROOT."""
    out = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    paths = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip('"')
        if path.startswith(OWN_PREFIX):
            continue  # the ledger's own files
        paths.append(path)
    return paths


def _snapshot():
    snap = {}
    for p in _dirty_files():
        try:
            snap[p] = os.stat(ROOT / p).st_mtime_ns
        except FileNotFoundError:
            snap[p] = None  # deleted
    return snap


def _label_from_transcript(path):
    """The chat's custom title if it has one, else its first message."""
    title = first = None
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if '"custom-title"' in line:
                    try:
                        title = json.loads(line).get("customTitle") or title
                    except json.JSONDecodeError:
                        pass
                elif first is None and '"type":"user"' in line.replace(" ", ""):
                    try:
                        content = json.loads(line).get("message", {}).get("content")
                    except json.JSONDecodeError:
                        continue
                    if isinstance(content, list):
                        content = " ".join(b.get("text", "") for b in content
                                           if isinstance(b, dict) and b.get("type") == "text")
                    if isinstance(content, str) and content.strip() and not content.lstrip().startswith("<"):
                        first = " ".join(content.split())
    except OSError:
        return None
    label = title or first
    return label[:LABEL_MAX] if label else None


def _state_path(session):
    return STATE_DIR / f"{session}.json"


def _load_state(session):
    try:
        return json.loads(_state_path(session).read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(session, state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _state_path(session).write_text(json.dumps(state))


def pre(hook):
    session = hook.get("session_id") or "unknown"
    state = _load_state(session)
    now = time.time()
    if not state.get("label") or now - state.get("label_ts", 0) > LABEL_REFRESH_S:
        label = _label_from_transcript(hook.get("transcript_path", ""))
        if label:
            state["label"] = label
        state["label_ts"] = now
    state["snapshot"] = _snapshot()
    state["tool"] = hook.get("tool_name")
    _save_state(session, state)


def post(hook):
    session = hook.get("session_id") or "unknown"
    state = _load_state(session)
    before = state.pop("snapshot", None)
    if before is None:
        return
    after = _snapshot()
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    if changed:
        LEDGER_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().isoformat(timespec="seconds")
        with open(LEDGER, "a", encoding="utf-8") as fh:
            for p in changed:
                fh.write(json.dumps({
                    "ts": stamp, "session": session, "label": state.get("label"),
                    "file": p, "tool": hook.get("tool_name"),
                    "deleted": after.get(p) is None and p in before,
                }) + "\n")
    _save_state(session, state)


def owners():
    """{file: latest ledger entry} for the files that are uncommitted now."""
    latest = {}
    try:
        with open(LEDGER, encoding="utf-8") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                latest[e["file"]] = e
    except OSError:
        pass
    return {p: latest.get(p) for p in _dirty_files()}


def who():
    by_chat = {}
    for path, e in owners().items():
        key = (e["session"], e.get("label")) if e else None
        by_chat.setdefault(key, []).append((path, e))
    lines = []
    for key in sorted(by_chat, key=lambda k: (k is None, (k or ("", ""))[1] or "")):
        if key is None:
            lines.append("no chat on record (by hand, the review page, or before the ledger):")
        else:
            session, label = key
            lines.append(f'{label or "(no title)"}  [{session[:8]}]')
        for path, e in sorted(by_chat[key]):
            when = f"  {e['ts'][:16].replace('T', ' ')}" if e else ""
            lines.append(f"    {path}{when}")
    return "\n".join(lines) if lines else "nothing uncommitted"


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "who"
    if cmd == "who":
        print(who())
        return
    try:
        hook = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return
    {"pre": pre, "post": post}[cmd](hook)


if __name__ == "__main__":
    try:
        main(sys.argv)
    except Exception as exc:  # never block a tool call
        print(f"edit_ledger: {exc}", file=sys.stderr)
    sys.exit(0)
