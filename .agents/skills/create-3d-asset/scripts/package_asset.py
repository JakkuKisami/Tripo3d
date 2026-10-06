#!/usr/bin/env python3
"""Package persistent user deliverables without API keys, upload tokens or signed URLs."""
import argparse
import json
from pathlib import Path
import zipfile
from tripo_asset import atomic_json,digest


def package(job_path,report_path,output):
    job_path=Path(job_path).resolve();directory=job_path.parent
    job=json.loads(job_path.read_text());report=json.loads(Path(report_path).read_text())
    if not report.get('integrity_valid'):raise ValueError('A valid integrity report is required')
    model=Path(report['model']).resolve()
    if digest(model)!=report['sha256']:raise ValueError('Model changed after validation')
    files={model}
    # Include downloaded models, archives and associated buffers/textures, never raw state.
    for task in job['tasks'].values():
        for item in task.get('downloads',[]):
            path=Path(item['path']).resolve()
            if not path.is_relative_to(directory):raise ValueError('Download is outside persistent job directory')
            if digest(path)!=item['sha256']:raise ValueError('Downloaded file integrity changed')
            files.add(path)
    for image in report.get('images',[]):
        path=Path(image['path']).resolve()
        if digest(path)!=image['sha256']:raise ValueError('Extracted texture changed after validation')
        files.add(path)
    for item in report.get('dependencies',[])+report.get('map_files',[]):
        path=Path(item['path']).resolve()
        if digest(path)!=item['sha256']:raise ValueError('Model dependency or material map changed after validation')
        files.add(path)
    for reference in job['references'].values():
        path=Path(reference['path']).resolve()
        if digest(path)!=reference['sha256']:raise ValueError('Reference changed after inspection')
        files.add(path)
    # glTF external files are retained by the validated directory, including extracted archives.
    if model.suffix.lower()=='.gltf':
        files.update(p.resolve() for p in model.parent.rglob('*') if p.is_file() and p.suffix.lower() in {'.bin','.png','.jpg','.jpeg','.webp'})
    manifest={'asset_description':job['description'],'targets':job['targets'],
        'task_ids':{stage:task.get('task_id') for stage,task in job['tasks'].items()},
        'validation':{k:v for k,v in report.items() if k not in {'model','images','materials','dependencies','map_files'}},'files':[]}
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise ValueError('Deliverable already exists; use a new versioned filename')
    # Ensure local paths stay in the job, and retain subdirectories to preserve glTF URI references.
    for path in sorted(files):
        if not path.is_relative_to(directory):raise ValueError('Deliverable outside persistent job directory')
        manifest['files'].append({'path':str(path.relative_to(directory)),'bytes':path.stat().st_size,'sha256':digest(path)})
    manifest['validation']['images']=[{'dimensions':image['dimensions'],'path':str(Path(image['path']).resolve().relative_to(directory)),'sha256':image['sha256']} for image in report.get('images',[])]
    manifest['validation']['materials']=[{'name':m['name'],'maps':{k:str(Path(v).resolve().relative_to(directory)) for k,v in m.get('maps',{}).items()}} for m in report.get('materials',[])]
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):archive.write(path,str(path.relative_to(directory)))
        archive.writestr('manifest.json',json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(output) as archive:
        if archive.testzip():raise ValueError('Packaged archive CRC failure')
    atomic_json(output.with_suffix('.manifest.json'),manifest)
    return {'path':str(output),'bytes':output.stat().st_size,'sha256':digest(output),'task_ids':manifest['task_ids'],'deviations':report.get('deviations',[])}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--job',required=True);p.add_argument('--validation',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    try:print(json.dumps(package(a.job,a.validation,a.output),indent=2))
    except (ValueError,OSError,KeyError) as e:print('Packaging failed: '+str(e),file=__import__('sys').stderr);raise SystemExit(1)
