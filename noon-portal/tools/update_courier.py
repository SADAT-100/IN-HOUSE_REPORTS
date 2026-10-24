"""Standard update for the Noon courier report (account 12539).

Inputs, all in inputs/courier/:
  base-from-workbook.json   items, products and the In House fee model, from prepare_data.py on the workbook
  finance-*.csv             Noon "Transaction View Report" export (Finance > Reports), Jan 1 to today.
                            The newest file wins; it replaces all statements, payouts, deductions, ads and order fees.

Usage: python3 -I update_courier.py            -> writes data.json, then run build.py as usual

What the finance export changes:
  - statements, payouts (bank transfers, reversals kept as negatives) and balance deductions (CTH invoices)
  - monthly ads fees and ad subsidies
  - Noon-view order fees: every order gets the sum of ALL its order and order_update rows, so subsidies and
    fee corrections settled in later weeks are counted. The In House view is left as the workbook has it."""
import csv, json, glob, os, sys, collections, datetime as dt

here = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(here, 'inputs', 'courier')
D = json.load(open(os.path.join(IN, 'base-from-workbook.json')))
fin = sorted(glob.glob(os.path.join(IN, 'finance-*.csv')), key=os.path.getmtime)
if not fin: sys.exit('No finance-*.csv in ' + IN)
src = fin[-1]
R = list(csv.DictReader(open(src, encoding='utf-8-sig')))
need = {'Reference Nr', 'Order Nr', 'Transaction Date', 'Transaction Type', 'Total', 'Net Proceeds', 'Referral Fee including VAT'}
if not need <= set(R[0]): sys.exit('Not a Noon Transaction View export: missing ' + ', '.join(sorted(need - set(R[0]))))
n = lambda x: float(str(x).replace(',', '') or 0) if x not in (None, '') else 0.0
r2 = lambda x: round(x + 0.0, 2)
day = lambda s: dt.datetime.strptime(s.strip(), '%m/%d/%Y').date()
ACCT = D['meta']['account']

# ---- statements, same fields as the workbook's PS tab ----
COLS = [('np', 'Net Proceeds'), ('referral', 'Referral Fee including VAT'), ('fulfil', 'Fullfilment & Logistics Fees including VAT'), ('shipCredit', 'Shipping Credits including VAT'),
        ('otherOrder', 'Other Order Fees including VAT'), ('subsidy', 'Order Subsidies including VAT'), ('nonOrderFee', 'Non-Order Fees including VAT'),
        ('nonOrderSubsidy', 'Non-Order Subsidies including VAT'), ('others', 'Others including VAT'), ('total', 'Total')]
stm, payments, deductions = {}, [], []
ads = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
for r in R:
    ref, tt, d = r['Reference Nr'], r['Transaction Type'], day(r['Transaction Date'])
    if tt == 'payment': payments.append([d.isoformat(), r2(-n(r['Total']))]); continue
    if tt == 'balance_transfer':
        # transfers between Noon's own SA and AE contracts net to zero; the rest are invoices taken from the balance
        if r['Title'].count('-') >= 4 and r['Title'].split('-')[0] != r['Contract'] and r['Title'].split('-')[1] == r['Contract']: continue
        if r['Contract'] != 'MPABXOQGVZSA' and r['Title'].split('-')[0] == r['Contract']: continue
        deductions.append([d.isoformat(), ref, r2(n(r['Total']))]); ads[d.month][2] += n(r['Total']); continue
    s = stm.setdefault(ref, dict({'ref': ref, 'date': d, 'rows': 0, 'orderTotal': 0.0, 'updateTotal': 0.0}, **{k: 0.0 for k, _ in COLS}))
    s['rows'] += 1
    for k, c in COLS: s[k] += n(r[c])
    if tt == 'order': s['orderTotal'] += n(r['Total'])
    elif tt == 'order_update': s['updateTotal'] += n(r['Total'])
    elif tt == 'statement_fee': ads[d.month][0] += n(r['Non-Order Fees including VAT']); ads[d.month][1] += n(r['Non-Order Subsidies including VAT'])
