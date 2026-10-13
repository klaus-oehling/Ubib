"""Offline tests for Ubib (no network required).

Run with:  pytest -q
"""

from __future__ import annotations

import io
import zipfile

import pandas as pd
import pytest

from ubib import catalog, storage
from ubib.api import load
from ubib.sources import available_sources, get_source
from ubib.sources import microdados_pnad as mp
from ubib.transform.frequency import detect_frequency, to_period_end


def test_shipped_catalog_loads():
    names = catalog.names()
    assert len(names) > 100
    # every source referenced by the catalog must be a registered adapter
    assert catalog.sources().issubset(set(available_sources()))


def test_params_json_parsing():
    td = [n for n in catalog.names() if catalog.get(n).source == "tesouro_direto"]
    assert td, "expected at least one tesouro_direto series"
    assert isinstance(catalog.get(td[0]).params, dict)


def test_storage_normalize_dedup_and_sort():
    idx = pd.to_datetime(["2020-03-31", "2020-01-31", "2020-02-29", "2020-02-29"])
    raw = pd.Series([3, 1, 2, 2.5], index=idx)
    s = storage.normalize(raw, "X")
    assert list(s.index.strftime("%Y-%m")) == ["2020-01", "2020-02", "2020-03"]
    assert s.loc["2020-02-29"] == 2.5  # last duplicate wins
    assert s.index.name == "Date"


def test_frequency_detection():
    monthly = pd.Series(range(60), index=pd.date_range("2015-01-15", periods=60, freq="MS"))
    daily = pd.Series(range(400), index=pd.date_range("2020-01-01", periods=400, freq="D"))
    assert detect_frequency(monthly) == "M"
    assert detect_frequency(daily) == "D"


def test_to_period_end_resamples_to_month_end():
    monthly = pd.Series(range(3), index=pd.to_datetime(["2020-01-10", "2020-02-10", "2020-03-10"]))
    pe = to_period_end(monthly, "M")
    assert list(pe.index.day) == [31, 29, 31]


def test_unknown_series_raises():
    with pytest.raises(KeyError):
        catalog.get("does-not-exist")


def test_load_update_false_on_an_uncached_series_raises(tmp_path):
    """update=False means "no network", for series exactly as for microdata."""
    from ubib.config import Config

    cfg = Config(config_path=tmp_path / "c.toml", data_dir=tmp_path)
    name = next(n for n in catalog.names() if catalog.get(n).source == "sgs")
    with pytest.raises(FileNotFoundError, match="not cached yet"):
        load(name, update=False, verbose=False, config=cfg)


def test_load_update_false_reads_the_cache_without_network(tmp_path):
    pytest.importorskip("pyarrow")          # the cache is parquet
    from ubib.config import Config

    cfg = Config(config_path=tmp_path / "c.toml", data_dir=tmp_path)
    name = next(n for n in catalog.names() if catalog.get(n).source == "sgs")
    original = pd.Series(
        [1.0, 2.0], index=pd.to_datetime(["2020-01-31", "2020-02-29"]), name=name
    )
    storage.save(original, "sgs", name, cfg)

    got = load(name, update=False, verbose=False, config=cfg)
    assert got.tolist() == [1.0, 2.0]


