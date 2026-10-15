"""Turn the Noon KSA courier workbook into the compact data.json the Noon portal embeds.
Usage: python3 -I prepare_data.py <workbook.xlsx> <out.json>"""
import sys, json, re, datetime as dt
import openpyxl

src, out = sys.argv[1], sys.argv[2]
wb = openpyxl.load_workbook(src, read_only=True, data_only=True)

def num(v):
    if v is None or isinstance(v, str) and not re.match(r'^\s*-?[\d.,]+\s*$', v): return 0.0
    try: return float(str(v).replace(',', '')) if isinstance(v, str) else float(v)
    except Exception: return 0.0
r2 = lambda x: round(x + 0.0, 2)
BASE = dt.datetime(2026, 1, 1)
mins = lambda d: int((d - BASE).total_seconds() // 60) if isinstance(d, dt.datetime) else None

# ---- product titles from the statement ----
titles = {}
ws = wb['PS-12539']
rows = ws.iter_rows(values_only=True); H = list(next(rows)); ix = {h: i for i, h in enumerate(H)}
stm = {}
for r in rows:
    if r[ix['Reference Nr']] is None: continue
    sku = r[ix['SKUs']]
    if sku and r[ix['Title']] and sku not in titles: titles[sku] = str(r[ix['Title']]).strip()
    ref = r[ix['Reference Nr']]; ttype = r[ix['Transaction Type']]
    s = stm.setdefault(ref, {'ref': ref, 'date': r[ix['Transaction Date']], 'rows': 0, 'np': 0, 'referral': 0, 'fulfil': 0, 'shipCredit': 0, 'otherOrder': 0, 'subsidy': 0, 'nonOrderFee': 0, 'nonOrderSubsidy': 0, 'others': 0, 'total': 0, 'orderTotal': 0, 'updateTotal': 0})
    s['rows'] += 1
    for k, col in [('np', 'Net Proceeds'), ('referral', 'Referral Fee including VAT'), ('fulfil', 'Fullfilment & Logistics Fees including VAT'), ('shipCredit', 'Shipping Credits including VAT'), ('otherOrder', 'Other Order Fees including VAT'), ('subsidy', 'Order Subsidies including VAT'), ('nonOrderFee', 'Non-Order Fees including VAT'), ('nonOrderSubsidy', 'Non-Order Subsidies including VAT'), ('others', 'Others including VAT'), ('total', 'Total')]:
        s[k] += num(r[ix[col]])
    if ttype == 'order': s['orderTotal'] += num(r[ix['Total']])
    elif ttype == 'order_update': s['updateTotal'] += num(r[ix['Total']])
statements = []
for s in sorted(stm.values(), key=lambda s: s['date']):
    s['date'] = s['date'].strftime('%Y-%m-%d')
    statements.append({k: (r2(v) if isinstance(v, float) else v) for k, v in s.items()})

# ---- items ----
ws = wb['sales_export_09-19-2026_12_21_4']
rows = ws.iter_rows(values_only=True); H = list(next(rows))
seen = {}; cols = []
for h in H: seen[h] = seen.get(h, 0) + 1; cols.append(h if seen[h] == 1 else f'{h}#2')
ix = {h: i for i, h in enumerate(cols)}
STATUS = ['Delivered', 'Shipped', 'Processing', 'Pending Confirmation', 'CIR', 'Could Not Be Delivered', 'Cancelled']
FUL = {'Fulfilled by Partner (FBP)': 'Flex', 'Fulfilled by Noon (FBN)': 'FBN', 'Supermall': 'Supermall'}
CH = ['Flex', 'FBN', 'Supermall']
skus, skuIx, items = [], {}, []
for r in rows:
    g = lambda c: r[ix[c]]
    if not g('item_nr'): continue
    sku = str(g('sku'))
    if sku not in skuIx:
        skuIx[sku] = len(skus)
        ps = g('partner_sku'); ps = ('%d' % ps) if isinstance(ps, float) and ps.is_integer() else str(ps if ps is not None else '')
        skus.append([sku, ps, titles.get(sku, ''), g('Cat') or '', g('family') or '', g('brand_code') or ''])
    order = str(g('item')); suffix = str(g('item_nr'))[len(order) + 1:]
    items.append([mins(g('order_timestamp')), order, suffix, skuIx[sku], STATUS.index(g('status')), CH.index(FUL[g('fulfillment_model')]),
        r2(num(g('gmv_lcy'))), r2(num(g('Net Proceeds'))), r2(num(g('Referal  & Vat'))), r2(num(g('Shipping cost & Vat'))), r2(num(g('Order Subsidies & VAT'))), r2(num(g('Cost'))),
        r2(num(g('Comm'))), r2(num(g('Shipping'))), r2(num(g('Order Subsidies & VAT#2'))),
        r2(num(g('Revenue'))), r2(num(g('Profit'))), r2(num(g('Revenue2'))), r2(num(g('Profit2'))),
        mins(g('shipment_timestamp')), mins(g('delivered_timestamp'))])

# ---- statement & payment sheet ----
ws = wb['Statment&Payment']
month, vat, payments, fbn, stLines = 0, [], [], [], []
def pay_date(s, m):
    a, b, y = [int(x) for x in s.split('.')]
    opts = [(b, a), (a, b)]  # (month, day): dd.mm first, then mm.dd
    for mm, dd in opts:
        if mm == m and dd <= 31: return dt.date(y, mm, dd)
    for mm, dd in opts:
        if mm == m + 1 and dd <= 31: return dt.date(y, mm, dd)
    return None
for r in list(ws.iter_rows(values_only=True))[1:]:
    if r[0] and str(r[0]).startswith('Month'): month = int(str(r[0])[5:])
    lbl, amt = r[1], r[2]
    if isinstance(amt, str): amt = num(amt.replace('=', '').replace('\n', ''))
    if lbl and amt not in (None, ''):
        lbl = str(lbl)
        if lbl.startswith('Vat_'):
            m = re.match(r'Vat_(\d{4})-(\d{2})-(\d{2})', lbl); d = dt.date(int(m[1]), int(m[3]), int(m[2]))
            vat.append([d.isoformat(), r2(num(amt))])
        elif lbl.startswith('FBN'): fbn.append([month, r2(num(amt))])
        else: stLines.append([lbl, r2(num(amt))])
    if r[5] and r[6] not in (None, ''):
        d = pay_date(str(r[5]), month)
        if d: payments.append([d.isoformat(), r2(num(r[6]))])
payments.sort()

# ---- monthly non-order fees ----
ws = wb['All Fee']; fees = []
for r in ws.iter_rows(values_only=True):
    if r[0] and str(r[0]).startswith('Month '):
        fees.append([int(str(r[0])[6:])] + [r2(num(x)) for x in r[1:6]])

asOf = max(i[0] for i in items if i[0] is not None)
data = {'meta': {'account': '12539', 'channel': 'Noon KSA courier', 'file': 'Sales KSA 2026 2.xlsx', 'base': '2026-01-01', 'asOf': asOf,
        'status': STATUS, 'channels': CH},
        'skus': skus, 'items': items, 'statements': statements, 'stLines': stLines, 'vat': vat, 'fbn': fbn, 'payments': payments, 'fees': fees}
json.dump(data, open(out, 'w'), ensure_ascii=False, separators=(',', ':'))
print('items', len(items), 'skus', len(skus), 'titled', sum(1 for s in skus if s[2]), 'statements', len(statements), 'payments', len(payments), 'vat', len(vat), 'fbn', len(fbn), 'fees', len(fees))
print('stmt total', r2(sum(s['total'] for s in statements)), 'sheet PS lines', r2(sum(x[1] for x in stLines)), 'vat', r2(sum(x[1] for x in vat)), 'fbn', r2(sum(x[1] for x in fbn)), 'paid', r2(sum(p[1] for p in payments)))
