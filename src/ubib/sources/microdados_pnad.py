"""IBGE -- PNAD microdata (continuous quarterly and the older annual survey).

Microdata is not a time series: each file is a fixed-width table with one
person (or household) per row, no header and no delimiter. It therefore does
**not** go through :func:`ubib.load` -- which would force a date index, coerce
every field to a number and cache to parquet -- but through
:func:`ubib.microdata`, which downloads, unpacks and reads the file into a
DataFrame.

``code`` is the file's URL on the IBGE FTP. ``params`` carries ``key`` (the
short identifier), ``expect`` (the package contents the catalog predicts:
``single``, ``household_person`` or ``metro_regions``), ``survey``
(``continuous`` for the quarterly series, ``continuous_annual`` for the annual
visita files, ``annual`` for the old survey) and, where the dictionary has an
address of its own, ``layout_url``.

Package layouts (verified against the real archives)::

    1976-1986  Dados/PNAD76BR.txt          1 file
    1983,1988  Dados/PND83RM1.DAT ... RM8  8 files, one per metropolitan region
    1987/89/90 PND1987N.DAT                bare .DAT, no zip
    1992-1999  DADOS/DOM92.DAT + PES92.DAT 2 files (household and person)
    1997       Dados/Domicilios97 (+ .zip) no extension; the .zip copies are skipped
    2001-2012  <year>/Dados/DOM2001.TXT    2 files, under the year's folder
    2013-2015  Dados/DOM2013.txt           2 files
    PNADC      PNADC_012012.txt            1 file, at the ROOT of the zip (no folder)
    visita 1   PNADC_2023_visita1.txt      1 file, annual PNAD contínua

The 2007, 2009, 2011 and 2012 packages ship a *second* ``Dados`` directory
under ``Marca de imputação/`` holding ``PESSTATUS*``/``DOMSTATUS*``: those are
imputation flags, not microdata, and are excluded.

Everything is written only under ``<data_dir>/microdados_pnad``. Downloads land
in a temporary file inside that same folder, and every output path is checked
against it before being written, so a hostile member name (``../``) cannot
escape.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import zipfile
from pathlib import Path

import pandas as pd

from . import _http
from .base import Source

log = logging.getLogger("ubib.microdados_pnad")

#: Copy buffer. These files exceed 500 MB; 4 MB blocks keep the work in C and
#: memory use flat.
_BUFFER = 4 * 1024 * 1024

#: Extensions accepted as data. ``""`` covers 1997, whose members have none.
_DATA_EXT = {"", ".txt", ".dat"}

#: Role of each member, by filename. Order matters: ``PNAD76BR`` starts with a
#: ``P`` and would otherwise be mistaken for a person file.
_ROLE_PATTERNS = (
    ("metro",     re.compile(r"RM\d", re.I)),
    ("single",    re.compile(r"^(PNAD\d+|PND\d{4}N)", re.I)),
    ("household", re.compile(r"^(DOM|Domicilio|D\d{2}BR)", re.I)),
    ("person",    re.compile(r"^(PES|Pessoa|P\d{2}BR)", re.I)),
)


class MicrodadosPNAD(Source):
    """PNAD microdata. Use :func:`ubib.microdata`, not :func:`ubib.load`."""

    id = "microdados_pnad"

    # -- base-class contract ----------------------------------------------- #

    def fetch(self, spec, config):
        """Microdata is not a time series, so :func:`ubib.load` does not apply."""
        raise TypeError(
            f"'{spec.name}' is PNAD microdata, not a time series. "
            f"Use ubib.microdata('{spec.name}')."
        )

    # -- used by ubib.microdata --------------------------------------------- #

    def materialize(self, spec, config, *, update: bool = False) -> list[Path]:
        """Ensure the files exist on disk and return their paths, in order.

        ``update=False`` reads what is already extracted and never touches the
        network; if nothing is there it raises, rather than quietly starting a
        200 MB download the caller did not ask for.
        """
        target = _target_dir(config)
        expect = str(spec.params.get("expect") or "single").lower()
        key = _key(spec)

        existing = _already_extracted(target, key, expect)
        if existing and not update:
            log.info("%s: reusing %d extracted file(s)", key, len(existing))
            return existing
        if not update:
            raise FileNotFoundError(
                f"'{spec.name}' is not cached yet. "
                "Call microdata(..., update=True) to download it."
            )

        url = _resolve_url(str(spec.code))
        if url.lower().endswith(".dat"):
            return [_download_dat(url, target, key)]
        return _download_zip(url, target, key, expect)

    def layout_for(self, spec, config, *, update: bool = False):
        """Field positions for this entry, or ``None`` if none can be found.

        The continuous PNAD publishes one SAS input file covering every quarter.
        The annual survey publishes one per year: 2001-2012 bundle theirs inside
        the data package, the rest ship it in a sibling ``Layout.zip`` /
        ``Dicionarios_e_input_*.zip``. Years whose documentation is only a Word
        file (1976-1990) have no machine-readable layout and return ``None``.

        Returns a flat ``{name: (start, end, dtype)}`` for a one-file package,
        or ``{"household": {...}, "person": {...}}`` for a two-file one.
        """
        survey = str(spec.params.get("survey") or "").lower()
        if spec.params.get("layout_url"):
            return declared_layout(spec, config, update=update)
        if survey == "continuous":
            return pnadc_layout(config, update=update)
        return annual_layout(spec, config, update=update)


# --------------------------------------------------------------------------- #
# Target folder -- everything below it, nothing outside
# --------------------------------------------------------------------------- #
def _target_dir(config) -> Path:
    """``<data_dir>/microdados_pnad``, created if needed, as an absolute path."""
    target = (Path(config.data_dir) / MicrodadosPNAD.id).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def _inside(target: Path, path: Path) -> Path:
    """Return ``path`` if it really sits inside ``target``; otherwise raise.

    Guards against member names with ``..`` or an absolute path (zip slip).
    """
    path = path.resolve()
    if target != path and target not in path.parents:
        raise RuntimeError(
            f"microdados_pnad: refused to write outside the data folder.\n"
            f"  allowed folder: {target}\n  rejected path:  {path}"
        )
    return path


def _key(spec) -> str:
    """Short identifier for the package (e.g. ``1992_old``, ``201201_new``)."""
    raw = str(spec.params.get("key") or spec.name)
    return re.sub(r"[^0-9A-Za-z_]+", "_", raw).strip("_")


def _outputs(target: Path, key: str, expect: str) -> dict[str, Path]:
    """Final filenames for this package."""
    if expect == "household_person":
        return {"household": _inside(target, target / f"{key}_household.txt"),
                "person": _inside(target, target / f"{key}_person.txt")}
    return {"single": _inside(target, target / f"{key}.txt")}


def _already_extracted(target: Path, key: str, expect: str) -> list[Path]:
    wanted = list(_outputs(target, key, expect).values())
    return wanted if all(p.exists() and p.stat().st_size > 0 for p in wanted) else []


# --------------------------------------------------------------------------- #
# URL resolution
# --------------------------------------------------------------------------- #
def _resolve_url(url: str) -> str:
    """The catalogued URL, or today's equivalent if IBGE has renamed it.

    Suffixes like ``_20250815`` are republication dates: IBGE changes the date
    and the old link dies. Rather than requiring a catalog edit on every
    republication, a failed request triggers a directory listing and a search
    for the file with the same prefix.
    """
    try:
        _http.head(url)
        return url
    except Exception:  # noqa: BLE001 - any failure falls back to the listing
        pass

    folder, _, filename = url.rpartition("/")
    wanted = _file_prefix(filename)
    log.info("URL did not respond, looking for '%s*' in %s", wanted, folder)
    try:
        html = _http.get(folder + "/").text
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"microdados_pnad: could not download {url} nor list {folder}/ ({exc})"
        ) from exc

    # Look for the same kind of file that was asked for: the dictionaries are
    # loose .txt inputs, the data are .zip or .dat. Matching only .zip/.dat here
    # would silently fail to heal a renamed .txt.
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    allowed = ("." + suffix,) if suffix else (".zip", ".dat", ".txt")

    for href in sorted(set(re.findall(r'href="([^"?][^"]*)"', html))):
        name = href.rstrip("/").rpartition("/")[2]
        if name.lower().endswith(allowed) and _file_prefix(name) == wanted:
            log.info("using %s instead of the catalogued link", name)
            return folder + "/" + name
    raise RuntimeError(
        f"microdados_pnad: {url} does not exist and no '{wanted}*' was found in "
        f"{folder}/. IBGE may have reorganised the folder."
    )


def _file_prefix(name: str) -> str:
    """``PNADC_022019_20260324.zip`` -> ``PNADC_022019``; ``Dados.zip`` -> ``Dados``."""
    return re.sub(r"_\d{8}$", "", name.rsplit(".", 1)[0])


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #
def _download_to(url: str, path: Path) -> Path:
    """Stream ``url`` into ``path`` through a neighbouring temporary file."""
    partial = path.with_suffix(path.suffix + ".partial")
    if partial.exists():
        partial.unlink()
    try:
        with _http.stream(url) as response:
            with partial.open("wb") as fh:
                shutil.copyfileobj(response.raw, fh, _BUFFER)
        partial.replace(path)
    finally:
        if partial.exists():
            partial.unlink()
    return path


def _download_dat(url: str, target: Path, key: str) -> Path:
    """1987, 1989 and 1990: a bare ``.DAT``, not compressed."""
    path = _inside(target, target / f"{key}.txt")
    _download_to(url, path)
    log.info("%s: %.1f MB", path.name, path.stat().st_size / 1e6)
    return path


def _download_zip(url: str, target: Path, key: str, expect: str) -> list[Path]:
    tmp = _inside(target, target / f".{key}.zip.tmp")
    preference = url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    try:
        _download_to(url, tmp)
        return extract(tmp, target, key, expect, preference)
    finally:
        if tmp.exists():
            tmp.unlink()


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
def classify(zf: zipfile.ZipFile,
             preference: str | None = None) -> dict[str, list[zipfile.ZipInfo]]:
    """Pick out the microdata members of a package, by role.

    Keeps only what looks like data (no extension, ``.txt`` or ``.dat``),
    dropping documentation, questionnaires, the inner ``.zip`` copies of 1997
    and the imputation flags (``*STATUS*``).

    Where to look depends on the package. The annual survey keeps its microdata
    in a ``Dados``/``DADOS`` folder -- under the year's folder for 2001-2012 --
    next to documentation and questionnaires, so only that folder matters. The
    continuous PNAD has no folder at all: the file sits at the root of the zip.
    Hence the ``Dados`` folder wins when present, and the root is used when not.

    ``preference`` is the package's own name (``PNADC_012012``) and breaks ties
    when more than one candidate survives.
    """
    candidates: list[tuple[list[str], zipfile.ZipInfo]] = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        parts = info.filename.replace("\\", "/").split("/")
        name = parts[-1]
        if not name or "STATUS" in name.upper():
            continue                                   # imputation flags
        _, dot, ext = name.rpartition(".")
        if dot and ("." + ext).lower() not in _DATA_EXT:
            continue                                   # .zip, .pdf, .doc, ...
        candidates.append((parts, info))

    in_dados = [(p, i) for p, i in candidates
                if any(x.lower() == "dados" for x in p[:-1])]
    chosen = in_dados or candidates

    if preference and len(chosen) > 1:
        wanted = preference.lower()
        exact = [(p, i) for p, i in chosen
                 if p[-1].rsplit(".", 1)[0].lower() == wanted]
        if exact:
            chosen = exact

    found: dict[str, list[zipfile.ZipInfo]] = {}
    for parts, info in chosen:
        found.setdefault(_role(parts[-1]), []).append(info)
    for members in found.values():
        members.sort(key=lambda i: i.filename.upper())
    return found


def _role(name: str) -> str:
    base = name.rsplit(".", 1)[0] if "." in name else name
    for role, pattern in _ROLE_PATTERNS:
        if pattern.search(base):
            return role
    return "single"


def extract(zip_path: Path, target: Path, key: str, expect: str,
            preference: str | None = None) -> list[Path]:
    """Extract the microdata from ``zip_path`` under its final names.

    ``preference`` is the package's name at IBGE (without extension), used to
    break ties. The on-disk file is temporary and cannot serve that purpose.
    """
    target = target.resolve()
    outputs = _outputs(target, key, expect)

    with zipfile.ZipFile(zip_path) as zf:
        _save_layout(target, key, _layout_from_archive(zf))
        found = classify(zf, preference)
        if not found:
            raise RuntimeError(
                f"microdados_pnad: {zip_path.name} holds no recognisable "
                "microdata file."
            )
        shape = _shape(found)
        if shape != expect:
            raise RuntimeError(
                f"microdados_pnad: '{key}' is catalogued as '{expect}', but the "
                f"package holds '{shape}' "
                f"({ {k: len(v) for k, v in found.items()} }). "
                "IBGE may have changed its contents; check before using it."
            )

        if expect == "household_person":
            written = [_write(zf, found["household"], outputs["household"], target),
                       _write(zf, found["person"], outputs["person"], target)]
        elif expect == "metro_regions":
            written = [_write(zf, found["metro"], outputs["single"], target)]
        else:
            members = [i for group in found.values() for i in group]
            written = [_write(zf, members, outputs["single"], target)]

    for p in written:
        log.info("%s: %.1f MB", p.name, p.stat().st_size / 1e6)
    return written


#: Members that look like a SAS input file rather than data.
_RE_INPUT_MEMBER = re.compile(r"(input|sas)", re.I)


def _layout_from_archive(zf: zipfile.ZipFile) -> dict:
    """Parse any SAS input files bundled in a package or layout archive.

    Returns ``{}`` when there are none, ``{"household":..., "person":...}`` when
    there is one per file, or ``{"single":...}`` for a lone input.
    """
    parsed: list[tuple[str, dict]] = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = info.filename.replace("\\", "/").split("/")[-1]
        if not _RE_INPUT_MEMBER.search(name) or "STATUS" in name.upper():
            continue
        if not name.lower().endswith((".txt", ".sas")):
            continue
        try:
            text = zf.read(info).decode("latin-1", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        layout = _parse_sas_input(text)
        if len(layout) < 10:
            continue
        _check_lrecl(layout, text, name)
        layout[_LABELS] = _parse_sas_labels(text)
        parsed.append((name, layout))

    return _assign_roles(parsed)


def _assign_roles(parsed: list[tuple[str, dict]]) -> dict:
    """Decide which parsed input describes the household file and which the person.

    By name first. IBGE's naming wanders (``INPUT DOM2001.txt``, ``SasDom97.txt``,
    ``SAS_D96BR.txt``), so when the names say nothing and exactly two inputs were
    found, the record width decides instead: a household record is always far
    shorter than a person record (165 vs 1552 in 1992, 199 vs 804 in 2011).
    That is structural, not a guess about filenames.
    """
    if not parsed:
        return {}

    byname: dict[str, dict] = {}
    unnamed: list[tuple[str, dict]] = []
    for name, layout in parsed:
        role = _input_role(name)
        if role == "single":
            unnamed.append((name, layout))
        else:
            byname.setdefault(role, layout)

    if {"household", "person"} <= set(byname):
        return {"household": byname["household"], "person": byname["person"]}

    # One role named, the other not: the leftover takes the empty slot.
    if len(byname) == 1 and len(unnamed) == 1:
        missing = ({"household", "person"} - set(byname)).pop()
        log.info("assigned '%s' as the %s layout by elimination",
                 unnamed[0][0], missing)
        return {**byname, missing: unnamed[0][1]}

    if not byname and len(unnamed) == 2:
        (n_a, lay_a), (n_b, lay_b) = sorted(
            unnamed, key=lambda pair: max(e for _, e, _ in pair[1].values()))
        log.info("filenames %r and %r do not say which is which; assigning by "
                 "record width (%d vs %d)", n_a, n_b,
                 max(e for _, e, _ in lay_a.values()),
                 max(e for _, e, _ in lay_b.values()))
        return {"household": lay_a, "person": lay_b}

    if len(parsed) == 1:
        return {"single": parsed[0][1]}

    raise RuntimeError(
        "microdados_pnad: could not tell which layout belongs to which file. "
        f"Inputs found: {[n for n, _ in parsed]}. Pass them explicitly with "
        "layout={'household': {...}, 'person': {...}}."
    )


#: Which file an input describes. Unlike the data members, these are named
#: ``INPUT DOM2001.txt`` / ``SasPes97.txt``, so the role sits in the middle of
#: the name and cannot be matched from the start.
#: ``D96BR``/``P96BR`` mirrors how 1996 names its data files, so its layout
#: files follow suit (``SAS_D96BR.txt``). No word boundary before the letter:
#: ``_`` is a word character, so ``\bD`` would never match after an underscore.
_RE_INPUT_HOUSEHOLD = re.compile(r"dom(?!ain)|domicilio|D\d{2}BR", re.I)
_RE_INPUT_PERSON = re.compile(r"pes(?!o)|pessoa|P\d{2}BR", re.I)


def _input_role(name: str) -> str:
    base = name.rsplit(".", 1)[0]
    if _RE_INPUT_HOUSEHOLD.search(base):
        return "household"
    if _RE_INPUT_PERSON.search(base):
        return "person"
    return "single"


def _save_layout(target: Path, key: str, layout: dict) -> None:
    if not layout:
        return
    path = _inside(target, target / f"{key}_layout.json")
    path.write_text(json.dumps(layout, ensure_ascii=False), encoding="utf-8")
    log.info("%s: layout saved (%s)", key,
             ", ".join(f"{k}={len(v)}" for k, v in layout.items()))


def _load_saved_layout(target: Path, key: str):
    path = target / f"{key}_layout.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {role: {n: tuple(v) for n, v in lay.items()} for role, lay in raw.items()}


def _shape(found: dict[str, list]) -> str:
    """Label for what the package holds, to check against the catalog."""
    if "metro" in found:
        return "metro_regions"
    if "household" in found and "person" in found:
        return "household_person"
    total = sum(len(v) for v in found.values())
    return "single" if total == 1 else f"unexpected:{total} files"


def _write(zf: zipfile.ZipFile, members: list[zipfile.ZipInfo],
           path: Path, target: Path) -> Path:
    """Copy ``members`` (concatenating when several) into ``path``.

    Concatenation only happens for the metropolitan-region years, whose eight
    files share one fixed-width layout. A newline is inserted between files
    only when the previous one did not already end in one, so the last record
    of one file never runs into the first of the next.
    """
    path = _inside(target, path)
    partial = path.with_suffix(path.suffix + ".partial")
    try:
        with partial.open("wb") as out:
            last = b""
            for info in members:
                if last and not last.endswith((b"\n", b"\r")):
                    out.write(b"\n")
                with zf.open(info) as src:
                    while block := src.read(_BUFFER):
                        out.write(block)
                        last = block[-1:]
        partial.replace(path)
    finally:
        if partial.exists():
            partial.unlink()
    return path


# --------------------------------------------------------------------------- #
# Variable dictionary (field positions)
#
# The files are fixed-width with no header: without the positions there is no
# way to split the columns. IBGE publishes them as SAS input files, but in four
# different places depending on the era, and each is resolved here:
#
#   quarterly PNADC   one input for the whole series      pnadc_layout()
#   annual visita 1   one input per year, URL catalogued  declared_layout()
#   annual 2001-2012  bundled inside the data package     _layout_from_archive()
#   annual 1992-1999  sibling Layout.zip in the same      annual_layout()
#   annual 2013-2015  folder as the data
#
# 1976-1990 is the exception: documented only as Word files, so no layout can
# be derived and the caller has to supply one.
# --------------------------------------------------------------------------- #
_PNADC_DOC = ("https://ftp.ibge.gov.br/Trabalho_e_Rendimento/"
              "Pesquisa_Nacional_por_Amostra_de_Domicilios_continua/Trimestral/"
              "Microdados/Documentacao/")

#: One SAS INPUT line. Three spellings appear across the years::
#:
#:     @0001  Ano      $4.        PNAD contínua
#:     @1     V0101    $CHAR2.    annual PNAD, 1992-1999
#:     @0068  V1028     9.8       numeric, 8 implied decimals
_RE_SAS_INPUT = re.compile(
    r"@(?P<start>\d+)\s+(?P<name>\w+)\s+"
    r"(?P<char>\$(?:CHAR)?)?(?P<width>\d+)\.(?P<dec>\d*)"
    r"(?P<tail>[^@]*)",          # até a próxima variável: aqui mora o rótulo
    re.I,
)

#: Reserved key under which labels travel inside a saved layout.
_LABELS = "_labels"


def _parse_sas_labels(text: str) -> dict[str, str]:
    """``{name: label}`` from the ``/* ... */`` comment beside each variable.

    IBGE documents what every variable means right there in the input file.
    Keeping those labels is what makes it possible to find, say, the household
    per-capita income in a year whose codes you do not know by heart.
    """
    labels = {}
    for m in _RE_SAS_INPUT.finditer(text):
        comment = re.search(r"/\*(.*?)\*/", m.group("tail") or "", re.S)
        if comment:
            labels[m.group("name")] = " ".join(comment.group(1).split())
    return labels


def _parse_sas_input(text: str) -> dict[str, tuple[int, int, str]]:
    """Turn a SAS input file into ``{name: (start, end, dtype)}``."""
    layout: dict[str, tuple[int, int, str]] = {}
    for m in _RE_SAS_INPUT.finditer(text):
        start = int(m.group("start"))
        width = int(m.group("width"))
        if m.group("char"):
            dtype = "str"
        else:
            dtype = "float" if m.group("dec") and int(m.group("dec")) else "int"
        layout[m.group("name")] = (start, start + width - 1, dtype)
    return layout


def _check_lrecl(layout: dict, text: str, origin: str) -> None:
    """Cross-check the parsed width against the LRECL the input file declares.

    SAS input files state the record length themselves, which is a free and
    completely independent check that the positions were read correctly.
    """
    declared = re.search(r"LRECL\s*=\s*(\d+)", text, re.I)
    if not declared or not layout:
        return
    parsed = max(e for _, e, _ in layout.values())
    # LRECL is a read buffer and is often rounded up (4000 for a 3645-wide
    # record), so only an overflow means the positions are wrong.
    if parsed > int(declared.group(1)):
        log.warning("%s: parsed width %d exceeds the declared LRECL=%s",
                    origin, parsed, declared.group(1))


def _validate_layout(layout: dict, origin: str, sample: str = "") -> dict:
    """Reject an implausible layout instead of silently producing wrong columns."""
    if len(layout) < 10:
        raise RuntimeError(
            f"microdados_pnad: only {len(layout)} variable(s) could be read from "
            f"{origin}; dozens were expected, so the file format has changed.\n"
            f"First lines:\n{sample[:600]}"
        )
    # Overlaps are legitimate here: IBGE exposes UF both on its own and as the
    # leading digits of the control number, so UF (5,6) sits inside V0102
    # (5,12). Worth noting, never worth refusing.
    ordered = sorted((s, e, n) for n, (s, e, *_) in layout.items())
    overlaps = [(n_a, n_b) for (s_a, e_a, n_a), (s_b, _, n_b)
                in zip(ordered, ordered[1:]) if s_b <= e_a]
    if overlaps:
        log.debug("%s: %d overlapping field(s), e.g. %s", origin,
                  len(overlaps), overlaps[:3])
    return layout


def pnadc_layout(config, *, update: bool = False) -> dict[str, tuple[int, int, str]]:
    """Field positions for the continuous PNAD, fetched from IBGE and cached.

    IBGE publishes a single input file for the whole quarterly series, so one
    layout serves every quarter from 2012 to today. The parsed result is cached
    as ``<data_dir>/microdados_pnad/pnadc_layout.json`` -- a plain JSON map of
    ``{variable: [start, end, dtype]}`` that you can open and read. Delete it,
    or pass ``update=True``, to fetch it again.

    The annual PNAD has no equivalent: its dictionaries are published per year
    in formats that are not machine-readable, which is why those entries need
    an explicit ``layout=``.
    """
    target = _target_dir(config)
    cache = _inside(target, target / "pnadc_layout.json")
    if cache.exists() and not update:
        return {k: tuple(v) for k, v in
                json.loads(cache.read_text(encoding="utf-8")).items()}

    url = _resolve_url(_PNADC_DOC + "Dicionario_e_input.zip")
    tmp = _inside(target, target / ".pnadc_dictionary.zip.tmp")
    try:
        _download_to(url, tmp)
        with zipfile.ZipFile(tmp) as zf:
            entries = [i for i in zf.infolist()
                       if not i.is_dir() and i.filename.lower().endswith(".txt")]
            text = ""
            for info in entries:            # the input file is the .txt with "@n name"
                raw = zf.read(info).decode("latin-1", errors="replace")
                if _RE_SAS_INPUT.search(raw):
                    text = raw
                    break
        if not text:
            raise RuntimeError(
                f"microdados_pnad: no SAS input file inside "
                f"{url.rsplit('/', 1)[-1]} (members: "
                f"{[i.filename for i in entries][:10]})."
            )
    finally:
        if tmp.exists():
            tmp.unlink()

    layout = _validate_layout(_parse_sas_input(text), url.rsplit("/", 1)[-1], text)
    _check_lrecl(layout, text, url.rsplit("/", 1)[-1])
    cache.write_text(json.dumps(layout, ensure_ascii=False), encoding="utf-8")
    log.info("PNADC layout: %d variables", len(layout))
    return layout


#: Sibling archives that hold an annual year's dictionary. The naming drifted
#: over the decades: ``Documentacao.zip`` (1976), ``Layout.zip`` (1992-1999),
#: ``Dicionarios_e_input_<date>.zip`` (2013-2015).
_RE_LAYOUT_ARCHIVE = re.compile(r"(layout|documenta|dicionario|dicionarios)", re.I)


def declared_layout(spec, config, *, update: bool = False):
    """Layout for an entry whose catalog row names its own input file.

    The annual PNAD contínua (visita) publishes one SAS input per year as a
    loose ``.txt`` beside the data, so the catalog carries its URL directly.
    """
    target = _target_dir(config)
    key = _key(spec)
    if not update:
        saved = _load_saved_layout(target, key)
        if saved:
            return saved["single"] if set(saved) == {"single"} else saved

    url = _resolve_url(str(spec.params["layout_url"]))
    layout = _layout_from_url(url, target)
    if not layout:
        log.warning("%s: could not read a layout from %s", key, url)
        return None
    _save_layout(target, key, layout)
    return layout["single"] if set(layout) == {"single"} else layout


def annual_layout(spec, config, *, update: bool = False):
    """Field positions for one annual-PNAD year, or ``None`` if unavailable.

    Looks in three places, cheapest first: the layout saved when the package was
    extracted (2001-2012 bundle their own input files), then a sibling archive
    in the year's folder on the FTP (``Layout.zip`` and friends). Years whose
    documentation is only a Word file -- 1976 through 1990 -- have nothing
    machine-readable, and the caller is told so rather than guessed at.
    """
    target = _target_dir(config)
    key = _key(spec)

    if not update:
        saved = _load_saved_layout(target, key)
        if saved:
            return saved["single"] if set(saved) == {"single"} else saved

    folder = str(spec.code).rpartition("/")[0] + "/"
    try:
        html = _http.get(folder).text
    except Exception as exc:  # noqa: BLE001
        log.info("could not list %s (%s)", folder, exc)
        return None

    candidates = sorted({
        h.rstrip("/").rpartition("/")[2] for h in re.findall(r'href="([^"?][^"]*)"', html)
        if h.lower().endswith(".zip") and _RE_LAYOUT_ARCHIVE.search(h)
    })
    for name in candidates:
        layout = _layout_from_url(folder + name, target)
        if layout:
            _save_layout(target, key, layout)
            return layout["single"] if set(layout) == {"single"} else layout

    log.warning(
        "%s: no machine-readable dictionary found in %s (looked at %s). "
        "IBGE publishes this year's layout only as a Word document; pass the "
        "positions yourself with layout={...}.", key, folder, candidates or "nothing",
    )
    return None


def _layout_from_url(url: str, target: Path) -> dict:
    """Parse a layout published either as a zip archive or a bare .txt input."""
    tmp = _inside(target, target / ".layout_download.tmp")
    try:
        _download_to(url, tmp)
        if not zipfile.is_zipfile(tmp):
            text = tmp.read_text(encoding="latin-1", errors="replace")
            layout = _parse_sas_input(text)
            if len(layout) < 10:
                return {}
            _check_lrecl(layout, text, url.rsplit("/", 1)[-1])
            return {"single": layout}
        with zipfile.ZipFile(tmp) as zf:
            return _layout_from_archive(zf)
    except Exception as exc:  # noqa: BLE001 - a wrong guess is not fatal
        log.debug("%s did not yield a layout (%s)", url, exc)
        return {}
    finally:
        if tmp.exists():
            tmp.unlink()


# --------------------------------------------------------------------------- #
# Reading
#
# No CSV reader applies here: the file has neither separator nor header. The
# fast way to read fixed width is to treat each line as one string and slice it
# by position, vectorised -- with polars when available, with pandas otherwise.
# Both avoid ``read_fwf``, which is several times slower on these files.
# --------------------------------------------------------------------------- #
#: A separator that never occurs in the microdata (digits, letters and spaces
#: only), used to make the reader hand back the whole line as one column.
_NO_SEPARATOR = "\x01"

#: Sentinel meaning "every variable in the dictionary".
ALL = "all"


def labels_of(layout: dict) -> dict[str, str]:
    """The ``{variable: label}`` map carried alongside a layout, if any."""
    found = layout.get(_LABELS)
    if isinstance(found, dict):
        return dict(found)
    return {r: lab for role, sub in layout.items() if isinstance(sub, dict)
            for r, lab in (sub.get(_LABELS) or {}).items()} if layout else {}


def variables(layout: dict) -> pd.DataFrame:
    """Everything known about a layout's variables, as a table to search.

    ``name``, ``start``, ``end``, ``width``, ``dtype`` and IBGE's own ``label``::

        v = ubib.microdata_variables("PNAD microdados - 2011_old")
        v[v.label.str.contains("PER CAPITA", case=False, na=False)]
    """
    if _by_role_layout(layout):
        frames = []
        for role in ("household", "person", "single"):
            if role in layout:
                one = variables(layout[role])
                one.insert(0, "file", role)
                frames.append(one)
        return pd.concat(frames, ignore_index=True)

    labels = labels_of(layout)
    rows = [{"name": n, "start": s, "end": e, "width": e - s + 1,
             "dtype": d, "label": labels.get(n, "")}
            for n, (s, e, d) in _normalize_layout(layout).items()]
    return pd.DataFrame(rows).sort_values("start", ignore_index=True)


def _by_role_layout(layout) -> bool:
    return isinstance(layout, dict) and bool(
        {"household", "person"} & {k for k, v in layout.items() if isinstance(v, dict)
                                   and k != _LABELS})


def _normalize_layout(layout: dict) -> dict[str, tuple[int, int, str]]:
    """Accept ``(start, end)`` or ``(start, end, dtype)`` and return the long form."""
    out = {}
    for name, value in layout.items():
        if name == _LABELS:            # labels travel with the layout, not in it
            continue
        start, end = int(value[0]), int(value[1])
        dtype = value[2] if len(value) > 2 else "str"
        if start < 1 or end < start:
            raise ValueError(f"invalid positions for '{name}': {value!r}")
        out[name] = (start, end, dtype)
    return out


def _select(layout: dict, columns) -> dict:
    """Narrow ``layout`` to ``columns`` (``ALL``/``None`` keeps everything)."""
    if columns is None or (isinstance(columns, str) and columns.lower() == ALL):
        return layout
    if isinstance(columns, str):
        columns = [columns]
    missing = [c for c in columns if c not in layout]
    if missing:
        raise KeyError(
            f"variables not in the dictionary: {missing}. "
            f"Available, for example: {list(layout)[:10]}"
        )
    return {c: layout[c] for c in columns}


def _read_polars(path: Path, layout: dict) -> pd.DataFrame:
    import polars as pl

    lines = pl.scan_csv(
        path, separator=_NO_SEPARATOR, has_header=False, new_columns=["_line"],
        quote_char=None, truncate_ragged_lines=True, encoding="utf8-lossy",
        infer_schema_length=0,
    )
    exprs = []
    for name, (start, end, dtype) in layout.items():
        col = pl.col("_line").str.slice(start - 1, end - start + 1).str.strip_chars()
        if dtype == "int":
            col = col.cast(pl.Int64, strict=False)
        elif dtype == "float":
            col = col.cast(pl.Float64, strict=False)
        exprs.append(col.alias(name))
    return lines.select(exprs).collect().to_pandas()


#: Largest value an Int64 column can hold.
_INT64_MAX = 2 ** 63 - 1


def _refine_dtypes(path: Path, layout: dict, sample: int = 1000) -> dict:
    """Decide int vs float from the data, because the dictionary under-specifies.

    IBGE declares the survey weights (``V1027``, ``V1028`` and the 200 replicate
    weights) with no decimal places, but stores them with decimals. Trusting the
    declaration would either null them out (polars casts non-integers to null)
    or turn every weight into a warning (pandas). Sampling the first lines
    settles it cheaply and silently: a declared-integer field whose values carry
    decimals, or overflow Int64, is read as float.
    """
    ints = [(n, s, e) for n, (s, e, d) in layout.items() if d == "int"]
    if not ints:
        return layout

    as_float: set[str] = set()
    with Path(path).open("r", encoding="latin-1") as fh:
        for i, line in enumerate(fh):
            if i >= sample:
                break
            for name, start, end in ints:
                if name in as_float:
                    continue
                text = line[start - 1:end].strip()
                if not text:
                    continue
                if "." in text or "," in text:
                    as_float.add(name)
                elif len(text) > 18 and text.lstrip("-").isdigit():
                    try:
                        if abs(int(text)) > _INT64_MAX:
                            as_float.add(name)
                    except ValueError:
                        pass

    if as_float:
        log.info(
            "%d of %d integer-declared fields hold non-integer values and will "
            "be read as float (e.g. %s)",
            len(as_float), len(ints), ", ".join(sorted(as_float)[:3]),
        )
    return {n: (s, e, "float" if n in as_float else d)
            for n, (s, e, d) in layout.items()}


def _to_number(values, name: str, dtype: str):
    """Convert a sliced column to a number, tolerating whatever dtype arrives.

    ``pd.to_numeric`` returns different dtypes depending on the pandas version
    and on whether strings are object-, Python- or Arrow-backed, and a direct
    ``astype("Int64")`` raises on several of them. Going through float64 works
    from all of them; a field that will not fit an integer (too wide, or not
    whole) is kept as float rather than bringing the read down.
    """
    numbers = pd.to_numeric(values, errors="coerce").astype("float64")
    if dtype != "int":
        return numbers
    try:
        return numbers.astype("Int64")
    except (TypeError, ValueError):
        # _refine_dtypes normally catches this from the sample; a field whose
        # decimals only appear later still degrades quietly rather than failing.
        log.debug("'%s' does not fit an integer; keeping it as float", name)
        return numbers


def _read_pandas(path: Path, layout: dict) -> pd.DataFrame:
    lines = pd.read_csv(
        path, sep=_NO_SEPARATOR, header=None, names=["_line"], dtype=str,
        engine="c", quoting=3, encoding="latin-1", keep_default_na=False,
        on_bad_lines="skip",
    )["_line"].astype("object")
    out = {}
    for name, (start, end, dtype) in layout.items():
        col = lines.str.slice(start - 1, end).str.strip()
        out[name] = _to_number(col, name, dtype) if dtype in ("int", "float") else col
    return pd.DataFrame(out)


def merge_keys(household: dict, person: dict) -> list[str]:
    """Variables identifying a household, present identically in both files.

    The key is not the same across the decades -- 1992 uses ``CONTROL`` (6
    chars) plus ``V0103``, while 2001-2015 use ``V0102`` (8 chars, UF included)
    plus ``V0103`` -- so it is derived rather than hardcoded: every variable
    that appears in both layouts at exactly the same position is, by
    construction, household-level information repeated on each person record.

    Matching ignores case, because IBGE is not consistent about it: the 1999
    household input declares ``v0102`` while its person input declares
    ``V0102``. Returns ``(household_name, person_name)`` pairs so each file
    keeps the spelling IBGE gave it.
    """
    hh, pp = _normalize_layout(household), _normalize_layout(person)
    by_upper = {n.upper(): n for n in pp}
    pairs = []
    for name, pos in hh.items():
        twin = by_upper.get(name.upper())
        if twin and pp[twin][:2] == pos[:2]:
            pairs.append((name, twin))
    return pairs


def merge_household_person(household: pd.DataFrame, person: pd.DataFrame,
                           keys: list[str]) -> pd.DataFrame:
    """Attach each household's attributes to every person living in it.

    A left join from the person side: one row per person, household columns
    repeated. Row count is preserved, and a person whose household is missing
    keeps their own data with empty household fields rather than vanishing.
    """
    pairs = [(k, k) if isinstance(k, str) else tuple(k) for k in keys]
    if not pairs:
        raise ValueError(
            "no shared identifier between the household and person layouts, "
            "so they cannot be merged safely."
        )
    missing = ([h for h, _ in pairs if h not in household.columns]
               + [p for _, p in pairs if p not in person.columns])
    if missing:
        raise KeyError(
            f"merge keys {missing} were not read; include them in 'columns' "
            "or use columns='all'."
        )
    household = household.rename(columns={h: p for h, p in pairs if h != p})
    keys = [p for _, p in pairs]
    before = len(person)
    merged = person.merge(household, on=keys, how="left", suffixes=("", "_dom"),
                          validate="many_to_one")
    if len(merged) != before:
        raise RuntimeError(
            f"merge changed the row count ({before} -> {len(merged)}); the key "
            f"{keys} does not identify a household uniquely."
        )
    log.info("merged on %s: %d people x %d columns", keys, len(merged), merged.shape[1])
    return merged


def check_layout(path, layout: dict, lines: int = 200) -> dict:
    """Compare a layout against the file, to catch a misaligned dictionary.

    A fixed-width file has one honest check available without knowing the
    variables: the record width. If the dictionary's last field ends somewhere
    other than the end of the line, the positions do not belong to this file
    and every column after the mismatch would be silently wrong.

    Returns a report and logs a warning when the widths disagree.
    """
    normalized = _normalize_layout(layout)
    declared = max(end for _, end, _ in normalized.values())
    widths: dict[int, int] = {}
    with Path(path).open("r", encoding="latin-1") as fh:
        for i, line in enumerate(fh):
            if i >= lines:
                break
            widths[len(line.rstrip("\r\n"))] = widths.get(len(line.rstrip("\r\n")), 0) + 1

    found = max(widths, key=widths.get) if widths else 0
    report = {"declared_width": declared, "file_width": found,
              "widths_seen": widths, "variables": len(normalized),
              "matches": declared == found, "overflow": found > declared}

    if found > declared:
        # Records wider than the dictionary: the positions cannot be right.
        log.warning(
            "the file's records are %d wide but the layout only declares %d "
            "columns (%s). The dictionary does not match this file.",
            found, declared, dict(sorted(widths.items(), key=lambda kv: -kv[1])[:3]),
        )
    elif found < declared:
        # Normal: IBGE strips trailing blanks, and its own input files say
        # MISSOVER -- a record may stop early and the rest is missing.
        tail = [n for n, (s, _, _) in normalized.items() if s > found]
        log.info(
            "records are %d wide against a declared %d: trailing blanks were "
            "stripped, so %d variable(s) past position %d come back empty%s.",
            found, declared, len(tail), found,
            f" (e.g. {', '.join(tail[:3])})" if tail else "",
        )
    return report


def read(path, layout: dict | None = None, columns=ALL,
         verify_width: bool = False) -> pd.DataFrame:
    """Read a fixed-width microdata file into a DataFrame.

    Parameters
    ----------
    path:
        An already-extracted ``.txt`` file.
    layout:
        ``{variable: (start, end)}`` or ``{variable: (start, end, dtype)}``,
        with 1-based positions as in the IBGE dictionaries and ``dtype`` one of
        ``"str"``/``"int"``/``"float"``. Without it there is no way to know
        where each variable begins, and reading is refused rather than
        inventing columns.
    columns:
        ``"all"`` (default) or a list of variable names. Selecting a few
        variables is much faster and lighter than reading all of them.
    verify_width:
        Check the dictionary's total width against the file's records first and
        warn on a mismatch. Used when the layout was fetched rather than given,
        since a quarter whose record width changed would otherwise be read
        silently wrong.
    """
    path = Path(path)
    if not layout:
        raise ValueError(
            f"{path.name} is fixed-width with no header: pass "
            "layout={variable: (start, end)} from the IBGE variable dictionary "
            "(Documentacao.zip for the relevant year)."
        )
    normalized = _normalize_layout(layout)
    if verify_width:
        check_layout(path, normalized)          # logs a warning if they disagree
    selected = _refine_dtypes(path, _select(normalized, columns))
    try:
        return _read_polars(path, selected)
    except ImportError:
        log.info("polars is not installed; reading with pandas (several times "
                 "slower on a file this size -- 'pip install polars' fixes it)")
        return _read_pandas(path, selected)
