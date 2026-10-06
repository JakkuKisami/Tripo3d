export function createMesh(shape, width = 1, height = 1, segments = 32) {
  if (!['sphere', 'cylinder', 'cone', 'torus'].includes(shape)) throw new Error('Unknown shape');
  if (![width, height].every(x => Number.isFinite(x) && x > 0) || !Number.isInteger(segments) || segments < 3 || segments > 128) throw new Error('Invalid dimensions');
  const vertices = [], faces = [];
  const rows = shape === 'torus' || shape === 'sphere' ? 16 : 1;
  for (let j = 0; j <= rows; j++) {
    const v = j / rows;
    for (let i = 0; i < segments; i++) {
      const a = i / segments * Math.PI * 2;
      let r, y;
      if (shape === 'sphere') { r = Math.sin(v * Math.PI) * width; y = Math.cos(v * Math.PI) * height; }
      if (shape === 'cylinder') { r = width; y = (v * 2 - 1) * height; }
      if (shape === 'cone') { r = (1 - v) * width; y = (v * 2 - 1) * height; }
      if (shape === 'torus') { r = width * (0.7 + 0.3 * Math.cos(v * Math.PI * 2)); y = height * 0.3 * Math.sin(v * Math.PI * 2); }
      vertices.push([Math.cos(a) * r, y, Math.sin(a) * r]);
    }
  }
  for (let j = 0; j < rows; j++) for (let i = 0; i < segments; i++) {
    const a = j * segments + i, b = j * segments + (i + 1) % segments;
    faces.push([a, b, b + segments, a + segments]);
  }
  if (shape === 'cylinder' || shape === 'cone') {
    faces.push(Array.from({length: segments}, (_, i) => segments - 1 - i));
    if (shape === 'cylinder') faces.push(Array.from({length: segments}, (_, i) => segments + i));
  }
  return {vertices, faces};
}
export function toOBJ(mesh) {
  return '# Tripo3d procedural mesh\n' + mesh.vertices.map(v => 'v ' + v.join(' ')).join('\n') + '\n' + mesh.faces.map(f => 'f ' + f.map(i => i + 1).join(' ')).join('\n') + '\n';
}
