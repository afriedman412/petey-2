"""Hand-curated blank-PDF filename -> form_id map.

Lifted from petey-master/scripts/bootstrap_labeler.py (the script itself
stays behind). Used by backfill.py to seed aliases.
"""

KNOWN_PDF_TO_FORM_ID = {
    "f1040.pdf": "1040",
    "f1041.pdf": "form_1041",
    "f1065.pdf": "form_1065",
    "f1065sk1.pdf": "schedule_k_1",
    "schedule_k_1.pdf": "schedule_k_1",
    "f1098.pdf": "1098",
    "f1098t.pdf": "1098_t",
    "f1099b.pdf": "1099_b",
    "f1099div.pdf": "1099_div",
    "f1099g.pdf": "1099_g",
    "f1099int.pdf": "1099_int",
    "f1099k.pdf": "1099_k",
    "f1099msc.pdf": "1099_misc",
    "f1099r.pdf": "1099_r",
    "f1099s.pdf": "1099_s",
    "1099_nec_blank.pdf": "1099_nec",
    "f4868.pdf": "form_4868",
    "f941.pdf": "form_941",
    "fw2.pdf": "w_2",
    "fw9.pdf": "w_9",
    "acord25_blank.pdf": "acord_25",
    "cms1500_fillable.pdf": "cms_1500",
}
