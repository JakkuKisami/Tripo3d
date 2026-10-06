import test from 'node:test';
import assert from 'node:assert/strict';
import {createMesh,toOBJ} from '../src/mesh.js';
for(const shape of ['sphere','cylinder','cone','torus']) test(`${shape} produces valid exportable geometry`,()=>{
 const mesh=createMesh(shape,1.2,.8,32);
 assert.ok(mesh.vertices.length>0);assert.ok(mesh.faces.length>0);
 assert.ok(mesh.vertices.every(v=>v.length===3&&v.every(Number.isFinite)));
 assert.ok(mesh.faces.every(f=>f.length>=3&&f.every(i=>Number.isInteger(i)&&i>=0&&i<mesh.vertices.length)));
 const obj=toOBJ(mesh).split('\n');
 assert.equal(obj.filter(l=>l.startsWith('v ')).length,mesh.vertices.length);
 assert.equal(obj.filter(l=>l.startsWith('f ')).length,mesh.faces.length);
 assert.ok(!obj.some(l=>/NaN|undefined|Infinity/.test(l)));
});
test('dimensions change the generated geometry',()=>{const m=createMesh('cylinder',2,3);assert.equal(Math.max(...m.vertices.map(v=>v[0])),2);assert.equal(Math.max(...m.vertices.map(v=>v[1])),3);});
test('invalid shape and dimensions fail explicitly',()=>{assert.throws(()=>createMesh('unknown'));assert.throws(()=>createMesh('sphere',0));assert.throws(()=>createMesh('sphere',1,1,2));});
