"""The defect classes, as data rather than prose.

`OBSERVATIONS.md` carries the failure classes as numbered narrative and the
38 hand-classified candidates as a markdown table. Neither is readable by a
detector, so every pass has grown its own private vocabulary:
`cluster_misalignment.classify_issue` returns `compound_widget`,
`method_delta.classify` returns `substring`, `structural_defects` reports
class 12 and 13 by number, and `correct.py`'s guard counters invented three
more names today. The same defect therefore has up to four spellings and no
single place says which of them anything can fix.

This module is that place. Each class records what produces it, who owns
it, how it is found, and — the field that makes the cascade legible — which
tier resolves it.

## The tiers

    0  build       the labeler, before anything runs
    1  validate    fill -> extract -> score -> classify
    2  correct     edit the blueprint deterministically
    3  escalate    render the page and ask a VLM

A class whose `tier` is 0 is a labeler fix and no loop will correct it. A
class whose `tier` is 2 is correctable today. `tier: 3` is the residue that
genuinely needs the page, and keeping that set small is the whole argument
for the cascade: on the current corpus it is 4 widgets.

## Every class needs a DIAGNOSIS and a CORRECTION

A class with no detector is a story someone told once; a class with no fix is
a complaint. Both halves are required, and the table prints them side by side
so a missing one is visible rather than remembered:

    detector    how it is FOUND, mechanically
    fix         what repairs it, for forms produced from now on
    inline_fix  what repairs a blueprint ALREADY written

`--check` lists classes missing a diagnosis. `--gaps` lists classes missing a
retroactive correction. Both should be empty; neither is yet.

## An upstream fix does not repair what is already on disk

`tier: 0` means the labeler was changed so the defect stops being produced.
It says nothing about the 146 blueprints already written, which keep the
defect until someone acts on them — and the only alternatives are a full
relabel, which is paid and rewrites most field names, or an in-place
correction.

So every class carries `inline_fix` as well: the operation that repairs an
existing blueprint. Fixing a class upstream and leaving `inline_fix` empty
is not "done", it is done for future forms only, and
`defect_taxonomy.py --gaps` lists exactly those. Caption widgets stopped
being produced this session and 241 of them still sit in 31 blueprints.

## Whether validation can SEE the class at all

A detector is not the same thing as validation coverage. The loop has two
arms and they see different defects:

    native   reads each value back through the SAME AcroForm path the
             generator wrote it by. Grades the plumbing.
    petey    never sees the widget layer; finds each value on the page by
             the blueprint's own name and description.

Ground truth is keyed by AcroForm path, and the blueprint's binding decides
which ground-truth value a field is graded against. So under `native` alone a
wrong name REDEFINES the target instead of failing it — the arm that reports
95.1% agreement across 40,230 field-instances is structurally incapable of
seeing a misbinding. `petey` is the escape, and it has run on 74 of 796 cases.

`validation` records that, per class:

    native         the blind arm's own verdicts surface it
    petey          needs the meaning-based arm; native cancels it out
    external       VALIDATION-PROOF. No run of any arm reveals it; it takes
                   evidence from outside the loop — the publisher's AcroForm
                   name or tooltip, a VLM, or a person.
    self_scoring   WORSE than invisible: the loop scores it AGREE, so a
                   passing run is positive confirmation of the defect.

`--blind` lists the `external` and `self_scoring` classes. Those are the ones
where a green validation run means nothing, and they are the reason an agree
rate is never evidence on its own.

## `owner` is not `tier`

`owner` says whose mistake it is; `tier` says who can repair it. They
diverge often enough to be worth separating: `bad_ground_truth` is the
generator's mistake but nothing in the loop repairs it, and `ocr_garble` is
the parser's mistake that the SCORER should absorb.

Usage:
    python defect_taxonomy.py                 # the table
    python defect_taxonomy.py --check         # classes without a detector
    python defect_taxonomy.py --blind         # classes validation cannot see
    python defect_taxonomy.py --canon         # the reference case for each
    python defect_taxonomy.py --conflicts     # rules that fight, and the order
    python defect_taxonomy.py --tier 2
"""
from __future__ import annotations

import argparse
import collections
from dataclasses import dataclass, field as dc_field
from typing import Optional


@dataclass(frozen=True)
class DefectClass:
    name: str
    owner: str          # labeler | generator | blueprint | parser | scorer | reader
    tier: Optional[int]  # which tier repairs it; None = nothing does yet
    signature: str      # the gt / native / petey relationship that shows it
    fix: str            # what the repair actually is
    # Which arm of the validation loop can SEE this class. See the module
    # docstring: `external` means validation is structurally blind to it and
    # `self_scoring` means validation actively passes it.
    validation: Optional[str] = None
    detector: Optional[str] = None   # module that finds it, if any
    inline_fix: Optional[str] = None  # repairs blueprints ALREADY written
    # The reference case, as `form:field — what is observed`. A class
    # without one is how you end up writing a second rule for the same
    # defect: the next form that looks similar has nothing to be tested
    # against, so it gets its own rule. See --canon.
    canonical: Optional[str] = None
    # Classes whose repair pulls this field the OPPOSITE way. Two rules that
    # both fire on one field and disagree will oscillate: A moves it, B moves
    # it back, and each looks correct in isolation. Every pair listed here
    # must have a `precedence` saying which wins and why. See --conflicts.
    conflicts_with: tuple[str, ...] = ()
    precedence: Optional[str] = None
    aliases: tuple[str, ...] = ()    # other spellings in the codebase
    observations_class: Optional[str] = None   # OBSERVATIONS.md anchor
    notes: str = ""


