import sys,urllib.request,urllib.parse,json
dom,id_,sel=sys.argv[1:4]; p={'$select':sel,'$limit':'100'}
for a in sys.argv[4:]:
    k,v=a.split('=',1); p['$'+k]=v
u=f"https://{dom}/resource/{id_}.json?"+urllib.parse.urlencode(p)
try: r=json.load(urllib.request.urlopen(u))
except urllib.error.HTTPError as e: print("ERR",e.code,e.read()[:300]); sys.exit()
for x in r: print(x)
