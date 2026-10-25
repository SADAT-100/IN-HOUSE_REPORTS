# In-House Noon Reports

One page for both In House accounts on Noon KSA. It opens on an animated "In-House Noon Reports" intro with two cards, Bulky (account 18947) and Courier (account 12539). Picking a card opens that account's full portal. Inside the portal, the Account switch in the side menu and the account button in the top bar change accounts or bring the intro back.

Each account keeps its own date range, delivery type filter and last page. The theme is shared.

To rebuild it after the account data changes (see `../noon-portal/README.md` for making each data file):

```
python3 ../noon-portal/tools/build.py bulky-data.json courier-data.json index.html
```
