# Ubib

**Ubib** is a unified, systematic way to import economic data — public data from
central banks, statistics offices and multilateral institutions, plus Bloomberg
for licensed users. One catalog, one function, one storage format.

- **One function to learn:** `ubib.load(...)` — plus `ubib.microdata(...)` for survey microdata.
- **One catalog:** ~9,900 entries in a single Excel workbook shipped with the package.
- **One config:** your keys and data folder in `~/.ubib/config.toml`.
- **One storage format:** every series cached as a single Parquet file.

---

## Install

Install straight from GitHub:

```bash
# core (all public sources)
pip install git+https://github.com/klaus-oehling/Ubib.git

# with Bloomberg support (needs a terminal; see below)
pip install "ubib[bloomberg] @ git+https://github.com/klaus-oehling/Ubib.git"
```

For development, clone and install in editable mode:

```bash
git clone https://github.com/klaus-oehling/Ubib.git
cd Ubib
pip install -e .
```

`pip install` writes nothing to your home folder and stores no keys.

---

## Quick start

```python
import ubib

# 1) Configure once (writes ~/.ubib/config.toml)
ubib.define_config(
    data_dir="~/ubib_data",
    api_keys={"fred": "YOUR_FRED_KEY", "bls": "YOUR_BLS_KEY"},
)

# 2) Download and use data
s  = ubib.load("10YTEASURY", update=True)              # one series -> Series
df = ubib.load(["10YTEASURY", "US GDP"], update=True)  # several   -> DataFrame
s  = ubib.load("10YTEASURY")                           # later: instant, from cache
```

---

## Configuration

The library stores no keys of its own. You configure it once, from Python.

### `ubib.define_config(data_dir, *, api_keys=None, credentials=None, config_path=None)`

Creates (or overwrites) `~/.ubib/config.toml`. Returns nothing.

| argument | meaning |
|----------|---------|
| `data_dir` | Folder where downloaded series are cached (created if missing). |
| `api_keys` | `{source: key}` mapping. Recognised: `fred`, `bls`, `bea`, `inegi`, `banxico`, `us_census` (`ubib.API_KEY_NAMES`). |
| `credentials` | `{name: value}` for login-based sources (e.g. `bcch_user`, `bcch_password`; `ubib.CREDENTIAL_NAMES`). |
| `config_path` | Alternate location to write to. Defaults to `UBIB_CONFIG` env var or `~/.ubib/config.toml`. |

```python
ubib.define_config(
    data_dir="~/ubib_data",
    api_keys={"fred": "...", "bls": "...", "bea": "..."},
    credentials={"bcch_user": "you@example.com", "bcch_password": "..."},
)
```

### `ubib.get_config()`

Returns the saved `Config` object (raises a clear error if you haven't called
`define_config` yet). The `Config` exposes:

```python
cfg = ubib.get_config()
cfg.data_dir                       # Path to the data cache
cfg.config_path                    # Path to config.toml
cfg.api_key("fred")                # a key, or None
cfg.credential("bcch_user")        # a credential, or None
cfg.series_path("fred", "US GDP")  # Path of a cached series' parquet file
```

### `ubib.template_text()`

Returns the shipped blank config template as a string (reference only).

---

## Loading data

### `ubib.load(series, *, update=False, frequency=None, format_index=True, config=None)`

The one function you'll use most. All options are keyword-only and validated.

**`series`** — what to load; the return type follows the input:

```python
ubib.load("US GDP")                                  # str  -> a pandas Series
ubib.load(["US GDP", "10YTEASURY"])                  # list -> a DataFrame (these columns)
ubib.load({"GDP": "US GDP", "10y": "10YTEASURY"})    # dict -> a DataFrame (your labels)
```

**`update`** (`bool`, default `False`)

