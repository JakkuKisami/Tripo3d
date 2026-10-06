"""Run in Blender: convert a local glTF/FBX to GLB; verify material retention separately."""
import argparse
import json
from pathlib import Path
import sys
import bpy

p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--report',required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
source=Path(a.input).resolve();destination=Path(a.output).resolve()
if source==destination or destination.exists():raise ValueError('Refuse to overwrite source or existing output')
bpy.ops.wm.read_factory_settings(use_empty=True)
if source.suffix.lower() in {'.glb','.gltf'}:bpy.ops.import_scene.gltf(filepath=str(source))
elif source.suffix.lower()=='.fbx':bpy.ops.import_scene.fbx(filepath=str(source))
else:raise ValueError('Expected GLB, glTF or FBX')
objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
if not objects:raise ValueError('No meshes imported')
triangles=0;uvs=True
for obj in objects:
 obj.data.calc_loop_triangles();triangles+=len(obj.data.loop_triangles);uvs=uvs and bool(obj.data.uv_layers)
if not uvs:raise ValueError('Missing UVs; cannot claim texture preservation')
missing=[i.name for i in bpy.data.images if i.source=='FILE' and i.size[0]==0]
if missing:raise ValueError('Missing textures on import')
destination.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.export_scene.gltf(filepath=str(destination),export_format='GLB',export_materials='EXPORT',export_image_format='AUTO',export_texcoords=True)
Path(a.report).write_text(json.dumps({'source':str(source),'output':str(destination),'imported_triangles':triangles,'uv_present':uvs,'note':'No remeshing, scaling, or UV repacking applied. Material retention is not guaranteed, especially for FBX; validate exported GLB and compare maps separately.'},indent=2)+'\n')
print('LOCAL_CONVERSION_COMPLETE')
