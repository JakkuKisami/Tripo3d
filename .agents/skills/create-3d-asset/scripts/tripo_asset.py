#!/usr/bin/env python3
"""Durable Tripo workflow. Standard-library HTTP; never retries a submission."""
import argparse
import contextlib
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = 'https://api.tripo3d.ai/v2/openapi'
VIEWS = ('front', 'left', 'back', 'right')
TERMINAL = {'success', 'failed', 'cancelled', 'banned', 'expired', 'unknown'}


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.state-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)
        dfd = os.open(path.parent, os.O_DIRECTORY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('API redirect refused; authentication stays on the API host')


class Client:
    def __init__(self):
        self.key = os.environ.get('TRIPO_API_KEY')
        if not self.key: raise RuntimeError('Set TRIPO_API_KEY securely in environment settings')
        # No prefix test: proxy-backed variables can be placeholders.
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, endpoint, body=None, content_type='application/json', timeout=45):
        raw = json.dumps(body).encode() if body is not None and content_type == 'application/json' else body
        request = urllib.request.Request(BASE + endpoint, data=raw, method=method,
            headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': content_type, 'Accept': 'application/json'})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'Tripo HTTP {e.code}; response body omitted for credential safety') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RuntimeError('Tripo transport failed; no automatic submission retry') from None
        if payload.get('code') != 0:
            raise RuntimeError('Tripo API rejected request; code ' + str(payload.get('code')))
        if not isinstance(payload.get('data'), dict): raise RuntimeError('Unexpected Tripo response')
        return payload['data']

    def upload(self, path):
        if Path(path).stat().st_size > 20 * 1024 * 1024: raise ValueError('Reference exceeds Tripo 20 MB upload limit')
        boundary = 'TripoAsset' + uuid.uuid4().hex
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="reference.jpg"\r\n'
                'Content-Type: image/jpeg\r\n\r\n').encode() + Path(path).read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
        return self.request('POST', '/upload', body, 'multipart/form-data; boundary=' + boundary)['image_token']

    def submit(self, payload): return self.request('POST', '/task', payload)['task_id']
    def status(self, task_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', task_id): raise ValueError('Invalid task ID')
        return self.request('GET', '/task/' + task_id)


def prompt_for(description, kind, pose, view):
    pose_rule = f'Exact pose: {pose}.' if pose else ('Neutral A-pose suitable for modeling.' if kind in {'character','outfit'} else 'Stable neutral pose appropriate to this asset.')
    return (f'Create one model-ready {view} orthographic reference image of this {kind}: {description}\n'
        f'{pose_rule} If an existing reference or mannequin is supplied, preserve its proportions and pose exactly; its pose overrides defaults. '
        'Use the same approved design, proportions, scale, pose, materials, and even lighting in every view. '
        'Rotate the camera only; do not mirror left/right or turn the subject. Left and right mean the subject’s anatomical sides. '
        'Show the entire asset unobstructed with comfortable margins, centered at the identical image scale on a plain neutral gray background. '
        'Use even diffuse studio lighting without dramatic shadows. No perspective distortion, text, frames, scenery, aura, particles, or VFX. '
        'Exclude unwanted weapons, scabbards, and accessories for a clean base model; retain integral design features. '
        'Render detachable equipment as separate assets when appropriate. Show only this single asset in this image. '
        'For modular environment pieces preserve grid-aligned dimensions, flat connection boundaries, and consistent module scale. '
        'Do not invent hidden-side details inconsistent with the approved design.')


def initialize(directory, description, kind, pose=None, target=12500):
    directory = Path(directory).resolve(); state = directory / 'job.json'
    if state.exists(): raise RuntimeError('Job already exists; resume it instead of initializing again')
    if not 10000 <= target <= 15000: raise ValueError('Target must be within 10,000–15,000 triangles')
    directory.mkdir(parents=True, exist_ok=True)
    data = {'schema_version': 1, 'description': description, 'kind': kind, 'pose': pose,
        'targets': {'triangles': target, 'triangle_range': [10000,15000], 'texture_size': 4096, 'pbr': True},
        'references': {}, 'tasks': {}, 'deliverables': [], 'created_at': time.time()}
    atomic_json(state, data)
    atomic_json(directory / 'reference-prompts.json', {view: prompt_for(description, kind, pose, view) for view in VIEWS})
    return state


@contextlib.contextmanager
def locked_job(path):
    path = Path(path).resolve()
    with open(path.with_suffix('.lock'), 'a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Another command is working on this job') from None
        data = json.loads(path.read_text())
        yield data, lambda: atomic_json(path, data)


def register_references(job, save, directory, paths, review_note):
    from PIL import Image
    if job['tasks']: raise RuntimeError('References are frozen after the first submission')
    if not review_note.strip(): raise ValueError('Record visual consistency inspection before upload')
    if not paths.get('front'): raise ValueError('Front view is required')
    refs = {}
    directory = Path(directory) / 'references'; directory.mkdir(exist_ok=True)
    dimensions = set()
    for view in VIEWS:
        if not paths.get(view): continue
        source = Path(paths[view]).resolve()
        with Image.open(source) as image:
            image.load()
            if min(image.size) < 256: raise ValueError('Reference is too small for modeling')
            dimensions.add(image.size)
            # Normalizing to actual JPEG matches the official v2 file type.
            if image.mode == 'RGBA':
                background = Image.new('RGB', image.size, (128,128,128)); background.paste(image, mask=image.getchannel('A')); image = background
            else: image = image.convert('RGB')
            target = directory / (view + '.jpg'); image.save(target, quality=95, subsampling=0)
        refs[view] = {'path': str(target), 'sha256': digest(target), 'source_sha256': digest(source), 'size': list(image.size)}
    if len(dimensions) > 1: raise ValueError('Use identical canvas dimensions for all views; regenerate or pad without rescaling the subject')
    job['references'] = refs
    job['review'] = {'inspected_at': time.time(), 'note': review_note, 'hashes': {v:r['sha256'] for v,r in refs.items()}}
    save()


def upload_references(job, save, client):
    if not job.get('review'): raise RuntimeError('Inspect and register references first')
    for view, ref in job['references'].items():
        if digest(ref['path']) != ref['sha256']: raise RuntimeError('Reference changed after inspection; inspect and register again')
        if job['review']['hashes'].get(view) != ref['sha256']: raise RuntimeError('Unreviewed reference')
        if not ref.get('file_token'):
            token = client.upload(ref['path'])
            if not isinstance(token, str) or not token: raise RuntimeError('Missing upload token')
            ref['file_token'] = token; save()


def successful_parent(job, parent):
    task = job['tasks'].get(parent, {})
    if task.get('status') != 'success' or not task.get('task_id'): raise RuntimeError('Parent task must be checked and successful')
    return task['task_id']


def build_payload(job, stage, parent=None):
    target = job['targets']['triangles']
    if stage == 'generation':
        refs = job['references']
        if len(refs) < 2: raise RuntimeError('Multiview requires at least two reviewed images')
        if 'front' not in refs or not job.get('review'): raise RuntimeError('Reviewed front reference is required')
        for r in refs.values():
            if not r.get('file_token'): raise RuntimeError('Upload references before generation')
            if digest(r['path']) != r['sha256']: raise RuntimeError('Reference changed after upload')
        return {'type': 'multiview_to_model', 'model_version': 'v2.5-20250123',
            'files': [{'type':'jpg','file_token':refs[v]['file_token']} if v in refs else {} for v in VIEWS],
            'face_limit': target, 'texture': True, 'pbr': True, 'texture_quality': 'detailed',
            'quad': False, 'smart_low_poly': True, 'export_uv': True, 'auto_size': False}
    source = successful_parent(job, parent or 'generation')
    if stage == 'lowpoly':
        return {'type':'highpoly_to_lowpoly','original_model_task_id':source,
            'model_version':'P-v2.0-20251225','face_limit':target,'quad':False,'bake':True}
    if stage not in {'glb','fbx'}: raise ValueError('Unknown stage')
    return {'type':'convert_model','original_model_task_id':source,'format':'GLTF' if stage=='glb' else 'FBX',
        'texture_size':4096,'texture_format':'PNG','face_limit':target,'quad':False,'pack_uv':False,
        'bake':True,'scale_factor':1.0,'with_animation':False}


def submit_stage(job, save, client, stage, parent=None):
    existing = job['tasks'].get(stage)
    if existing:
        if existing.get('task_id'): return existing['task_id']
        raise RuntimeError('Submission outcome is uncertain. Reconcile with Tripo support or attach the existing task ID; do not resubmit')
    payload = build_payload(job, stage, parent)
    # Durable intent BEFORE the paid request. An interrupted response cannot trigger a duplicate.
    record = {'status':'submission_uncertain','submitted_at':time.time(),'payload':payload,
        'request_sha256':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()}
    job['tasks'][stage] = record; save()
    task_id = client.submit(payload)
    if not isinstance(task_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',task_id):
        raise RuntimeError('Missing/invalid task ID; outcome uncertain')
    record.update(task_id=task_id,status='queued'); save()
    return task_id


def check_status(job, save, client, stage):
    record = job['tasks'].get(stage)
    if not record or not record.get('task_id'): raise RuntimeError('No task ID; reconcile uncertain submission first')
    task = client.status(record['task_id'])
    if task.get('task_id') != record['task_id']: raise RuntimeError('Status response task ID mismatch')
    record.update(status=task.get('status','unknown'),progress=task.get('progress'),checked_at=time.time())
    # Persist only output URLs, no echoed input/credential-bearing error strings.
    record['output'] = task.get('output') or {}
    record['error_code'] = task.get('error_code'); save()
    return record


def wait_task(job, save, client, stage, timeout=1800, interval=10):
    if timeout <= 0 or interval < 2: raise ValueError('Use a positive timeout and intervals of at least 2 seconds')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = check_status(job, save, client, stage)
        print(json.dumps({k:record.get(k) for k in ('task_id','status','progress')}),flush=True)
        if record['status'] in TERMINAL:
            if record['status'] != 'success': raise RuntimeError('Task finished with status ' + record['status'])
            return record
        time.sleep(min(interval, max(0,deadline-time.monotonic())))
        interval = min(30,interval*1.25)
    raise TimeoutError('Polling timed out; task ID is saved. Resume without submitting again')


def safe_https(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Result URL must be HTTPS without embedded credentials')
    # Provider output URLs should be public CDN objects, never loopback/private endpoints.
    import ipaddress
    try:
        if not ipaddress.ip_address(parsed.hostname).is_global: raise ValueError('Non-public result host')
    except ValueError as e:
        if str(e) == 'Non-public result host': raise
    if parsed.hostname in {'localhost','metadata.google.internal'} or parsed.hostname.endswith(('.local','.internal')):
        raise ValueError('Non-public result host')
    return parsed


class SafeDownloadRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_https(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def download_file(url, target, opener=None):
    safe_https(url)
    opener = opener or urllib.request.build_opener(SafeDownloadRedirect())
    target = Path(target); partial=target.with_suffix(target.suffix+'.part')
    try:
        # No Authorization header on signed download URLs. TLS verification remains enabled.
        with opener.open(urllib.request.Request(url),timeout=60) as response, open(partial,'wb') as out:
            length=response.headers.get('Content-Length'); count=0
            for block in iter(lambda:response.read(1024*1024),b''):
                count+=len(block)
                if count>2*1024**3: raise ValueError('Result exceeds 2 GiB safety limit')
                out.write(block)
            out.flush();os.fsync(out.fileno())
        if not count or (length and count!=int(length)): raise ValueError('Empty or truncated download')
        os.replace(partial,target)
    finally:
        if partial.exists(): partial.unlink()
    return {'path':str(target.resolve()),'sha256':digest(target),'bytes':target.stat().st_size}


def output_urls(output):
    def walk(value, parts):
        if isinstance(value,str) and value.startswith('https://'): yield '_'.join(parts),value
        elif isinstance(value,dict):
            for k,v in value.items(): yield from walk(v,parts+[str(k)])
        elif isinstance(value,list):
            for i,v in enumerate(value): yield from walk(v,parts+[str(i)])
    return list(walk(output,[]))


def download_results(job, save, stage, directory):
    record=job['tasks'].get(stage,{})
    if record.get('status')!='success': raise RuntimeError('Check successful task status before downloading')
    directory=Path(directory)/'results'/stage;directory.mkdir(parents=True,exist_ok=True)
    urls=output_urls(record.get('output',{}))
    if not urls: raise RuntimeError('No downloadable output; refresh status or consult current official API docs')
    files=record.setdefault('downloads',[])
    for label,url in urls:
        extension=Path(urllib.parse.urlsplit(url).path).suffix.lower()
        if extension not in {'.glb','.gltf','.fbx','.zip','.obj','.bin','.png','.jpg','.jpeg','.webp'}: extension='.bin'
        name=re.sub(r'[^A-Za-z0-9_-]','_',label)[:100] or 'result'
        name+='-'+hashlib.sha256(label.encode()).hexdigest()[:8]
        target=directory/(name+extension)
        existing=next((f for f in files if f.get('output_field')==label),None)
        if existing and Path(existing['path']).exists() and digest(existing['path'])==existing['sha256']:continue
        result=download_file(url,target)
        if extension=='.bin':
            with open(target,'rb') as downloaded:magic=downloaded.read(32)
            detected='.glb' if magic.startswith(b'glTF') else '.zip' if magic.startswith(b'PK\x03\x04') else '.png' if magic.startswith(b'\x89PNG') else '.jpg' if magic.startswith(b'\xff\xd8') else '.fbx' if magic.startswith(b'Kaydara FBX Binary') else None
            if detected:
                new_target=target.with_suffix(detected);os.replace(target,new_target);result['path']=str(new_target.resolve())
        result['output_field']=label
        if existing:files.remove(existing)
        files.append(result);save()
    return files


def attach_task(job, save, client, stage, task_id):
    if stage in job['tasks'] and job['tasks'][stage].get('task_id') not in {None,task_id}:
        raise RuntimeError('Do not replace an existing task ID')
    remote=client.status(task_id)
    if remote.get('task_id')!=task_id:raise ValueError('Task ID mismatch')
    expected={'generation':'multiview_to_model','lowpoly':'highpoly_to_lowpoly','glb':'convert_model','fbx':'convert_model'}[stage]
    if remote.get('type')!=expected:raise ValueError('Task type does not match stage')
    previous=job['tasks'].get(stage,{})
    # When reconciling lost submission responses, require exact payload fields from server input.
    if previous.get('payload'):
        echoed=remote.get('input') or {}
        if any(echoed.get(k)!=v for k,v in previous['payload'].items() if k!='type'):
            raise ValueError('Task input differs from uncertain submission; reconcile manually with provider')
    job['tasks'][stage]={**previous,'task_id':task_id,'status':remote.get('status','unknown'),'output':remote.get('output') or {}}
    save()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init');init.add_argument('--output',required=True);init.add_argument('--description',required=True)
    init.add_argument('--kind',choices=['character','outfit','creature','prop','environment'],required=True)
    init.add_argument('--pose');init.add_argument('--target',type=int,default=12500)
    for name in ['refs','upload','submit','status','resume','attach','download','payload']:
        p=sub.add_parser(name);p.add_argument('--job',required=True)
        if name in ['submit','status','resume','attach','download','payload']:
            p.add_argument('--stage',choices=['generation','lowpoly','glb','fbx'],default='generation')
        if name in ['submit','payload']:p.add_argument('--parent',choices=['generation','lowpoly'])
        if name=='submit':p.add_argument('--allow-charge',action='store_true',help='Use only after user authorization and applicable billing approval')
        if name=='refs':
            for view in VIEWS:p.add_argument('--'+view)
            p.add_argument('--inspected',action='store_true');p.add_argument('--review-note',required=True)
        if name=='resume':p.add_argument('--timeout',type=float,default=1800);p.add_argument('--interval',type=float,default=10)
        if name=='attach':p.add_argument('--task-id',required=True)
    args=parser.parse_args()
    if args.command=='init': print(initialize(args.output,args.description,args.kind,args.pose,args.target));return
    with locked_job(args.job) as (job,save):
        directory=Path(args.job).resolve().parent
        if args.command=='refs':
            if not args.inspected:raise RuntimeError('Visually inspect each image before recording --inspected')
            register_references(job,save,directory,{v:getattr(args,v) for v in VIEWS},args.review_note);print('Reviewed references saved');return
        if args.command=='payload':print(json.dumps(build_payload(job,args.stage,args.parent),indent=2));return
        if args.command=='download':
            files=download_results(job,save,args.stage,directory)
            print(json.dumps(files,indent=2));return
        if args.command=='submit' and not args.allow_charge:raise RuntimeError('Paid submission requires --allow-charge and prior user/billing authorization')
        client=Client()
        if args.command=='upload':upload_references(job,save,client);print('View uploads persisted')
        elif args.command=='submit':print(submit_stage(job,save,client,args.stage,args.parent))
        elif args.command=='status':
            record=check_status(job,save,client,args.stage);print(json.dumps({k:record.get(k) for k in ['task_id','status','progress','error_code']}))
        elif args.command=='resume':wait_task(job,save,client,args.stage,args.timeout,args.interval)
        elif args.command=='attach':attach_task(job,save,client,args.stage,args.task_id);print('Task ID attached without submission')


if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError,TimeoutError,OSError,KeyError) as e:
        # Never print provider exceptions/response bodies or signed URLs.
        print('Error: '+str(e) if isinstance(e,(RuntimeError,ValueError,TimeoutError)) else 'Error: local file or response schema failure',file=__import__('sys').stderr)
        raise SystemExit(1)
