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

    def test_a_text_box_on_the_line_matches_a_taller_key_box(self):
        """2026-11-02, question 15: a text field's height is arbitrary; the band on the line (overlap 0.42) is the
        answer, and the plain overlap count is kept alongside."""
        k = {"fields": [{"id": "a", "rect": [100, 100, 300, 124], "kind": "text"}], "groups": []}
        p = {"fields": [{"id": "a", "rect": [100, 114, 300, 124], "kind": "text"}], "groups": []}
        c = S.score_page(k, p)
        assert c["found_hit"] == 1 and c["found_hit_iou"] == 0

    def test_either_way_around_a_caption_in_the_box_matches(self):
        """A caption in a drawn box's top-left corner: the band below it or the band beside it are both the answer."""
        k = {"fields": [{"id": "a", "rect": [0, 0, 50, 30], "kind": "text"}], "groups": []}
        for band in ([0, 10, 50, 30], [38, 0, 50, 30]):
            p = {"fields": [{"id": "b", "rect": band, "kind": "text"}], "groups": []}
            assert S.score_page(k, p)["found_hit"] == 1

    def test_a_box_on_another_line_does_not_match(self):
        k = {"fields": [{"id": "a", "rect": [100, 100, 300, 112], "kind": "text"}], "groups": []}
        p = {"fields": [{"id": "b", "rect": [100, 108, 300, 132], "kind": "text"}], "groups": []}
        assert S.score_page(k, p)["found_hit"] == 0

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

    def test_types_follow_the_page(self):
        """2026-11-01: what looks like a checkbox is one (a Y / N text box, an option group drawn as text boxes);
        comb cells, a text group's boxes and printed fields keep their type."""
        def t(code, rect, **kw):
            return {"x_petey_id": code, "type": "string", "widget": {"page": 1, "rect": rect, "widget_type": "text"},
                    **kw}
        fields = {
            "yn": t("1", [10, 10, 20, 20]),                                   # a lone Y / N box
            "opts": {"x_petey_id": "2", "type": "category", "widgets": {      # options drawn as text widgets
                "a": {"page": 1, "rect": [10, 40, 30, 50], "widget_type": "text"},
                "b": {"page": 1, "rect": [40, 40, 60, 50], "widget_type": "text"}}},
            "c1": t("3", [100, 100, 110, 110]), "c2": t("4", [110, 100, 120, 110]),   # a comb of three cells
            "c3": t("5", [120.5, 100, 130.5, 110]),
            "mm": t("6", [10, 200, 20, 210]), "dd": t("7", [30, 200, 40, 210]),       # a date in two boxes
            "ini": t("8", [10, 300, 20, 310], x_petey_printed={"source": "review"}),  # an initials box
            "name": t("9", [10, 400, 200, 412])}
        k = K.page_keys({"fields": fields}, entities=[{"fields": ["6", "7"]}])[1]
        assert {f["id"]: f["kind"] for f in k["fields"]} == {
            "1": "choice", "2.a": "choice", "2.b": "choice", "3": "text", "4": "text", "5": "text",
            "6": "text", "7": "text", "8": "printed", "9": "text"}

    def test_checkboxes_spaced_along_a_line_are_not_a_comb(self):
        rects = {"a": [10, 10, 20, 20], "b": [40, 10, 50, 20], "c": [70, 10, 80, 20]}
        assert K.comb_cells(rects) == set()
        assert K.comb_cells({**rects, "d": [20, 10, 30, 20], "e": [30.5, 10, 40, 20]}) == {"a", "d", "e", "b"}

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

    def test_key_types_tagged_text_fields_printed(self):
        sig = {"x_petey_id": "1_1", "type": "string", "x_petey_printed": {"source": "review"},
               "widget": {"page": 1, "rect": [0, 0, 100, 12], "widget_type": "text"}}
        box = {"x_petey_id": "1_2", "type": "boolean", "x_petey_printed": {"source": "review"},
               "widget": {"page": 1, "rect": [0, 20, 8, 28], "widget_type": "checkbox"}}
        nm = {"x_petey_id": "1_3", "type": "string", "widget": {"page": 1, "rect": [0, 40, 100, 52], "widget_type": "text"}}
        k = K.page_keys({"fields": {"sig": sig, "box": box, "nm": nm}})[1]
        assert {f["id"]: f["kind"] for f in k["fields"]} == {"1_1": "printed", "1_2": "choice", "1_3": "text"}


