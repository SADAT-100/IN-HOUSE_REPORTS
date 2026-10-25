"""Standard update for the Noon reports: courier (12539) and bulky (18947).

Usage: python3 -I update_noon.py courier|bulky   -> writes data.json (courier) or bulky/data.json; then build.py as usual.

Put the Noon exports in inputs/<account>/, each from 1 January to today. For each kind the newest file wins:
  sales-*.csv        Account Health & Reports > Sales. Several files are merged by item number (e.g. Jan-Jun + Jul-today).
  finance-*.csv      Payments & Fees > Transaction View Report: what Noon credited and charged each item and order,
                     payouts and deductions. Optional, but without it new items have no Noon fees.
  statements-*.csv   Payments & Fees statements export: charge names and VAT per statement, payouts and deductions.
  base-from-workbook.json   reference from the old workbook: unit cost and category per SKU, delivery type and the
                     In House fees for the items the workbook had.

Rules
  Items       one per sales row.
  Noon view   with a finance export: every fee and subsidy Noon booked against the order or item, including later corrections;
              net proceeds = what Noon credited the item, else the sales price. Without one: the workbook's figures, and no fees
              for newer items (flagged on the Data page).
  In House    from June 2026 the workbook's model (courier: no commission, +5.00 per item; bulky: commission 23% of net
              proceeds, 3.00 shipping per item). Before June the workbook's own figures, or the Noon view for items it lacks.
  Unit cost   by SKU from the workbook; new SKUs have no cost until one is added (listed when this runs)."""
import csv, json, glob, os, sys, collections, datetime as dt

