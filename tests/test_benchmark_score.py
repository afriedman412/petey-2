"""The flat-structure benchmark's key and scorer (eval/benchmark_key.py, eval/benchmark_score.py; 2026-10-30)."""
import benchmark_key as K
import benchmark_score as S


def _page():
    """A date in three boxes (one value), a name line, a Yes / No group, a 2 x 2 grid of text, two block copies."""
    return {"fields": [{"id": "m", "rect": [100, 100, 120, 112], "kind": "text"},
                       {"id": "d", "rect": [122, 100, 142, 112], "kind": "text"},
                       {"id": "y", "rect": [144, 100, 184, 112], "kind": "text"},
                       {"id": "nm", "rect": [100, 130, 300, 142], "kind": "text"},
                       {"id": "yes", "rect": [100, 160, 108, 168], "kind": "choice"},
                       {"id": "no", "rect": [130, 160, 138, 168], "kind": "choice"},
                       {"id": "a1", "rect": [100, 200, 150, 212], "kind": "text"},
                       {"id": "a2", "rect": [160, 200, 210, 212], "kind": "text"},
                       {"id": "b1", "rect": [100, 220, 150, 232], "kind": "text"},
                       {"id": "b2", "rect": [160, 220, 210, 232], "kind": "text"},
                       {"id": "c1", "rect": [100, 300, 200, 312], "kind": "text"},
                       {"id": "c2", "rect": [100, 320, 200, 332], "kind": "text"},
                       {"id": "e1", "rect": [300, 300, 400, 312], "kind": "text"},
                       {"id": "e2", "rect": [300, 320, 400, 332], "kind": "text"}],
            "groups": [["m", "d", "y"], ["yes", "no"]],
            "grids": [{"cells": [{"field": "a1", "row": 1, "col": 1}, {"field": "a2", "row": 1, "col": 2},
                                 {"field": "b1", "row": 2, "col": 1}, {"field": "b2", "row": 2, "col": 2}]}],
            "blocks": [{"cells": [{"field": "c1", "copy": 0, "slot": 0}, {"field": "c2", "copy": 0, "slot": 1},
                                  {"field": "e1", "copy": 1, "slot": 0}, {"field": "e2", "copy": 1, "slot": 1}]}]}


def _f1(c, rel):
    return c[f"{rel}_tp"] == c[f"{rel}_tp"] + c[f"{rel}_fp"] == c[f"{rel}_tp"] + c[f"{rel}_fn"]


