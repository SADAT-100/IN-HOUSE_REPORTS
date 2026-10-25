"""Assemble the Noon portal: head + Noon CSS + body/JS, with the account data embedded.
One account:   python3 -I build.py <data.json> <out.html>
Both accounts: python3 -I build.py <bulky data.json> <courier data.json> <out.html>
With both, the page opens on the In-House Noon Reports intro and lets you pick or switch accounts."""
import json, sys, os
here = os.path.dirname(os.path.abspath(__file__))
*srcs, dst = sys.argv[1:]
sets = {}
for f in srcs:
    D = json.load(open(f))
    sets['bulky' if D['meta']['account'] == '18947' else 'courier'] = D
embed = next(iter(sets.values())) if len(sets) == 1 else sets
data = json.dumps(embed, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
if len(sets) == 1:
    chan = next(iter(sets))
    title = 'Noon ' + chan.title() + ' Portal'
    desc = 'Noon KSA ' + chan + ' channel reports for In House: sales, orders, products, payouts, fees, returns and delivery.'
else:
    title = 'In-House Noon Reports'
    desc = 'Noon KSA reports for In House, Bulky and Courier accounts: sales, orders, products, payouts, fees, returns and delivery.'
head = f'''<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700;800&family=Manrope:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
'''
tpl = head + open(os.path.join(here, 'css.part')).read() + open(os.path.join(here, 'body.part')).read()
out = tpl.replace('/*__DATA__*/null', data, 1)
open(dst, 'w').write(out)
print(len(out))
