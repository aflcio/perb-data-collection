"""Decide which side of a case caption is the employer and which is the union.

WHAT THIS FILE IS FOR
---------------------
State labour-board captions are ``A v. B``, but the order of the parties is a
procedural fact (complainant v. respondent, petitioner v. respondent), not a
role.  Assigning ``employer_name`` / ``union_name`` from caption *position*
therefore produces confident, plausible, wrong parties — a township filed as a
union, or an individual grievant filed as an employer.  Downstream a wrong
party is worse than a null: both a researcher and the name matcher trust it.

So roles here are decided by *content*.  There is deliberately no positional
fallback.  Three content rules do the work:

* **Head noun.**  A body whose name *ends* in an organisation-of-employees
  noun — Association, Union, Local 88, Lodge, Chapter, Federation, Guild,
  Employees, Officers — is a labour organisation even when the rest of the
  name is a place or a public body.  ``Crook County Deputy Sheriffs
  Association`` is a union, not a county.  The head noun beats every public
  token, which is what makes it impossible to file an association as the
  employer.  The position matters: ``Certain Employees of Nyssa School
  District`` has "Employees" as a *modifier*, not as the head, and is not a
  union.
* **Public token.**  A body carrying a public-employer token and no union head
  is the public employer.
* **Compound side.**  One side may name several parties (``Multnomah County
  and AFSCME Local 88``).  Such a side is split only when the split is proven:
  every fragment must classify on its own, and the split is only used when it
  actually yields both roles.  That keeps ``Fire and Rescue`` and ``Water &
  Electric`` intact, since "Rescue Bureau" classifies as nothing.

When the tokens do not settle a role, the column is left empty.
"""

from __future__ import annotations

import re
from html import unescape

# --- token vocabularies -------------------------------------------------
#
# "Strong" tokens settle what kind of body this is wherever they appear.
# "Weak" tokens are shared vocabulary (Association, Council, Alliance …) that
# only mean "union" when no strong public-employer token is present.

_STRONG_UNION_TOKENS: tuple[str, ...] = (
    # "Union" is a place adjective, not the organisation noun, when it leads a
    # public-body phrase: "Union High School District 5", "Union County",
    # "Union School District", "Union Township", "Union City". It counts as
    # a union token everywhere else — as the head noun ("Teamsters Union"),
    # or followed by "Local"/"No."/a number/"of" ("Union of Operating
    # Engineers", "Union Local 371", "Union No. 5").
    # "City of Union" is the town, and "Klamath Union-Mazama High School" is a
    # school named for two places, so a hyphenated place before the school
    # noun is a place too.
    r"(?<!city of )union(?!(?:-[a-z]+)?\s+(?:high\s+school|free\s+school\s+district|"
    r"school\s+district|county|township|city))s?\b",
    r"local(?:s)?\b",
    r"lodge(?=\s+(?:no\.?\s*)?#?[a-z]?-?\d)",  # Lodge 7, Lodge W-261; not "Oak Lodge Water Services"
    r"federation",
    r"brotherhood",
    r"sisterhood",
    r"guild",
    r"labor organization",
    r"labour organization",
    r"bargaining unit",
    r"bargaining council",  # East County Bargaining Council: OEA's regional body
    r"united academics",  # United Academics of Oregon State University
    r"atu\b",  # ATU Division 757
    r"amalgamated transit",
    r"education association",
    r"educational? support",
    r"employees'? association",
    r"employes'? association",  # PLRB captions use this spelling
    r"nurses'? association",
    r"police association",
    r"police officers",
    r"patrolmen",
    r"firefighters",
    r"fire fighters",
    r"professional staff",
    r"teachers",
    r"afl[- ]?cio",
    r"afscme",
    r"seiu",
    r"teamsters",
    r"iuoe",
    r"psea",
    r"aft\b",
    r"nea\b",
    r"oea\b",
    r"osea\b",
    r"aaup\b",
    r"fop\b",
    r"iaff\b",
    r"ufcw",
    r"ibew",
    r"uaw\b",
    r"cwa\b",
    r"ibt\b",
    r"unite here",
    r"steelworkers",
    r"(?:fraternal\s+)?order\s+of\s+police",
    r"laborers",
    r"liuna\b",
    r"carpenters",
    r"machinists",
    r"operating engineers",
    r"letter carriers",
    r"ppcoa",
    r"vsea",
    r"aflcio",
)

