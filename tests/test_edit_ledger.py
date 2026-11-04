"""The edit ledger credits a chat with the files that changed during its tool
calls, and nothing else; `who` lists the uncommitted files by chat."""
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "edit_ledger.py"


def _repo(tmp_path):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (tmp_path / "app.py").write_text("x")
    git("add", "app.py")
    git("commit", "-q", "-m", "init")
    return git


def _transcript(tmp_path, first, title=None):
    p = tmp_path / "chat.jsonl"
    lines = [json.dumps({"type": "user", "message": {"role": "user", "content": first}})]
    if title:
        lines.append(json.dumps({"type": "custom-title", "customTitle": title}))
    p.write_text("\n".join(lines) + "\n")
    return p


def _run(tmp_path, cmd, hook=None):
    env = {**os.environ, "PETEY_EDIT_LEDGER_ROOT": str(tmp_path)}
    return subprocess.run(
        [sys.executable, str(SCRIPT), cmd], cwd=tmp_path, env=env,
        input=json.dumps(hook) if hook else None, capture_output=True, text=True,
    )


def _ledger(tmp_path):
    p = tmp_path / "runs" / "edit_ledger" / "ledger.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_change_during_a_tool_call_is_credited_to_the_chat(tmp_path):
    _repo(tmp_path)
    hook = {"session_id": "abc12345-x", "transcript_path": str(_transcript(tmp_path, "wire the splits")),
            "tool_name": "Edit"}
    (tmp_path / "by_hand.py").write_text("andrew")  # before the call: not the chat's
    assert _run(tmp_path, "pre", hook).returncode == 0
    (tmp_path / "app.py").write_text("changed")
    (tmp_path / "new.py").write_text("new")
    assert _run(tmp_path, "post", hook).returncode == 0

    entries = _ledger(tmp_path)
    assert {e["file"] for e in entries} == {"app.py", "new.py"}
    assert all(e["session"] == "abc12345-x" and e["label"] == "wire the splits" for e in entries)

    out = _run(tmp_path, "who").stdout
    assert "wire the splits  [abc12345]" in out
    assert "by_hand.py" in out.split("no chat on record")[1]


def test_custom_title_wins_and_quiet_calls_log_nothing(tmp_path):
    _repo(tmp_path)
    hook = {"session_id": "s2", "transcript_path": str(_transcript(tmp_path, "hello", title="splits chat")),
            "tool_name": "Read"}
    _run(tmp_path, "pre", hook)
    _run(tmp_path, "post", hook)
    assert _ledger(tmp_path) == []
    (tmp_path / "app.py").write_text("z")
    _run(tmp_path, "pre", hook)
    (tmp_path / "app.py").write_text("zz")
    _run(tmp_path, "post", hook)
    assert _ledger(tmp_path)[-1]["label"] == "splits chat"


def test_post_without_pre_and_bad_input_never_fail(tmp_path):
    _repo(tmp_path)
    assert _run(tmp_path, "post", {"session_id": "s3"}).returncode == 0
    r = subprocess.run([sys.executable, str(SCRIPT), "pre"], cwd=tmp_path, input="not json",
                       capture_output=True, text=True, env={**os.environ, "PETEY_EDIT_LEDGER_ROOT": str(tmp_path)})
    assert r.returncode == 0
