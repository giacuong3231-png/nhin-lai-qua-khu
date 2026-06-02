# Manual CSVs — delisted / un-fetchable tickers

Some tickers cannot be pulled from any live API and must be supplied by hand.
The clearest example is **ROS (FLC Faros)**: it was delisted from HOSE in 2022,
and `vnstock` removes the price history of delisted symbols — calling the API for
ROS returns nothing (and historically could even break the run). So the pipeline
**never** calls an API for these; `normalize.py` reads the CSV directly from this
folder. This same mechanism works for any future delisted ticker.

These files are intentionally committed to git (see `.gitignore`) because they
are not reproducible from the pipeline.

## File format

Place a file named `<TICKER>.csv` in this directory, e.g. `ROS.csv`.

| column  | meaning                                              |
|---------|------------------------------------------------------|
| `date`  | trading date, `YYYY-MM-DD` (e.g. `2016-09-01`)       |
| `close` | closing price **in VND** (full dong, NOT thousands)  |

- Header row required. Column names are case-insensitive; `time`/`price` are also
  accepted as aliases for `date`/`close`.
- One row per trading day. Gaps are fine — `normalize.py` forward-fills onto the
  shared daily axis.
- Price must already be in **VND** (e.g. a ROS price of 2,500 VND is written as
  `2500`, not `2.5`). No currency conversion or thousands-scaling is applied to
  manual series.
- Rows with non-numeric or non-positive prices are dropped.

### Example `ROS.csv`

```csv
date,close
2016-09-01,12500
2016-09-02,12800
2016-12-01,11500
2017-11-03,180000
2022-08-31,3500
```

## Sourcing the data

For ROS, historical adjusted closing prices (2016–2022) can be exported from
CafeF or FireAnt historical-price pages. If the CSV is absent, the pipeline logs
`ROS manual CSV missing — skipped` and continues without it.
