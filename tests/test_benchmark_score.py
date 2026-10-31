"""The flat-structure benchmark's key and scorer (eval/benchmark_key.py, eval/benchmark_score.py; 2026-10-30): fields
found, typed right, grouped, splits combined."""
import benchmark_key as K
import benchmark_score as S


def _page():
    """A date in three boxes (one value), a name line, a Yes / No group, a lone checkbox."""
    return {"fields": [{"id": "m", "rect": [100, 100, 120, 112], "kind": "text"},
                       {"id": "d", "rect": [122, 100, 142, 112], "kind": "text"},
                       {"id": "y", "rect": [144, 100, 184, 112], "kind": "text"},
                       {"id": "nm", "rect": [100, 130, 300, 142], "kind": "text"},
                       {"id": "yes", "rect": [100, 160, 108, 168], "kind": "choice"},
                       {"id": "no", "rect": [130, 160, 138, 168], "kind": "choice"},
                       {"id": "x", "rect": [100, 200, 108, 208], "kind": "choice"}],
            "groups": [["m", "d", "y"], ["yes", "no"]]}


class TestScore:
    def test_key_against_itself_is_perfect(self):
        k = _page()
        c = S.score_page(k, k)
        assert c["found_hit"] == c["found_key"] == c["found_found"] == 5 and c["kind_right"] == 5
        assert c["group_tp"] == 1 and c["group_fp"] == c["group_fn"] == 0 and c["group_exact"] == c["group_key"] == 1
        assert c["split_hit"] == c["split_key"] == 1 and c["split_found_hit"] == c["split_found"] == 1

    def test_one_box_over_the_whole_date_is_the_same_value(self):
        k = _page()
        p = _page()
        p["fields"] = [f for f in p["fields"] if f["id"] not in ("m", "d", "y")] + \
            [{"id": "date", "rect": [100, 100, 184, 112], "kind": "text"}]
        p["groups"] = [["yes", "no"]]
        c = S.score_page(k, p)
        assert c["found_hit"] == 5 and c["split_hit"] == 1 and c["split_found"] == 0

    def test_date_parts_found_but_not_combined_miss_the_value(self):
        k = _page()
        p = _page()
        p["groups"] = [["yes", "no"]]
        c = S.score_page(k, p)
        assert c["found_hit"] == 4 and c["found_found"] == 7 and c["split_hit"] == 0

    def test_combining_two_separate_answers_is_not_a_split(self):
        k = _page()
        p = _page()
        p["groups"] = [["m", "d", "y", "nm"], ["yes", "no"]]
        c = S.score_page(k, p)
        assert c["split_found"] == 1 and c["split_found_hit"] == 0 and c["split_hit"] == 0

    def test_loose_choice_boxes_lose_the_group(self):
        k = _page()
        p = _page()
        p["groups"] = [["m", "d", "y"]]
        c = S.score_page(k, p)
        assert c["found_hit"] == 5 and c["group_fn"] == 1 and c["group_tp"] == 0 and c["group_exact"] == 0

    def test_a_group_with_an_extra_box_is_not_rebuilt_exactly(self):
        k = _page()
        p = _page()
        p["groups"] = [["m", "d", "y"], ["yes", "no", "x"]]
        c = S.score_page(k, p)
        assert c["group_tp"] == 1 and c["group_fp"] == 2 and c["group_exact"] == 0

    def test_wrong_kind_is_found_but_typed_wrong(self):
        k = _page()
        p = _page()
        p["fields"] = [{**f, "kind": "text"} if f["id"] == "x" else f for f in p["fields"]]
        c = S.score_page(k, p)
        assert c["found_hit"] == 5 and c["kind_right"] == 4

    def test_box_drawn_off_by_a_little_still_matches(self):
        k = _page()
        p = _page()
        p["fields"] = [{**f, "rect": [f["rect"][0] + 1, f["rect"][1], f["rect"][2] + 1, f["rect"][3] + 1]}
                       for f in p["fields"]]
        assert S.score_page(k, p)["found_hit"] == 5

    def test_no_prediction_scores_zero(self):
        c = S.score_page(_page(), None)
        assert c["found_hit"] == 0 and c["found_key"] == 5 and c["split_key"] == 1


class TestKey:
    BP = {"fields": {
        "yn": {"x_petey_id": "1", "type": "category", "widgets": {
            "yes": {"page": 1, "rect": [10, 10, 18, 18], "widget_type": "checkbox"},
            "no": {"page": 1, "rect": [30, 10, 38, 18], "widget_type": "checkbox"}}},
        "xbox": {"x_petey_id": "2", "type": "boolean", "widget": {"page": 1, "rect": [50, 10, 58, 18],
                                                                  "widget_type": "text"}},
        "sig": {"x_petey_id": "3", "type": "string", "widget": {"page": 1, "rect": [10, 50, 200, 70],
                                                                "widget_type": "signature"}},
        "mm": {"x_petey_id": "4", "type": "string", "widget": {"page": 2, "rect": [10, 10, 30, 20],
                                                               "widget_type": "text"}},
        "dd": {"x_petey_id": "5", "type": "string", "widget": {"page": 2, "rect": [32, 10, 52, 20],
                                                               "widget_type": "text"}}}}

    def test_kinds_groups_and_split_fields(self):
        keys = K.page_keys(self.BP, entities=[{"fields": ["4", "5"]}])
        kinds = {f["id"]: f["kind"] for f in keys[1]["fields"]}
        assert kinds == {"1.yes": "choice", "1.no": "choice", "2": "choice", "3": "text"}
        assert keys[1]["groups"] == [["1.yes", "1.no"]]
        assert keys[2]["groups"] == [["4", "5"]]

    def test_key_built_from_a_blueprint_scores_perfect_against_itself(self):
        for k in K.page_keys(self.BP, entities=[{"fields": ["4", "5"]}]).values():
            c = S.score_page(k, k)
            assert c["found_hit"] == c["found_key"] and c["kind_right"] == c["found_hit"]
            assert c["split_hit"] == c["split_key"]