REGISTRY: tuple[DefectClass, ...] = (

    # ---- name bound to the wrong widget -------------------------------
    # One mechanism, three shapes, distinguished by what the edge set
    # forms. Superseded `block_shift`, which named the spatial symptom and
    # could not see a rotation that crosses a page boundary.
    DefectClass(
        name="name_rotation",
        owner="labeler", tier=2,
        canonical="cf_1_fillable — a 4-long cycle spanning two pages, which is why the geometric pass cannot see it",
        validation="petey",
        signature="edges petey[A]==gt[path_B] close a cycle",
        fix="permute the widget blocks around the cycle",
        detector="correct.py",
        aliases=("block_shift", "reciprocal_swap", "sibling_swap"),
        observations_class="block_shift / class 13",
        inline_fix="permute the widget blocks around the cycle",
        notes="A total permutation: every name gets one widget, none is "
              "orphaned, so applying it is lossless. cf_1_fillable's cycle "
              "is 4 long and spans two pages, which is why the geometric "
              "pass in cluster_misalignment.py cannot find it.",
    ),
    DefectClass(
        name="name_slide",
        owner="labeler", tier=2,
        canonical="2022_rev_form_1014r:city_nm — its gt is an EMAIL; the chain slides email -> city -> state by one widget",
        validation="petey",
        signature="the same edges form an open chain",
        fix="rebind along the chain; the tail widget is orphaned",
        detector="correct.py; also publisher_name.py --types where it "
                 "contradicts a type_rejects_value field",
        aliases=("block_shift",),
        observations_class="block_shift",
        inline_fix="rebind along the chain; name the orphan from its path",
        notes="2022_rev_form_1014r slides four names down one widget: "
              "email_address_txt -> city_nm -> state_abbreviation_cd -> "
              "state_abbreviation_cd_2. Correctable, but leaves an orphan.\n\n"
              "A second detector, and a higher-precision one, is the "
              "conjunction of two independent signals: the publisher's name "
              "asserts a type that contradicts the declared one AND "
              "extraction produced a value that type rejected. Neither alone "
              "is strong — the name oracle runs at 47% and a type clash is "
              "often a defensible refinement — but together they found 76 "
              "fields, and the publisher's name then NAMES the field the "
              "widget really holds, which the value-identity edges in "
              "correct.py cannot supply.",
    ),
    DefectClass(
        name="block_renumbered",
        owner="labeler", tier=2,
        conflicts_with=("name_rotation", "name_slide",),
        precedence="RENUMBER BEFORE PERMUTING. Both want the same 42 fields on 2025-schedule-a. The corrector infers rebindings from value identity, which on five interchangeable broker blocks is near-worthless -- any broker's name matches any slot -- so it manufactures cycles. The publisher's ordinal is deterministic. Renumber from it, THEN run the corrector on what is left.",
        canonical="2025-schedule-a:agent_broker_1a_name_address_line_1_txt — bound to the publisher's insBrokerName_03, i.e. broker 3",
        validation="petey",
        signature="inside one publisher-numbered repeating block, our row "
                  "index RESTARTS, so two rows claim the same index",
        fix="take the row index from the publisher's own ordinal",
        detector="publisher_name.py --blocks",
        inline_fix="renumber the slugs from the publisher's ordinal; "
                   "deterministic, because the publisher numbered the block",
        aliases=("duplicate_row_family",),
        observations_class=None,
        notes="CAUSE: per-page labeling with no continuation of an ordinal "
              "series across a page break. 2025-schedule-a repeats one broker "
              "block seven times vertically and the publisher indexes them "
              "_01.._07. Brokers 1-2 sit on page 1 and 3-7 on page 2, and "
              "`auto_label` labels page by page -- so on page 2 it saw five "
              "fresh identical blocks and started counting at 1 again, giving "
              "`1a`..`5a` for brokers 3..7. (The `a` is the sub-item within a "
              "block, not a row letter. An earlier note here blamed the "
              "form's printed sub-item letters; that was wrong, and it would "
              "send the next reader to the page layout instead of to the "
              "labeler's batching.) 42 fields, two naming families for one "
              "series, and nothing downstream can tell that agent_broker_1a "
              "is broker 3. f5500sa is the same family with the same defect.\n\n"
              "Because the cause is the page break, expect this wherever a "
              "repeating block spans one -- it is not specific to this "
              "form.\n\n"
              "Detecting it took three tries and the two failures are the "
              "point. Comparing ANY trailing digit read 77.8% disagreement, "
              "because IRS names like `f1_6` and `c2_1` are sequential widget "
              "indices. The XFA subscript is worse: on cbp7501 every widget "
              "in a column is `descriptiona1[0..N]` and the subscripts do not "
              "follow row order -- manifest_qty_row5 is [2] while row1 is "
              "[6]. What works is structural: >=3 members of one stem whose "
              "SEPARATED ordinals form a run, then flag only blocks where our "
              "sequence restarts. A consistent offset is innocent (i-9 counts "
              "from 0, we count from 1: 104 false hits), and so is a publisher "
              "numbering CELLS across a 2D grid (form_1005's `Past Year_1..8` "
              "spans three fields x two years, so 1,2,1,2 is correct and its "
              "10 hits are still false).\n\n"
              "Subentry numbering (1, 2, 3a, 3b, 3c, 4) is safe: those give "
              "slug ordinals 1,2,3,3,3,4, which is non-decreasing, so the "
              "verdict is `monotonic` and nothing is renamed. That falls out "
              "of the test being order-based rather than uniqueness-based.",
    ),
    DefectClass(
        name="orphan_widget",
        owner="labeler", tier=2,
        validation="external",
        signature="a widget holds no name after a chain is rebound",
        fix="name it from its AcroForm field name or /TU, else escalate",
        detector="correct.py",
        observations_class=None,
        inline_fix="name it from the AcroForm name, else escalate",
        notes="Value identity can only say where an EXISTING name belongs, "
              "never invent one. 54% of data widgets carry a readable "
              "AcroForm name and 51% a tooltip (union 67%, name_sources.py), "
              "so 9 of 13 current orphans resolve with no model at all.",
    ),
    DefectClass(
        name="wrong_widget",
        owner="labeler", tier=3,
        validation="petey",
        signature="gt==native!=petey with no edge to any other widget",
        fix="relabel from the page; no permutation explains it",
        detector="method_delta.py",
        inline_fix="render the widget's rect and relabel it from the page "
                   "(tier 3). Not deterministic, but it IS the in-place "
                   "repair: leaving inline_fix empty implied no path exists.",
        aliases=("class_8b", "cross_family_semantic"),
        observations_class="class 8",
        notes="Includes the form-family bias: IRS-style names applied to "
              "non-IRS widgets. Distinguished from name_slide by the "
              "absence of a target — the value petey returned was written "
              "into no widget on the form.",
    ),

    # ---- the blueprint is right and something else is wrong -----------
    DefectClass(
        name="unfilled_group",
        owner="generator", tier=None,
        canonical="any radio form before petey-synthetic d659037 — gt said 'Male', the page held nothing, petey guessed 'Male' from the field name and scored AGREE",
        validation="self_scoring",
        signature="gt names a group member, the page holds nothing, native "
                  "reports None and a meaning-based reader guesses the name",
        fix="collect radio group NAMES not widget handles, re-resolve in a "
            "fresh page.widgets() pass, and never write Off to siblings",
        detector="render_pdf's radio_errors / radio_unmatched report",
        inline_fix="re-fill and re-score every run of an affected form; the "
                   "blueprint is not at fault so there is nothing to edit",
        aliases=("radio_never_filled",),
        observations_class=None,
        notes="The clearest case of validation confirming a defect. pymupdf "
              "Widget holds a WEAK reference to its page, so collecting "
              "handles in one pass and writing in another raised "
              "ReferenceError that a broad except discarded; with the handles "
              "alive, writing Off to siblings after setting the match "
              "overwrote the selection and the last member won. Ground truth "
              "said 'Male', the page held nothing. `native` honestly reported "
              "None and scored a MISS while a meaning-based reader guessed "
              "'Male' from the field name and scored AGREE — so the eval "
              "REWARDED the hallucination and penalised the honest reader. "
              "44 of 451 sources carry radios, 348 groups. Fixed in "
              "petey-synthetic main (d659037); kept here because the class is "
              "what makes the failure mode findable again, not the bug.",
    ),
    DefectClass(
        name="bad_ground_truth",
        owner="generator", tier=None,
        validation="native",
        signature="gt != native before naming enters it",
        fix="generator prompt: one value per widget",
        detector="method_delta.py",
        observations_class="class 5",
        notes="Not evidence about the label. Nothing in the loop repairs "
              "it; it needs a gen-side change.",
    ),
    DefectClass(
        name="compound_widget",
        owner="generator", tier=None,
        canonical="spreading_location_sec — holds '14 / 18N / 07W' and petey returns '14'",
        validation="native",
        signature="petey's value is a substantial part of this field's own gt",
        fix="generator prompt: do not cram city+state+zip into one widget",
        detector="correct.py",
        aliases=("substring", "compound_widget"),
        observations_class="class 5",
        notes="spreading_location_sec holds '14 / 18N / 07W' and petey "
              "returns '14'. The parts resemble neighbours' values, so this "
              "must be excluded before edges are built or it manufactures "
              "false rebindings. Guarded by requiring the part be >=4 chars "
              "and <=75% of the whole.",
    ),
    DefectClass(
        name="ambiguous_target",
        owner="generator", tier=None,
        canonical="cf_2_fillable:established_loc_no vs footer_loc_no — one value, two fields that could take it",
        validation="petey",
        signature="the value petey returned was written into 2+ widgets",
        fix="generator: distinct values per widget, so diagnosis is possible",
        detector="correct.py",
        observations_class=None,
        notes="Blocks diagnosis rather than being a defect itself: 39 "
              "candidate edges are undecidable because the target value is "
              "not unique. cf_2_fillable writes 'LC-2024-TX-00847' into "
              "both established_loc_no and footer_loc_no. Cheap to fix "
              "gen-side and it would convert 39 unknowns into signal.",
    ),
    DefectClass(
        name="similar_entity",
        owner="blueprint", tier=3,
        canonical="principal_organization_nm — petey returns 'Lone Star Compression LLC' where gt is 'Lone Star Energy Services LLC'; name and type are both right",
        validation="petey",
        signature="gt and petey are both valid values of the same kind",
        fix="prose: a description saying which of the two is meant",
        detector="s2_meaning.py — a model is shown the filled page and the "
                 "field names with NO geometry, so a name that does not "
                 "describe its widget disagrees",
        observations_class="similar_entity",
        inline_fix="add a description saying which entity is meant",
        notes="principal_organization_nm gets 'Lone Star Compression LLC' "
              "where gt is 'Lone Star Energy Services LLC'. Name and "
              "semantic type are both correct and there is nothing to "
              "choose by, so only a description fixes it. The first class "
              "the /TU tooltip work addresses directly.",
    ),

    # ---- reader / parser / scorer -------------------------------------
    DefectClass(
        name="ocr_garble",
        owner="parser", tier=1,
        conflicts_with=("name_rotation", "name_slide",),
        precedence="NEITHER WINS; the comparison is tiered instead. Garble breaks exact value identity and so HIDES real rebindings, while tolerating it manufactures false ones. correct.py therefore compares in three tiers (exact, punct, fuzzy) and never applies a fuzzy edge that name_agrees does not independently support.",
        canonical="1099_nec_blank:recipient_nm — petey returns 'Cll J R' for 'Calloway, James R'; characters dropped, not a different field",
        validation="petey",
        signature="petey's value is a near-miss of the right one",
        fix="scorer: absorb it via is_transcription_noise",
        detector="worklist.py",
        observations_class="ocr_garble",
        notes="Appeared with force_text=True, which recovers text printed "
              "over vector graphics and recovers some of it degraded. Net "
              "strongly positive. Also HIDES real rebindings by breaking "
              "exact value identity, which is why correct.py compares in "
              "three tiers.",
    ),
    DefectClass(
        name="format_variance",
        owner="scorer", tier=1,
        conflicts_with=("name_rotation", "name_slide",),
        precedence="SCORER, NOT CORRECTOR. '1' against '0001' is padding. Normalising it inside the corrector's comparison would turn a scorer gap into a rebinding, so the corrector deliberately does NOT normalise, and the fix belongs to the scorer.",
        canonical="'1' against '0001' — padding, and filing it as compound_widget would blame the generator for a scorer gap",
        validation="native",
        signature="same value, different shape ('1' vs '0001', '4%' vs 0.04)",
        fix="scorer: coerce both sides through one type path",
        detector="correct.py",
        aliases=("name_format",),
        observations_class="class 4 / class 10",
        notes="Split out of compound_widget today: containment between "
              "'1' and '0001' is incidental to padding, and filing it as a "
              "compound widget would blame the generator for a scorer gap. "
              "90 occurrences, the largest single disposition after "
              "no_target.",
    ),
    DefectClass(
        name="name_format",
        owner="scorer", tier=1,
        conflicts_with=("name_rotation", "name_slide",),
        precedence="SCORER, NOT CORRECTOR. Same reasoning as format_variance: reordering 'Hargrove, Dale R.' to 'Dale R. Hargrove' is not evidence that the field is bound to the wrong widget.",
        canonical="f1065sk1:partner_name_address_txt — 'Harmon, Patricia J' against 'Harmon Patricia J'",
        validation="native",
        signature="'Hargrove, Dale R.' vs 'Dale R. Hargrove'",
        fix="scorer: normalise both sides, or accept token reordering",
        detector=None,
        observations_class="name_format",
        notes="Reordering is deliberately NOT normalised away in "
              "correct.py's comparison, or a scorer gap would be mistaken "
              "for a rebinding.",
    ),
    DefectClass(
        name="template_text",
        owner="reader", tier=1,
        validation="native",
        signature="petey returns printed form furniture, not a filled value",
        fix="extract: template-ink cleanup inside the widget rect",
        detector="structural_defects.py",
        aliases=("generator_echoed_label",),
        observations_class="class 9 / C14",
        notes="C14 sub-variant is interactive control captions.",
    ),
    DefectClass(
        name="caption_field",
        owner="labeler", tier=0,
        conflicts_with=("orphan_widget",),
        precedence="DROP FIRST, THEN EXCLUDE. Removing a caption field leaves its widget nameless, and the orphan rule would invent a name for furniture. A dropped caption's widget is not an orphan and must not be offered one.",
        canonical="ao040a — 13 of its 96 'successes' were captions agreeing with themselves",
        validation="self_scoring",
        signature="gt is the printed label; petey returns the real value",
        fix="drop ReadOnly widgets carrying a default value at enumeration",
        detector="auto_label.py",
        observations_class="class 12 (sibling of)",
        inline_fix="drop the field (ReadOnly widget carrying a default)",
        notes="Some form-conversion tools emit the printed caption as a "
              "locked field beside the data field it labels: Form5020 has a "
              "widget named `31` holding '31. SOCIAL SECURITY NUMBER' next "
              "to `31_SOC_A_SECUPITi_NUMB` holding the number. Found by the "
              "validation loop flagging employee_ssn as a defect, where "
              "petey was RIGHT and the blueprint was wrong. 384 widgets "
              "across 42 forms; ao038 has 57. Both conditions required: "
              "ReadOnly alone is a locked real field (1,683 of those), so "
              "the flag by itself would discard 4x more signal than noise.",
    ),
    DefectClass(
        name="pushbutton_field",
        owner="labeler", tier=0,
        canonical="01_114:print_form_btn — gt is None and petey returns the caption 'PRINT FORM'",
        validation="external",
        signature="gt is always None; petey returns the button caption",
        fix="drop pushbuttons at enumeration",
        detector="structural_defects.py",
        observations_class="class 12",
        inline_fix="drop the field (pushbutton holds no value)",
        notes="Fixed at the labeler on 2026-09-22; 77 instances remain in "
              "the 121 blueprints that predate the fix. A relabel clears "
              "them, so this is tier 0, not a correction.",
    ),
    DefectClass(
        name="yn_column",
        owner="parser", tier=1,
        validation="petey",
        signature="paired Yes/No checkboxes with export_value Yes/No",
        fix="extract: radio/checkbox group handling",
        detector=None,
        observations_class="class 7 / C8",
        notes="Class 7 fix landed; the residue is the column layout where "
              "Yes and No sit in separate columns of a grid.",
    ),
    DefectClass(
        name="mistyped_field",
        owner="labeler", tier=0,
        conflicts_with=("name_slide", "block_renumbered", "wrong_widget",),
        precedence="REBIND BEFORE RETYPING. Both fire on the same symptom -- a value the declared type refuses -- and retyping first destroys the evidence: once patient_birth_dt is a string it accepts the surname and looks fixed, so nothing ever finds the bad binding, and a later rebind leaves the type wrong. The discriminator is measured: where the publisher's asserted type CONTRADICTS the declared one, rebind (76 of 175 type_rejects_value fields); where it AGREES, retype.",
        canonical="5021:patient_birth_dt — declared `date`, bound to a widget holding the surname 'Okonkwo'",
        validation="native",
        signature="the clip reads the true value and _coerce_typed returns None",
        fix="retype the field, or extend the semantic_types registry",
        detector="clip_failures.py",
        aliases=("type_rejects_value",),
        observations_class="class 3 / class 8",
        inline_fix="retype from the publisher's name and tooltip, but ONLY "
                   "where the binding is confirmed — see notes",
        notes="Found by asking why the deterministic reader disagreed rather "
              "than assuming it misread: coercion is RIGHT to refuse the "
              "value, so the reader and the scorer are both innocent. 259 "
              "rows across 38 forms, 175 distinct (form, field) pairs.\n\n"
              "CORRECTED 2026-09-23: the declared type is NOT always the "
              "defect, and retyping would often make things worse. Of the 175 "
              "distinct pairs, 76 are `name_slide` — the field is bound to "
              "the WRONG WIDGET and its type is right for its name. `5021` "
              "declares patient_birth_dt a date and the widget it points at "
              "is the publisher's `Parient Last Name`; the neighbours slid "
              "too (patient_nm -> `Parient First Name`, "
              "patient_address_line_1_txt -> `Patient Name: Number and "
              "Street`). Retyping that field to string would give us a "
              "birth-date field holding a surname. Check the publisher's "
              "asserted type BEFORE retyping: agreement means retype, "
              "contradiction means rebind.",
    ),
    DefectClass(
        name="missing_semantic_type",
        owner="labeler", tier=0,
        validation="external",
        signature="an obvious identifier carries semantic_type: null",
        fix="extend the semantic_types registry, or relabel",
        detector=None,
        inline_fix="re-run semantic_types.lookup over every field in every "
                   "blueprint and attach the semantic_type and pattern it "
                   "resolves; a remediate.py rule. Only where the slug "
                   "resolves -- do NOT append _nm to force a hit, which "
                   "scores 100% typed and dropped library agreement from 153 "
                   "to 136 when tried.",
        observations_class="class 2 / class 3",
        notes="Class 3 is the specific case of a date COMPONENT typed as a "
              "whole date (_yr, _begin_dt). A WRONG type, as opposed to a "
              "missing one, is now detectable — see mistyped_field.",
    ),

    # ---- preconditions, not defects -----------------------------------
    DefectClass(
        name="opaque_widget_name",
        owner="labeler", tier=None,
        canonical="1099_nec_blank — every path is `f1_6`-style; the number is a widget index carrying no meaning",
        validation="external",
        signature="no readable AcroForm name and no /TU tooltip",
        fix="none available; the labeler has only proximity to work from",
        detector="name_sources.py",
        observations_class=None,
        notes="32.6% of data widgets corpus-wide, but 80% within tax — the "
              "vertical the library is otherwise measured best on. Not a "
              "defect: a precondition that predicts where the labeler is "
              "working blind, and the reason an orphan escalates to tier 3 "
              "rather than resolving locally.",
    ),
    # ---- classes found 2026-09-28 with label-grounded ground truth -------
    # `score.shape_mismatch` compares the VLM's value for a box against
    # what the blueprint DECLARES for it (type / pattern / values); the
    # geometry arm cannot see any of these because it reads by path.
    # The retype pass (`retype.py`) is their in-place repair.
    DefectClass(
        name="pattern_on_nonstring",
        owner="labeler", tier=0,
        canonical="vba21526ez:disability_1_approximate_onset_dt — `type: date` carrying `^\\d{4}-\\d{2}-\\d{2}$`, which spec §5.6 forbids",
        validation="external",
        signature="field.type in (date, number, integer) and 'pattern' in field",
        fix="semantic_types.enrich_field emits `pattern` only for type string",
        detector="retype.py (pattern_dropped)",
        inline_fix="retype.py: drop the pattern (1,348 fields, 2026-09-28)",
        notes="The registry keeps canonical shapes on date/number types as documentation; the emitter used to copy them onto the field.",
    ),
    DefectClass(
        name="part_typed_as_whole",
        owner="labeler", tier=0,
        canonical="vba21526ez:birth_dt_mm — a 2-digit month box typed `date` because `_dt` matched; 79 of 328 fields on that form",
        validation="petey",
        signature="gt == native; value shorter than the declared pattern's minimum width, or a date/number type on a box whose maxlen/width cannot hold one",
        fix="semantic_types: date_month / date_day / date_year / id_part rules BEFORE the whole-value rules; parts are strings with their own shape",
        detector="score.shape_mismatch (date_type_vs_value, pattern_vs_value); retype.py (part_by_name, part_by_maxlen, date_narrow_widget)",
        inline_fix="retype.py: string + part pattern from the name, else from the box max length (`^\\d{1,n}$`), else from a box narrower than 28pt",
        aliases=("date_part_as_date", "ssn_part_as_ssn"),
        notes="Separator-free comb boxes are NOT parts: an SSN in a 9-cell comb keeps `ssn` with the dashes removed from the pattern (separators_dropped_by_maxlen).",
    ),
    DefectClass(
        name="short_shape_on_wide_box",
        owner="labeler", tier=2,
        canonical="1099_nec_blank:recipient_city_state_zip_txt — `_state` matched inside the name, so a 2-letter pattern sits on a box 200pt wide holding 'Nashville, TN 37203'",
        validation="petey",
        signature="pattern max width <= 5 on a text box wider than 120pt with no maxlen",
        fix="none at the labeler yet: the registry's token match (`_state`, `_zip`) fires inside compound names",
        detector="score.shape_mismatch (pattern_vs_value); retype.py (wide_widget_short_pattern)",
        inline_fix="retype.py: drop the pattern and semantic_type (256 fields, 2026-09-28)",
        notes="A labeler-side fix would be a compound-name guard in semantic_types.lookup (city_state_zip is not a state).",
    ),
    DefectClass(
        name="missing_description",
        owner="labeler", tier=0,
        canonical="vba21526ez — 322 widgets with a publisher tooltip, 0 descriptions in the committed blueprint; 51 fields unlocatable by name for the meaning-based reader",
        validation="petey",
        signature="method_delta: petey returns null for a field whose name alone does not locate it (unlocatable)",
        fix="auto_label carries /TU tooltips and XFA radio captions into `description`",
        detector="method_delta.py (unlocatable)",
        inline_fix="retype.py --describe: tooltips and XFA choice captions into empty descriptions (8,221 fields, 2026-09-28)",
        notes="On 526EZ (image mode) unlocatable went 51 -> 39 and agree 173 -> 190 with descriptions in place.",
    ),
    DefectClass(
        name="repeated_section_ambiguity",
        owner="labeler", tier=None,
        canonical="vba21526ez:veteran_ssn_part1_3 — the by-name reader returns the FIRST SSN on the form; correct.py marks every such chain contradicted",
        validation="petey",
        signature="gt == native != petey, and petey's value equals another copy of the same field (veteran vs claimant, table rows)",
        fix="a naming convention that carries the copy or row (section/row prefix), applied at labeling time",
        detector="correct.py (contradicted chains); method_delta.py (unlocatable/substring)",
        inline_fix=None,
        notes="The largest residue in the 589 library-wide candidates (2026-09-28). Not a rebind: the widget is right, the name is under-specified.",
    ),
    DefectClass(
        name="nonnumeric_in_numeric_field",
        owner="blueprint", tier=None,
        canonical="f720:irs_no_79_other_fuels_rate — a `percent` column whose printed value is 'Various' or 'Free' (24 on f720, 85 on CBP 7501)",
        validation="petey",
        signature="type number/integer; label-grounded value is a word",
        fix="type string with a pattern that admits the printed vocabulary, or a `values` list where the column is closed",
        detector="score.shape_mismatch (number_type_vs_value)",
        inline_fix=None,
        notes="162 library-wide after the retype pass; concentrated on rate/duty columns.",
    ),
    DefectClass(
        name="approximate_date_month_year",
        owner="generator", tier=None,
        canonical="vba21526ez:disability_1_approximate_onset_dt — tooltip asks for MM/DD/YYYY, the printed label says 'approximate', the generator wrote 03/2008",
        validation="petey",
        signature="type date; value matches MM/YYYY or YYYY-MM",
        fix="generator: honour the tooltip's format when the label is looser; or blueprint: `date` with a month precision flag (spec question)",
        detector="score.shape_mismatch (date_type_vs_value)",
        inline_fix=None,
        notes="35 fields on 526EZ; the blueprint is right by the publisher's own tooltip.",
    ),
    DefectClass(
        name="value_overflows_box",
        owner="generator", tier=1,
        canonical="f1040 flat case, local generator before fit_to_widget: 'Consulting rendered invoice' in a 2-digit comb box; dashed SSN in a 9-cell comb loses two digits",
        validation="native",
        signature="gt != native on the flat case only; native holds a prefix of gt",
        fix="generator sizes values to the box: maxlen, comb, rect width (synth.local.fit_to_widget; blind prompt states maxlen)",
        detector="method_delta.py (flat-only substring)",
        inline_fix=None,
        notes="The old cached ground truth was generated without box limits, so its flat cases still carry this class.",
    ),
    DefectClass(
        name="rule_violation",
        owner="generator", tier=1,
        canonical="i130: two of child_adopted_ind / child_born_in_wedlock_ind / ... held at once (a reciprocal clear-others group in the XFA scripts)",
        validation="native",
        signature="more than one member of a `mutex` rule holds a value, on the extracted side or in the ground truth",
        fix="generator enforces `rules:` after the draw (synth.local); the scorer reports `rule_violation` as its own verdict",
        detector="score.check_rules",
        inline_fix=None,
        notes="Rules come from reciprocal XFA clear-others scripts (30 checkbox groups on 5 hybrids, 2026-09-28); the emitter writes them as x_petey_rules.",
    ),
)

