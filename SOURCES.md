# Data sources

Ubib provides one adapter per data provider. Each row in the catalog names the
`source` it comes from; this document describes every source the library covers.

**Access legend**

- **Open** — no authentication required.
- **API key** — needs a free key in your config `api_keys` (see the README).
- **Login** — needs free registration credentials in your config `credentials`.
- **Terminal** — needs a Bloomberg terminal and the `xbbg`/`blpapi` packages.

## Brazil

| `source` | Provider | Coverage | Access | `code` format |
|----------|----------|----------|--------|---------------|
| `sgs` | Banco Central do Brasil (SGS) | Interest rates, FX, monetary and credit aggregates, and thousands of other series | Open | Numeric series id (e.g. `433`) |
| `sidra` | IBGE (SIDRA) | National accounts, inflation (IPCA/INPC), employment, industrial and agricultural production | Open | SIDRA values query path |
| `ipea` | IPEADATA | Curated macroeconomic and regional series | Open | `SERCODIGO` |
| `olinda` | Banco Central do Brasil (Focus) | Market expectations (median forecasts) for inflation, GDP, Selic, FX, etc. | Open | Indicator name (e.g. `IPCA`) |
| `comexstat` | MDIC (ComexStat) | Foreign trade — exports and imports | Open | `flow/discriminator/value` |
| `anp` | ANP | Oil, gas and fuel statistics | Open | Page keyword + sheet parameters |
| `anac` | ANAC | Air transport demand and supply | Open | Sheet/row parameters |
| `caged` | MTE / PDET (Novo CAGED) | Formal employment (hirings, dismissals, balances) | Open | Sheet parameters |
| `cielo` | Cielo | ICVA expanded retail index | Open | — |
| `tesouro_direto` | Tesouro Nacional | Government bond prices and yields | Open | File id + sheet |
| `tesouro_rmd` | Tesouro Nacional | Monthly public-debt report (RMD) | Open | Sheet/column parameters |
| `tesouro_rtn` | Tesouro Nacional | National Treasury result (RTN) | Open | Sheet/column parameters |
| `microdados_pnad` | IBGE (FTP) | PNAD **microdata** — one row per person/household, 1976-2026 | Open | Full URL of the package on the IBGE FTP |

## United States

| `source` | Provider | Coverage | Access | `code` format |
|----------|----------|----------|--------|---------------|
| `fred` | Federal Reserve Bank of St. Louis (FRED) | Broad macroeconomic and financial database | API key | FRED series id (e.g. `GDP`) |
| `bls` | Bureau of Labor Statistics | Prices (CPI), employment, wages | API key | BLS series id (e.g. `CUUR0000SA0`) |
| `bea` | Bureau of Economic Analysis | National accounts (NIPA), GDP components | API key | `DataSet,Table,Freq,SeriesCode` |
| `us_census` | U.S. Census Bureau | Economic indicators time series (EITS) | API key | JSON query object |

## Europe

| `source` | Provider | Coverage | Access | `code` format |
|----------|----------|----------|--------|---------------|
| `ecb` | European Central Bank (Data Portal) | Rates, monetary statistics, exchange rates | Open | `FLOW/KEY` |
| `eurostat` | Eurostat | EU-wide economic and social statistics | Open | JSON `{table, params}` |
| `ons` | UK Office for National Statistics | UK macroeconomic statistics | Open | JSON query object |
| `ine_spain` | INE (Spain) | Spanish economic statistics | Open | JSON query object |

## Latin America

| `source` | Provider | Coverage | Access | `code` format |
|----------|----------|----------|--------|---------------|
| `inegi` | INEGI (Mexico) | Mexican economic indicators | API key (token) | Indicator id |
| `banxico` | Banco de México (SIE) | Mexican monetary and financial series | API key (token) | Series id |
| `bcch` | Banco Central de Chile | Chilean macroeconomic series | Login | JSON `{series_code}` |

## Asia-Pacific & Canada

| `source` | Provider | Coverage | Access | `code` format |
|----------|----------|----------|--------|---------------|
| `abs` | Australian Bureau of Statistics | Australian economic statistics | Open | JSON query object |
| `statcan` | Statistics Canada (WDS) | Canadian economic statistics | Open | Vector id (e.g. `v41690973`) |

## International

