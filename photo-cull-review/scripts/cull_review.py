#!/usr/bin/env python3
"""Local photo previews and verified copies; never an automatic aesthetic judge."""
import argparse
import base64
import hashlib
import json
import re
import shutil
import sys
import time
import uuid
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps

FORMATS={'.jpg','.jpeg','.png','.webp','.tif','.tiff'}
STATES={'unreviewed','priority','candidate','defer','exclude'}

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def write(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def inside(a,b):
    try:a.resolve().relative_to(b.resolve());return True
    except ValueError:return False

def new_output(out,*inputs):
    if out.exists():raise ValueError('Output already exists; choose a new folder')
    for src in inputs:
        if inside(out,src) or inside(src,out):raise ValueError('Input and output folders must be separate, not nested')

def local(root,rel):
    if not isinstance(rel,str):raise ValueError('Relative path must be text')
    p=Path(rel)
    if p.is_absolute() or '..' in p.parts or not p.parts:raise ValueError('Unsafe relative path')
    result=root/p
    if not inside(result,root):raise ValueError('Path escapes source folder')
    return result

def manifest(project):
    m=read(project/'manifest.json')
    if not isinstance(m,dict) or not isinstance(m.get('photos'),list) or not isinstance(m.get('unread'),list):raise ValueError('Invalid project manifest')
    if not isinstance(m.get('project_id'),str) or not re.fullmatch(r'[a-f0-9]{32}',m['project_id']):raise ValueError('Invalid project ID')
    seen=set()
    for r in m['photos']:
        if not isinstance(r,dict) or not re.fullmatch(r'[a-f0-9]{16}',str(r.get('id',''))):raise ValueError('Invalid photo ID')
        if r['id'] in seen:raise ValueError('Duplicate photo ID')
        seen.add(r['id'])
        if not re.fullmatch(r'[a-f0-9]{64}',str(r.get('sha256',''))):raise ValueError('Invalid photo hash')
        local(project,r['relative']);local(project,r['preview'])
        if r.get('status') not in STATES:raise ValueError('Invalid photo status')
    return m

def validated_source(root,row):
    p=local(root,row['relative'])
    if not p.is_file() or p.is_symlink():raise ValueError('Missing or symlink source: '+row['relative'])
    if digest(p)!=row['sha256']:raise ValueError('Source changed: '+row['relative'])
    return p

def snapshot(project):
    dest=project/'history'/str(time.time_ns());dest.mkdir(parents=True)
    for name in ['manifest.json','review.html']:
        if (project/name).exists():shutil.copyfile(project/name,dest/name)

def image_url(path):return 'data:image/jpeg;base64,'+base64.b64encode(path.read_bytes()).decode('ascii')

def render(project,manifest):
    photos=[]
    for row in manifest['photos']:
        item=dict(row);item['preview']=image_url(local(project,row['preview']))
        detail=project/'details'/(row['id']+'.jpg')
        item['detail']=image_url(detail) if detail.exists() else None
        photos.append(item)
    payload={'project_id':manifest['project_id'],'title':manifest['title'],'photos':photos,'unread_count':len(manifest['unread'])}
    template=(Path(__file__).resolve().parents[1]/'assets/review.html').read_text(encoding='utf-8')
    encoded=json.dumps(payload,ensure_ascii=False).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    (project/'review.html').write_text(template.replace('__DATA__',encoded),encoding='utf-8')

def prepare(args):
    source=args.source.resolve();out=args.output.resolve()
    if not source.is_dir():raise ValueError('Source folder not found')
    new_output(out,source)
    # Symlink files and directories are not followed.
    files=sorted((p for p in source.rglob('*') if p.is_file()),key=lambda p:p.relative_to(source).as_posix())
    if not files:raise ValueError('Source folder contains no files')
    out.mkdir(parents=True);(out/'previews').mkdir();(out/'sheets').mkdir()
    rows=[];unread=[]
    for path in files:
        rel=path.relative_to(source).as_posix()
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if inside(parent,source)):
            unread.append({'relative':rel,'reason':'symlink-skipped'});continue
        if path.suffix.lower() not in FORMATS:
            unread.append({'relative':rel,'reason':'unsupported-format'});continue
        try:
            before=digest(path)
            with Image.open(path) as original:
                when=str(original.getexif().get(36867) or original.getexif().get(306) or '')
                im=ImageOps.exif_transpose(original).convert('RGB')
                width,height=im.size
                im.thumbnail((1600,1600))
                identifier=hashlib.sha256((rel+'\0'+before).encode()).hexdigest()[:16]
                preview='previews/'+identifier+'.jpg'
                im.save(out/preview,quality=86)
            if digest(path)!=before:raise ValueError('Source changed during preview creation')
            rows.append({'id':identifier,'relative':rel,'sha256':before,'width':width,'height':height,'time':when,'preview':preview,'status':'unreviewed','reason':'尚未完成视觉判断','group':'未分组'})
        except Exception as exc:
            unread.append({'relative':rel,'reason':'decode-or-read-failed: '+type(exc).__name__})
    rows.sort(key=lambda r:(not bool(r['time']),r['time'],r['relative']))
    project_id=uuid.uuid4().hex
    manifest={'version':1,'project_id':project_id,'title':args.title,'source_count':len(files),'photos':rows,'unread':unread,'order_note':'EXIF时间优先、缺失时路径排序；必须结合画面复核跨设备时钟与动作顺序'}
    write(out/'manifest.json',manifest)
    write(out/'decisions-template.json',[{k:r[k] for k in ('id','status','reason','group')} for r in rows])
    for start in range(0,len(rows),20):
        sheet=Image.new('RGB',(1200,1150),'#182126');d=ImageDraw.Draw(sheet)
        for j,row in enumerate(rows[start:start+20]):
            with Image.open(out/row['preview']) as im:
                im.thumbnail((280,190));x=10+(j%4)*300;y=10+(j//4)*230
                sheet.paste(im,(x+(280-im.width)//2,y))
            label=f"{start+j+1:04d}  {row['id']}"
            d.text((x,y+195),label,fill='white')
        sheet.save(out/'sheets'/f'{start//20+1:03d}.jpg',quality=88)
    render(out,manifest)
    print(json.dumps({'readable':len(rows),'unread':len(unread),'project':str(out),'note':'Previews prepared; no visual selection has been performed'},ensure_ascii=False))

def review(args):
    project=args.project.resolve();m=manifest(project);decisions=read(args.decisions)
    if not isinstance(decisions,list):raise ValueError('Decisions must be an array')
    known={r['id']:r for r in m['photos']};seen=set()
    for d in decisions:
        if not isinstance(d,dict) or set(d)-{'id','status','reason','group'}:raise ValueError('Invalid decision fields')
        if d.get('id') not in known or d['id'] in seen:raise ValueError('Unknown or repeated decision ID')
        seen.add(d['id'])
        if d.get('status') not in STATES:raise ValueError('Invalid status')
        if not isinstance(d.get('reason'),str) or not isinstance(d.get('group'),str):raise ValueError('Reason and group must be strings')
    snapshot(project)
    for d in decisions:known[d['id']].update(d)
    write(project/'manifest.json',m);render(project,m)
    print('Review updated; historical snapshot preserved. No source images copied or changed.')

def detail(args):
    project=args.project.resolve();m=manifest(project)
    matches=[r for r in m['photos'] if r['id']==args.id]
    if len(matches)!=1:raise ValueError('ID must match exactly one photo')
    row=matches[0];source=validated_source(args.source.resolve(),row)
    x,y,w,h=args.box
    if not (0<=x<1 and 0<=y<1 and w>0 and h>0 and x+w<=1 and y+h<=1):raise ValueError('Box must fit in normalized image bounds')
    target=project/'details'/(row['id']+'.jpg')
    if target.exists():raise ValueError('Detail already exists; preserve it and create a new project revision to replace')
    with Image.open(source) as original:
        im=ImageOps.exif_transpose(original).convert('RGB');iw,ih=im.size
        box=tuple(round(v) for v in (x*iw,y*ih,(x+w)*iw,(y+h)*ih))
        if box[0]>=box[2] or box[1]>=box[3]:raise ValueError('Box is smaller than one pixel')
        im=im.crop(box);im.thumbnail((1600,1600));target.parent.mkdir(exist_ok=True)
        im.save(target,quality=90)
    snapshot(project);row['detail_box']=args.box;write(project/'manifest.json',m);render(project,m)
    print('Detail preview created without upscaling; visually verify the region.')

def copy_photos(args):
    project=args.project.resolve();source=args.source.resolve();out=args.output.resolve()
    new_output(out,source,project);m=manifest(project);known={r['id']:r for r in m['photos']}
    if args.scope=='candidates':
        chosen=[r for r in m['photos'] if r['status'] in ('priority','candidate')]
    else:
        if not args.selection:raise ValueError('selected scope needs --selection')
        selection=read(args.selection)
        if selection.get('project_id')!=m['project_id']:raise ValueError('Selection belongs to another project')
        if not isinstance(selection.get('selected'),list):raise ValueError('selected must be an array')
        chosen=[];seen=set()
        for entry in selection['selected']:
            if not isinstance(entry,dict) or entry.get('id') not in known:raise ValueError('Unknown selected ID')
            row=known[entry['id']]
            if any(entry.get(k)!=row[k] for k in ('relative','sha256')):raise ValueError('Selection path/hash mismatch')
            if row['id'] in seen:raise ValueError('Duplicate selected ID')
            seen.add(row['id']);chosen.append(row)
    todo=[];skipped=[]
    for row in chosen:
        if Path(row['relative']).suffix.lower() not in ('.jpg','.jpeg'):
            skipped.append({'relative':row['relative'],'reason':'Only JPEG copied; other formats need separate instruction'});continue
        src=validated_source(source,row)
        folder='用户选择' if args.scope=='selected' else ('优先看' if row['status']=='priority' else '其他候选')
        dst=local(out,folder+'/'+row['relative']);todo.append((row,src,dst))
    if len({str(dst) for _,_,dst in todo})!=len(todo):raise ValueError('Duplicate output paths')
    report={'project_id':m['project_id'],'scope':args.scope,'copied':[],'skipped':skipped,'complete':False}
    out.mkdir(parents=True)
    try:
        for row,src,dst in todo:
            dst.parent.mkdir(parents=True,exist_ok=True)
            with src.open('rb') as reader,dst.open('xb') as writer:shutil.copyfileobj(reader,writer)
            if digest(dst)!=row['sha256']:raise ValueError('Copied content differs: '+row['relative'])
            report['copied'].append({'id':row['id'],'relative':row['relative'],'destination':dst.relative_to(out).as_posix(),'sha256':row['sha256']})
        report['complete']=True
    except Exception as exc:
        report['error']=str(exc);raise
    finally:write(out/'copy-report.json',report)
    print(json.dumps({'copied':len(report['copied']),'skipped':len(skipped),'note':'Only requested JPEG copies; source files unchanged'},ensure_ascii=False))

def main():
    ap=argparse.ArgumentParser(description=__doc__);subs=ap.add_subparsers(dest='command',required=True)
    p=subs.add_parser('prepare');p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--title',default='照片审核');p.set_defaults(func=prepare)
    p=subs.add_parser('review');p.add_argument('--project',type=Path,required=True);p.add_argument('--decisions',type=Path,required=True);p.set_defaults(func=review)
    p=subs.add_parser('detail');p.add_argument('--project',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--id',required=True);p.add_argument('--box',type=float,nargs=4,required=True);p.set_defaults(func=detail)
    p=subs.add_parser('copy');p.add_argument('--project',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--scope',choices=['candidates','selected'],required=True);p.add_argument('--selection',type=Path);p.set_defaults(func=copy_photos)
    args=ap.parse_args()
    try:args.func(args)
    except (ValueError,OSError,KeyError,TypeError) as exc:ap.exit(1,'Stopped: '+str(exc)+'\n')

if __name__=='__main__':main()
