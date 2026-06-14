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