# --------------------------------------------------------------------------- #
# PNAD microdata -- all offline: the archives are built in memory
# --------------------------------------------------------------------------- #
def _zip(members: dict[str, bytes]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    buf.seek(0)
    return buf


def test_microdata_entries_are_catalogued():
    names = [n for n in catalog.names()
             if catalog.get(n).source == "microdados_pnad"]
    # 58 quarterly (2012Q1-2026Q2) + 35 annual (1976-2015) + 12 annual visita 1;
    # grows with each new release, hence a floor rather than equality.
    assert len(names) >= 105, f"expected at least 105 entries, found {len(names)}"
    for n in names:
        spec = catalog.get(n)
        assert spec.code.startswith("https://ftp.ibge.gov.br/"), n
        assert spec.params.get("expect") in {"single", "household_person",
                                             "metro_regions"}, n
        assert spec.params.get("survey") in {"continuous", "continuous_annual",
                                             "annual"}, n
        assert spec.params.get("key"), n


def test_microdata_is_not_loadable_as_a_series():
    """ubib.load() would destroy microdata; it must refuse with a clear message."""
    name = next(n for n in catalog.names()
                if catalog.get(n).source == "microdados_pnad")
    with pytest.raises(TypeError, match="ubib.microdata"):
        get_source("microdados_pnad").fetch(catalog.get(name), None)


@pytest.mark.parametrize("members,expect,roles", [
    ({"Dados/PNAD76BR.txt": b"a\n"}, "single", {"single"}),
    ({"DADOS/DOM92.DAT": b"a\n", "DADOS/PES92.DAT": b"b\n"},
     "household_person", {"household", "person"}),
    ({"Dados/D96BR.TXT": b"a\n", "Dados/P96BR.TXT": b"b\n"},
     "household_person", {"household", "person"}),
    ({f"Dados/PND83RM{i}.DAT": b"a\n" for i in range(1, 9)},
     "metro_regions", {"metro"}),
    # 2001-2012 keep the microdata under the year's folder
    ({"2001/Dados/DOM2001.TXT": b"a\n", "2001/Dados/PES2001.TXT": b"b\n"},
     "household_person", {"household", "person"}),
    # continuous PNAD: a bare file at the root, no folder at all
    ({"PNADC_012012.txt": b"a\n"}, "single", {"single"}),
])
def test_microdata_member_classification(members, expect, roles):
    with zipfile.ZipFile(_zip(members)) as zf:
        found = mp.classify(zf)
    assert set(found) == roles
    assert mp._shape(found) == expect


def test_microdata_pnadc_file_sits_at_the_archive_root(tmp_path):
    """The continuous PNAD has no intermediate folder: zip -> file."""
    path = tmp_path / "PNADC_012012.zip"
    path.write_bytes(_zip({"PNADC_012012.txt": b"record\n"}).getvalue())
    (out,) = mp.extract(path, tmp_path, "201201_new", "single", "PNADC_012012")
    assert out.name == "201201_new.txt"
    assert out.read_bytes() == b"record\n"


def test_microdata_root_package_prefers_the_member_named_like_the_package(tmp_path):
    """If something rides along at the root, the package name breaks the tie."""
    path = tmp_path / "PNADC_012012.zip"
    path.write_bytes(_zip({"PNADC_012012.txt": b"data\n",
                           "readme.txt": b"instructions\n"}).getvalue())
    (out,) = mp.extract(path, tmp_path, "201201_new", "single", "PNADC_012012")
    assert out.read_bytes() == b"data\n"


def test_microdata_dados_folder_wins_over_root_when_both_exist(tmp_path):
    with zipfile.ZipFile(_zip({"readme.txt": b"x\n",
                               "Dados/PNAD76BR.txt": b"a\n"})) as zf:
        found = mp.classify(zf)
    names = {i.filename for v in found.values() for i in v}
    assert names == {"Dados/PNAD76BR.txt"}


def test_microdata_ignores_docs_inner_zips_and_imputation_flags():
    """1997 ships duplicate .zips; 2007-2012 ship imputation flags."""
    with zipfile.ZipFile(_zip({
        "Dados/Domicilios97": b"a\n",
        "Dados/Domicilios97.zip": b"PK\x03\x04",          # compressed duplicate
        "Dados/Pessoas97": b"b\n",
        "Dados/Pessoas97.zip": b"PK\x03\x04",
        "Questionario/quest.pdf": b"%PDF",                # documentation
        "Marca de imputacao/Dados/PESSTATUS2007.txt": b"x\n",
    })) as zf:
        found = mp.classify(zf)
    assert mp._shape(found) == "household_person"
    names = {i.filename for v in found.values() for i in v}
    assert names == {"Dados/Domicilios97", "Dados/Pessoas97"}


def test_microdata_metro_files_are_concatenated_without_loss(tmp_path):
    members = {f"Dados/PND88RM{i}.DAT": f"line{i}\n".encode() for i in range(1, 9)}
    path = tmp_path / "pkg.zip"
    path.write_bytes(_zip(members).getvalue())
    (out,) = mp.extract(path, tmp_path, "1988_old", "metro_regions")
    assert out.name == "1988_old.txt"
    assert out.read_bytes() == b"".join(f"line{i}\n".encode() for i in range(1, 9))


def test_microdata_refuses_package_that_differs_from_the_catalog(tmp_path):
    path = tmp_path / "pkg.zip"
    path.write_bytes(_zip({"Dados/DOM92.DAT": b"a\n",
                           "Dados/PES92.DAT": b"b\n"}).getvalue())
    with pytest.raises(RuntimeError, match="catalogued as 'single'"):
        mp.extract(path, tmp_path, "1992_old", "single")


def test_microdata_never_writes_outside_its_folder(tmp_path):
    """A hostile member name must not escape the data folder (zip slip)."""
    target = tmp_path / "microdados_pnad"
    target.mkdir()
    path = tmp_path / "pkg.zip"
    path.write_bytes(_zip({"Dados/../../../../ESCAPED.txt": b"a\n"}).getvalue())
    (out,) = mp.extract(path, target, "1999_old", "single")
    assert out.parent == target.resolve()
    assert not (tmp_path.parent / "ESCAPED.txt").exists()
    with pytest.raises(RuntimeError):
        mp._inside(target.resolve(), tmp_path / "outside.txt")


# -- reading ---------------------------------------------------------------- #
LAYOUT = {"year": (1, 4, "str"), "uf": (5, 6, "int"), "income": (7, 12, "float")}


def _sample(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("201231001234\n20133500987 \n", encoding="ascii")
    return path


def test_read_requires_a_layout(tmp_path):
    with pytest.raises(ValueError, match="layout"):
        mp.read(_sample(tmp_path))


def test_read_slices_fixed_width_and_casts(tmp_path):
    df = mp.read(_sample(tmp_path), LAYOUT)
    assert list(df.columns) == ["year", "uf", "income"]
    assert df["year"].tolist() == ["2012", "2013"]
    assert df["uf"].tolist() == [31, 35]
    assert df["income"].tolist() == [1234.0, 987.0]


def test_read_columns_all_is_the_default(tmp_path):
    path = _sample(tmp_path)
    assert list(mp.read(path, LAYOUT).columns) == list(LAYOUT)
    assert list(mp.read(path, LAYOUT, columns="all").columns) == list(LAYOUT)
    assert list(mp.read(path, LAYOUT, columns=None).columns) == list(LAYOUT)


def test_read_columns_subset_and_unknown_name(tmp_path):
    path = _sample(tmp_path)
    df = mp.read(path, LAYOUT, columns=["uf"])
    assert list(df.columns) == ["uf"]
    with pytest.raises(KeyError, match="not in the dictionary"):
        mp.read(path, LAYOUT, columns=["nope"])


def test_read_accepts_two_element_positions(tmp_path):
    df = mp.read(_sample(tmp_path), {"year": (1, 4)})
    assert df["year"].tolist() == ["2012", "2013"]


def test_microdata_uncached_with_update_false_raises(tmp_path):
    """update=False must never start a download, the way load() documents it."""
    class _Cfg:
        data_dir = tmp_path

    spec = catalog.get(next(n for n in catalog.names()
                            if catalog.get(n).source == "microdados_pnad"))
    adapter = get_source("microdados_pnad")
    with pytest.raises(FileNotFoundError, match="not cached yet"):
        adapter.materialize(spec, _Cfg(), update=False)


def test_microdata_cached_with_update_false_is_offline(tmp_path):
    """An extracted package is reused without touching the network."""
    class _Cfg:
        data_dir = tmp_path

    spec = catalog.get("PNAD microdados - 201201_new")
    target = tmp_path / "microdados_pnad"
    target.mkdir(parents=True)
    (target / "201201_new.txt").write_text("record\n", encoding="ascii")

    paths = get_source("microdados_pnad").materialize(spec, _Cfg(), update=False)
    assert [p.name for p in paths] == ["201201_new.txt"]


@pytest.mark.parametrize("values,dtype,expected_kind", [
    (pd.Series(["12", "34"], dtype=object), "int", "Int64"),
    (pd.Series(["12", "  "], dtype=object), "int", "Int64"),
    (pd.Series(["12", "  "], dtype="string[python]"), "int", "Int64"),
    (pd.Series([], dtype=object), "int", "Int64"),
    (pd.Series(["1" * 25], dtype=object), "int", "float64"),   # too wide: degrades
    (pd.Series(["1.5"], dtype=object), "int", "float64"),      # not whole: degrades
    (pd.Series(["12", "ab"], dtype=object), "float", "float64"),
])
def test_to_number_never_raises_whatever_the_dtype(values, dtype, expected_kind):
    """astype("Int64") blows up on object, oversized and fractional input."""
    out = mp._to_number(values, "field", dtype)
    assert str(out.dtype) == expected_kind


def test_refine_dtypes_rescues_weights_declared_as_integers(tmp_path):
    """IBGE declares the PNADC weights integer but stores them with decimals.

    Trusting the declaration makes polars null them out and pandas warn 202
    times; sampling the data settles it silently.
    """
    path = tmp_path / "w.txt"
    path.write_text("2012123456789  1234.5678931\n"
                    "2012123456790  2234.5678935\n", encoding="ascii")
    layout = {"Ano": (1, 4, "int"), "UPA": (5, 13, "int"),
              "V1027": (14, 25, "int"), "UF": (26, 27, "str")}
    refined = mp._refine_dtypes(path, mp._normalize_layout(layout))
    assert refined["V1027"][2] == "float"      # decimals spotted
    assert refined["Ano"][2] == "int"          # genuine integers untouched
    assert refined["UPA"][2] == "int"

    df = mp.read(path, layout)
    assert df["V1027"].tolist() == [1234.56789, 2234.56789]   # not nulled
    assert str(df["UPA"].dtype) == "Int64"                    # ids stay integer


def test_refine_dtypes_demotes_values_too_wide_for_int64(tmp_path):
    path = tmp_path / "big.txt"
    path.write_text(("9" * 25) + "\n", encoding="ascii")
    refined = mp._refine_dtypes(path, mp._normalize_layout({"x": (1, 25, "int")}))
    assert refined["x"][2] == "float"


def test_check_layout_only_flags_records_wider_than_the_layout(tmp_path):
    """Short records are normal: IBGE strips trailing blanks (SAS MISSOVER)."""
    path = tmp_path / "f.txt"
    path.write_text("1234567890\n1234567890\n", encoding="ascii")   # 10 wide
    short = mp.check_layout(path, {"a": (1, 4), "BRANCOS": (5, 40)})
    assert not short["overflow"]        # merely padded: not a problem
    wide = mp.check_layout(path, {"a": (1, 4)})
    assert wide["overflow"]             # file has data the layout ignores


def test_check_layout_flags_a_misaligned_dictionary(tmp_path):
    path = tmp_path / "f.txt"
    path.write_text("1234567890\n1234567890\n", encoding="ascii")   # 10 wide
    ok = mp.check_layout(path, {"a": (1, 4), "b": (5, 10)})
    assert ok["matches"] and ok["file_width"] == 10 and ok["declared_width"] == 10
    bad = mp.check_layout(path, {"a": (1, 4), "b": (5, 40)})
    assert not bad["matches"] and bad["declared_width"] == 40


def test_sas_input_parser():
    texto = """
    INPUT
    @0001  Ano        $4.
    @0005  Trimestre  $1.
    @0006  UF          2.
    @0008  V1028       9.8
    ;
    """
    layout = mp._parse_sas_input(texto)
    assert layout["Ano"] == (1, 4, "str")
    assert layout["Trimestre"] == (5, 5, "str")
    assert layout["UF"] == (6, 7, "int")
    assert layout["V1028"] == (8, 16, "float")


def test_sas_input_parser_handles_the_char_spelling():
    """The 1992-1999 annual inputs write $CHAR2. where PNADC writes $2."""
    texto = """
    INPUT
    @1   V0101   $CHAR2.   /* ANO DA PESQUISA  */
    @3   UF      $CHAR2.   /* UF               */
    @5   CONTROL $CHAR6.   /* NUMERO DE CONTROLE */
    @11  V0103   $CHAR3.   /* NUMERO DE SERIE  */
    @16  V0105        2.   /* TOTAL MORADORES  */
    """
    layout = mp._parse_sas_input(texto)
    assert layout["V0101"] == (1, 2, "str")
    assert layout["CONTROL"] == (5, 10, "str")
    assert layout["V0105"] == (16, 17, "int")


class _FakeHTTP:
    """Stands in for the FTP: the catalogued name is gone, a newer one is there."""

    LISTING = (
        '<a href="input_PNADC_2025_visita1_20260923.txt">x</a>'
        '<a href="dicionario_PNADC_microdados_2025_visita1_20260923.xls">x</a>'
        '<a href="PNADC_2025_visita1_20260923.zip">x</a>'
    )

    def head(self, url, **kw):
        raise RuntimeError("404")           # the catalogued URL is dead

    def get(self, url, **kw):
        return type("R", (), {"text": self.LISTING})()


@pytest.mark.parametrize("asked,expected", [
    # a renamed dictionary is a .txt -- matching only .zip/.dat missed it
    ("input_PNADC_2025_visita1_20260508.txt",
     "input_PNADC_2025_visita1_20260923.txt"),
    # and the data package still resolves to the .zip, not the .xls or .txt
    ("PNADC_2025_visita1_20250822.zip", "PNADC_2025_visita1_20260923.zip"),
])
def test_resolve_url_heals_a_rename_keeping_the_file_type(monkeypatch, asked, expected):
    monkeypatch.setattr(mp, "_http", _FakeHTTP())
    got = mp._resolve_url("https://ftp.ibge.gov.br/whatever/" + asked)
    assert got.rsplit("/", 1)[1] == expected


def test_with_keys_splits_a_request_across_the_two_files():
    """V4742 is on the person record, V0105 on the household one."""
    from ubib.microdata import _with_keys

    hh = {"V0101": (1, 2), "V0102": (5, 10), "V0105": (16, 17)}
    pes = {"V0101": (1, 2), "V0102": (5, 10), "V4742": (766, 777)}
    asked = ["V4742", "V0105"]
    assert _with_keys(asked, ["V0101", "V0102"], hh) == ["V0101", "V0102", "V0105"]
    assert _with_keys(asked, ["V0101", "V0102"], pes) == ["V0101", "V0102", "V4742"]


def test_merged_result_returns_only_the_requested_columns():
    """The join keys are plumbing: added to read the files, dropped after."""
    hh = pd.DataFrame({"V0101": ["95"], "UF": ["11"], "V0102": ["001200"],
                       "V0103": ["001"], "V4614": [810.0], "V0105": [5]})
    pes = pd.DataFrame({"V0101": ["95"], "UF": ["11"], "V0102": ["001200"],
                        "V0103": ["001"], "V4729": [378]})
    keys = ["V0101", "UF", "V0102", "V0103"]
    merged = mp.merge_household_person(hh, pes, keys)
    asked = ["V4614", "V0105", "V4729"]
    assert list(merged[[c for c in asked if c in merged.columns]].columns) == asked


def test_roles_fall_back_to_record_width_when_names_say_nothing():
    """A household record is always far shorter than a person record."""
    narrow = {f"v{i}": (i + 1, i + 1, "str") for i in range(60)}
    wide = {f"w{i}": (i + 1, i + 1, "str") for i in range(800)}
    roles = mp._assign_roles([("ARQ_A.txt", wide), ("ARQ_B.txt", narrow)])
    assert len(roles["household"]) == 60
    assert len(roles["person"]) == 800


def test_roles_fill_the_empty_slot_by_elimination():
    named = {f"v{i}": (i + 1, i + 1, "str") for i in range(60)}
    other = {f"w{i}": (i + 1, i + 1, "str") for i in range(800)}
    roles = mp._assign_roles([("INPUT DOM2001.txt", named), ("mystery.txt", other)])
    assert roles["household"] is named and roles["person"] is other


def test_roles_refuse_to_guess_when_there_are_too_many():
    lay = {f"v{i}": (i + 1, i + 1, "str") for i in range(60)}
    with pytest.raises(RuntimeError, match="could not tell which layout"):
        mp._assign_roles([("a.txt", lay), ("b.txt", lay), ("c.txt", lay)])


def test_input_role_is_found_mid_filename():
    """Inputs are named 'INPUT DOM2001.txt', so ^DOM would never match."""
    assert mp._input_role("INPUT DOM2001.txt") == "household"
    assert mp._input_role("input PES2011.txt") == "person"
    assert mp._input_role("SasDom97.txt") == "household"
    assert mp._input_role("SAS_PES99.txt") == "person"
    # 1996 names its layouts after its data files: D96BR / P96BR. No word
    # boundary before the letter -- "_" is a word char, so \bD never matches.
    assert mp._input_role("SAS_D96BR.txt") == "household"
    assert mp._input_role("SAS_P96BR.txt") == "person"
    assert mp._input_role("input_PNADC_2012_a_2014_visita1.txt") == "single"


def test_merge_keys_are_derived_and_case_insensitive():
    """1999 declares v0102 in one file and V0102 in the other."""
    household = {"V0101": (1, 2), "UF": (3, 4), "v0102": (5, 10),
                 "V0103": (11, 13), "V0105": (16, 17)}
    person = {"V0101": (1, 2), "UF": (3, 4), "V0102": (5, 10),
              "V0103": (11, 13), "V0301": (14, 15)}
    pairs = mp.merge_keys(household, person)
    assert pairs == [("V0101", "V0101"), ("UF", "UF"),
                     ("v0102", "V0102"), ("V0103", "V0103")]


def test_merge_attaches_household_to_every_person():
    household = pd.DataFrame({"V0102": ["a", "b"], "V0105": [2, 1]})
    person = pd.DataFrame({"V0102": ["a", "a", "b"], "V0301": [1, 2, 1]})
    merged = mp.merge_household_person(household, person, ["V0102"])
    assert len(merged) == 3                      # one row per person
    assert merged["V0105"].tolist() == [2, 2, 1]  # household repeated


def test_merge_refuses_a_key_that_is_not_unique_per_household():
    household = pd.DataFrame({"V0102": ["a", "a"], "V0105": [2, 3]})
    person = pd.DataFrame({"V0102": ["a"], "V0301": [1]})
    with pytest.raises(Exception):               # pandas validate="many_to_one"
        mp.merge_household_person(household, person, ["V0102"])


def test_merge_reports_keys_that_were_not_read():
    household = pd.DataFrame({"V0105": [1]})
    person = pd.DataFrame({"V0301": [1]})
    with pytest.raises(KeyError, match="were not read"):
        mp.merge_household_person(household, person, ["V0102"])


def test_lrecl_only_complains_when_the_layout_overflows_it():
    """lrecl is a read buffer and is often rounded up; only overflow is wrong."""
    caplog = []
    layout = {"a": (1, 100, "str")}
    mp._check_lrecl(layout, "infile x lrecl=4000;", "ok.txt")      # no warning
    mp._check_lrecl({"a": (1, 5000, "str")}, "lrecl=4000;", "bad.txt")
    assert caplog == []                                           # no exception


def test_layout_validation_rejects_garbage():
    """Too few variables means the format changed and nothing was understood."""
    with pytest.raises(RuntimeError, match="format has changed"):
        mp._validate_layout({"a": (1, 2, "str")}, "x.txt")


def test_layout_validation_accepts_deliberate_overlaps():
    """UF (5,6) sits inside V0102 (5,12) on purpose -- IBGE exposes both."""
    layout = {f"v{i}": (10 + i, 10 + i, "str") for i in range(12)}
    layout.update({"V0102": (5, 12, "str"), "UF": (5, 6, "str")})
    assert mp._validate_layout(layout, "x.txt") is layout