ACC = (sys.argv[1:] or ['courier'])[0]
if ACC not in ('courier', 'bulky'): sys.exit('Usage: update_noon.py courier|bulky')
BULKY = ACC == 'bulky'
here = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(here, 'inputs', ACC); OUT = os.path.join(here, 'bulky' if BULKY else '', 'data.json')
newest = lambda pat: sorted(glob.glob(os.path.join(IN, pat)), key=os.path.getmtime)
B = json.load(open(os.path.join(IN, 'base-from-workbook.json')))
CONTRACT = 'MPABRCRW4JSA' if BULKY else 'MPABXOQGVZSA'
n = lambda x: float(str(x).replace(',', '')) if x not in (None, '') else 0.0
r2 = lambda x: round(x + 0.0, 2)
read = lambda f: list(csv.DictReader(open(f, encoding='utf-8-sig')))
BASE = dt.datetime(2026, 1, 1)
mins = lambda s: int((dt.datetime.strptime(s.strip()[:19], '%Y-%m-%d %H:%M:%S') - BASE).total_seconds() // 60) if s and s.strip() else None
STATUS = B['meta']['status']; CH = B['meta']['channels']
SOLD = {STATUS.index(x) for x in ('Delivered', 'Shipped', 'Processing', 'Pending Confirmation')}; CANCEL = STATUS.index('Cancelled')
IH_FROM = mins('2026-06-01 00:00:00')

sales_files, fin_files, stmt_files = newest('sales-*.csv'), newest('finance-*.csv'), newest('statements-*.csv')
if not sales_files: sys.exit('Need at least one sales-*.csv in ' + IN)
sales = {}
for f in sales_files:
    rows = read(f)
    if 'item_nr' not in rows[0] or 'status' not in rows[0]: sys.exit(f + ' is not a Noon sales export')
    for r in rows: sales[r['item_nr'].strip()] = r
R = read(fin_files[-1]) if fin_files else []
if R and not {'Reference Nr', 'Transaction Type', 'Total', 'Item Nr'} <= set(R[0]): sys.exit(fin_files[-1] + ' is not a Noon Transaction View export')
S = read(stmt_files[-1]) if stmt_files else []
day = lambda s: dt.datetime.strptime(s.strip(), '%m/%d/%Y').date()

bsku = {s[0]: s for s in B['skus']}
bitem = {it[1] + '-' + str(it[2]): it for it in B['items']}
cost = {}
for it in B['items']: cost.setdefault(B['skus'][it[3]][0], it[11])

# ---------- finance export ----------
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
        if len(p) >= 5 and p[0].startswith('MP') and p[1].startswith('MP'): continue  # Noon moving money between its own contracts
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

# ---------- statements export: charge names, VAT; and the money, when there is no finance export ----------
noonFees, vat = collections.defaultdict(lambda: collections.defaultdict(float)), []
SMAP = {'Net Proceeds': 'np', 'Referral Fee': 'referral', 'Referral Fee Adjustment': 'referral', 'Directship Outbound Fee': 'fulfil', 'FBN Outbound Fee': 'fulfil',
        'Directship Outbound Fee (Subsidy)': 'subsidy', 'Advertising Fee': 'nonOrderFee', 'Advertising Fee (Subsidy)': 'nonOrderSubsidy'}
for r in S:
    if r['Contract'] != CONTRACT: continue
    t, d, a = r['Transaction'], dt.date.fromisoformat(r['Date'][:10]), n(r['Amount'])
    if t == 'statement': noonFees[r['Date'][:7]][r['Details EN'].strip()] += a
    elif t == 'invoice' and 'VAT' in r['Details EN']: vat.append([r['Date'][:10], r2(a)])
    if R: continue
    if t == 'payout': payments.append([d.isoformat(), r2(-a)])
    elif t == 'contract_transfer':
        p = r['Reference'].split('-')
        if len(p) >= 5 and p[0].startswith('MP') and p[1].startswith('MP'): continue
        deductions.append([d.isoformat(), r['Reference'], r2(a)]); acct[(d.year, d.month)][2] += a
    elif t in ('statement', 'invoice'):
        ref = r['Reference'] if t == 'statement' else r['Details EN'].split(' ')[0]
        s = stm.setdefault(ref, dict({'ref': ref, 'date': d, 'rows': 0, 'orderTotal': 0.0, 'updateTotal': 0.0, 'vat': 0.0}, **{k: 0.0 for k, _ in COLS}))
        s['rows'] += 1; s['total'] += a
        if t == 'invoice': s['vat'] += a; continue
        k = SMAP.get(r['Details EN'].strip(), 'otherOrder'); s[k] += a
        if k == 'nonOrderFee': acct[(d.year, d.month)][0] += a
        if k == 'nonOrderSubsidy': acct[(d.year, d.month)][1] += a
payments.sort(); deductions.sort()

bycode = collections.defaultdict(collections.Counter)
for sk, code in ftype.items():
    if sk in bsku and bsku[sk][3]: bycode[code][bsku[sk][3]] += 1
def cat_for(sk, family):
    code = ftype.get(sk)
    if code and bycode[code]: return bycode[code].most_common(1)[0][0]
    return (code.split('-')[-1] if code else family or 'Other').replace('_', ' ').title()

def channel(r, old):
    if not BULKY: return CH.index({'Fulfilled by Partner (FBP)': 'Flex', 'Fulfilled by Noon (FBN)': 'FBN', 'Supermall': 'Supermall'}.get(r['fulfillment_model'], 'Flex'))
    if old: return old[5]                                   # bulky delivery type was tagged by hand in the workbook
    return CH.index('FBN' if 'FBN' in r['fulfillment_model'] else 'Not set')

# ---------- items ----------
skus, skuIx, items, nocost, nofee = [], {}, [], collections.Counter(), 0
def sku_ix(r):
    sk = r['sku'].strip()
    if sk not in skuIx:
        b = bsku.get(sk); skuIx[sk] = len(skus)
        skus.append([sk, r['partner_sku'].strip() or (b[1] if b else ''), (b[2] if b and b[2] else title.get(sk, '')), b[3] if b and b[3] else cat_for(sk, r['family']),
                     r['family'] or (b[4] if b else ''), r['brand_code'] or (b[5] if b else '')])
    return skuIx[sk]
by_order = collections.defaultdict(list)
for key in sorted(sales, key=lambda k: (sales[k]['order_timestamp'], k)):
    r = sales[key]; order, suf = key.rsplit('-', 1); sk = r['sku'].strip(); old = bitem.get(key)
    st = STATUS.index(r['status'].strip()) if r['status'].strip() in STATUS else STATUS.index('Processing')
    gmv = r2(n(r['gmv_lcy'] or r['offer_price']))
    np_ = r2(fnp[key]) if fnp.get(key, 0) > 0 else (old[7] if old and not R else gmv)
    if sk not in cost and st != CANCEL: nocost[sk] += 1
    it = [mins(r['order_timestamp']), order, suf, sku_ix(r), st, channel(r, old), gmv, np_, 0.0, 0.0, 0.0, r2(cost.get(sk, 0.0)),
          0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, mins(r['shipment_timestamp']), mins(r['delivered_timestamp'])]
    items.append(it); by_order[order].append(it)

def money(it, fees):
    if it[4] in SOLD: rev = it[7] + fees; return r2(rev), r2(rev - it[11])
    return r2(fees), r2(fees)
def inhouse(it, old):
    late = it[0] is not None and it[0] >= IH_FROM
    if late and not BULKY:
        it[12:15] = [0.0, 5.0, 0.0]
        if it[4] not in SOLD: it[17] = it[18] = 5.0 if it[4] != CANCEL else 0.0; return
    elif late and BULKY:
        it[12:15] = [0.0, 0.0, 0.0] if it[4] == CANCEL else [r2(-.23 * it[7]), -3.0, 0.0] if it[4] in SOLD else [0.0, -3.0, 0.0]
    elif old: it[12:15] = old[12:15]
    else: it[12:15] = it[8:11]
    it[17], it[18] = money(it, sum(it[12:15]))
for order, its in by_order.items():
    live = [it for it in its if it[4] != CANCEL] or its
    holder = min(live, key=lambda it: int(it[2]) if it[2].isdigit() else 0)
    for it in its:
        old = bitem.get(order + '-' + it[2])
        if R:
            f = [a + (b if it is holder else 0) for a, b in zip(fee.get(order + '-' + it[2], [0.0] * 3), fee.get(order, [0.0] * 3))]
        elif old: f = old[8:11]
        else: f = [0.0, 0.0, 0.0]; nofee += it[4] != CANCEL
        it[8], it[9], it[10] = (r2(x) for x in f); it[15], it[16] = money(it, sum(it[8:11]))
        inhouse(it, old)

statements = []
for s in sorted(stm.values(), key=lambda s: (s['date'], s['ref'])):
    s['date'] = s['date'].isoformat(); statements.append({k: (r2(v) if isinstance(v, float) else v) for k, v in s.items()})
first_ts = min(it[0] for it in items if it[0] is not None); asOf = max(it[0] for it in items if it[0] is not None)
srcs = R or S
fin = {'file': os.path.basename(fin_files[-1]) if R else None, 'statementsFile': os.path.basename(stmt_files[-1]) if S else None,
       'from': (min(day(r['Transaction Date']) for r in R) if R else min(dt.date.fromisoformat(r['Date'][:10]) for r in S)).isoformat() if srcs else None,
       'to': (max(day(r['Transaction Date']) for r in R) if R else max(dt.date.fromisoformat(r['Date'][:10]) for r in S)).isoformat() if srcs else None,
       'rows': len(R) or len(S), 'ordersUpdated': sum(1 for o in by_order if o in fee or any(o + '-' + it[2] in fee for it in by_order[o])),
       'ordersNotInSales': len({r['Order Nr'] for r in R if r['Order Nr'] not in ('', 'NA')} - set(by_order)), 'noCost': len(nocost), 'noCostItems': sum(nocost.values()),
       'noFeeItems': nofee, 'feesFrom': 'finance' if R else 'workbook'}
D = {'meta': dict(B['meta'], file=' + '.join(sorted(os.path.basename(f) for f in sales_files)), asOf=asOf, finance=fin),
     'skus': skus, 'items': items, 'statements': statements, 'stLines': [], 'vat': sorted(vat), 'fbn': [], 'payments': payments, 'deductions': deductions,
     'fees': [[m, r2(a[0]), r2(a[1]), r2(a[2]), 0.0, 0.0] for (y, m), a in sorted(acct.items())],
     'noonFees': {k: {n_: r2(v) for n_, v in sorted(d.items(), key=lambda x: x[1])} for k, d in sorted(noonFees.items())}}
json.dump(D, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
cnt = collections.Counter(STATUS[it[4]] for it in items)
print(ACC, 'items', len(items), 'orders', len(by_order), 'skus', len(skus), dict(cnt))
print('orders', (BASE + dt.timedelta(minutes=first_ts)).date(), 'to', (BASE + dt.timedelta(minutes=asOf)), '| workbook items not in sales:', len(set(bitem) - set(sales)))
print('statements', len(statements), r2(sum(s['total'] for s in statements)), 'payouts', len(payments), r2(sum(p[1] for p in payments)), 'deductions', r2(sum(x[2] for x in deductions)), 'vat', r2(sum(v[1] for v in vat)))
L = [it for it in items if it[4] != CANCEL]
print('Noon view ref/ship/subs/profit', [r2(sum(it[k] for it in L)) for k in (8, 9, 10, 16)], 'In House profit', r2(sum(it[18] for it in L)), '| items without Noon fees', nofee)
print('SKUs without a unit cost', len(nocost), 'items', sum(nocost.values()))
for sk, c in nocost.most_common(8): print('  ', sk, c, skus[skuIx[sk]][2][:60], '|', skus[skuIx[sk]][3])
