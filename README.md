# Ubib

**Ubib** is a unified, systematic way to import economic data — public data from
central banks, statistics offices and multilateral institutions, plus Bloomberg
for licensed users. One catalog, one function, one storage format.

- **One function to learn:** `ubib.load(...)`.
- **One catalog:** ~9,300 series in a single Excel workbook shipped with the package.
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
├── api.py            # load() / update() — the public API
├── config.py         # define_config / get_config (~/.ubib/config.toml)
├── catalog.py        # reads metadata.xlsx
├── storage.py        # one parquet file per series
├── sources/          # one module per provider + the registry
└── transform/        # frequency handling
```
