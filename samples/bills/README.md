# Sample bills

Synthetic statements built from the real published prices in
`data/a3_reference_table.csv`, with problems planted deliberately so each check has
something to find. Every file is marked SYNTHETIC on its face.

All are for **Doylestown Hospital** - pick that in the Bill tab, or the price
comparison has nothing to compare against.

| File | What it is for | Total |
|---|---|---|
| `01_overcharged` | Lines billed above the hospital's own published price. | $12,990.14 |
| `02_duplicate` | The same code posted twice on one statement. | $4,929.00 |
| `03_quantity` | A visit-level code billed ten times over. | $16,590.00 |
| `04_unspecified` | An unclassified drug code that declines to say what was given. | $6,679.00 |
| `05_ambulance` | Includes a ground ambulance line - the federal carve-out. | $5,756.00 |
| `06_summary_not_itemised` | A summary with no billing codes - should be rejected. | $9,600.00 |
| `07_clean` | Every line exactly at the published price - nothing should flag. | $3,532.00 |

Rebuild with `python3 tools/make_sample_bills.py`.
