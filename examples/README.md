# Example exports

These files are synthetic. They were written by hand for the tests and the README demo, for an
invented site (example.com). No real Search Console or Bing data is in this repo.

The column headers are illustrative. Neither vendor publishes the exact headers of its export,
so this tool finds columns by alias and lets you set them by hand. See the main README.

Things the data is built to show:

- `gsc/Pages.csv` holds the page table. `Countries.csv`, `Devices.csv` and `Dates.csv` have no
  page column, so they cannot be joined and are skipped.
- `bing/cited-pages.csv` writes some URLs differently (http, www, trailing slash, a utm
  parameter). They still join.
- `bing/queries-by-page.csv` is a query-to-page table. One page (`/tools/checker`) appears only
  here, so its citation total is a sum of query rows.
- `bing/grounding-queries.csv` is a plain query table. One query in it maps to no page.