| `source` | Provider | Coverage | Access | `code` format |
|----------|----------|----------|--------|---------------|
| `worldbank` | World Bank (WDI) | World development indicators by country | Open | Country code + indicator code |
| `imf` | International Monetary Fund | IFS and other IMF datasets | Open | `DATASET/KEY` |

## Licensed

| `source` | Provider | Coverage | Access | `code` format |
|----------|----------|----------|--------|---------------|
| `bloomberg` | Bloomberg (via `xbbg`) | Securities, indices, fundamentals and any Bloomberg field | Terminal | `TICKER,FIELD` |

---

Several Brazilian sources publish their data as spreadsheets behind their
websites; for those, the catalog's `params` column carries the sheet/column
hints the adapter needs. Most other sources are JSON or CSV web APIs.

## Microdata sources

One source in the table above is not a time series at all. `microdados_pnad`
delivers the raw PNAD survey files: fixed-width tables with one **person or
household per row**, no header and no delimiter, hundreds of megabytes each.

Because `ubib.load()` would index them by date and coerce every field to a
number — destroying them — these entries are reached through a separate
function, `ubib.microdata()`, which downloads, unpacks and reads the file into
a DataFrame. `ubib.microdata_files()` returns the paths instead.

| | |
|---|---|
| Entries | 105 — 58 quarterly (PNAD contínua, 2012Q1-2026Q2), 12 annual visita 1 (2012-2025, no 2020/2021) and 35 annual (PNAD antiga, 1976-2015) |
| Naming | `PNAD microdados - 201201_new` (quarterly), `- 2023_visita1` (annual visita 1), `- 1992_old` (annual) |
| Stored at | `data_dir/microdados_pnad/`, as `.txt` |
| `params` | `{"key": ..., "expect": "single" \| "household_person" \| "metro_regions", "survey": "continuous" \| "continuous_annual" \| "annual"}`, plus `layout_url` where the dictionary has its own address — checked against what IBGE actually ships |

### Splitting the columns

The files are fixed-width with no header, so the field positions come from
IBGE's variable dictionary — the reader will not guess them.

Where that dictionary lives differs by era, and all four cases are resolved
automatically:

| entries | dictionary |
|---|---|
| quarterly `*_new` | one SAS input for the whole series, cached as `pnadc_layout.json` |
| `*_visita1` | one input per year, its URL carried in the catalog row |
| `*_old` 2001-2012 | bundled inside the data package, captured while unpacking |
| `*_old` 1992-1999, 2013-2015 | sibling `Layout.zip` / `Dicionarios_e_input_*.zip`, found by listing the year's folder |

The exception is 1976-1990, published only as Word documents. Those return no
layout and say so; pass `layout={...}` or take the file with
`microdata_files()`.

Every parsed layout is cross-checked against the `LRECL` the input file
declares, which is a free and independent confirmation that the positions were
read correctly.

The two files of an annual year are merged into one table by default
(`merge=False` keeps them apart). The key is derived from the layouts rather
than hardcoded, because it changed across eras — `CONTROL`+`V0103` in 1992,
`V0102`+`V0103` from 2001 — and because IBGE's own capitalisation differs
between the two files of the same year (`v0102` vs `V0102` in 1999).

Reading is done by slicing each line by position, vectorised — with polars when
it is installed, pandas otherwise. Both avoid `read_fwf`, which is several
times slower on files of this size.

Field types come from the data as well as the dictionary: IBGE declares the
survey weights (`V1027`, `V1028`, and `V1028001`-`V1028200`) as integers but
stores them with decimals, so the first lines are sampled and those fields are
read as float. A record is 3,478 characters wide with 420 variables, and a
quarter holds around 570,000 of them.

The packages are not uniform, in two ways.

*What they hold:* one file, or a household file plus a person file, or eight
files (1983 and 1988, one per metropolitan region, concatenated on extraction).

*Where they hold it:* the annual packages keep the microdata in a `Dados`
folder — under the year's folder for 2001-2012 — alongside documentation and
questionnaires. The quarterly PNAD contínua packages have no folder at all: the
file sits at the root of the zip. So the adapter uses the `Dados` folder when
the package has one and the archive root when it does not, with the package's
own name breaking any tie.

`.DAT`, `.TXT` and extensionless members are all plain ASCII and are normalised
to `.txt`. The imputation-flag files that ship alongside the 2007, 2009, 2011
and 2012 data are excluded.

Reading the files needs the variable dictionary IBGE publishes as
`Documentacao.zip` beside each year's data — see the README.
