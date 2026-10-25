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
parts editor, block types, eval/field_identifiers).
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
