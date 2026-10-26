"""The field-name standard, in one place (Andrew, 2026-10-24, to ship that weekend; docs/NAMING.md "The standard"):

    [block subject]_[block iteration]_[field subject]_[suffix]_[field iteration]_[part]

    child_2_ssn_part1     the second child's SSN, its first box
    ssn_2_part1           a second SSN, outside any block, its first box
    phone_nbr_2_area      a second phone number's area code
    first_nm, zip_cd      the suffix before the number: "first name" and "zip code" read alike

- The suffix is the short form, always: a name never ends in `name` / `number` / `code` before its number and part
  (first_nm, business_nm, account_nbr, state_cd).
- The field's number counts the whole value (subject and suffix), so it comes before the part (phone 2's area code).
- A part is a word (area, line, month) or one token `part1` / `part2`, never two bare numbers in a row.
- A block alone gets no number; once a second copy exists every copy is numbered, the first `_1_` too
  (petey/validate/block_types.block_parts).

Every printer of a name from its parts goes through `print_name` (labeling's structure.print_name, the review page's
parts editor, block types, petey/validate/field_identifiers).
"""
from __future__ import annotations

import re

ORDER = ("block_prefix", "block_iteration", "subject", "suffix", "iteration", "part")
SHORT = {"name": "nm", "number": "nbr", "code": "cd"}


def standard(ident: dict) -> dict:
    """The parts as the standard prints them: a long suffix word made short, whether given as the suffix or as the
    subject's last word with no suffix (first_name -> first + nm); a part `part_1` / `part 1` as `part1`."""
    out = {k: (str(v).strip() if v is not None else v) for k, v in ident.items()}
    suf = (out.get("suffix") or "").lower()
    if suf in SHORT:
        out["suffix"] = SHORT[suf]
    elif not suf and out.get("subject"):
        words = out["subject"].split("_")
        if len(words) > 1 and words[-1] in SHORT:
            out["subject"], out["suffix"] = "_".join(words[:-1]), SHORT[words[-1]]
        elif len(words) == 1 and words[0] in SHORT and out.get("block_prefix"):     # child_2_name -> child_2_nm
            out["subject"], out["suffix"] = "", SHORT[words[0]]
    if out.get("part"):
        out["part"] = re.sub(r"^part[\s_]+(\d+)$", r"part\1", out["part"])
    return out


def print_name(ident: dict) -> str:
    """The field name from its parts, in the standard's order, absent parts skipped, joined by `_`."""
    p = standard(ident)
    return "_".join(str(p[k]) for k in ORDER if p.get(k) not in (None, ""))


def short_suffix(name: str) -> str:
    """A saved name with the short suffix: a last word (before a trailing number) `name` / `number` / `code` made
    short (business_phone_number -> business_phone_nbr, agency_name_2 -> agency_nm_2). Names with no such word come
    back as they are. For the bulk rename of names that carry no stored parts."""
    m = re.match(r"^(.*?)_(name|number|code)((?:_\d+)?)$", name)
    if not m or not m.group(1):
        return name
    return f"{m.group(1)}_{SHORT[m.group(2)]}{m.group(3)}"


LINE_WORDS = {"line", "row", "box", "item", "page", "part", "question", "q", "col", "column", "section", "step"}


def parse(name: str, suffixes: set, part_words: set = frozenset(), group: bool = False) -> dict:
    """A name read into its parts in the standard's shape, from the end (Andrew, 2026-10-25: a name proposed by
    "improve name" fills the parts, '"improve name" should also change "subject"'): a part (a word of `part_words`
    or part1), the field's number, the suffix (`suffixes`, or name / number / code made short; an option group has
    none), and in what is left a number followed by field words is the block's (child_2_first_nm), unless it labels
    a line (address_line_1). child_2_first_name -> child / 2 / first / nm; procedure_cd_2 -> procedure / cd / 2."""
    import re
    toks = [t for t in name.split("_") if t]
    out: dict = {}
    if len(toks) > 1 and (toks[-1] in part_words or re.fullmatch(r"part\d+", toks[-1])):
        out["part"] = toks.pop()
    if len(toks) > 1 and toks[-1].isdigit() and (group or toks[-2] in suffixes or toks[-2] in SHORT):
        out["iteration"] = toks.pop()
    if not group and len(toks) > 1 and (toks[-1] in suffixes or toks[-1] in SHORT):
        out["suffix"] = SHORT.get(toks[-1], toks[-1])
        toks.pop()
    for i in range(1, len(toks) - 1):
        if toks[i].isdigit() and toks[i - 1] not in LINE_WORDS:
            out["block_prefix"], out["block_iteration"] = "_".join(toks[:i]), toks[i]
            toks = toks[i + 1:]
            break
    if toks:
        out["subject"] = "_".join(toks)
    return standard(out)


KEY = "x_petey_identifiers"


def parts_for(name: str, spec: dict | None = None) -> dict:
    """A name's parts, read from it (`parse`, with the standard's suffixes and part words; an option group has no
    suffix), that print exactly that name: when the reading would print another (a long suffix made short), the name
    is all subject, so a name given by hand is never changed behind the person's back (Andrew, 2026-10-26: names and
    parts in step, "construct them from pieces")."""
    from petey.validate.standardize_names import PARTS_AFTER, SUFFIXES, _is_group
    p = {k: v for k, v in parse(name, SUFFIXES, PARTS_AFTER, group=_is_group(spec or {})).items() if v}
    # a number inside the name is the block's only where the form says so (its block types, its grids): read from the
    # name alone it stays with the subject's words (line_29_covered_all_12_months_ind: not block 12)
    if p.get("block_prefix"):
        p["subject"] = "_".join(x for x in (p.pop("block_prefix"), p.pop("block_iteration", None), p.get("subject"))
                                if x)
    return p if print_name(p) == name else {"subject": name}


