import json 
from collections import Counter 
from trendforge.services.maestro_client import MaestroClient 
c=MaestroClient('http://127.0.0.1:42130') 
print('ping', c.ping()) 
m=c.models() 
models=m.get('models') if isinstance(m,dict) else m 
fam=Counter() 
keys=[] 
for it in models or []: 
  d=it if isinstance(it,dict) else {} 
  fam[str(d.get('family') or 'other')]+= 
  blob=' '.join(str(d.get(k) or '') for k in ('name','model_type','family','architecture')) 
  if any(k in blob.lower() for k in ('ltx','wan','hunyuan','i2v','t2v','story','director')): keys.append(blob[:160]) 
print('count', len(models or [])) 
print('families', fam.most_common(25)) 
print('KEY_MODELS') 
[print('-',x) for x in keys[:80]] 