statements = []
for s in sorted(stm.values(), key=lambda s: (s['date'], s['ref'])):
    s['date'] = s['date'].isoformat(); statements.append({k: (r2(v) if isinstance(v, float) else v) for k, v in s.items()})
payments.sort(); deductions.sort()

# ---- Noon-view order fees from every order row ----
# Item rows (with an Item Nr) stay on their item; order-level rows (shipping, subsidies) go on one item of the order.
fee = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
def parts(r): return [n(r['Referral Fee including VAT']),
    n(r['Fullfilment & Logistics Fees including VAT']) + n(r['Shipping Credits including VAT']) + n(r['Other Order Fees including VAT']) + n(r['Others including VAT']),
    n(r['Order Subsidies including VAT'])]
for r in R:
    if r['Transaction Type'] in ('order', 'order_update') and r['Order Nr'] not in ('', 'NA'):
        k = r['Item Nr'].strip() or r['Order Nr']
        for i, v in enumerate(parts(r)): fee[k][i] += v
CANCEL = D['meta']['status'].index('Cancelled'); SOLD = {D['meta']['status'].index(x) for x in ('Delivered', 'Shipped', 'Processing', 'Pending Confirmation')}
by_order = collections.defaultdict(list)
for it in D['items']: by_order[it[1]].append(it)
known = set(by_order) | {it[1] + '-' + str(it[2]) for it in D['items']}
before = [sum(it[k] for it in D['items'] if it[4] != CANCEL) for k in (8, 9, 10, 16)]
updated = lost = 0
for o, its in by_order.items():
    keys = [o] + [o + '-' + str(it[2]) for it in its]
    if not any(k in fee for k in keys): continue
    updated += 1
    live = [it for it in its if it[4] != CANCEL] or its
    holder = next((it for it in live if it[8] or it[9] or it[10]), None) or min(live, key=lambda it: int(it[2]) if str(it[2]).isdigit() else 0)
    for it in its:
        f = [a + (b if it is holder else 0) for a, b in zip(fee.get(o + '-' + str(it[2]), [0.0] * 3), fee.get(o, [0.0] * 3))]
        if it[4] == CANCEL: lost += sum(f)
        it[8], it[9], it[10] = (r2(x) for x in f)
        fees = it[8] + it[9] + it[10]
        if it[4] in SOLD: it[15] = r2(it[7] + fees); it[16] = r2(it[15] - it[11])
        else: it[15] = it[16] = r2(fees)
after = [sum(it[k] for it in D['items'] if it[4] != CANCEL) for k in (8, 9, 10, 16)]

# ---- monthly account charges: ads, ad subsidy, deductions; damaged-return credits and VAT are not in this export ----
D['fees'] = [[m, r2(a[0]), r2(a[1]), r2(a[2]), 0.0, 0.0] for m, a in sorted(ads.items())]
D['statements'], D['payments'], D['deductions'] = statements, payments, deductions
D['stLines'], D['vat'], D['fbn'] = [], [], []
dates = [day(r['Transaction Date']) for r in R]
D['meta']['finance'] = {'file': os.path.basename(src), 'from': min(dates).isoformat(), 'to': max(dates).isoformat(), 'rows': len(R),
    'net': r2(sum(n(r['Total']) for r in R)), 'ordersUpdated': updated, 'ordersNotInSales': len({k.rsplit('-', 1)[0] if k not in by_order and '-' in k else k for k in fee} - set(by_order))}
json.dump(D, open(os.path.join(here, 'data.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
print('finance file', os.path.basename(src), D['meta']['finance'])
print('statements', len(statements), r2(sum(s['total'] for s in statements)), 'payouts', len(payments), r2(sum(p[1] for p in payments)), 'deductions', len(deductions), r2(sum(x[2] for x in deductions)))
print('order fees ref/ship/subs/profit before', [r2(x) for x in before], 'after', [r2(x) for x in after], 'fees left on cancelled items', r2(lost))
