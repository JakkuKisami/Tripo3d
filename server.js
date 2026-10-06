import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const root = new URL('./', import.meta.url);
const files = new Map([['/', 'index.html'], ['/src/app.js', 'src/app.js'], ['/src/mesh.js', 'src/mesh.js'], ['/style.css', 'style.css']]);
http.createServer(async (req, res) => {
  const path = files.get(new URL(req.url, 'http://localhost').pathname);
  if (!path) { res.writeHead(404); res.end('Not found'); return; }
  try {
    const body = await readFile(fileURLToPath(new URL(path, root)));
    res.writeHead(200, { 'Content-Type': path.endsWith('.js') ? 'text/javascript' : path.endsWith('.css') ? 'text/css' : 'text/html', 'X-Content-Type-Options': 'nosniff' });
    res.end(body);
  } catch { res.writeHead(500); res.end('Unable to load application'); }
}).listen(Number(process.env.PORT || 3000), '0.0.0.0', () => console.log('Tripo3d listening on port ' + (process.env.PORT || 3000)));
