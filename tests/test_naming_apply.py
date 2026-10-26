"""eval/naming_apply_2026_10_26.py (Andrew, 2026-10-26: "let's just rename everything"): parts that print the name are
left; parts that no longer do (a name changed by hand since 2026-10-24) are read again from the name, which wins; a
rename onto a name another field has or gets is left out; flagged readings are written too."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
import naming_apply_2026_10_26 as NA  # noqa: E402


def test_plan(monkeypatch):
    fields = {
        "tooth_nbr_1": {"x_petey_identifiers": {"subject": "tooth", "suffix": "nbr", "iteration": "1"}},   # left
        "plaintiff_2_nm": {"x_petey_identifiers": {"subject": "group_p2", "iteration": "2"}},             # stale
        "tooth_2_nbr": {},                                                                                 # new
        "a_1_txt": {}, "a_txt_1": {},                                                                      # clash
        "b_1_amt": {},                                                                                     # flagged
    }
    read = {"plaintiff_2_nm": ({"subject": "plaintiff", "suffix": "nm", "iteration": "2"}, []),
            "tooth_2_nbr": ({"subject": "tooth", "suffix": "nbr", "iteration": "2"}, []),
            "a_1_txt": ({"subject": "a", "suffix": "txt", "iteration": "1"}, []),
            "a_txt_1": ({"subject": "a", "suffix": "txt", "iteration": "1"}, []),
            "b_1_amt": ({"subject": "b", "suffix": "amt", "iteration": "1"}, ["2 numbers vary: which one iterates?"])}
    monkeypatch.setattr(NA.FI, "read_form", lambda bid, bp: read)
    ren, ids, n = NA.plan("t", {"fields": fields})
    assert "tooth_nbr_1" not in ids and n["kept"] == 1
    assert ids["plaintiff_2_nm"]["subject"] == "plaintiff" and ren["plaintiff_2_nm"] == "plaintiff_nm_2" and n["stale"] == 1
    assert ren["tooth_2_nbr"] == "tooth_nbr_2"
    assert "a_1_txt" not in ren and n["clash"] == 1         # a_txt_1 is another field's name
    assert ren["b_1_amt"] == "b_amt_1" and n["flagged"] == 1


def test_reread_takes_only_unflagged_readings_that_move_the_number(monkeypatch):
    """2026-10-26 (Andrew: "go for it"): grid cells the identifier reading now places are renamed when the same words
    print with the number moved; a reading that changes words, is flagged, or lands on another field's name is left."""
    read = {"csl_premium_1_amt": ({"subject": "csl_premium", "suffix": "amt", "iteration": "1"}, []),
            "weight_lbs_txt_1": ({"subject": "weight_lbs", "suffix": "txt", "part": "1"}, []),          # same name
            "plan_1_name": ({"subject": "plan", "suffix": "nm", "iteration": "1"}, []),                  # words change
            "x_1_amt": ({"subject": "x", "suffix": "amt", "iteration": "1"}, ["2 numbers vary"]),        # flagged
            "y_1_amt": ({"subject": "y", "suffix": "amt", "iteration": "1"}, [])}                        # clash
    monkeypatch.setattr(NA.FI, "read_form", lambda bid, bp: read)
    fields = {n: {} for n in read} | {"y_amt_1": {}}
    ren, ids = NA.reread("t", {"fields": fields})
    assert ren == {"csl_premium_1_amt": "csl_premium_amt_1"} and ids["csl_premium_1_amt"]["iteration"] == "1"
