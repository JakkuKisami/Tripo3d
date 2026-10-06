"""Offline regression tests; no real API requests or paid submissions."""
import contextlib
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from PIL import Image
import tripo_asset as workflow
import validate_asset as validator
import package_asset as packaging


def make_glb(path,triangles=12500,size=4096):
    chunks=[];views=[]
    def put(raw):
        offset=sum(map(len,chunks));views.append({'buffer':0,'byteOffset':offset,'byteLength':len(raw)})
        raw+=b'\0'*((-len(raw))%4);chunks.append(raw);return len(views)-1
    pos=put(struct.pack('<9f',0,0,0,1,0,0,0,1,0));uv=put(struct.pack('<6f',0,0,1,0,0,1))
    idx=put(struct.pack('<'+'H'*(triangles*3),*([0,1,2]*triangles)))
    images=[]
    for color in [(100,150,200),(128,128,255),(255,160,20)]:
        image=Image.new('RGB',(size,size),color);stream=io.BytesIO();image.save(stream,format='PNG');image.close()
        images.append({'bufferView':put(stream.getvalue()),'mimeType':'image/png'})
    binary=b''.join(chunks)
    doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],'bufferViews':views,
        'accessors':[{'bufferView':pos,'componentType':5126,'count':3,'type':'VEC3'},
                     {'bufferView':uv,'componentType':5126,'count':3,'type':'VEC2'},
                     {'bufferView':idx,'componentType':5123,'count':triangles*3,'type':'SCALAR'}],
        'images':images,'textures':[{'source':i} for i in range(3)],
        'materials':[{'pbrMetallicRoughness':{'baseColorTexture':{'index':0},'metallicRoughnessTexture':{'index':2}},'normalTexture':{'index':1}}],
        'meshes':[{'primitives':[{'attributes':{'POSITION':0,'TEXCOORD_0':1},'indices':2,'material':0}]}],
        'nodes':[{'mesh':0}],'scenes':[{'nodes':[0]}],'scene':0}
    raw=json.dumps(doc).encode();raw+=b' '*((-len(raw))%4)
    glb=struct.pack('<4sII',b'glTF',2,12+8+len(raw)+8+len(binary))+struct.pack('<II',len(raw),0x4e4f534a)+raw+struct.pack('<II',len(binary),0x004e4942)+binary
    Path(path).write_bytes(glb)
    return doc


