---
name: create-3d-asset
description: Create textured 3D assets from descriptions or existing references using consistent generated orthographic images and the Tripo.ai multiview API. Use for characters, outfits, creatures, props, and modular environments, especially Unreal Engine assets targeting 10,000–15,000 triangles and verified 4K PBR textures. Support resumable jobs, GLB/FBX delivery, and output validation.
---

# Create 3D Asset

Read [Tripo API and commands](references/tripo-api.md) before executing scripts. Read [reference image method](references/reference-method.md) before generating or inspecting images. Use this skill directory in the current workspace.

## Prepare

1. Resolve the requested asset, pose, retained integral features, excluded accessories, and detachable pieces from the user's description. Treat all views of a subject as one asset. Default to one clean base model; create detachable equipment as separate jobs. Ask only for missing information that prevents execution.
2. Locate this skill directory and a persistent deliverable directory. In this cloud workspace use `/workspace/shared/downloads/create-3d-asset/<unique-asset-name>/`; do not store outputs, keys, or task state in Git. If another persistent storage tool is available, upload the final files there and verify persistence. Do not claim a local file has been uploaded to external storage.
3. Check `TRIPO_API_KEY` by presence only, available image-generation tools, Python 3.10+, Pillow, and Blender when conversion is needed. Use injected authentication or an approved secret store. Never print keys, response bodies, raw environment dumps, signed output URLs, or credential files. If a capability is missing, complete independent work and state the precise blocker. Never substitute unrelated images.
4. Initialize one job with `scripts/tripo_asset.py init`. Reuse an existing `job.json` for interrupted work. Default to 12,500 triangles and 4096×4096 PBR maps. These are targets to verify, not guaranteed API results.

## Generate and inspect references

Use the available image-generation capability (here `image_gen.imagegen`) to produce a front orthographic image, then separate back, left, and right images anchored to that approved design. Use the generated `reference-prompts.json` and reference method. Include the user's reference/mannequin and the approved front in subsequent edits; inspect local images before passing them to image editing. If images lack local paths, use the tool's recent-image mechanism only when it includes every necessary reference. Follow the image tool's schema, including its long-running wait and image-return requirements.

Preserve identical design, proportions, scale, pose, materials, and lighting in every view. Use a neutral T-pose/A-pose for characters unless specified; an existing mannequin's exact pose and proportions take priority. Show the complete unobstructed asset with margins on a neutral background under even lighting. Preserve integral features and exclude unwanted equipment, scenery, aura, particles, and VFX. See the reference method for outfits and modular assets.

Inspect every image with the available image-viewing tool. Compare silhouettes, landmarks, asymmetries, pose, materials, colors, crop, and scale. Correct inconsistent views before upload. Create a three-quarter image only when it helps inspection; never put it in a cardinal slot. Limit review sheets to two assets per page at screenshot-readable scale; upload individual views, never a sheet. Record the inspection with `refs --inspected --review-note ...`. This flag records the agent's actual visual review; it does not perform or prove visual consistency itself.

## Generate the model

1. Run `upload`; it persists each view's upload token and detects changed files.
2. Submit `generation` using `--allow-charge` only when the user's asset request authorizes paid generation and applicable billing/approval requirements are satisfied. Do not add unnecessary confirmation, but never bypass a required approval. A setup-only request authorizes no paid task. Poll with `resume` (10–30 second intervals, default 30 minute timeout).
3. Never automatically retry a task submission. Reuse recorded task IDs. An uncertain submission permanently blocks that stage until reconciled with provider support or `attach` using a verified existing ID. Do not delete the marker or create a fresh job to bypass it.
4. Download the generation result and validate it. Prefer `pbr_model` when returned; do not select an untextured `base_model` as the textured deliverable. If it exceeds the triangle range, submit a supported `lowpoly` job with 12,500 face limit and baking; validate its UVs/materials after download. Keep the original files. Do not force another charged job when a timeout or lost response may hide an existing task.
5. Use a `glb` conversion stage (API format `GLTF`) with requested `texture_size=4096`, PNG textures, baking, and `pack_uv=false`. `texture_quality="detailed"` alone does not establish 4K. Conversion documents diffuse-map sizing only and its explicit 4096 acceptance is ambiguous; read the API reference and report this live-test limitation. Verify every PBR map separately. The API may return a GLB or a glTF archive; inspect the actual output and convert glTF locally with Blender if necessary. Request `fbx` conversion from the same successful source when available and authorized. Use `--parent lowpoly` after remeshing. Conversion stages may incur charges.

## Verify and deliver

Validate the selected GLB/glTF with `scripts/validate_asset.py`; extract ZIP archives safely first. Use `scripts/blender_asset.py` to import FBX or package glTF as GLB when needed, then validate its output. Keep API-produced FBX when available, but report it unverified unless it imports successfully. Prefer verified GLB plus extracted PBR textures as the authoritative material deliverable: an offline FBX round-trip test retained geometry/UVs but lost some PBR links, which validation correctly reported. Blender import/export can alter material representation; compare counts, UV presence, and texture maps before claiming preservation. Do not upscale a smaller image and call it native 4K.

Report actual rendered triangle count, texture dimensions, UV presence, PBR map availability, file hashes, and deviations. The validator exports textures and splits packed metallic/roughness/occlusion channels for Unreal use. Exit 2 means integrity passed but target requirements did not; never describe it as a full pass. Unsupported compressed geometry or sparse accessors require an independent validator, not guessed counts. Geometry integrity does not establish artistic fidelity, watertightness, rigging, animation, or collision readiness. Compare model preview/import against the references before declaring design fidelity.

Package validated models, references, extracted textures, validation evidence, and a sanitized task-ID manifest with `scripts/package_asset.py`. Persist and link the ZIP and preferred GLB, plus FBX and textures when present. Provide task IDs. Use the current storage workflow and persist user-facing copies in the thread output directory when provided; use the storage provider's returned links after uploading elsewhere. Do not invent a Tripo dashboard URL or imply API jobs appear in the consumer website. State any unresolved target or live-test limitation clearly.