- `False` → read from the local cache (raises if the series isn't cached yet).
- `True` → download fresh from the source, save to cache, and return it.

```python
ubib.load("US GDP", update=True)   # first time / refresh
ubib.load("US GDP")                # afterwards: instant, from disk
```

**`frequency`** (`"D"`/`"M"`/`"Q"`/`"A"` or `None`) — resample to this frequency,
keeping the last observation in each period. Applied on **every** call, including
cached reads, so you can re-aggregate without re-downloading:

```python
ubib.load("10YTEASURY", frequency="Q")   # cached monthly data -> quarterly
```

**`format_index`** (`bool`, default `True`)

- `True` → align dates to period-end at the declared/detected frequency.
- `False` → return the raw dates exactly as the source provided them.

**`config`** — optional `Config` to use instead of your saved one (mainly for tests).

Errors are immediate and specific: a wrong positional or wrong-typed option
raises `TypeError`/`ValueError`, and an unknown series name raises `KeyError`
listing it — all before any network call.

### `ubib.update(series, **kwargs)`

Shorthand for `load(series, update=True, **kwargs)`.

---

## Discovering what's available

### `ubib.available_series()`
List of every series name in the catalog (the keys you pass to `load`).

### `ubib.available_sources()`
List of every supported source id (see `SOURCES.md`).

### `ubib.available_microdata()`
List of every microdata entry (the keys you pass to `microdata`, not `load`).

### `ubib.info(name)`
Catalog metadata for one series:

```python
ubib.info("US GDP")
# {'name': 'US GDP', 'source': 'fred', 'code': 'GDP',
#  'params': {}, 'frequency': None, 'description': '...'}
```

---

## Where data is stored

One Parquet file per series at `data_dir/<source>/<name>.parquet`, each with a
`Date` index and a single value column. You can read them directly:

```python
import pandas as pd
pd.read_parquet(ubib.get_config().series_path("fred", "US GDP"))
```

Microdata is the exception: those files stay in their original fixed-width text
form under `data_dir/microdados_pnad/`, since parquet and a `Date` index do not
apply to them. See [Microdata](#microdata).

---

## The catalog

The catalog is the Excel workbook `src/ubib/data/metadata.xlsx`, one sheet
(`series`), one row per series:

| column | meaning |
|--------|---------|
| `name` | Unique key you pass to `ubib.load`. |
| `source` | Adapter id (`sgs`, `fred`, `bloomberg`, …). |
| `code` | Source identifier (series id, `TICKER,FIELD`, JSON params, …). |
| `params` | Optional JSON with extra parsing parameters. May be blank. |
| `frequency` | Optional `D`/`M`/`Q`/`A` override of auto-detection. |
| `description` | Optional human-readable label. |

To add your own series, append a row and refresh the in-memory catalog:

```python
import ubib.catalog as catalog
catalog.reload()
```

---

## Microdata

Some entries are not time series: PNAD **microdata** is a fixed-width table with
one person or household per row, no header, no delimiter, hundreds of megabytes
per file. `ubib.load()` would index it by date and coerce every field to a
number, which would destroy it — so microdata has its own entry point,
`ubib.microdata()`, which returns a DataFrame.

### `ubib.microdata(series, *, columns="all", layout=None, update=False, verbose=True, config=None)`

Downloads (once), unpacks and reads the file into a DataFrame.

```python
import ubib

df = ubib.microdata("PNAD microdados - 202401_new")
df = ubib.microdata("PNAD microdados - 202401_new",
                    columns=["Ano", "Trimestre", "VD4020"])   # much faster
```

| argument | meaning |
|----------|---------|
| `series` | An entry name, or a list/dict of them. |
| `columns` | `"all"` (default) or a list of variable names. A quarter has ~400 variables; naming the handful you need is far faster and lighter. |
| `layout` | `{variable: (start, end[, dtype])}`, 1-based. Only needed for the annual PNAD (see below). |
| `update` | `False` reads what is already extracted and never touches the network, raising `FileNotFoundError` if nothing is there; `True` downloads. |
| `verbose` | One line per entry, with a progress bar when there are several. |
| `config` | Alternate `Config`. |

Returns a `DataFrame` for a one-file package, `{"household": df, "person": df}`
for a two-file one, and `{name: …}` when you pass several entries.

### Where the columns come from

These files are **fixed-width with no header** — no separator to split on — so
the column positions come from IBGE's variable dictionary.

- **PNAD contínua (`*_new`)**: IBGE publishes one input file covering every
  quarter. Ubib fetches and caches it automatically; you pass nothing.
- **PNAD anual visita 1 (`*_visita1`)**: one input file per year, whose URL the
  catalog carries. Fetched automatically.
- **PNAD anual (`*_old`)**: 2001-2012 bundle their input files inside the data
  package itself; 1992-1999 and 2013-2015 ship them in a sibling `Layout.zip` /
  `Dicionarios_e_input_*.zip`, found by listing the year's folder. All resolved
  automatically.
- **1976-1990**: IBGE published these only as Word documents, so there is no
  machine-readable layout. Those entries say so and point you at
  `microdata_files()`; pass `layout={...}` if you transcribe the positions
  yourself. Nothing is ever guessed.

### Household and person

The annual PNAD ships two files per year, and `microdata()` returns them merged
by default: one row per person, with their household's columns attached.

```python
df = ubib.microdata("PNAD microdados - 1992_old")                 # merged
raw = ubib.microdata("PNAD microdados - 1992_old", merge=False)   # {"household":…, "person":…}
```

The merge key is derived, not hardcoded, because it changed over the decades —
1992 uses `CONTROL`+`V0103`, 2001-2015 use `V0102`+`V0103` — and IBGE is not
even consistent about capitalisation (`v0102` in the 1999 household file,
`V0102` in its person file). Every variable appearing in both layouts at the
same position is taken as the household identifier, matched case-insensitively.
The merge is validated many-to-one and refuses to run if the key does not
identify a household uniquely, so it cannot quietly multiply rows.

Reading uses polars — the file is read as one column of raw lines and sliced by
position, which is vectorised and runs at roughly disk speed. If polars is
unavailable it falls back to pandas, same logic, several times slower. A quarter
is ~570,000 rows × 420 columns, so on the pandas path the difference is minutes,
not seconds:

```bash
pip install polars
```

Field types are decided from the data, not only from the dictionary. IBGE
declares the survey weights (`V1027`, `V1028` and the 200 replicate weights)
with no decimal places but stores them with decimals, so Ubib samples the first
lines and reads those as float. Taking the declaration at face value would
either null them out or bury you in warnings.

### The variable dictionary on disk

`pnadc_layout.json` in the data folder is the parsed dictionary: a plain JSON
map of `{variable: [start, end, dtype]}`. IBGE publishes **one** input file for
the whole quarterly series, so that single layout serves every quarter; it is
downloaded once, cached, and re-read from disk afterwards. Delete the file to
force a refresh. When a layout was fetched rather than supplied, its total
width is checked against the file's records on every read, so a quarter whose
record width changed would be flagged instead of silently misread.

The annual PNAD has no such file — its dictionaries are published per year in
formats that are not machine-readable, which is exactly why those entries
require `layout=`.

### `ubib.check_microdata_layout(path, layout)`

A fixed-width file offers one honest check without knowing its variables: the
record width. If the dictionary's last field does not end where the lines end,
the positions do not belong to that file and every column past the mismatch
would be silently wrong.

```python
ubib.check_microdata_layout(path, layout)
# {'declared_width': 414, 'file_width': 414, 'variables': 397, 'matches': True, ...}
```

### `ubib.microdata_files(series, ...)`

Same download and unpacking, but returns the **paths** instead of reading —
for when you would rather parse the file yourself.

```python
caminho = ubib.microdata_files("PNAD microdados - 201201_new")
```

Files are written **only** to `data_dir/microdados_pnad/`, as `1976_old.txt`,
`1992_old_household.txt`, `201201_new.txt`. A second call without
`update=True` reuses what is on disk and touches the network not at all.

The packages IBGE ships are not uniform — one file, or a household plus a
person file, or eight files (one per metropolitan region, concatenated on
extraction). `.DAT`, `.TXT` and extensionless members are all plain ASCII and
come out as `.txt`. Each package is checked against what the catalog declares,
and a mismatch raises rather than guessing.

### `ubib.read_microdata(path, layout, columns="all")`
The reader on its own, for any fixed-width file.

### `ubib.microdata_dir()`
Path of the folder the files are written to.

---

## Bloomberg

Bloomberg series are loaded exactly like any other — `ubib.load("ABSVERT BZ Equity Rendimento", update=True)` — but require a machine with a Bloomberg terminal plus the `xbbg`
and `blpapi` packages (install the `[bloomberg]` extra, then install `blpapi`
from Bloomberg's index). The `code` for these series is `"TICKER,FIELD"`.

---

## Sources

See `SOURCES.md` for a description of every data source the library covers.

## Layout

```
src/ubib/
├── api.py            # load() / update() — the public API for series
├── microdata.py      # microdata() — survey files, returned as paths
├── config.py         # define_config / get_config (~/.ubib/config.toml)
├── catalog.py        # reads metadata.xlsx
├── storage.py        # one parquet file per series
├── sources/          # one module per provider + the registry
└── transform/        # frequency handling
```
