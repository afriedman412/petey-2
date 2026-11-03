"""Duplicate pages and forms from the page inventory (eval/page_dups.py, Andrew 2026-10-31)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
import page_dups as pd  # noqa: E402

INKED = "f" * 16 + "0" * 48                      # 64 bits set of 256: a page with something drawn on it


def _p(page=1, words=(), dhash=INKED, sha=None):
    words = list(words)
    return {"page": page, "n_words": len(words), "words_sha": sha or str(hash(tuple(words))), "vocab": sorted(set(words)),
            "dhash": dhash}


def _flip(h, n):                                  # n bits of the hash flipped
    return f"{int(h, 16) ^ ((1 << n) - 1):064x}"


def test_same_words_same_page():
    w = [f"w{i}" for i in range(30)]
    assert pd.same_page(_p(words=w), _p(words=w, dhash=_flip(INKED, 200)))


def test_alike_and_mostly_the_same_words():
    w = [f"w{i}" for i in range(100)]
    assert pd.same_page(_p(words=w), _p(words=w[:95] + ["2024", "rev", "x", "y", "z"], dhash=_flip(INKED, 30)))
    assert not pd.same_page(_p(words=w), _p(words=w[:50] + [f"v{i}" for i in range(50)], dhash=_flip(INKED, 30)))


def test_looking_the_same_needs_ink_and_about_as_many_words():
    w = [f"w{i}" for i in range(100)]
    garbled = [f"g{i}" for i in range(100)]
    assert pd.same_page(_p(words=w), _p(words=garbled, dhash=_flip(INKED, 5)))
    assert not pd.same_page(_p(words=w), _p(words=garbled[:50], dhash=_flip(INKED, 5)))
    empty = "0" * 64
    assert not pd.same_page(_p(dhash=empty), _p(dhash=empty))          # near-empty pages all look alike


def test_forms_join_only_when_every_page_matches(tmp_path):
    w1, w2, w3 = ([f"{k}{i}" for i in range(40)] for k in "abc")
    other = "0" * 32 + "f" * 16 + "0" * 16                             # page 2 drawn elsewhere than page 1
    blanks = [{"blank": "A", "pdf": "a.pdf", "pages": [_p(1, w1), _p(2, w2, dhash=other)]},
              {"blank": "B", "pdf": "b.pdf", "pages": [_p(1, w1), _p(2, w2, dhash=other)]},
              {"blank": "C", "pdf": "c.pdf", "pages": [_p(1, w1), _p(2, w3, dhash=_flip(other, 120))]}]
    (tmp_path / "pages.jsonl").write_text("\n".join(map(json.dumps, blanks)))
    (tmp_path / "forms.json").write_text(json.dumps({"lib__a": "A", "bm__b": "B", "bm__c": "C", "je__a": "A"}))
    out = pd.find(tmp_path)
    assert out["forms"] == [["bm__b", "je__a", "lib__a"]]
    assert out["pages"] == [[["bm__b", 1], ["bm__c", 1], ["lib__a", 1]]]   # page 1 shared with bm__c; one id a blank