_WEAK_UNION_TOKENS: tuple[str, ...] = (
    r"association",
    r"council",
    r"organization",
    r"alliance",
    r"chapter",
)

_STRONG_PUBLIC_TOKENS: tuple[str, ...] = (
    r"city\b",
    r"borough",
    r"township",
    r"county",
    r"\bco\b\.?",  # Hood River Co. — county, abbreviated
    r"village",
    r"town of",
    r"municipality",
    r"school district",
    r"school board",
    r"charter school",
    r"\besd\b",
    r"board of education",
    r"board of school directors",
    r"\bboard\b",  # Eugene Water & Electric Board, School Board
    r"intermediate unit",
    r"area vocational",
    r"community college",
    r"college",
    r"university",
    r"commonwealth",
    r"state of",
    r"department of",
    r"bureau of",
    r"housing",
    r"port of",
    r"port authority",
    r"transit",
    r"authority",
    r"commission",
    r"district attorney",
    r"sheriff",
    r"public schools",
    r"public works",
    r"school system",
    r"hospital",
    r"library",
    r"utility",
    r"water",
    r"electric",
    r"parks",
    r"fire and rescue",
    r"fire district",
    r"metro\b",
    r"tri-?met\b",
    r"council of governments",
    r"district\b",
)


def _compile(tokens: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile("|".join(rf"(?:{t})" for t in tokens), flags=re.I)


_STRONG_UNION_RE = _compile(_STRONG_UNION_TOKENS)
_WEAK_UNION_RE = _compile(_WEAK_UNION_TOKENS)
_STRONG_PUBLIC_RE = _compile(_STRONG_PUBLIC_TOKENS)

# --- head-noun detection -------------------------------------------------

# Nouns that name an organisation *of employees* when they are the head of the
# name (its last significant word).
_UNION_HEAD_TAIL_RE = re.compile(
    r"\b(?:"
    r"assn|association|associations|"
    r"(?<!city of )unions?|lodge|chapter|federation|guild|"
    r"brotherhood|sisterhood|"
    r"employees|employes|officers|patrolmen|firefighters|"
    r"professors|academics|faculty|faculties|"
    r"local|"
    r"nea|oea|osea|aaup|afscme|seiu|aft|iaff|fop|ppcoa|afl[-\s]?cio"
    r")[’']?s?\.?$",
    flags=re.I,
)

# "Association of …", "Organization of …", "Chapter of …": the organisation
# noun leads a prepositional phrase, so it is still the head of the name.
_UNION_OF_RE = re.compile(
    r"\b(?:association|assn|organization|chapter|federation|council|guild|union)"
    r"[’']?s?\s+(?:of|for)\b(?!\s+governments\b)",
    flags=re.I,
)

# Numbered subordinate bodies: Local 88, Council 75, Lodge No. 12, Chapter 3.
_NUMBERED_UNIT_RE = re.compile(
    # "Colonial Intermediate Unit 20" is a Pennsylvania school entity, not a
    # bargaining unit.
    r"\b(?:local|council|lodge|chapter|district council|(?<!intermediate )unit)\s+(?:no\.?\s*)?#?\d+",
    flags=re.I,
)

# Acronyms that name a labour organisation when they trail a name in
# parentheses or after a slash/hyphen: (PSU-AAUP), /OEA, -OEA-NEA, (PPCOA).
_UNION_ACRONYM_RE = re.compile(
    r"\b(?:aaup|oea|nea|osea|afscme|seiu|aft|afl[-\s]?cio|iaff|fop|ibew|ufcw|"
    r"uaw|cwa|ibt|iuoe|psea|vsea|ppcoa)\b",
    flags=re.I,
)

_TRAILING_PAREN_RE = re.compile(r"\s*\(([^)]*)\)\s*$")
_TRAILING_NOISE_RE = re.compile(r"(?:[,;]?\s*et\.?\s*al\.?)?[\s,;:.\-–—#]*$", flags=re.I)


# A procedural label trailing a party: "… Association (LCDSA) - Intervenor".
# The label names the party's standing in the case, not the party.
_ROLE_LABEL_RE = re.compile(
    r"\s*[-–—,(]\s*(?:intervenors?|respondents?|petitioners?|complainants?)\s*\)?\s*$",
    flags=re.I,
)


def normalize_side(text: str) -> str:
    """Trim caption punctuation and collapse whitespace on one side."""
    side = re.sub(r"\s+", " ", (text or "")).strip()
    side = _ROLE_LABEL_RE.sub("", side)
    return side.strip(" ,;:.-–— ").strip()


def _tails(side: str) -> list[str]:
    """Progressively strip trailing noise, returning each candidate head form.

    ``Marion County Sheriff Sergeant's Association`` yields itself;
    ``Portland State University Chapter … Professors (PSU-AAUP)`` yields the
    form without the acronym; ``Nyssa School District #26`` yields
    ``Nyssa School District``.
    """
    out: list[str] = []
    current = side
    for _ in range(4):
        current = _TRAILING_NOISE_RE.sub("", current).strip()
        if not current:
            break
        out.append(current)
        stripped = _TRAILING_PAREN_RE.sub("", current).strip()
        if stripped == current:
            # Also peel a trailing affiliate chain: "…Association-OEA-NEA".
            chain = re.sub(r"[-/]\s*[A-Za-z]{2,8}\s*$", "", current).strip()
            if chain == current or not chain:
                break
            current = chain
        else:
            current = stripped
    return out


def has_union_head(text: str) -> bool:
    """True when the name's head noun is an organisation of employees.

    This is the rule that makes filing an association as the employer
    impossible: it fires even when the name also carries a place or a public
    token (``Benton County Deputy Sheriff's Association``).
    """
    side = normalize_side(text)
    if not side:
        return False
    if _NUMBERED_UNIT_RE.search(side) or _UNION_OF_RE.search(side):
        return True
    tails = _tails(side)
    for tail in tails:
        if _UNION_HEAD_TAIL_RE.search(tail):
            return True
    # A trailing parenthetical or slash/hyphen acronym: (PSU-AAUP), /OEA.
    match = _TRAILING_PAREN_RE.search(side)
    if match and _UNION_ACRONYM_RE.search(match.group(1)):
        return True
    trailer = re.search(r"[-/]\s*([A-Za-z][A-Za-z\-/]*)\s*$", side)
    if trailer and _UNION_ACRONYM_RE.search(trailer.group(1)):
        return True
    return False


def _whole_side_is_one_union(side: str) -> bool:
    """True when the *whole* side's own head noun names a union, so a side
    containing ' and ' must never be torn into two parties.

    This is deliberately narrower than :func:`has_union_head`: it skips the
    tail-word list (``... Association`` at the very end also matches a
    legitimate two-party compound like ``Bay Area Hospital and Oregon
    Licensed Practical Nurses Association``) and the numbered-unit check
    (``... and AFSCME Local 88`` also ends in a numbered unit, but is a
    legitimate compound too). What is left — a leading "Association of …"
    / "Union of …" phrase, or a trailing union acronym in parentheses or
    after a hyphen/slash — only ever names one organisation, "and" included:
    ``Association of Pennsylvania State College and University Faculties``,
    ``State College and University Professional Association, PSEA/NEA``.
    """
    if _UNION_OF_RE.search(side):
        return True
    match = _TRAILING_PAREN_RE.search(side)
    if match and _UNION_ACRONYM_RE.search(match.group(1)):
        return True
    trailer = re.search(r"[-/]\s*([A-Za-z][A-Za-z\-/]*)\s*$", side)
    if trailer and _UNION_ACRONYM_RE.search(trailer.group(1)):
        return True
    return False


def is_union(text: str) -> bool:
    """True when the side names a labour organisation."""
    side = normalize_side(text)
    if not side:
        return False
    if has_union_head(side):
        return True
    if _STRONG_UNION_RE.search(side):
        return True
    if _WEAK_UNION_RE.search(side) and not _STRONG_PUBLIC_RE.search(side):
        return True
    return False


def is_public_employer(text: str) -> bool:
    """True when the side names a public employer and not a labour body."""
    side = normalize_side(text)
    if not side:
        return False
    if is_union(side):
        return False
    return bool(_STRONG_PUBLIC_RE.search(side))


# --- individuals ---------------------------------------------------------

_ORG_HINT_RE = re.compile(
    r"\b(inc|llc|corp|corporation|company|co|dept|institute|society|"
    r"center|centre|hospital|systems?|services?|group|trust|fund|"
    r"agency|office|division|committee|board|academy|library|"
    r"authority|district|association|union|local)\b",
    flags=re.I,
)

# Two or three capitalised words, optional middle initial and suffix.
_PERSONAL_NAME_RE = re.compile(
    r"^[A-Z][A-Za-z'’\-]+"
    r"(?:\s+[A-Z]\.?)?"
    r"(?:\s+[A-Z][A-Za-z'’\-]+){1,2}"
    r"(?:,?\s+(?:Jr|Sr|II|III|IV)\.?)?$"
)

# Initials standing in for a name in a redacted caption: "S. R.", "L.H.".
_INITIALS_RE = re.compile(r"^(?:[A-Z]\.\s*){2,4}$")

# A bare surname: one capitalised word, no organisational vocabulary.
_SURNAME_RE = re.compile(r"^[A-Z][A-Za-z'’\-]{1,}$")


def is_personal_name(text: str) -> bool:
    """True when the side looks like an individual, not an organisation."""
    side = normalize_side(text)
    if not side:
        return False
    if _INITIALS_RE.match(side + ("." if not side.endswith(".") else "")):
        return True
    if _INITIALS_RE.match(re.sub(r"\s+", " ", side)):
        return True
    if _ORG_HINT_RE.search(side):
        return False
    if _STRONG_UNION_RE.search(side) or _WEAK_UNION_RE.search(side):
        return False
    if _STRONG_PUBLIC_RE.search(side):
        return False
    if _PERSONAL_NAME_RE.match(side):
        return True
    return bool(_SURNAME_RE.match(side))


# --- compound sides ------------------------------------------------------

# Only " and " (with or without a serial comma) separates parties.  A bare
# comma does not: it appears inside single names — "American Federation of
# State, County and Municipal Employees", "Oregon AFSCME, Council 75".
# An ampersand joins parties the same way ("Colonial Intermediate Unit 20 &
# Pennsylvania State Education Association"); a split still has to prove both
# roles, and a side whose own head names one union is never split.
_ATOM_SPLIT_RE = re.compile(r"\s*,\s*and\s+|\s+and\s+|\s+&\s+", flags=re.I)


def _classify(fragment: str) -> str:
    """Role of one fragment of a compound side, or "" when it proves nothing.

    A one-word fragment only counts when the word is itself a labour
    organisation (``AFSCME``); otherwise a stray ``County`` would let a split
    run through the middle of a name.
    """
    if len(fragment.split()) < 2 and not _STRONG_UNION_RE.fullmatch(fragment.strip(".,")):
        return ""
    if is_union(fragment):
        return "union"
    if is_public_employer(fragment):
        return "public"
    return ""


# A fragment that can only be a public body: "City of Ashland", "Klamath
# County", "State of Oregon, Department of Corrections". Deliberately narrower
# than the public token list: "State College" (a town in Pennsylvania, and the
# opening of a union's own name) must not qualify.
_MUNICIPAL_LEAD_RE = re.compile(
    r"^(?:the\s+)?(?:city|town|county|state|port|village|borough|township)\s+of\b"
    r"|^(?:the\s+)?(?:government\s+of\s+the\s+)?district\s+of\s+columbia\b"
    r"|\b(?:county|school\s+district|department|sheriff[’']?s?\s+office|"
    r"police\s+department|fire\s+district)\b",
    flags=re.I,
)


def _is_municipal_lead(fragment: str) -> bool:
    return bool(_MUNICIPAL_LEAD_RE.search(fragment)) and _classify(fragment) == "public"


# One capitalised word reads as a surname, but these open union names:
# "Construction and General Laborers' Union", "Plumbers and Steamfitters
# Local 290", "Professional and Technical Employees, Local 17".
_NOT_A_SURNAME = frozenset(
    """
    allied amalgamated american associated bakery brick building civil
    classified clerical commercial construction electrical federal food
    general hotel independent industrial international iron municipal
    national office operating painters plumbers professional public
    restaurant retail service sheet stationary technical trades transport
    united
    """.split()
)


def _is_cofiling_individual(atom: str) -> bool:
    return (
        len(atom.split()) == 1
        and atom.lower().strip(".,") not in _NOT_A_SURNAME
        and is_personal_name(atom)
    )


def split_side(text: str) -> tuple[list[str], list[str]]:
    """Return ``(public_parts, union_parts)`` for one side of a caption.

    A side naming several parties is split only when every fragment of the
    split classifies on its own *and* the split yields both roles — otherwise
    the side is classified whole, which is what keeps ``Fire and Rescue`` and
    ``Water & Electric`` from being torn in half.
    """
    side = normalize_side(text)
    if not side:
        return [], []

    # "Fairview Training Center; AFSCME Local 1246; Department of Justice
    # (DOJ)": a respondent list. Each entry is a party, classified on its own,
    # and an entry that proves nothing (an individual) drops out.
    if ";" in side:
        publics: list[str] = []
        unions: list[str] = []
        for piece in side.split(";"):
            piece = re.sub(r"^\s*and\s+", "", piece, flags=re.I)
            its = re.match(r"\s*its\s+(.+)$", piece, flags=re.I)
            if its:
                # "AFSCME; and its Portland, Oregon City and Metropolitan
                # Employees Local 189": the union's own subordinate body.
                if is_union(its.group(1)):
                    unions.append(normalize_side(its.group(1)))
                continue
            p, u = split_side(piece)
            publics += p
            unions += u
        return publics, unions

    atoms = [a.strip() for a in _ATOM_SPLIT_RE.split(side) if a.strip()]

    # "Multnomah County Deputy Sheriffs Association-Multnomah County": two
    # parties joined by a bare hyphen. Split only when the left half ends on a
    # union head and the right half is a municipal body, because hyphens also
    # sit inside single names (Salem-Keizer, OEA-NEA).
    if len(atoms) == 1:
        hyphen = re.fullmatch(r"(.+?\S)-(\S.+)", side)
        if hyphen:
            left, right = hyphen.group(1), hyphen.group(2)
            if (
                _UNION_HEAD_TAIL_RE.search(left)
                and not _STRONG_PUBLIC_RE.search(left.split()[-1])
                and _is_municipal_lead(right)
            ):
                return [right], [left]

    # "Mt. Hood Community College Faculty Association and Kotulski": an
    # individual co-filing with the union. The individual is neither party.
    # A bare surname only: two capitalised words ("Rescue Bureau") are as
    # likely the tail of a name as a person.
    if len(atoms) > 1 and _is_cofiling_individual(atoms[-1]):
        rest = _rejoin(side, atoms, 0, len(atoms) - 1)
        if has_union_head(rest):
            side, atoms = rest, atoms[:-1]
    # And leading: "Miller and Gresham Grade Teachers Association".
    if len(atoms) > 1 and _is_cofiling_individual(atoms[0]):
        rest = _rejoin(side, atoms, 1, len(atoms))
        if has_union_head(rest):
            side, atoms = rest, atoms[1:]

    if _whole_side_is_one_union(side) and not (
        len(atoms) > 1 and _is_municipal_lead(atoms[0])
    ):
        # The side's own head noun already names one union; never split it,
        # even though a fragment before " and " would classify on its own.
        # Unless the side opens on a municipal body: in "City of Ashland and
        # IBEW, Local 659 (IBEW)" the trailing acronym is the second party's,
        # not the whole side's.
        return [], [side]

    if len(atoms) > 1:
        best = _best_segmentation(side, atoms)
        if best is not None:
            publics = [seg for seg, role in best if role == "public"]
            unions = [seg for seg, role in best if role == "union"]
            return publics, unions

    role = _classify(side)
    if role == "public":
        return [side], []
    if role == "union":
        return [], [side]
    return [], []


def _rejoin(side: str, atoms: list[str], start: int, end: int) -> str:
    """Re-cut the original text spanning atoms[start:end], separators intact."""
    first = atoms[start]
    last = atoms[end - 1]
    i = side.find(first)
    j = side.find(last, i if i >= 0 else 0)
    if i < 0 or j < 0:
        return " and ".join(atoms[start:end])
    return side[i : j + len(last)].strip()


def _best_segmentation(
    side: str, atoms: list[str]
) -> list[tuple[str, str]] | None:
    """Coarsest consecutive grouping (>= 2) that all classify and covers both roles.

    Coarsest, not finest: a finer split cuts through single names that contain
    their own "and" — ``American Federation of State, County and Municipal
    Employees`` — while the coarse groups that would glue two parties together
    fail the mixed-roles requirement and are rejected anyway.
    """
    n = len(atoms)
    best: list[tuple[str, str]] | None = None

    def walk(start: int, acc: list[tuple[str, str]]) -> None:
        nonlocal best
        if best is not None and len(acc) >= len(best):
            return
        if start == n:
            if len(acc) < 2:
                return
            roles = {role for _, role in acc}
            if roles == {"public", "union"} and (best is None or len(acc) < len(best)):
                best = list(acc)
            return
        for end in range(start + 1, n + 1):
            piece = _rejoin(side, atoms, start, end)
            role = _classify(piece)
            if role:
                acc.append((piece, role))
                walk(end, acc)
                acc.pop()

    walk(0, [])
    return best


def distinct_parties(parties: list[str]) -> list[str]:
    """Drop repeats, keeping the shortest form of each party.

    A party named twice in one caption is one party, and the longer form is
    usually the shorter one with individuals appended ("Monroe Elementary
    Education Association, Sexton, Gellert").
    """
    def key(party: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", party.lower()).strip()

    def same(longer: str, shorter: str) -> bool:
        # At a word boundary, so "AFSCME Local 881" is not "AFSCME Local 88".
        return longer == shorter or longer.startswith(shorter + " ")

    kept: list[str] = []
    for party in sorted(parties, key=len):
        if not any(same(key(party), key(k)) for k in kept):
            kept.append(party)
    # Caption order, each kept party once.
    return [p for i, p in enumerate(parties) if p in kept and p not in parties[:i]]


def assign_roles(left: str, right: str) -> tuple[str, str]:
    """Return ``(employer_name, union_name)`` for one caption's two sides.

    Either column is empty whenever the tokens do not prove the role.  An
    individual's name is never returned in either column, and two bodies of the
    same kind facing each other (county v. county) prove nothing — unless one
    side is a compound that names both roles by itself.
    """
    a, b = normalize_side(left), normalize_side(right)
    if not a or not b:
        # A one-sided caption proves nothing about roles.
        return "", ""

    a_public, a_union = split_side(a)
    b_public, b_union = split_side(b)

    a_compound = len(a_public) + len(a_union) > 1
    b_compound = len(b_public) + len(b_union) > 1
    compound = a_compound or b_compound

    employer = ""
    if a_public and b_public and not compound:
        employer = ""  # two public bodies facing each other prove nothing
    else:
        employer = "; ".join(a_public + b_public)

    # One union or none. A caption naming two ("Ashland Police Association v.
    # City of Ashland and IBEW Local 659") is a unit clarification or a raid,
    # and which union represents the unit is the outcome, stated only in the
    # order. Picking the petitioner would file the applicant as the
    # representative.
    unions = distinct_parties(a_union + b_union)
    union = unions[0] if len(unions) == 1 else ""

    # Never let one side occupy both columns.
    if employer and union and employer == union:
        return "", ""
    return employer, union


# --- cleaning a party string lifted from a caption -------------------------

def strip_unbalanced_parens(text: str) -> str:
    """Drop the ``)`` a caption draws as its right-hand column.

    Only a ``)`` with no open ``(`` before it goes: "AFL-CIO (IBPO)" keeps its
    parenthetical, "Respondent. ) ) )" and "Petitioner)" lose the column.
    """
    out: list[str] = []
    depth = 0
    for char in text or "":
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                out.append(" ")
                continue
            depth -= 1
        out.append(char)
    return "".join(out)
_TRAILING_VERSUS_RE = re.compile(r"[\s,]+(?:v|vs)\.?\s*$", flags=re.I)
_TRAILING_ROLE_RE = re.compile(
    r"[\s,;.]*\b(?:charging\s+part(?:y|ies)|petitioners?|respondents?|"
    r"intervenors?|complainants?|appellants?|appellees?|plaintiffs?|defendants?|"
    r"agency|employer|labor\s+organization|incumbent)\s*[,.;:]?\s*$",
    flags=re.I,
)
_TRAILING_CASE_NO_RE = re.compile(r"\s*\bcase\s+no\.?\s*[:#]?\s*\S*\s*$", flags=re.I)


def clean_party_text(text: str) -> str:
    """Strip the typography a caption wraps around a party name.

    HTML entities (a Word export writes ``&nbsp;``, sometimes double-escaped as
    ``&amp;nbsp;``), the ``)`` column that separates a caption from its case
    number, a trailing ``v.``/``vs.`` and a trailing procedural label
    ("Petitioner", "Respondent.", "Charging Party,") all come off. The name's
    own punctuation stays.
    """
    value = text or ""
    for _ in range(2):
        value = unescape(value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"&nbsp;?", " ", value, flags=re.I)
    value = strip_unbalanced_parens(value)
    value = re.sub(r"\s+", " ", value).strip()
    for _ in range(3):
        before = value
        value = _TRAILING_CASE_NO_RE.sub("", value)
        value = _TRAILING_VERSUS_RE.sub("", value)
        value = _TRAILING_ROLE_RE.sub("", value)
        value = value.strip(" ,;:-–—")
        if value == before:
            break
    # A leading article is caption style, not part of the name.
    value = re.sub(r"^the\s+(?=[A-Z])", "", value, flags=re.I)
    return value.strip()
