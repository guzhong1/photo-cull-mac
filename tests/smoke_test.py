from pathlib import Path
import subprocess, sys, json, tempfile, hashlib
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "photo-cull-review/scripts/cull_review.py"

def run(*args,ok=True):
 p=subprocess.run([sys.executable,str(TOOL),*[str(x) for x in args]],capture_output=True,text=True)
 assert (p.returncode==0)==ok,(args,p.stdout,p.stderr)
 return p
def read(p):return json.loads(p.read_text())
def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def picture(p,n):
 im=Image.new('RGB',(960,640),'#cad7d7');d=ImageDraw.Draw(im)
 d.rectangle((0,440,960,640),fill='#465e68');d.rectangle((80+n*15,120,300+n*15,440),fill='#286f75')
 d.ellipse((540-n*12,150,750-n*12,360),fill='#e5a466');d.text((24,24),f'DEMO {n:02d} - GEOMETRIC TEST IMAGE - NO REAL PERSON',fill='#172d35')
 im.save(p,quality=90)

with tempfile.TemporaryDirectory() as td:
 t=Path(td);src=t/'source';src.mkdir();(src/'one').mkdir();(src/'two').mkdir()
 picture(src/'one/SAME.JPG',1);picture(src/'two/SAME.JPG',2);picture(src/'other.JPG',3)
 Image.new('RGB',(120,180),'green').save(src/'a.png')
 (src/'unknown.ARW').write_bytes(b'unsupported raw fixture');(src/'broken.jpg').write_bytes(b'not an image')
 originals={p.relative_to(src).as_posix():sha(p) for p in src.rglob('*') if p.is_file()}
 project=t/'project';run('prepare','--source',src,'--output',project)
 m=read(project/'manifest.json');assert len(m['photos'])==4 and len(m['unread'])==2
 assert all(r['status']=='unreviewed' for r in m['photos'])
 assert all(not Image.open(project/r['preview']).getexif() for r in m['photos'])
 decisions=[{'id':r['id'],'status':'priority' if r['relative']=='one/SAME.JPG' else 'candidate','reason':'Test UI only','group':'demo'} for i,r in enumerate(m['photos'])]
 save(t/'decisions.json',decisions);run('review','--project',project,'--decisions',t/'decisions.json')
 assert len(list((project/'history').iterdir()))==1
 before=(project/'manifest.json').read_bytes();bad=decisions+[decisions[0]];save(t/'bad.json',bad)
 run('review','--project',project,'--decisions',t/'bad.json',ok=False);assert (project/'manifest.json').read_bytes()==before
 row=next(r for r in m['photos'] if r['relative'].endswith('other.JPG'))
 run('detail','--project',project,'--source',src,'--id',row['id'],'--box',0.1,0.1,0.5,0.5)
 assert Image.open(project/'details'/(row['id']+'.jpg')).size==(480,320)
 run('detail','--project',project,'--source',src,'--id',row['id'],'--box',0.1,0.1,0.5,0.5,ok=False)
 copies=t/'copies';run('copy','--project',project,'--source',src,'--output',copies,'--scope','candidates')
 report=read(copies/'copy-report.json');assert len(report['copied'])==3 and len(report['skipped'])==1
 for r in report['copied']:
  dest=copies/r['destination'];source=src/r['relative'];assert sha(dest)==sha(source) and dest.stat().st_ino!=source.stat().st_ino
 assert {r['relative'] for r in report['copied']}=={'one/SAME.JPG','two/SAME.JPG','other.JPG'}
 assert sum(r['destination'].startswith('优先看/') for r in report['copied'])==1
 assert sum(r['destination'].startswith('其他候选/') for r in report['copied'])==2
 run('copy','--project',project,'--source',src,'--output',copies,'--scope','candidates',ok=False)
 selection={'project_id':m['project_id'],'selected':[{k:row[k] for k in ('id','relative','sha256')}]};save(t/'selection.json',selection)
 run('copy','--project',project,'--source',src,'--output',t/'selected','--scope','selected','--selection',t/'selection.json')
 assert len(read(t/'selected/copy-report.json')['copied'])==1
 selection['project_id']='wrong';save(t/'selection.json',selection)
 run('copy','--project',project,'--source',src,'--output',t/'wrong','--scope','selected','--selection',t/'selection.json',ok=False);assert not (t/'wrong').exists()
 run('prepare','--source',src,'--output',src/'nested',ok=False)
 assert originals=={p.relative_to(src).as_posix():sha(p) for p in src.rglob('*') if p.is_file()}
 (src/'other.JPG').write_bytes(b'changed source')
 run('copy','--project',project,'--source',src,'--output',t/'changed','--scope','candidates',ok=False);assert not (t/'changed').exists()


print("All smoke tests passed. Source protection, previews, decisions, copies and failure cases verified.")