BY_NAME = {d.name: d for d in REGISTRY}

# Every alias and guard-counter key any pass emits -> canonical class.
ALIASES: dict[str, str] = {}
for _d in REGISTRY:
    ALIASES[_d.name] = _d.name
    for _a in _d.aliases:
        ALIASES.setdefault(_a, _d.name)
# correct.py's tiered counters collapse onto their class.
for _t in ("exact", "punct", "fuzzy"):
    ALIASES[f"ambiguous_target_{_t}"] = "ambiguous_target"


def canonical(label: str) -> Optional[str]:
    """Map any spelling a pass emits onto a registry class name."""
    return ALIASES.get(label)


# Classes whose in-place repair is implemented by correct.py's --apply path
# (apply_rebinds). remediate.py's are discovered from its RULES table.
_CORRECT_APPLIES = {"name_rotation", "name_slide", "orphan_widget"}

# A protocol carried out by a PROMPT is implemented, not missing. These are
# the classes whose repair runs through a model rather than a rule, with
# what performs it. Blunter than a rule -- `--relabel` rewrites the whole
# form rather than one field -- which is a property of the repair worth
# recording, not a reason to call it absent.
_PROMPT_APPLIES = {
    "wrong_widget": "prompt: auto_label --relabel (whole form)",
    "similar_entity": "prompt: auto_label --relabel (whole form)",
}