class TestLightPrediction:
    def test_light_path_blueprint_becomes_a_prediction_with_its_splits(self):
        import benchmark_light as L
        bp = {"fields": {
            "p1_o1": {"x_petey_id": "1", "type": "category", "widgets": {
                "opt1": {"page": 1, "rect": [10, 10, 18, 18], "widget_type": "checkbox"},
                "opt2": {"page": 1, "rect": [30, 10, 38, 18], "widget_type": "checkbox"}}},
            "p1_f1": {"x_petey_id": "2", "type": "string", "widget": {"page": 1, "rect": [10, 40, 30, 50],
                                                                      "widget_type": "text"}},
            "p1_f2": {"x_petey_id": "3", "type": "string", "widget": {"page": 1, "rect": [32, 40, 52, 50],
                                                                      "widget_type": "text"}},
            "p1_f3": {"x_petey_id": "4", "type": "boolean", "widget": {"page": 1, "rect": [60, 40, 68, 48],
                                                                       "widget_type": "checkbox"}}}}
        p = L.to_prediction(bp, [{"fields": ["2", "3"]}])
        assert {f["id"]: f["kind"] for f in p["fields"]} == {"p1_o1.opt1": "choice", "p1_o1.opt2": "choice",
                                                             "p1_f1": "text", "p1_f2": "text", "p1_f3": "choice"}
        assert p["groups"] == [["p1_o1.opt1", "p1_o1.opt2"], ["p1_f1", "p1_f2"]]
        assert L.to_prediction(bp)["groups"] == [["p1_o1.opt1", "p1_o1.opt2"]]


class TestPrinted:
    """The third field type (Andrew, 2026-10-31): printed = expected to be hand-written (signatures, initials,
    printed names)."""

    @staticmethod
    def _signed():
        k = _page()
        k["fields"].append({"id": "sig", "rect": [100, 240, 300, 256], "kind": "printed"})
        return k

    def test_key_against_itself_types_the_signature_printed(self):
        c = S.score_page(self._signed(), self._signed())
        assert c["kind_right"] == c["found_hit"] == 6
        assert c["type_printed_key"] == c["type_printed_found"] == c["type_printed_hit"] == 1
        assert c["type_text_key"] == 2 and c["type_choice_key"] == 3

    def test_a_signature_found_as_text_is_found_but_typed_wrong(self):
        p = self._signed()
        p["fields"] = [{**f, "kind": "text"} if f["id"] == "sig" else f for f in p["fields"]]
        c = S.score_page(self._signed(), p)
        assert c["found_hit"] == 6 and c["kind_right"] == 5
        assert c["type_printed_hit"] == 0 and c["type_printed_found"] == 0 and c["type_text_found"] == 3

    def test_printed_fields_in_a_group_make_one_printed_value(self):
        k = self._signed()
        k["fields"].append({"id": "sig2", "rect": [302, 240, 400, 256], "kind": "printed"})
        k["groups"].append(["sig", "sig2"])
        c = S.score_page(k, k)
        assert c["type_printed_key"] == 1 and c["split_key"] == 2 and c["split_hit"] == 2

    def test_report_has_a_line_a_type(self):
        lines = S.report(S.score_page(self._signed(), self._signed()))
        assert sum(ln.strip().startswith(("text ", "choice ", "printed ")) for ln in lines) == 3

    def test_key_marks_only_text_fields_printed(self):
        k = K.mark_printed(_page(), {"nm", "x"})
        assert {f["id"]: f["kind"] for f in k["fields"]}["nm"] == "printed"
        assert {f["id"]: f["kind"] for f in k["fields"]}["x"] == "choice"


class TestPrintedRecord:
    def test_confirm_writes_the_page_and_refuses_choice_boxes(self, tmp_path):
        import json

        import pytest

        from petey.validate import printed_fields as pf
        (tmp_path / "bm__x__p1.json").write_text(json.dumps(_page()))
        rec = tmp_path / "field_types.json"
        assert pf.printed_ids("bm__x__p1", pf.load(rec)) is None
        pf.confirm("bm__x__p1", ["nm"], record=rec, key_dir=tmp_path)
        assert pf.printed_ids("bm__x__p1", pf.load(rec)) == {"nm"}
        pf.confirm("bm__x__p1", [], record=rec, key_dir=tmp_path)
        assert pf.printed_ids("bm__x__p1", pf.load(rec)) == set()
        with pytest.raises(ValueError):
            pf.confirm("bm__x__p1", ["yes"], record=rec, key_dir=tmp_path)


class TestPrintedCandidates:
    def test_caption_words_beside_and_below(self):
        import benchmark_printed as P
        words = [(20, 100, 80, 110, "Signature"), (100, 125, 160, 135, "Printed"), (162, 125, 200, 135, "Name"),
                 (20, 160, 80, 170, "Middle"), (82, 160, 120, 170, "Initial")]
        assert P.SAYS.search(P.caption(words, [90, 98, 300, 112]))          # on its line, to the left
        assert P.SAYS.search(P.caption(words, [100, 110, 300, 122]))        # the words just below
        assert not P.SAYS.search(P.caption(words, [130, 158, 200, 172]))    # "Middle Initial" is not initials

    def test_names(self):
        import benchmark_printed as P
        assert P.name_says("applicant_signature") and P.name_says("witness_printed_nm") and P.name_says("initials")
        assert not P.name_says("signature_dt") and not P.name_says("spouse_middle_initial")
        assert not P.name_says("p2_f24")