class TestPrintedOnTheBlueprint:
    """Printed is stored on the field (Andrew, 2026-10-31: "printed types should move to blueprints, they are fields")."""

    def _setup(self, tmp_path, monkeypatch):
        import json

        import yaml

        from petey.validate import draft, field_ids
        bp = {"fields": {
            "sig": {"x_petey_id": "1_1", "type": "string", "widget": {"page": 1, "rect": [0, 0, 100, 12], "widget_type": "text"}},
            "nm": {"x_petey_id": "1_2", "type": "string", "widget": {"page": 1, "rect": [0, 20, 100, 32], "widget_type": "text"}},
            "yes": {"x_petey_id": "1_3", "type": "boolean", "widget": {"page": 1, "rect": [0, 40, 8, 48], "widget_type": "checkbox"}},
            "p2": {"x_petey_id": "2_1", "type": "string", "widget": {"page": 2, "rect": [0, 0, 100, 12], "widget_type": "text"}}}}
        real = tmp_path / "x.bpt"
        real.write_text(yaml.safe_dump(bp, sort_keys=False))
        key = {"form": "bm__x", "page": 1, "fields": [{"id": "1_1", "kind": "text"}, {"id": "1_2", "kind": "text"},
                                                      {"id": "1_3", "kind": "choice"}]}
        (tmp_path / "bm__x__p1.json").write_text(json.dumps(key))
        monkeypatch.setattr(draft, "DRAFTS", tmp_path / "drafts")
        moved = []
        monkeypatch.setattr(field_ids, "_rehash", lambda bid, old, new: moved.append((bid, old != new)) or [])
        return real, moved

    def test_the_sheet_writes_the_blueprint_and_its_records_follow(self, tmp_path, monkeypatch):
        import pytest
        import yaml

        from petey.validate import printed_fields as pf
        real, moved = self._setup(tmp_path, monkeypatch)
        rec = tmp_path / "field_types.json"
        out = pf.confirm("bm__x__p1", ["1_1"], record=rec, key_dir=tmp_path, real=real)
        assert out["printed"] == ["1_1"] and moved == [("bm__x", True)]
        f = yaml.safe_load(real.read_text())["fields"]
        assert f["sig"]["x_petey_printed"]["source"] == "printed_sheet" and "x_petey_printed" not in f["nm"]
        assert list(pf.load(rec)) == ["bm__x__p1"]
        out = pf.confirm("bm__x__p1", [], record=rec, key_dir=tmp_path, real=real)          # unmarked: taken off
        assert out["printed"] == [] and "x_petey_printed" not in yaml.safe_load(real.read_text())["fields"]["sig"]
        with pytest.raises(ValueError):
            pf.confirm("bm__x__p1", ["1_3"], record=rec, key_dir=tmp_path, real=real)    # a checkbox is never printed

    def test_the_review_tab_works_in_the_working_copy(self, tmp_path, monkeypatch):
        import pytest
        import yaml

        from petey.validate import draft
        from petey.validate import printed_fields as pf
        real, moved = self._setup(tmp_path, monkeypatch)
        before = real.read_text()
        assert pf.set_field("bm__x", "nm", True, real) == ["nm: printed (hand-written)"]
        assert real.read_text() == before                       # the blueprint waits for Save
        copy = draft.working("bm__x", real)
        assert copy != real and yaml.safe_load(copy.read_text())["fields"]["nm"]["x_petey_printed"]["source"] == "review"
        assert pf.set_field("bm__x", "nm", True, real) == []    # already printed: nothing
        with pytest.raises(ValueError):
            pf.set_field("bm__x", "yes", True, real)
        # with the copy open, the sheet writes into it too
        pf.confirm("bm__x__p1", ["1_1"], record=tmp_path / "r.json", key_dir=tmp_path, real=real)
        assert real.read_text() == before and moved == []
        assert pf.printed_on("bm__x", 1, real) == ["1_1"]


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


class TestTuningSet:
    """`benchmark_key.py --spare` (2026-11-03): the tuning set is the same forms' other pages, never the key's."""

    def test_spare_pages_are_the_ones_the_key_did_not_pick(self):
        keys = {pg: {"fields": [{}] * n} for pg, n in {1: 40, 2: 12, 3: 55, 4: 9, 5: 30}.items()}
        assert K.pick_pages(keys) == [3, 1]
        assert K.pick_pages(keys, spare=True) == [5, 2]            # page 4: under SPARE_MIN fields
        assert not set(K.pick_pages(keys)) & set(K.pick_pages(keys, spare=True))

    def test_light_runner_reads_and_writes_where_it_is_told(self, tmp_path, monkeypatch):
        import benchmark_light as BL
        import flat_light as FL
        from petey.validate import compound_values as cv
        key, out = tmp_path / "dev_key", tmp_path / "dev_pred"
        (key / "pages").mkdir(parents=True)
        (key / "pages" / "a__p1.pdf").write_bytes(b"")
        seen = {}
        bp = {"fields": {"p1_f1": {"type": "string", "x_petey_id": "1",
                                   "widget": {"page": 1, "rect": [1, 2, 30, 12], "widget_type": "text"},
                                   "x_petey_geometry": {"source": "finder", "jev_is_field": 0.9}}}}
        monkeypatch.setattr(FL, "build", lambda pdf, pid, workers: (seen.setdefault("pdf", pdf), (bp, {"tokens": 5,
                            "finder_boxes": 1, "kept": 1}))[1])
        monkeypatch.setattr(cv, "find", lambda b: [])
        r = BL.run_page("a__p1", key, out, keep=True)
        assert seen["pdf"] == key / "pages" / "a__p1.pdf" and r["tokens"] == 5
        assert (out / "light" / "a__p1.json").exists() and (out / "light_splits" / "a__p1.json").exists()
        kept = __import__("json").loads((out / "light_bp" / "a__p1.json").read_text())
        assert kept["fields"]["p1_f1"]["x_petey_geometry"]["jev_is_field"] == 0.9
