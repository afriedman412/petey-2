"""The pre-commit hook refuses a commit that stages blueprints with anything
else; library-only and code-only commits go through."""
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / ".githooks" / "pre-commit"


def _repo(tmp_path):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("config", "core.hooksPath", str(HOOK.parent))
    (tmp_path / "blueprints").mkdir()
    return git


def _stage(tmp_path, git, *paths):
    for p in paths:
        (tmp_path / p).write_text(p)
        git("add", p)


def test_mixed_commit_refused(tmp_path):
    git = _repo(tmp_path)
    _stage(tmp_path, git, "blueprints/w9.bpt", "app.py")
    r = git("commit", "-q", "-m", "mixed")
    assert r.returncode != 0
    assert "app.py" in r.stderr
    assert git("rev-parse", "HEAD").returncode != 0  # nothing committed


def test_library_only_commit_allowed(tmp_path):
    git = _repo(tmp_path)
    _stage(tmp_path, git, "blueprints/w9.bpt", "blueprints/acord25.bpt")
    assert git("commit", "-q", "-m", "library").returncode == 0


def test_code_only_commit_allowed(tmp_path):
    git = _repo(tmp_path)
    _stage(tmp_path, git, "app.py", "README.md")
    assert git("commit", "-q", "-m", "code").returncode == 0


def test_deleting_a_blueprint_counts_as_library(tmp_path):
    git = _repo(tmp_path)
    _stage(tmp_path, git, "blueprints/w9.bpt")
    git("commit", "-q", "-m", "library")
    _stage(tmp_path, git, "app.py")
    git("rm", "-q", "blueprints/w9.bpt")
    assert git("commit", "-q", "-m", "mixed").returncode != 0
