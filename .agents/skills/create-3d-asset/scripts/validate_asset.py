#!/usr/bin/env python3
"""Validate GLB/glTF integrity, actual triangles, UVs and embedded/external PBR images."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile
from PIL import Image

FORMATS={5120:('b',1),5121:('B',1),5122:('h',2),5123:('H',2),5125:('I',4),5126:('f',4)}
COUNTS={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT2':4,'MAT3':9,'MAT4':16}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def at(items,index,label):
    if type(index) is not int or index<0 or index>=len(items):raise ValueError('Invalid '+label+' index')
    return items[index]


def local_bytes(uri,root):
    if uri.startswith('data:'):
        header,data=uri.split(',',1)
        if ';base64' not in header:raise ValueError('Only base64 data URIs supported')
        return base64.b64decode(data,validate=True)
    from urllib.parse import unquote,urlsplit
    if urlsplit(uri).scheme or uri.startswith('//'):raise ValueError('External network URI is not a self-contained deliverable')
    path=(root/unquote(uri)).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('Asset URI escapes deliverable directory')
    return path.read_bytes()


def load_document(path):
    path=Path(path).resolve();raw=path.read_bytes();bin_chunk=None
    if path.suffix.lower()=='.glb':
        if len(raw)<20:raise ValueError('Truncated GLB')
        magic,version,length=struct.unpack_from('<4sII',raw)
        if magic!=b'glTF' or version!=2 or length!=len(raw):raise ValueError('Invalid GLB header/length')
        offset=12;chunks=[]
        while offset<len(raw):
            if offset+8>len(raw):raise ValueError('Truncated chunk header')
            n,kind=struct.unpack_from('<II',raw,offset);offset+=8
            if n%4 or offset+n>len(raw):raise ValueError('Invalid GLB chunk bounds/alignment')
            chunks.append((kind,raw[offset:offset+n]));offset+=n
        if not chunks or chunks[0][0]!=0x4e4f534a:raise ValueError('GLB JSON chunk must be first')
        if len(chunks)>2 or (len(chunks)==2 and chunks[1][0]!=0x004e4942):raise ValueError('Unsupported GLB chunk layout')
        doc=json.loads(chunks[0][1].decode('utf-8').rstrip(' \x00'))
        if len(chunks)==2:bin_chunk=chunks[1][1]
    elif path.suffix.lower()=='.gltf':doc=json.loads(raw)
    else:raise ValueError('Use a .glb or .gltf; convert FBX with blender_asset.py first')
    if doc.get('asset',{}).get('version')!='2.0':raise ValueError('Expected glTF 2.0')
    unsupported=set(doc.get('extensionsRequired',[]))-{'KHR_materials_unlit','KHR_texture_transform','KHR_materials_emissive_strength'}
    if unsupported:raise ValueError('Unsupported required extensions; cannot verify: '+','.join(sorted(unsupported)))
    buffers=[]
    for index,buffer in enumerate(doc.get('buffers',[])):
        data=local_bytes(buffer['uri'],path.parent) if 'uri' in buffer else bin_chunk if index==0 else None
        if data is None or len(data)<buffer['byteLength']:raise ValueError('Missing/truncated buffer')
        buffers.append(data[:buffer['byteLength']])
    for view in doc.get('bufferViews',[]):
        b=at(buffers,view['buffer'],'buffer');start=view.get('byteOffset',0);size=view['byteLength']
        if start<0 or size<0 or start+size>len(b):raise ValueError('Buffer view exceeds buffer')
    return path,doc,buffers


def read_accessor(doc,buffers,index):
    a=at(doc['accessors'],index,'accessor')
    if 'sparse' in a:raise ValueError('Sparse accessor requires an independent validator')
    if 'bufferView' not in a:raise ValueError('Missing accessor buffer view')
    fmt,size=FORMATS[a['componentType']];components=COUNTS[a['type']]
    view=at(doc['bufferViews'],a['bufferView'],'buffer view');stride=view.get('byteStride',size*components)
    if stride<size*components or stride%size:raise ValueError('Invalid accessor stride')
    start=a.get('byteOffset',0);count=a['count'];end=start+max(0,count-1)*stride+(size*components if count else 0)
    if count<0 or start<0 or end>view['byteLength']:raise ValueError('Accessor exceeds buffer view')
    base=view.get('byteOffset',0)+start;buffer=at(buffers,view['buffer'],'buffer')
    values=[struct.unpack_from('<'+fmt*components,buffer,base+i*stride) for i in range(count)]
    if a['componentType']==5126:
        import math
        if not all(math.isfinite(x) for v in values for x in v):raise ValueError('Non-finite geometry')
    return values


def extract_zip(path,directory):
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        infos=archive.infolist()
        if len(infos)>10000 or sum(i.file_size for i in infos)>2*1024**3:raise ValueError('Archive exceeds safe limits')
        for info in infos:
            target=(directory/info.filename).resolve()
            if not target.is_relative_to(directory) or '\\' in info.filename:raise ValueError('Unsafe archive path')
            if (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Archive symlink refused')
            if target.exists() and not info.is_dir():raise ValueError('Refuse to overwrite extracted files')
        bad=archive.testzip()
        if bad:raise ValueError('Archive CRC failure')
        archive.extractall(directory)
    return sorted(str(p) for p in directory.rglob('*') if p.suffix.lower() in {'.glb','.gltf','.fbx'})


def validate(path,texture_dir,target=12500,texture_size=4096):
    path,doc,buffers=load_document(path)
    # Read every accessor, including normals and UVs, to catch truncation/non-finite values.
    accessors=[read_accessor(doc,buffers,i) for i in range(len(doc.get('accessors',[])))]
    mesh_counts=[];all_have_uv=True;all_have_material=True
    for mesh in doc.get('meshes',[]):
        count=0
        for primitive in mesh['primitives']:
            attrs=primitive['attributes'];position=at(accessors,attrs['POSITION'],'position accessor')
            all_have_material=all_have_material and 'material' in primitive
            if at(doc['accessors'],attrs['POSITION'],'position accessor')['type']!='VEC3':raise ValueError('Invalid position accessor')
            for attribute in attrs.values():
                if len(at(accessors,attribute,'attribute accessor'))!=len(position):raise ValueError('Attribute vertex counts differ')
            all_have_uv=all_have_uv and 'TEXCOORD_0' in attrs
            if 'TEXCOORD_0' in attrs and at(doc['accessors'],attrs['TEXCOORD_0'],'UV accessor')['type']!='VEC2':raise ValueError('Invalid UV accessor')
            if 'indices' in primitive:
                a=at(doc['accessors'],primitive['indices'],'index accessor')
                if a['type']!='SCALAR' or a['componentType'] not in {5121,5123,5125}:raise ValueError('Invalid index accessor')
                indices=[v[0] for v in at(accessors,primitive['indices'],'index accessor')]
            else:indices=list(range(len(position)))
            if any(i<0 or i>=len(position) for i in indices):raise ValueError('Index outside vertex array')
            mode=primitive.get('mode',4)
            if mode==4:
                if len(indices)%3:raise ValueError('Incomplete triangle index group')
                triangles=[indices[i:i+3] for i in range(0,len(indices),3)]
            elif mode==5:triangles=[indices[i:i+3] for i in range(max(0,len(indices)-2))]
            elif mode==6:triangles=[[indices[0],indices[i],indices[i+1]] for i in range(1,len(indices)-1)]
            else:raise ValueError('Non-triangle primitive cannot satisfy model triangle budget')
            count+=sum(len(set(t))==3 for t in triangles)
            if 'material' in primitive and not 0<=primitive['material']<len(doc.get('materials',[])):raise ValueError('Invalid material index')
        mesh_counts.append(count)
    if not mesh_counts or sum(mesh_counts)==0:raise ValueError('No triangle geometry')
    nodes=doc.get('nodes',[]);scene=doc.get('scene',0);instance_count=0
    def visit(index,ancestors):
        if index in ancestors:raise ValueError('Scene graph cycle')
        node=at(nodes,index,'scene node');total=at(mesh_counts,node['mesh'],'mesh') if 'mesh' in node else 0
        return total+sum(visit(child,ancestors|{index}) for child in node.get('children',[]))
    if doc.get('scenes'):instance_count=sum(visit(n,set()) for n in at(doc['scenes'],scene,'scene').get('nodes',[]))
    else:instance_count=sum(mesh_counts)
    texture_dir=Path(texture_dir).resolve();texture_dir.mkdir(parents=True,exist_ok=True)
    images=[]
    for index,image in enumerate(doc.get('images',[])):
        if 'uri' in image:raw=local_bytes(image['uri'],path.parent)
        else:
            view=at(doc['bufferViews'],image['bufferView'],'image buffer view');offset=view.get('byteOffset',0);raw=at(buffers,view['buffer'],'image buffer')[offset:offset+view['byteLength']]
        with Image.open(io.BytesIO(raw)) as loaded:loaded.verify()
        with Image.open(io.BytesIO(raw)) as loaded:
            loaded.load();size=list(loaded.size)
            output=texture_dir/f'texture-{index}.png';loaded.save(output)
        images.append({'index':index,'dimensions':size,'path':str(output),'sha256':sha(output)})
    materials=[];pbr_ok=True;used_image_ids=set()
    textures=doc.get('textures',[])
    for i,mat in enumerate(doc.get('materials',[])):
        pbr=mat.get('pbrMetallicRoughness',{});maps={}
        for name,info in [('base_color',pbr.get('baseColorTexture')),('metallic_roughness',pbr.get('metallicRoughnessTexture')),('normal',mat.get('normalTexture')),('occlusion',mat.get('occlusionTexture')),('emissive',mat.get('emissiveTexture'))]:
            if info:
                image_id=at(textures,info['index'],'texture')['source'];image=at(images,image_id,'texture image');maps[name]=image['path'];used_image_ids.add(image_id)
                if info.get('texCoord',0)!=0:raise ValueError('Nonzero UV sets need independent validation')
        # Packed glTF roughness=G, metallic=B; export separate maps for Unreal import.
        if 'metallic_roughness' in maps:
            with Image.open(maps['metallic_roughness']) as packed:
                packed=packed.convert('RGB')
                for name,channel in [('roughness','G'),('metallic','B')]:
                    out=texture_dir/f'material-{i}-{name}.png';packed.getchannel(channel).save(out);maps[name]=str(out)
        if 'occlusion' in maps:
            with Image.open(maps['occlusion']) as packed:
                out=texture_dir/f'material-{i}-occlusion.png';packed.convert('RGB').getchannel('R').save(out);maps['occlusion']=str(out)
        pbr_ok=pbr_ok and all(k in maps for k in ('base_color','metallic_roughness','normal'))
        materials.append({'name':mat.get('name',f'material-{i}'),'maps':maps,'metallic_factor':pbr.get('metallicFactor',1),'roughness_factor':pbr.get('roughnessFactor',1)})
    pbr_ok=pbr_ok and bool(materials) and all_have_material
    dims_ok=bool(used_image_ids) and all(images[i]['dimensions']==[texture_size,texture_size] for i in used_image_ids)
    deviations=[]
    if not 10000<=instance_count<=15000:deviations.append(f'Triangle count {instance_count} is outside 10,000–15,000')
    if instance_count!=target:deviations.append(f'Actual triangle count {instance_count}; requested target {target} (API face_limit is a maximum)')
    if not dims_ok:deviations.append('One or more material textures are missing or are not 4096×4096')
    if not pbr_ok:deviations.append('Complete base-color, normal, metallic/roughness PBR maps are not present for every material')
    if not all_have_uv:deviations.append('One or more primitives lack TEXCOORD_0 UVs')
    if not instance_count:deviations.append('Active scene contains no rendered triangles')
    dependencies=[]
    for entry in doc.get('buffers',[])+doc.get('images',[]):
        uri=entry.get('uri','')
        if uri and not uri.startswith('data:'):
            from urllib.parse import unquote
            dependency=(path.parent/unquote(uri)).resolve()
            dependencies.append({'path':str(dependency),'sha256':sha(dependency)})
    map_files=[{'path':str(p),'sha256':sha(p)} for p in sorted({Path(v) for m in materials for v in m['maps'].values()})]
    return {'dependencies':dependencies,'map_files':map_files,'model':str(path),'sha256':sha(path),'bytes':path.stat().st_size,'integrity_valid':True,
        'unique_mesh_triangles':sum(mesh_counts),'scene_triangles':instance_count,'target_triangles':target,
        'triangle_range_met':10000<=instance_count<=15000,'texture_size_requested':texture_size,'texture_dimensions_met':dims_ok,
        'uv_present':all_have_uv,'pbr_maps_present':pbr_ok,'images':images,'materials':materials,
        'deviations':deviations,'targets_met':10000<=instance_count<=15000 and dims_ok and pbr_ok and all_have_uv}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True);p.add_argument('--report',required=True)
    p.add_argument('--textures');p.add_argument('--target',type=int,default=12500);p.add_argument('--extract-to')
    a=p.parse_args();path=Path(a.input)
    if path.suffix.lower()=='.zip':
        if not a.extract_to:raise ValueError('Supply --extract-to for a ZIP')
        models=extract_zip(path,a.extract_to)
        print(json.dumps({'archive_integrity_valid':True,'models':models},indent=2));return
    report=validate(path,a.textures or str(Path(a.report).parent/'textures'),a.target)
    Path(a.report).parent.mkdir(parents=True,exist_ok=True);Path(a.report).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'images','materials'}},indent=2))
    if not report['targets_met']:raise SystemExit(2)

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,IndexError,OSError,struct.error) as e:
        print('Validation failed: '+str(e),file=__import__('sys').stderr);raise SystemExit(1)