class TestScore:
    def test_key_against_itself_is_perfect(self):
        k = _page()
        c = S.score_page(k, k)
        assert c["text_hit"] == c["text_key"] == 10 and c["choice_hit"] == 2
        assert c["field_hit"] == 14 and c["kind_right"] == 14
        assert c["group_exact"] == c["group_key"] == 1 and c["grid_exact"] == 1 and c["block_exact"] == 1
        for rel in ("group", "row", "col", "copy", "slot"):
            assert _f1(c, rel)
        assert c["row_tp"] == 2 and c["col_tp"] == 2 and c["copy_tp"] == 2 and c["slot_tp"] == 2

    def test_one_box_over_the_whole_date_is_the_same_value(self):
        k = _page()
        p = _page()
        p["fields"] = [f for f in p["fields"] if f["id"] not in ("m", "d", "y")] + \
            [{"id": "date", "rect": [100, 100, 184, 112], "kind": "text"}]
        p["groups"] = [["yes", "no"]]
        c = S.score_page(k, p)
        assert c["text_hit"] == c["text_key"] == 10
        assert c["field_hit"] == 11                  # box to box, the three parts are not found one by one

    def test_date_parts_found_but_not_joined_miss_the_value(self):
        k = _page()
        p = _page()
        p["groups"] = [["yes", "no"]]
        c = S.score_page(k, p)
        assert c["text_hit"] == 9 and c["text_found"] == 12
        assert c["field_hit"] == 14

    def test_loose_choice_boxes_lose_the_group(self):
        k = _page()
        p = _page()
        p["groups"] = [["m", "d", "y"]]
        c = S.score_page(k, p)
        assert c["choice_hit"] == 2 and c["group_fn"] == 1 and c["group_tp"] == 0 and c["group_exact"] == 0

    def test_grid_with_rows_swapped_for_columns_scores_the_mixup(self):
        k = _page()
        p = _page()
        p["grids"] = [{"cells": [{"field": x["field"], "row": x["col"], "col": x["row"]}
                                 for x in k["grids"][0]["cells"]]}]
        c = S.score_page(k, p)
        assert c["row_tp"] == 0 and c["row_fp"] == 2 and c["row_fn"] == 2 and c["grid_exact"] == 0

    def test_relations_count_only_among_found_units(self):
        k = _page()
        p = _page()
        p["fields"] = [f for f in p["fields"] if f["id"] != "b2"]
        p["grids"] = [{"cells": [x for x in k["grids"][0]["cells"] if x["field"] != "b2"]}]
        c = S.score_page(k, p)
        assert c["row_fn"] == 0 and c["col_fn"] == 0 and c["row_tp"] == 1
        assert c["grid_exact"] == 0                  # a unit missed: not rebuilt

    def test_box_drawn_off_by_a_little_still_matches(self):
        k = _page()
        p = _page()
        p["fields"] = [{**f, "rect": [f["rect"][0] + 2, f["rect"][1], f["rect"][2] + 2, f["rect"][3] + 1]}
                       for f in p["fields"]]
        c = S.score_page(k, p)
        assert c["field_hit"] == 14

    def test_no_prediction_scores_zero(self):
        c = S.score_page(_page(), None)
        assert c["text_hit"] == 0 and c["text_key"] == 10 and c["grid_exact"] == 0


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
                                                               "widget_type": "text"}},
        "r1": {"x_petey_id": "6", "type": "string", "widget": {"page": 2, "rect": [10, 100, 50, 110]}},
        "r2": {"x_petey_id": "7", "type": "string", "widget": {"page": 2, "rect": [10, 120, 50, 130]}},
        "z": {"x_petey_id": "8", "type": "string", "widget": {"page": 3, "rect": [10, 120, 50, 130]}}}}

    def test_kinds_groups_and_split_fields(self):
        keys = K.page_keys(self.BP, entities=[{"fields": ["4", "5"]}])
        kinds = {f["id"]: f["kind"] for f in keys[1]["fields"]}
        assert kinds == {"1.yes": "choice", "1.no": "choice", "2": "choice", "3": "text"}
        assert keys[1]["groups"] == [["1.yes", "1.no"]]
        assert keys[2]["groups"] == [["4", "5"]]

    def test_grids_by_name_and_blocks_need_two_copies_on_the_page(self):
        grids = [{"grid": [{"name": "r1", "row": 1, "col": 1}, {"name": "r2", "row": 2, "col": 1}]}]
        types = [{"blocks": [["6"], ["8"]]}, {"blocks": [["6", None], ["7", None]]}]
        keys = K.page_keys(self.BP, grids=grids, types=types)
        assert keys[2]["grids"] == [{"cells": [{"field": "6", "row": 1, "col": 1},
                                               {"field": "7", "row": 2, "col": 1}]}]
        assert keys[2]["blocks"] == [{"cells": [{"field": "6", "copy": 0, "slot": 0},
                                                {"field": "7", "copy": 1, "slot": 0}]}]
        assert keys[3]["blocks"] == []

    def test_key_built_from_a_blueprint_scores_perfect_against_itself(self):
        keys = K.page_keys(self.BP, entities=[{"fields": ["4", "5"]}],
                           grids=[{"grid": [{"name": "r1", "row": 1, "col": 1}, {"name": "r2", "row": 2, "col": 1}]}])
        for k in keys.values():
            c = S.score_page(k, k)
            assert c["text_hit"] == c["text_key"] and c["choice_hit"] == c["choice_key"]
            assert c["grid_exact"] == c["grid_key"]
