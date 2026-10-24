"""Standard update for the Noon courier report (account 12539).

Put the Noon exports in inputs/courier/, each covering 1 January to today:
  sales-*.csv        Account Health & Reports > Sales export. Several files are merged by item number; the newest file wins.
  finance-*.csv      Payments & Fees > Transaction View Report. The newest file wins.
  statements-*.csv   Payments & Fees statements export (fee names and VAT per statement). Optional; the newest file wins.
  base-from-workbook.json   reference only: unit cost and category per SKU, and the In House fees the workbook had before June 2026.

Usage: python3 -I update_courier.py   -> writes data.json; then build.py as usual.

Rules
  Items        one per sales row. Net proceeds = what Noon credited the item in the finance export, else the sales price.
  Noon view    every fee and subsidy Noon booked against the order or item in the finance export, including later corrections.
  In House     from June 2026 the workbook's model: no commission, +5.00 per item, no subsidy. Before June the workbook's own figures,
               or the Noon view for items the workbook did not have.
  Unit cost    by SKU from the workbook; new SKUs have no cost until one is added (listed when this runs)."""
import csv, json, glob, os, sys, collections, datetime as dt

here = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(here, 'inputs', 'courier')
newest = lambda pat: sorted(glob.glob(os.path.join(IN, pat)), key=os.path.getmtime)
B = json.load(open(os.path.join(IN, 'base-from-workbook.json')))
n = lambda x: float(str(x).replace(',', '')) if x not in (None, '') else 0.0
r2 = lambda x: round(x + 0.0, 2)
read = lambda f: list(csv.DictReader(open(f, encoding='utf-8-sig')))
BASE = dt.datetime(2026, 1, 1)
mins = lambda s: int((dt.datetime.strptime(s.strip()[:19], '%Y-%m-%d %H:%M:%S') - BASE).total_seconds() // 60) if s and s.strip() else None
STATUS = B['meta']['status']; CH = B['meta']['channels']
FUL = {'Fulfilled by Partner (FBP)': 'Flex', 'Fulfilled by Noon (FBN)': 'FBN', 'Supermall': 'Supermall'}
SOLD = {STATUS.index(x) for x in ('Delivered', 'Shipped', 'Processing', 'Pending Confirmation')}; CANCEL = STATUS.index('Cancelled')
IH_FROM = mins('2026-06-01 00:00:00')

# ---------- inputs ----------
sales_files = newest('sales-*.csv'); fin_files = newest('finance-*.csv'); stmt_files = newest('statements-*.csv')
if not sales_files or not fin_files: sys.exit('Need at least one sales-*.csv and one finance-*.csv in ' + IN)
sales = {}
for f in sales_files:
    rows = read(f)
    if 'item_nr' not in rows[0] or 'status' not in rows[0]: sys.exit(f + ' is not a Noon sales export')
    for r in rows: sales[r['item_nr'].strip()] = r
R = read(fin_files[-1])
if not {'Reference Nr', 'Transaction Type', 'Total', 'Item Nr'} <= set(R[0]): sys.exit(fin_files[-1] + ' is not a Noon Transaction View export')
day = lambda s: dt.datetime.strptime(s.strip(), '%m/%d/%Y').date()

# ---------- reference from the workbook ----------
bsku = {s[0]: s for s in B['skus']}
bitem = {it[1] + '-' + str(it[2]): it for it in B['items']}
cost = {}
for it in B['items']: cost.setdefault(B['skus'][it[3]][0], it[11])

# ---------- finance: per item and per order ----------
COLS = [('np', 'Net Proceeds'), ('referral', 'Referral Fee including VAT'), ('fulfil', 'Fullfilment & Logistics Fees including VAT'), ('shipCredit', 'Shipping Credits including VAT'),
        ('otherOrder', 'Other Order Fees including VAT'), ('subsidy', 'Order Subsidies including VAT'), ('nonOrderFee', 'Non-Order Fees including VAT'),
        ('nonOrderSubsidy', 'Non-Order Subsidies including VAT'), ('others', 'Others including VAT'), ('total', 'Total')]
fee = collections.defaultdict(lambda: [0.0, 0.0, 0.0]); fnp = collections.defaultdict(float)
title, ftype = {}, {}
stm, payments, deductions = {}, [], []
acct = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
for r in R:
    tt, d, ref = r['Transaction Type'], day(r['Transaction Date']), r['Reference Nr']
    if r['SKUs'] and r['Item Nr']:
        if r['Title'] and not r['Title'].startswith(('PC', 'PG')): title.setdefault(r['SKUs'], r['Title'].strip())
        if r['Product Fulltype Code']: ftype.setdefault(r['SKUs'], r['Product Fulltype Code'])
    if tt == 'payment': payments.append([d.isoformat(), r2(-n(r['Total']))]); continue
    if tt == 'balance_transfer':
        p = r['Title'].split('-')
        if len(p) >= 5 and {p[0], p[1]} == {'MPABXOQGVZSA', 'MPC7RBR4XHSA'}: continue  # Noon moving money between its own SA and AE contracts
        deductions.append([d.isoformat(), ref, r2(n(r['Total']))]); acct[(d.year, d.month)][2] += n(r['Total']); continue
    s = stm.setdefault(ref, dict({'ref': ref, 'date': d, 'rows': 0, 'orderTotal': 0.0, 'updateTotal': 0.0}, **{k: 0.0 for k, _ in COLS}))
    s['rows'] += 1
    for k, c in COLS: s[k] += n(r[c])
    if tt == 'statement_fee': acct[(d.year, d.month)][0] += n(r['Non-Order Fees including VAT']); acct[(d.year, d.month)][1] += n(r['Non-Order Subsidies including VAT']); continue
    if tt == 'order': s['orderTotal'] += n(r['Total'])
    if tt == 'order_update': s['updateTotal'] += n(r['Total'])
    if r['Order Nr'] in ('', 'NA'): continue
    k = r['Item Nr'].strip() or r['Order Nr']
    f = fee[k]; f[0] += n(r['Referral Fee including VAT'])
    f[1] += n(r['Fullfilment & Logistics Fees including VAT']) + n(r['Shipping Credits including VAT']) + n(r['Other Order Fees including VAT']) + n(r['Others including VAT'])
    f[2] += n(r['Order Subsidies including VAT'])
    if tt == 'order' and r['Item Nr']: fnp[r['Item Nr'].strip()] += n(r['Net Proceeds'])

# category for SKUs the workbook never had: the workbook category most used for the same Noon product type
bycode = collections.defaultdict(collections.Counter)
for sk, code in ftype.items():
    if sk in bsku and bsku[sk][3]: bycode[code][bsku[sk][3]] += 1
def cat_for(sk, family):
    code = ftype.get(sk)
    if code and bycode[code]: return bycode[code].most_common(1)[0][0]
    return (code.split('-')[-1] if code else family or 'Other').replace('_', ' ').title()

# ---------- items ----------
skus, skuIx, items, nocost = [], {}, [], collections.Counter()
def sku_ix(r):
    sk = r['sku'].strip()
    if sk not in skuIx:
        b = bsku.get(sk)
        skuIx[sk] = len(skus)
        skus.append([sk, r['partner_sku'].strip() or (b[1] if b else ''), (b[2] if b and b[2] else title.get(sk, '')), b[3] if b and b[3] else cat_for(sk, r['family']),
                     r['family'] or (b[4] if b else ''), r['brand_code'] or (b[5] if b else '')])
    return skuIx[sk]
by_order = collections.defaultdict(list)
for key in sorted(sales, key=lambda k: (sales[k]['order_timestamp'], k)):
    r = sales[key]; order, suf = key.rsplit('-', 1); sk = r['sku'].strip()
    st = STATUS.index(r['status'].strip()) if r['status'].strip() in STATUS else STATUS.index('Processing')
    gmv = r2(n(r['gmv_lcy'] or r['offer_price'])); np_ = r2(fnp[key]) if fnp.get(key, 0) > 0 else gmv
    if sk not in cost and st != CANCEL: nocost[sk] += 1
    it = [mins(r['order_timestamp']), order, suf, sku_ix(r), st, CH.index(FUL.get(r['fulfillment_model'], 'Flex')), gmv, np_, 0.0, 0.0, 0.0, r2(cost.get(sk, 0.0)),
          0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, mins(r['shipment_timestamp']), mins(r['delivered_timestamp'])]
    items.append(it); by_order[order].append(it)

def money(it, fees):
    if it[4] in SOLD: rev = it[7] + fees; return r2(rev), r2(rev - it[11])
    return r2(fees), r2(fees)
for order, its in by_order.items():
    live = [it for it in its if it[4] != CANCEL] or its
    holder = min(live, key=lambda it: int(it[2]) if it[2].isdigit() else 0)
    for it in its:
        f = [a + (b if it is holder else 0) for a, b in zip(fee.get(order + '-' + it[2], [0.0] * 3), fee.get(order, [0.0] * 3))]
        if it[4] == CANCEL: f = [0.0, 0.0, 0.0] if not any(f) else f
        it[8], it[9], it[10] = (r2(x) for x in f); it[15], it[16] = money(it, sum(it[8:11]))
        old = bitem.get(order + '-' + it[2])
        if it[0] is not None and it[0] >= IH_FROM: h = [0.0, 5.0, 0.0]          # the workbook's In House model from June 2026
        elif old: h = old[12:15]                                              # before June: the workbook's own figures
        else: h = it[8:11]                                                    # before June, not in the workbook: same as Noon
        it[12], it[13], it[14] = (r2(x) for x in h)
        if it[0] is not None and it[0] >= IH_FROM and it[4] not in SOLD: it[17] = it[18] = 5.0 if it[4] != CANCEL else 0.0
        else: it[17], it[18] = money(it, sum(it[12:15]))

# ---------- statements, payouts, account charges ----------
statements = []
for s in sorted(stm.values(), key=lambda s: (s['date'], s['ref'])):
    s['date'] = s['date'].isoformat(); statements.append({k: (r2(v) if isinstance(v, float) else v) for k, v in s.items()})
payments.sort(); deductions.sort()
noonFees, vat = collections.defaultdict(lambda: collections.defaultdict(float)), []
if stmt_files:
    for r in read(stmt_files[-1]):
        if r['Contract'] != 'MPABXOQGVZSA': continue
        if r['Transaction'] == 'statement': noonFees[r['Date'][:7]][r['Details EN'].strip()] += n(r['Amount'])
        elif r['Transaction'] == 'invoice' and 'VAT' in r['Details EN']: vat.append([r['Date'], r2(n(r['Amount']))])
first_ts = min(it[0] for it in items if it[0] is not None); asOf = max(it[0] for it in items if it[0] is not None)
D = {'meta': dict(B['meta'], file=' + '.join(os.path.basename(f) for f in sales_files), asOf=asOf,
        finance={'file': os.path.basename(fin_files[-1]), 'from': min(day(r['Transaction Date']) for r in R).isoformat(), 'to': max(day(r['Transaction Date']) for r in R).isoformat(),
                 'rows': len(R), 'net': r2(sum(n(r['Total']) for r in R)), 'ordersUpdated': sum(1 for o in by_order if o in fee or any(o + '-' + it[2] in fee for it in by_order[o])),
                 'ordersNotInSales': len({r['Order Nr'] for r in R if r['Order Nr'] not in ('', 'NA')} - set(by_order)), 'statementsFile': os.path.basename(stmt_files[-1]) if stmt_files else None, 'noCost': len(nocost), 'noCostItems': sum(nocost.values())}),
     'skus': skus, 'items': items, 'statements': statements, 'stLines': [], 'vat': sorted(vat), 'fbn': [], 'payments': payments, 'deductions': deductions,
     'fees': [[m, r2(a[0]), r2(a[1]), r2(a[2]), 0.0, 0.0] for (y, m), a in sorted(acct.items())],
     'noonFees': {k: {n_: r2(v) for n_, v in sorted(d.items(), key=lambda x: x[1])} for k, d in sorted(noonFees.items())}}
json.dump(D, open(os.path.join(here, 'data.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
cnt = collections.Counter(STATUS[it[4]] for it in items)
print('sales files', [os.path.basename(f) for f in sales_files], 'items', len(items), 'orders', len(by_order), 'skus', len(skus), dict(cnt))
print('orders', (BASE + dt.timedelta(minutes=first_ts)).date(), 'to', (BASE + dt.timedelta(minutes=asOf)), '| workbook items not in sales:', len(set(bitem) - set(sales)))
print('statements', len(statements), r2(sum(s['total'] for s in statements)), 'payouts', r2(sum(p[1] for p in payments)), 'deductions', r2(sum(x[2] for x in deductions)), 'vat', r2(sum(v[1] for v in vat)))
L = [it for it in items if it[4] != CANCEL]
print('Noon view ref/ship/subs/profit', [r2(sum(it[k] for it in L)) for k in (8, 9, 10, 16)], 'In House profit', r2(sum(it[18] for it in L)))
print('SKUs without a unit cost', len(nocost), 'items', sum(nocost.values()))
for sk, c in nocost.most_common(15): print('  ', sk, c, skus[skuIx[sk]][2][:60], '|', skus[skuIx[sk]][3])