class FakeClient:
    def __init__(self):self.submits=[];self.uploads=[];self.calls=0;self.fail=False
    def upload(self,path):self.uploads.append(path);return 'test-upload-'+str(len(self.uploads))
    def submit(self,payload):
        self.submits.append(payload)
        if self.fail:raise RuntimeError('Simulated timeout after server accepts task')
        return 'test-task-001'
    def status(self,task_id):
        self.calls+=1
        return {'task_id':task_id,'type':'multiview_to_model','status':'success','progress':100,'output':{}}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.job_path=workflow.initialize(self.root/'asset','A bandit, no weapon or aura','character')
        self.job=json.loads(self.job_path.read_text());self.save=lambda:workflow.atomic_json(self.job_path,self.job)
        self.client=FakeClient()
    def tearDown(self):self.temp.cleanup()
    def refs(self):
        paths={}
        for view in workflow.VIEWS:
            path=self.root/(view+'.png');Image.new('RGB',(256,256),(100,100,100)).save(path);paths[view]=path
        workflow.register_references(self.job,self.save,self.job_path.parent,paths,'OFFLINE synthetic fixture; no artistic consistency claim')
        workflow.upload_references(self.job,self.save,self.client)
    def test_prompts_preserve_method(self):
        prompts=json.loads((self.job_path.parent/'reference-prompts.json').read_text())
        self.assertEqual(list(prompts),list(workflow.VIEWS))
        for v,p in prompts.items():
            for text in [v+' orthographic','proportions and pose exactly','comfortable margins','No perspective distortion','No perspective','aura','modular']:
                if text=='modular':continue
                self.assertIn(text,p)
    def test_reinitialize_refuses_duplicate(self):
        with self.assertRaises(RuntimeError):workflow.initialize(self.job_path.parent,'another','prop')
    def test_upload_resume_and_slot_order(self):
        self.refs();workflow.upload_references(self.job,self.save,self.client)
        self.assertEqual(len(self.client.uploads),4)
        payload=workflow.build_payload(self.job,'generation')
        self.assertEqual([f['file_token'] for f in payload['files']],['test-upload-'+str(i) for i in range(1,5)])
        self.assertEqual(payload['face_limit'],12500);self.assertTrue(payload['pbr']);self.assertFalse(payload['quad'])
    def test_missing_slot_keeps_placeholder(self):
        self.refs();del self.job['references']['back']
        files=workflow.build_payload(self.job,'generation')['files']
        self.assertEqual(files[1],{});self.assertEqual(files[2]['file_token'],'test-upload-3')
    def test_changed_reference_blocks_submit(self):
        self.refs();Path(self.job['references']['front']['path']).write_bytes(b'changed')
        with self.assertRaises(RuntimeError):workflow.build_payload(self.job,'generation')
    def test_review_and_front_required(self):
        with self.assertRaises(RuntimeError):workflow.upload_references(self.job,self.save,self.client)
        with self.assertRaises(ValueError):workflow.register_references(self.job,self.save,self.job_path.parent,{},'reviewed')
    def test_duplicate_submission_not_sent(self):
        self.refs();a=workflow.submit_stage(self.job,self.save,self.client,'generation');b=workflow.submit_stage(self.job,self.save,self.client,'generation')
        self.assertEqual(a,b);self.assertEqual(len(self.client.submits),1)
    def test_uncertain_submission_survives_reload(self):
        self.refs();self.client.fail=True
        with self.assertRaises(RuntimeError):workflow.submit_stage(self.job,self.save,self.client,'generation')
        disk=json.loads(self.job_path.read_text());self.assertEqual(disk['tasks']['generation']['status'],'submission_uncertain')
        with self.assertRaises(RuntimeError):workflow.submit_stage(disk,self.save,self.client,'generation')
        self.assertEqual(len(self.client.submits),1)
    def test_resume_only_polls(self):
        self.refs();workflow.submit_stage(self.job,self.save,self.client,'generation')
        with contextlib.redirect_stdout(io.StringIO()):workflow.wait_task(self.job,self.save,self.client,'generation',timeout=1)
        self.assertEqual(len(self.client.submits),1);self.assertEqual(self.job['tasks']['generation']['status'],'success')
    def test_timeout_preserves_id(self):
        self.job['tasks']['generation']={'task_id':'test-task-001','status':'running'}
        self.client.status=lambda t:{'task_id':t,'status':'running','output':{}}
        with patch('tripo_asset.time.sleep'),patch('tripo_asset.time.monotonic',side_effect=[0,0,0,2]),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(TimeoutError):workflow.wait_task(self.job,self.save,self.client,'generation',timeout=1)
        self.assertEqual(self.job['tasks']['generation']['task_id'],'test-task-001');self.assertFalse(self.client.submits)
    def test_conversion_requests_explicit_4k(self):
        self.job['tasks']['generation']={'task_id':'test-task-001','status':'success'}
        for stage,fmt in [('glb','GLTF'),('fbx','FBX')]:
            payload=workflow.build_payload(self.job,stage)
            self.assertEqual(payload['texture_size'],4096);self.assertEqual(payload['format'],fmt);self.assertFalse(payload['pack_uv']);self.assertTrue(payload['bake'])
        payload=workflow.build_payload(self.job,'lowpoly');self.assertEqual(payload['type'],'highpoly_to_lowpoly');self.assertTrue(payload['bake'])
    def test_attach_checks_type_and_input(self):
        self.job['tasks']['generation']={'status':'submission_uncertain','payload':{'type':'multiview_to_model','face_limit':12500}}
        with self.assertRaises(ValueError):workflow.attach_task(self.job,self.save,self.client,'generation','test-task-001')
        self.client.status=lambda t:{'task_id':t,'type':'multiview_to_model','status':'running','input':{'face_limit':12500},'output':{}}
        workflow.attach_task(self.job,self.save,self.client,'generation','test-task-001');self.assertEqual(self.job['tasks']['generation']['task_id'],'test-task-001')
    def test_missing_credential_blocks_client(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(RuntimeError):workflow.Client()
    def test_process_lock_prevents_competing_commands(self):
        with workflow.locked_job(self.job_path):
            with self.assertRaises(RuntimeError):
                with workflow.locked_job(self.job_path):pass
    def test_safe_result_urls(self):
        for url in ['http://cdn.example/a.glb','https://127.0.0.1/a','https://user:secret@cdn.example/a','https://localhost/a']:
            with self.assertRaises(ValueError):workflow.safe_https(url)
    def test_http_contract_and_no_post_retry(self):
        calls=[]
        class Opener:
            def open(self,req,timeout):
                calls.append(req)
                return contextlib.closing(io.BytesIO(json.dumps({'code':0,'data':{'task_id':'test-task-001'}}).encode()))
        with patch.dict(os.environ,{'TRIPO_API_KEY':'offline-placeholder'}):client=workflow.Client()
        client.opener=Opener();self.assertEqual(client.submit({'type':'multiview_to_model'}),'test-task-001')
        self.assertEqual(calls[0].full_url,workflow.BASE+'/task');self.assertEqual(calls[0].method,'POST')
        self.assertEqual(calls[0].get_header('Authorization'),'Bearer offline-placeholder')
        class FailingOpener:
            def open(self,*args,**kwargs):calls.append(None);raise TimeoutError()
        client.opener=FailingOpener()
        with self.assertRaises(RuntimeError):client.submit({})
        self.assertEqual(len(calls),2)
    def test_multipart_upload_contract(self):
        calls=[]
        class Opener:
            def open(self,req,timeout):
                calls.append(req)
                return contextlib.closing(io.BytesIO(b'{"code":0,"data":{"image_token":"test-upload-token"}}'))
        with patch.dict(os.environ,{'TRIPO_API_KEY':'offline-placeholder'}):client=workflow.Client()
        client.opener=Opener();image=self.root/'ref.jpg';image.write_bytes(b'JPEG FIXTURE')
        self.assertEqual(client.upload(image),'test-upload-token')
        self.assertEqual(calls[0].full_url,workflow.BASE+'/upload')
        self.assertIn(b'name="file"',calls[0].data);self.assertIn(b'JPEG FIXTURE',calls[0].data)
        self.assertTrue(calls[0].get_header('Content-type').startswith('multipart/form-data; boundary='))
    def test_downloader_omits_auth_and_rejects_truncation(self):
        calls=[]
        class Response(io.BytesIO):
            def __init__(self,body,length):super().__init__(body);self.headers={'Content-Length':str(length)}
        class Opener:
            def __init__(self,length):self.length=length
            def open(self,req,timeout):calls.append(req);return Response(b'abc',self.length)
        path=self.root/'result.glb'
        result=workflow.download_file('https://cdn.example/result.glb?signature=test',path,Opener(3))
        self.assertEqual(result['bytes'],3);self.assertIsNone(calls[0].get_header('Authorization'))
        with self.assertRaises(ValueError):workflow.download_file('https://cdn.example/result.glb',self.root/'truncated.glb',Opener(4))
        self.assertFalse((self.root/'truncated.glb').exists());self.assertFalse((self.root/'truncated.glb.part').exists())
    def test_mixed_canvas_dimensions_rejected(self):
        a=self.root/'a.png';b=self.root/'b.png';Image.new('RGB',(256,256)).save(a);Image.new('RGB',(512,256)).save(b)
        with self.assertRaises(ValueError):workflow.register_references(self.job,self.save,self.job_path.parent,{'front':a,'back':b},'inspected')
        self.assertNotIn('review',self.job)
    def test_failed_task_does_not_resubmit(self):
        self.job['tasks']['generation']={'task_id':'test-task-001','status':'running'}
        self.client.status=lambda t:{'task_id':t,'status':'failed','error_code':123,'output':{}}
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):workflow.wait_task(self.job,self.save,self.client,'generation',timeout=1)
        self.assertEqual(self.job['tasks']['generation']['status'],'failed');self.assertFalse(self.client.submits)
        self.assertEqual(workflow.submit_stage(self.job,self.save,self.client,'generation'),'test-task-001');self.assertFalse(self.client.submits)
    def test_changed_material_map_blocks_packaging(self):
        model=self.job_path.parent/'model.glb';make_glb(model,triangles=1,size=8)
        report=validator.validate(model,self.job_path.parent/'textures');report_path=self.job_path.parent/'validation.json';report_path.write_text(json.dumps(report))
        Path(report['map_files'][0]['path']).write_bytes(b'changed')
        with self.assertRaises(ValueError):packaging.package(self.job_path,report_path,self.job_path.parent/'asset.zip')
    def test_integrity_and_target_validation(self):
        model=self.job_path.parent/'model.glb';make_glb(model)
        report=validator.validate(model,self.job_path.parent/'textures')
        self.assertTrue(report['targets_met']);self.assertEqual(report['scene_triangles'],12500)
        self.assertEqual([i['dimensions'] for i in report['images']],[[4096,4096]]*3)
        self.assertTrue(report['uv_present']);self.assertTrue(report['pbr_maps_present'])
        report_path=self.job_path.parent/'validation.json';report_path.write_text(json.dumps(report))
        # Sensitive runtime state must not be included in public deliverables.
        self.job['tasks']['generation']={'task_id':'test-task-001','status':'success','output':{'model':'https://cdn.example/a?signature=DO_NOT_DELIVER'}};self.save()
        output=self.job_path.parent/'asset.zip';result=packaging.package(self.job_path,report_path,output)
        self.assertEqual(result['task_ids']['generation'],'test-task-001')
        with zipfile.ZipFile(output) as archive:
            self.assertIsNone(archive.testzip());self.assertNotIn('job.json',archive.namelist())
            self.assertNotIn('DO_NOT_DELIVER',archive.read('manifest.json').decode())
            self.assertIn('textures/material-0-roughness.png',archive.namelist())
    def test_deviations_reported_not_hidden(self):
        model=self.root/'small.glb';make_glb(model,triangles=1,size=8)
        report=validator.validate(model,self.root/'textures')
        self.assertFalse(report['targets_met']);self.assertFalse(report['texture_dimensions_met']);self.assertFalse(report['triangle_range_met'])
        self.assertGreaterEqual(len(report['deviations']),3)
    def test_truncated_glb_fails(self):
        model=self.root/'bad.glb';make_glb(model,triangles=1,size=8);model.write_bytes(model.read_bytes()[:-1])
        with self.assertRaises(ValueError):validator.validate(model,self.root/'textures')
    def test_archive_traversal_refused(self):
        archive=self.root/'bad.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape.glb',b'bad')
        with self.assertRaises(ValueError):validator.extract_zip(archive,self.root/'extracted')
    def test_negative_gltf_indices_fail(self):
        with self.assertRaises(ValueError):validator.at([{}],-1,'accessor')
        with self.assertRaises(ValueError):validator.at([{}],True,'accessor')
    def test_download_magic_and_resumption(self):
        self.job['tasks']['generation']={'status':'success','task_id':'test-task-001','output':{'pbr_model':'https://cdn.example/result?signature=test'}}
        source=self.root/'fixture.glb';make_glb(source,triangles=1,size=8)
        calls=[]
        def download(url,target):
            calls.append(url);Path(target).write_bytes(source.read_bytes())
            return {'path':str(Path(target).resolve()),'bytes':Path(target).stat().st_size,'sha256':workflow.digest(target)}
        with patch('tripo_asset.download_file',side_effect=download):
            files=workflow.download_results(self.job,self.save,'generation',self.job_path.parent)
            self.assertTrue(files[0]['path'].endswith('.glb'))
            workflow.download_results(self.job,self.save,'generation',self.job_path.parent)
        self.assertEqual(len(calls),1)
    def test_safe_archive_extract(self):
        archive=self.root/'ok.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('asset/model.gltf','{}')
        files=validator.extract_zip(archive,self.root/'extracted');self.assertEqual(len(files),1)
        with self.assertRaises(ValueError):validator.extract_zip(archive,self.root/'extracted')

if __name__=='__main__':unittest.main()
