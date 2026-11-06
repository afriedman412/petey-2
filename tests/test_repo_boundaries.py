"""The three parts of the repo stay apart (Andrew, 2026-11-05: split into the dataset with its runner, the web app,
and the petey package, which the app imports wholesale and which replaces petey on PyPI):

- the benchmark runner (the key builder, the scorer, the printed pass) reads the dataset through `petey_dataset` and
  never imports the petey package, so it can judge any method's predictions on its own;
- the petey package never imports the web app (`petey_review`: the review server and its page, hand_review, the page's
  own helpers, the extraction page);
- `petey_dataset` imports nothing from petey.
"""
import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = {"petey_review"}
RUNNER = ["benchmark_key", "benchmark_score", "benchmark_printed"]


def _modules(pkg: str):
    for p in sorted((ROOT / pkg).rglob("*.py")):
        if "review_app" in p.parts or "__pycache__" in p.parts:
            continue
        name = ".".join(p.relative_to(ROOT).with_suffix("").parts)
        yield name.removesuffix(".__init__"), p


def _imports(p: Path):
    """Every module an import statement in the file names, at any level."""
    tree = ast.parse(p.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
            for a in node.names:
                yield f"{node.module}.{a.name}"


def test_the_package_never_imports_the_app():
    crossings = [(name, m) for name, p in _modules("petey")
                 for m in _imports(p) if m in APP or any(m.startswith(a + ".") for a in APP)]
    assert crossings == []


def test_the_dataset_imports_nothing_from_petey():
    crossings = [(name, m) for name, p in _modules("petey_dataset") for m in _imports(p)
                 if m == "petey" or m.startswith("petey.")]
    assert crossings == []


def test_the_runner_imports_with_petey_blocked():
    code = f"""
import builtins, importlib, sys
sys.path[:0] = [{str(ROOT)!r}, {str(ROOT / 'eval')!r}]
real = builtins.__import__
def guard(name, *a, **k):
    if name == "petey" or name.startswith("petey."):
        raise ImportError("the runner imported " + name)
    return real(name, *a, **k)
builtins.__import__ = guard
for m in {RUNNER!r}:
    importlib.import_module(m)
"""
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