def sync_parts(fields: dict, names=None) -> list[str]:
    """Each field (of `names`, else every one) whose stored parts are missing or no longer print its name gets parts
    read from the name (`parts_for`), its grid membership kept. The names changed by a path that sends no parts (a
    name typed in Review, a grid's rename, a group's name, a field added) stay in step with their parts. What was
    set."""
    out = []
    for n in (names if names is not None else list(fields)):
        s = fields.get(n)
        if not isinstance(s, dict):
            continue
        st = s.get(KEY) if isinstance(s.get(KEY), dict) else None
        if st and print_name(st) == n:
            continue
        keep = {k: v for k, v in (st or {}).items() if k == "grid"}
        s[KEY] = {**parts_for(n, s), **keep}
        out.append(n)
    return out


def read_name(name: str, spec: dict | None = None, block: tuple | None = None, line: str | None = None,
              keyed: bool = False, part: str | None = None) -> tuple[dict, list[str]]:
    """(parts, flags) for one field, in the standard's order, with what the form says about it (Andrew, 2026-10-26:
    one parts reader; "it should know all_12_months is a subject, not an iteration or a block number"):

    block   (prefix, iteration) of the block the field is in (its block type's record): the name's start is the
            block's, the rest its position's
    line    the identifier of the grid line the field is a cell of (grid_naming.identify), when the lines count
            (29, 6a): the number of the name that is the line's says where it goes; a number after a line word stays
            with it (line_29_..., address_line_1); any other number inside the name stays in the subject
    keyed   the grid's lines are labels (real_estate, line_5_lesser_earned_income): nothing is renumbered
    part    the field is this part of a compound value (associate.compound_values: an SSN's boxes, a date's month):
            the name's last word is the part (veteran_ssn_1: box 1 of the SSN, not a second SSN)

    The parts print the name unless a flag says why not."""
    from petey.validate.standardize_names import PARTS_AFTER, SUFFIXES, _is_group
    group = _is_group(spec or {})
    flags: list[str] = []
    toks = [t for t in name.split("_") if t]
    out: dict = {}
    if block and block[0]:
        head = [*block[0].split("_"), *([block[1]] if block[1] else [])]
        if toks[:len(head)] == head and len(toks) > len(head):
            out["block_prefix"] = block[0]
            if block[1]:
                out["block_iteration"] = block[1]
            toks = toks[len(head):]
        else:
            flags.append(f"not printed from its block ({'_'.join(head)}_...)")
    pw = set(PARTS_AFTER) | ({part} if part and toks and toks[-1] == part else set())
    rest = {k: v for k, v in parse("_".join(toks), SUFFIXES, pw, group=group).items() if v}
    if rest.get("part") in SUFFIXES and not rest.get("suffix") and not rest.get("iteration") and not group:  # a year,
        rest["suffix"] = rest.pop("part")         # wiring_improvement_yr; not signature_2_day, a date's day
    if rest.get("subject") in SUFFIXES and not rest.get("suffix") and not group and (out or rest.get("iteration")):
        rest["suffix"] = rest.pop("subject")     # dependent_child_1_nm_2: the block's name, its second
    if rest.get("block_prefix"):                 # a number inside: the subject's, unless the line says otherwise
        rest["subject"] = "_".join(x for x in (rest.pop("block_prefix"), rest.pop("block_iteration", None),
                                               rest.get("subject")) if x)
    sub = (rest.get("subject") or "").split("_")
    if line and not keyed:
        def core(t):
            return t[:-1] if len(t) > 1 and t[-1].isalpha() and t[:-1].isdigit() else t
        lt = line.split("_")[-1]
        printed = any(sub[i] in (lt, core(lt)) and i > 0 and sub[i - 1] in LINE_WORDS for i in range(len(sub)))
        lettered = re.fullmatch(r"\d+", lt) and any(re.fullmatch(lt + r"[a-z]", t) for t in sub)    # item_5a_page
        if rest.get("iteration") in (lt, core(lt)) or out.get("block_iteration") in (lt, core(lt)) or printed \
                or lettered:
            pass
        elif not rest.get("iteration") and len(sub) > 1 and sub[-1] in (lt, core(lt)) and sub[-2] not in LINE_WORDS:
            rest["iteration"], rest["subject"] = sub[-1], "_".join(sub[:-1])      # x_1_amt: the line's, last
        elif not rest.get("iteration") and lt in sub and sub.index(lt) > 0 and sub[sub.index(lt) - 1] not in LINE_WORDS \
                and sub.count(lt) == 1 and not out.get("block_prefix"):
            i = sub.index(lt)                    # employment_2_to: the line's number before field words: a block's
            out["block_prefix"], out["block_iteration"] = "_".join(sub[:i]), lt
            rest["subject"] = "_".join(sub[i + 1:])
        else:
            nums = [t for t in toks if re.fullmatch(r"\d+[a-z]?", t)]
            flags.append(f"number {nums[-1]} is not its line's ({line})" if nums
                         else f"no number of its line ({line})")
    parts = {**out, **rest}
    if not parts.get("subject") and not (group or parts.get("block_prefix")):
        flags.append("name is only a suffix")
    elif not group and not parts.get("suffix"):
        flags.append("no standard suffix")             # soft: said, not a reason to leave the reading
    return {k: v for k, v in parts.items() if v}, flags
