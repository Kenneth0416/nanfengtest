---
name: read-table
description: Read open-data tables and APIs (Bank of England, ONS, Nomis, GLA, VOA, EPC, City of London) from CSV, Excel or JSON and save the series the team uses.
---
1. Only for 🟢 sources (Open Government Licence or similar). Keep the publisher and licence for attribution.
2. `read_table(source)`: look at the columns and the first rows. Many official files have header rows
   above the table: retry with `skiprows`. Excel files may need a `sheet`.
3. Work out which column is the date, which the value and the unit. Ignore notes rows and totals.
4. Keep only what the team uses: interest rates and gilt yields, London employment and unemployment,
   office floorspace and rateable values, development pipeline schemes, energy ratings of offices.
5. `save_series(source_id, publisher, title, url, licence, rows=[{date, indicator, value, unit}])`.
   Use stable indicator names (bank_rate, gilt_10y, london_unemployment_pct, ...).
6. If a value falls far outside its recent range, save it with a note and say so; do not drop it.
7. A spreadsheet of OUR OWN deals (a colleague's export, columns like property / tenant / rent / term)
   is 🔵 internal data, not open data: `deals_from_table(path, sheet)` files one internal record per row
   (see read-photo); never save_series.