# Deterministic repairs that EXIST as a function but are not yet called by
# remediate.py. The distinction matters: these need wiring, not designing.
_UNWIRED = {
    "block_renumbered": "code, unwired: publisher_name.repeating_blocks",
    "mistyped_field": "code, unwired: publisher_name.asserted_type",
    "missing_semantic_type": "code, unwired: semantic_types.lookup",
}


def _wrap(text: str, width: int = 70) -> list[str]:
    out, line = [], ""
    for w in text.split():
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


def executable_inline() -> dict[str, str]:
    """How each declared inline fix is actually carried out, if at all.

    `inline_fix` records a DECISION about what the repair is. It says nothing
    about whether anything performs it, and the two drifted: every
    blueprint-owned class declared a fix while several existed only as prose.

    A protocol does not have to be code. A prompt that relabels the field is
    an implementation; so is a VLM escalation. What is NOT an implementation
    is a sentence in this file, which is what `-- NOTHING --` means.
    """
    out: dict[str, str] = {n: "code: correct.py" for n in _CORRECT_APPLIES}
    try:
        from petey.validate import remediate
        for n in remediate.RULES:
            out[n] = "code: remediate.py"
    except Exception as e:                      # keep the table printable
        out["_error"] = f"remediate.py unavailable: {e!r}"
    out.update(_PROMPT_APPLIES)
    out.update(_UNWIRED)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", type=int, default=None)
    ap.add_argument("--check", action="store_true",
                    help="list classes with no detector")
    ap.add_argument("--gaps", action="store_true",
                    help="list classes with no in-place fix")
    ap.add_argument("--conflicts", action="store_true",
                    help="rules that fight over the same field, and which wins")
    ap.add_argument("--canon", action="store_true",
                    help="classes with no canonical reference case")
    ap.add_argument("--blind", action="store_true",
                    help="list classes validation cannot see, or passes")
    args = ap.parse_args()

    rows = [d for d in REGISTRY
            if args.tier is None or d.tier == args.tier]

    print("=" * 78)
    print("DEFECT TAXONOMY")
    print("=" * 78)
    print(f"{'class':22s} {'owner':10s} {'tier':>4}  "
          f"{'diagnosis':16s} {'retro':6s} {'validation sees':14s}")
    print("-" * 78)
    for d in rows:
        t = "-" if d.tier is None else str(d.tier)
        # Several detectors are a sentence now (name_slide names a
        # conjunction of two passes); the table wants just the module.
        diag = (d.detector or "").replace(".py", "")
        diag = diag.split(";")[0].split(" ")[0][:16] if diag else "-- NONE --"
        corr = "yes" if d.fix else "-- NONE --"
        retro = "yes" if d.inline_fix else ("n/a" if d.owner not in
                                            ("labeler", "blueprint") else "NO")
        vis = {"native": "native", "petey": "petey arm",
               "external": "NO - external", "self_scoring": "NO - PASSES IT",
               None: "-- unset --"}[d.validation]
        print(f"{d.name:22s} {d.owner:10s} {t:>4}  "
              f"{diag:16s} {retro:6s} {vis:14s}")
    n_diag = sum(1 for d in REGISTRY if d.detector)
    print()
    print(f"  diagnosis : {n_diag}/{len(REGISTRY)} classes")
    print(f"  correction: {sum(1 for d in REGISTRY if d.fix)}/"
          f"{len(REGISTRY)} classes")

    ex = executable_inline()
    owns = [d for d in REGISTRY
            if d.owner in ("labeler", "blueprint")
            and not d.fix.startswith("none available")]
    no_code = [d.name for d in owns if d.inline_fix and d.name not in ex]
    print()
    print("  in-place repairs — declared vs how it is CARRIED OUT:")
    for d in owns:
        print(f"    {d.name:24s} {'declared' if d.inline_fix else 'none':9s}"
              f"  {ex.get(d.name, '-- NOTHING --')}")
    kinds = collections.Counter(
        ex.get(d.name, "nothing").split(":")[0].split(",")[0] for d in owns)
    print("    " + "  ".join(f"{k}={v}" for k, v in kinds.most_common()))
    print(f"  {len(owns) - len(no_code)} of {len(owns)} are performed by "
          f"something; a prompt counts")

    blind = [d for d in REGISTRY if d.validation in ("external",
                                                     "self_scoring")]
    print()
    print("  what the validation loop can see:")
    for k, label in (("native", "the blind arm's own verdicts"),
                     ("petey", "only the meaning-based arm"),
                     ("external", "NOTHING in the loop — needs outside "
                                  "evidence"),
                     ("self_scoring", "the loop PASSES it — a green run "
                                      "confirms it")):
        n = sum(1 for d in REGISTRY if d.validation == k)
        if n:
            print(f"    {n:>3}  {k:13s} {label}")
    unset = [d.name for d in REGISTRY if not d.validation]
    if unset:
        print(f"    !! {len(unset)} unset: {', '.join(unset)}")
    print(f"  {len(blind)} of {len(REGISTRY)} classes are validation-proof; "
          f"the petey arm has run on 74 of 796 cases")

    print()
    by_tier = collections.Counter(
        "none" if d.tier is None else d.tier for d in REGISTRY)
    print("  classes by repairing tier:")
    for k in (0, 1, 2, 3, "none"):
        if k in by_tier:
            label = {0: "0 build", 1: "1 validate", 2: "2 correct",
                     3: "3 escalate", "none": "nothing repairs it"}[k]
            print(f"    {by_tier[k]:>3}  {label}")
    print()
    print("  classes by owner:")
    for k, v in collections.Counter(d.owner for d in REGISTRY).most_common():
        print(f"    {v:>3}  {k}")

    # Only a class whose ARTIFACT is the blueprint can have an in-place
    # repair. A generator or scorer defect leaves the blueprint correct, so
    # `inline_fix: None` is the right answer there and flagging it would
    # make this check noise that nobody reads.
    # A class with no repair at ALL is a precondition, not an unfixed defect
    # -- opaque_widget_name says "the labeler has only proximity to work
    # from". Counting it as a missing in-place fix made the check noisier
    # than the thing it was checking for.
    owns_bpt = [d for d in REGISTRY
                if d.owner in ("labeler", "blueprint")
                and not d.fix.startswith("none available")]
    upstream = [d for d in owns_bpt if d.tier == 0 and not d.inline_fix]
    no_inline = [d for d in owns_bpt if d.inline_fix is None]
    print()
    print(f"  blueprint-owned classes: {len(owns_bpt)}; "
          f"{len(owns_bpt) - len(no_inline)} declare an in-place fix")
    if upstream:
        print("  !! fixed upstream with NO in-place repair "
              "(existing blueprints keep the defect):")
        for d in upstream:
            print(f"       {d.name}")

    if args.gaps:
        print()
        print("  blueprint-owned classes with no in-place fix:")
        for d in no_inline:
            print(f"    {d.name:22s} tier={str(d.tier):4s} owner={d.owner:10s}"
                  f" {d.fix}")

    if args.conflicts:
        print()
        print("  RULES THAT FIGHT OVER THE SAME FIELD")
        print("  Two repairs that disagree will oscillate, so each pair "
              "needs a settled order:")
        seen_pairs = set()
        for d in REGISTRY:
            if not d.conflicts_with:
                continue
            print(f"\n    {d.name}  vs  {', '.join(d.conflicts_with)}")
            for line in _wrap(d.precedence or "!! NO PRECEDENCE RECORDED"):
                print(f"      {line}")
            for o in d.conflicts_with:
                seen_pairs.add(frozenset((d.name, o)))
        missing = [d.name for d in REGISTRY
                   if d.conflicts_with and not d.precedence]
        print(f"\n  {len(seen_pairs)} conflicting pairs, "
              f"{len(seen_pairs) - len(missing)} with a settled order")
        if missing:
            print("  !! unsettled — these WILL oscillate:")
            for n in missing:
                print(f"       {n}")

    if args.canon:
        print()
        print("  canonical reference cases — test a new occurrence against")
        print("  THESE before writing another rule:")
        for d in REGISTRY:
            if d.canonical:
                print(f"    {d.name:22s} {d.canonical}")
        missing = [d.name for d in REGISTRY if not d.canonical]
        print(f"\n  {len(REGISTRY) - len(missing)}/{len(REGISTRY)} have one.")
        if missing:
            print("  !! NO reference case — a lookalike form has nothing to "
                  "be checked against,\n     which is how one defect becomes "
                  "two rules:")
            for n in missing:
                print(f"       {n}")

    if args.blind:
        print()
        print("  VALIDATION-PROOF — a green run is not evidence for these:")
        for d in REGISTRY:
            if d.validation == "self_scoring":
                print(f"    {d.name:22s} PASSES IT   {d.signature}")
        for d in REGISTRY:
            if d.validation == "external":
                print(f"    {d.name:22s} invisible   {d.fix[:44]}")

    if args.check:
        missing = [d for d in REGISTRY if d.detector is None]
        print()
        print(f"  {len(missing)} of {len(REGISTRY)} classes have no detector:")
        for d in missing:
            print(f"    {d.name:22s} tier={d.tier}  fix: {d.fix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
