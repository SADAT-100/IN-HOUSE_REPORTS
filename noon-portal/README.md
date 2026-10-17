# Noon Courier Portal

Reporting portal for the In House store on Noon KSA, courier account 12539, run by channel managers Fedaa, Ayham and Sham: sales, orders, products, payouts, fees and ads, returns, and delivery. Every profit figure is shown twice, in the Noon view (Noon's own fee columns) and the In House view (the adjusted Comm, Shipping and subsidy columns).

Open `index.html` in a browser. The data from the workbook "Sales KSA 2026 2.xlsx" (orders 1 Jan to 19 Sep 2026) is built into the page. Uploading new data from the page will come once the standard Noon export is agreed.

To rebuild from a new workbook:

```
python3 tools/prepare_data.py "Sales KSA 2026 2.xlsx" data.json
python3 tools/build.py data.json index.html
```

- `index.html`: the portal, with data embedded
- `tools/prepare_data.py`: reads the workbook tabs into a compact data file (courier 12539 or bulky 18947, picked from the PS- tab name)
- `tools/build.py`, `tools/css.part`, `tools/body.part`: assemble the page. Give `build.py` two data files (bulky, then courier) to build the combined page in `../noon-reports/`.
