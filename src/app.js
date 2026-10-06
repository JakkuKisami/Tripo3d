import {createMesh, toOBJ} from './mesh.js';
const $ = id => document.getElementById(id);
const canvas = $('scene'), ctx = canvas.getContext('2d');
let shape = 'sphere', yaw = 0.6, pitch = -0.3, zoom = 1, dragging = null, mesh;
function rebuild() {
  mesh = createMesh(shape, Number($('width').value), Number($('height').value));
  for (const id of ['width','height']) $(id+'-value').textContent = Number($(id).value).toFixed(2);
  $('shape-name').textContent = shape.toUpperCase();
  $('stats').textContent = `${mesh.vertices.length} vertices / ${mesh.faces.length} faces`;
  document.querySelectorAll('[data-shape]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.shape === shape)));
  draw();
}
function draw() {
  const w = canvas.clientWidth, h = canvas.clientHeight, dpr = window.devicePixelRatio || 1;
  canvas.width = w * dpr; canvas.height = h * dpr; ctx.scale(dpr,dpr);
  ctx.clearRect(0,0,w,h);
  ctx.strokeStyle = '#ddd8e7'; ctx.lineWidth = 1;
  for (let i=-8;i<=8;i++) { ctx.beginPath();ctx.moveTo(w/2+i*40,h*.7);ctx.lineTo(w/2+i*65,h);ctx.stroke();ctx.beginPath();ctx.moveTo(0,h*.7+(i+8)*18);ctx.lineTo(w,h*.7+(i+8)*18);ctx.stroke(); }
  const points = mesh.vertices.map(([x,y,z]) => {
    const xx=x*Math.cos(yaw)+z*Math.sin(yaw), zz=-x*Math.sin(yaw)+z*Math.cos(yaw);
    const yy=y*Math.cos(pitch)-zz*Math.sin(pitch), depth=y*Math.sin(pitch)+zz*Math.cos(pitch);
    const scale=Math.min(w,h)*.29*zoom/(1+depth*.12);
    return [w/2+xx*scale,h/2-yy*scale,depth];
  });
  const color=$('color').value;
  mesh.faces.map(f=>({f,z:f.reduce((a,i)=>a+points[i][2],0)/f.length})).sort((a,b)=>b.z-a.z).forEach(({f,z})=>{
    ctx.beginPath();f.forEach((i,j)=> j ? ctx.lineTo(points[i][0],points[i][1]) : ctx.moveTo(points[i][0],points[i][1]));ctx.closePath();
    ctx.fillStyle=color;ctx.fill();ctx.fillStyle=`rgba(30,15,55,${Math.max(0,Math.min(.5,.19+z*.13))})`;ctx.fill();
    ctx.strokeStyle=$('wireframe').checked?'#625078':color;ctx.lineWidth=$('wireframe').checked?.7:.3;ctx.stroke();
  });
}
document.querySelectorAll('[data-shape]').forEach(b=>b.addEventListener('click',()=>{shape=b.dataset.shape;rebuild();}));
for(const id of ['width','height','color','wireframe']) $(id).addEventListener('input',rebuild);
canvas.addEventListener('pointerdown',e=>{dragging=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);});
canvas.addEventListener('pointermove',e=>{if(!dragging)return;yaw+=(e.clientX-dragging[0])*.01;pitch=Math.max(-1.5,Math.min(1.5,pitch+(e.clientY-dragging[1])*.01));dragging=[e.clientX,e.clientY];draw();});
for(const event of ['pointerup','pointercancel','lostpointercapture']) canvas.addEventListener(event,()=>dragging=null);
canvas.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.4,Math.min(1.7,zoom-e.deltaY*.001));draw();},{passive:false});
canvas.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();yaw+=(e.key==='ArrowRight'?.1:e.key==='ArrowLeft'?-.1:0);pitch=Math.max(-1.5,Math.min(1.5,pitch+(e.key==='ArrowUp'?.1:e.key==='ArrowDown'?-.1:0)));draw();});
$('reset').addEventListener('click',()=>{shape='sphere';yaw=.6;pitch=-.3;zoom=1;$('width').value=1;$('height').value=1;$('color').value='#b9a5ff';$('wireframe').checked=false;rebuild();});
$('export').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([toOBJ(mesh)],{type:'text/plain'}));const a=document.createElement('a');a.href=url;a.download=`tripo3d-${shape}.obj`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
new ResizeObserver(draw).observe(canvas);rebuild();
