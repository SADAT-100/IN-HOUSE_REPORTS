"""Assemble the Noon portal: head + Noon CSS + body/JS, with data.json embedded.
Usage: python3 -I build.py <data.json> <out.html>"""
import json, sys, os
here = os.path.dirname(os.path.abspath(__file__))
data = json.dumps(json.load(open(sys.argv[1])), ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
D = json.loads(data.replace('\\u003c', '<'))
chan = 'bulky' if D['meta']['account'] == '18947' else 'courier'
head = '''<title>Noon {{Chan}} Portal</title>
<meta name="description" content="Noon KSA {{chan}} channel reports for In House: sales, orders, products, payouts, fees, returns and delivery.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700&family=Manrope:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
'''
tpl = head + open(os.path.join(here, 'css.part')).read() + open(os.path.join(here, 'body.part')).read()
tpl = tpl.replace('{{ACCT}}', D['meta']['account']).replace('{{Chan}}', chan.title()).replace('{{chan}}', chan)
out = tpl.replace('/*__DATA__*/null', data, 1)
open(sys.argv[2], 'w').write(out)
print(len(out))
