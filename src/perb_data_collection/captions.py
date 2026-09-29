"""Read a board order's caption into its labelled parties.

WHAT THIS FILE IS FOR
---------------------
A caption lists each party followed by its procedural label::

    DEPARTMENT OF SERVICES FOR CHILDREN, YOUTH,
    AND THEIR FAMILIES,
    Charging Party,
    V.
    DELAWARE STATE AND FEDERAL EMPLOYEES
    LOCAL 1029, LABORERS INTERNATIONAL UNION
    OF NORTH AMERICA, AFL-CIO.
    Respondent.

The label is the only thing a caption says about a party's standing, so a name
lands in a role only when its own label follows it. Nothing is assigned by
position, and a label is a label only when it is the whole line or follows the
name after a comma: "Child and Family Services Agency" is a name, "Services,
Agency" and a bare "Agency" are labels.

Whether a party is the employer or the union is a separate question, answered
by content in :mod:`perb_data_collection.party_roles`.
"""

from __future__ import annotations

import re

from perb_data_collection.party_roles import clean_party_text, strip_unbalanced_parens

ROLE_WORDS = (
    r"petitioners?|respondents?|agency|intervenors?|complainants?|"
    r"labor\s+organization|employer|incumbent|charging\s+part(?:y|ies)|"
    r"appellants?|appellees?"
)
_LABEL_ONLY_RE = re.compile(rf"^\s*(?P<role>{ROLE_WORDS})\s*[,.;:]?\s*$", flags=re.I)
_LABEL_TRAILING_RE = re.compile(
    rf"^(?P<name>.*\S)\s*,\s*(?P<role>{ROLE_WORDS})\s*[,.;:]?\s*$", flags=re.I
)
_SEPARATOR_RE = re.compile(r"^\s*(?:-?\s*and\s*-?|v\.?|vs\.?)\s*$", flags=re.I)

# Caption furniture every board prints beside the parties. OCR renders the
# ")" column as "}", "]" or "|", and a Delaware caption uses a ":" column.
_DEFAULT_NOISE: tuple[re.Pattern[str], ...] = (
    re.compile(r"[}\]|]"),
    re.compile(r"(?<!\w):(?!\w)"),
)

ROLE_COLUMN: dict[str, str] = {
    "petitioner": "petitioner",
    "petitioners": "petitioner",
    "complainant": "petitioner",
    "complainants": "petitioner",
    "charging party": "petitioner",
    "charging parties": "petitioner",
    "appellant": "petitioner",
    "appellants": "petitioner",
    "respondent": "respondent",
    "respondents": "respondent",
    "appellee": "respondent",
    "appellees": "respondent",
    "labor organization": "respondent",
    "incumbent": "respondent",
    "agency": "agency",
    "employer": "agency",
    "intervenor": "intervenor",
    "intervenors": "intervenor",
}


def parse_labelled_caption(
    text: str,
    *,
    start_re: re.Pattern[str],
    end_re: re.Pattern[str],
    noise: tuple[re.Pattern[str], ...] = (),
    max_lines: int = 120,
) -> dict[str, list[str]]:
    """Return ``{"petitioner", "respondent", "agency", "intervenor", "labels"}``.

    Each role maps to the names the caption labels with it, in order.
    ``labels`` holds the raw label words seen (``charging party``,
    ``respondent``), so a caller can tell a ULP caption from a representation
    one. Empty lists when the caption is not found.
    """
    found: dict[str, list[str]] = {
        "petitioner": [], "respondent": [], "agency": [], "intervenor": [], "labels": [],
    }
    start = start_re.search(text or "")
    if not start:
        return found
    buffer: list[str] = []
    for raw in text[start.end():].splitlines()[:max_lines]:
        if end_re.search(raw):
            break
        line = raw
        for pattern in noise + _DEFAULT_NOISE:
            line = pattern.sub(" ", line)
        line = strip_unbalanced_parens(line).replace("_", " ")
        line = re.sub(r"\s+", " ", line).strip()
        if not line or not re.search(r"[A-Za-z]{2}", line):
            continue
        if _SEPARATOR_RE.match(line):
            buffer = []
            continue
        label = _LABEL_ONLY_RE.match(line)
        name_part = ""
        if not label:
            label = _LABEL_TRAILING_RE.match(line)
            if label:
                name_part = label.group("name")
        if label:
            if name_part:
                buffer.append(name_part)
            word = re.sub(r"\s+", " ", label.group("role").lower())
            found["labels"].append(word)
            name = clean_party_text(" ".join(buffer))
            if name:
                found[ROLE_COLUMN[word]].append(name)
            buffer = []
            continue
        # Short all-caps junk from OCR ("NN") is not a name line.
        if len(line) <= 3 and line.isupper():
            continue
        buffer.append(line)
    return found


def joined(names: list[str]) -> str:
    return "; ".join(names)
