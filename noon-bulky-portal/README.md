# Noon Bulky Portal

Reporting portal for the In House store on Noon KSA, bulky account 18947, run by channel managers Fedaa, Ayham and Sham. It uses the same page as the courier portal (`../noon-portal`), with Noon's numbers and In House's numbers side by side and a delivery type filter (Flex, Direct, New Ansari, FBN, Not set).

Open `index.html` in a browser. The data from the workbook "Sales Bulky 2026.xlsx" (orders 1 Jan to 12 Sep 2026) is built into the page.

To rebuild from a new workbook, use the shared tools in `../noon-portal/tools`:

```
python3 ../noon-portal/tools/prepare_data.py "Sales Bulky 2026.xlsx" data.json
python3 ../noon-portal/tools/build.py data.json index.html
```
