# Tripo3d

A small, local-first 3D shape studio. Create spheres, cylinders, cones, and tori; adjust proportions and color; orbit and zoom the canvas preview; export Wavefront OBJ geometry. No API keys, databases, accounts, or external packages are required.

## Development

Requires Node.js 22 or newer.

```sh
npm start
```

The development server listens on port 3000. Set `PORT` to use another port. Run `npm test` for geometry/export tests and `npm run check` for JavaScript syntax checks. No dependency installation or build is required.

## Controls

Drag to rotate, scroll to zoom, or focus the canvas and use arrow keys. Download OBJ exports geometry; the preview color is not included in the OBJ file. The renderer uses Canvas 2D with depth-sorted faces and is intended for exploring simple primitives rather than professional modeling. Sphere poles and cone tips use coincident vertices; exports are not guaranteed to be manifold fabrication meshes.

## Cloud tasks

Use the existing isolated checkout in `/workspace/Tripo3d`; creating a worktree is unnecessary. Start `npm start` for development and verify the root page and JavaScript resources respond successfully. Processes must be restarted in new tasks.
