# Data

`data/raw/` is not versioned. Generate the synthetic base with:

```bash
collection-plan generate-data            # or: python -m collection_plan generate-data
```

## History base (`history.csv`)

One row per base x month x region x tool x stage.

| Column | Type | Values |
|---|---|---|
| `base` | text | `target` (12 months) or `actual` (months up to the cut-off) |
| `month` | date | first day of the month |
| `region` | text | `Capital`, `North`, `South`, `East`, `West` |
| `tool` | text | `field_disconnection`, `re_disconnection`, `special_notice`, `remote_disconnection`, `field_visit` |
| `stage` | text | `selected`, `executed`, `paid` |
| `qty` | number | customers / actions |
| `value` | number | debt amount (currency units) |

To use real data, export it in this format (a CSV with these columns) and point the CLI to it:
`collection-plan run --data path/to/history.csv`. Keep real files out of the repository.
