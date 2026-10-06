# Tripo API contract and execution

## Official sources

Consult current official documentation before updating the integration or using a new model version:

- [Tripo platform documentation](https://platform.tripo3d.ai/docs)
- [Official Tripo SDK API reference](https://github.com/VAST-AI-Research/tripo-python-sdk/blob/master/docs/API.md)
- [Official client source](https://github.com/VAST-AI-Research/tripo-python-sdk/blob/master/tripo3d/client.py)
- [Official multipart implementation](https://github.com/VAST-AI-Research/tripo-python-sdk/blob/master/tripo3d/client_impl/aiohttp_client_impl.py)

Contract rechecked against current official Tripo documentation on 2026-10-06 using the web capability:

- [H2 multiview: exact view slots and at least two images](https://docs.tripo3d.ai/model-generation/multiview-to-model-v2-0-v2-5.html)
- [Direct upload: multipart and 20 MB limit](https://docs.tripo3d.ai/file-upload/quick-upload-directly.html)
- [Task query and expiring result URLs](https://docs.tripo3d.ai/task-query/get-your-task-result.html)
- [Smart low poly: current model version and baking](https://docs.tripo3d.ai/mesh-editing/smart-low-poly-p-v2-0-20251225.html)
- [Conversion: explicit diffuse texture size](https://docs.tripo3d.ai/export/conversion.html)

Use the supported v2 contract below; do not mix it with the newer v3 base URL or payload schema. No live authenticated or charged task has been executed. Test fixtures are synthetic models, not generated assets.

## Supported calls

Use HTTPS base `https://api.tripo3d.ai/v2/openapi` and `Authorization: Bearer <TRIPO_API_KEY>` loaded at runtime. Do not require a prefix check: injected proxy secrets may be placeholders. Do not send API authentication to output/CDN hosts. Keep TLS verification enabled. The wrapper uses standard-library HTTP rather than SDK downloads, which currently contain an automatic TLS-verification bypass; do not copy that behavior.

| Operation | Method and relative path | Contract |
| --- | --- | --- |
| Upload | `POST /upload` | multipart field `file`; response `data.image_token` |
| Submit | `POST /task` | JSON task payload; response `data.task_id` |
| Status | `GET /task/{task_id}` | `data.task_id`, `status`, `progress`, `output`, `error_code` |

The API response envelope uses numeric `code` and a `data` object. The official SDK retains direct multipart uploads as its supported fallback when STS dependencies are absent. This integration deliberately uses that path, not STS credentials. Uploads are normalized to actual JPEGs and sent as `{ "type": "jpg", "file_token": "..." }`.

For generation use `type="multiview_to_model"` with **exactly four positional slots: front, left, back, right**; missing optional views occupy `{}` rather than shifting later views. Front is mandatory. Current official endpoint documentation defines this order; older SDK examples used a conflicting order. The endpoint documentation takes precedence. At least two images are required. Do not place a three-quarter view in a side slot.

Default payload uses the documented stable multiview model `v2.5-20250123`, `face_limit=12500`, `quad=false`, `texture=true`, `pbr=true`, `texture_quality="detailed"`, `smart_low_poly=true`, `export_uv=true`, and `auto_size=false`. Newer documented model families exist, but changing versions may change option support and cost; check current documentation before using them. The face limit is a maximum, not a promise of exactly 12,500 triangles. Count downloaded geometry.

For explicit resolution use `type="convert_model"`, `original_model_task_id`, `format="GLTF"` or `"FBX"`, `texture_size=4096`, `texture_format="PNG"`, `face_limit=12500`, `quad=false`, `bake=true`, `pack_uv=false`, `scale_factor=1.0`, `with_animation=false`. Current conversion docs describe `texture_size` specifically for the diffuse color map, with a 4096 default for models >= v2.0. They also say explicit sizes should be smaller than that default, leaving acceptance of an explicit 4096 ambiguous until tested live. This script requests 4096 as the target; if rejected, preserve the task record and reconcile before any replacement paid submission. This option does not guarantee that normal or metallic/roughness maps are 4K. `texture_quality="detailed"` on generation does **not** document or guarantee 4096×4096. Verify every actual material image. This establishes the supported request parameter, not proof of live 4K output or native texel detail.

For supported remeshing use `type="highpoly_to_lowpoly"`, `original_model_task_id`, `model_version="P-v2.0-20251225"`, `face_limit=12500`, `quad=false`, `bake=true`. Baking retains/reprojects materials; UV coordinate identity is not guaranteed. Keep the original, verify UVs/maps and compare render appearance. Prefer generation's low-poly setting and avoid remeshing when the result already meets the range. Never drop textures to reach a polygon target.

Success outputs may contain `model`, `pbr_model`, `base_model`, and `rendered_image`; recursively download returned HTTPS output URLs. Signed links can expire: refresh task status and retry downloads only, never task submission. Preserve actual file extensions. If an output URL has no recognized suffix, the downloader recognizes GLB, ZIP, PNG, JPEG, and binary FBX magic; other content remains `.bin`. Inspect remaining files before validation, never assume a format from a field name. `GLTF` conversion can return a GLB or a glTF/texture archive; no API `format="GLB"` option is invented. Unpack ZIPs with the safe extractor and convert glTF locally when a single GLB is desired.

There is no documented per-task dashboard link in the consulted API. Return task IDs and files only. Do not assume API jobs appear in the consumer Tripo site.

## Setup and commands

POSIX Python 3.10+ and Pillow are required; Blender is optional for glTF packaging and FBX inspection. Pillow 12.3.0 and Blender are available in the current machine. In another environment create a virtual environment and run `python -m pip install -r <skill-dir>/scripts/requirements.txt`; the dependency is pinned to the locally validated Pillow release. No third-party HTTP client is required. Securely bind `TRIPO_API_KEY` to `api.tripo3d.ai`. Save credentials only through environment settings or a supported secret store. Permit the documentation host and the exact CDN/storage hosts returned by the API when needed. Do not widen unknown network allowlists or ask for keys in chat.

Run commands using the actual skill directory, for example:

```sh
SKILL_DIR=/workspace/Tripo3d/.agents/skills/create-3d-asset
ASSET_DIR=/workspace/shared/downloads/create-3d-asset/spectral-bandit-001
python3 "$SKILL_DIR/scripts/tripo_asset.py" init --output "$ASSET_DIR" --kind character --description 'Scary spectral Japanese bandit, no weapon or aura, for Unreal Engine'
```

Generate images with the available image-generation tool using `reference-prompts.json`; preserve the actual local file paths returned by that capability. Inspect each image before the following commands. Replace paths below with inspected images:

```sh
python3 "$SKILL_DIR/scripts/tripo_asset.py" refs --job "$ASSET_DIR/job.json" --front /path/front.png --back /path/back.png --left /path/left.png --right /path/right.png --inspected --review-note 'Compared pose, silhouette, proportions, scale, materials, lighting and asymmetric landmarks; no excluded equipment or VFX.'
python3 "$SKILL_DIR/scripts/tripo_asset.py" upload --job "$ASSET_DIR/job.json"
python3 "$SKILL_DIR/scripts/tripo_asset.py" payload --job "$ASSET_DIR/job.json"
```

The next commands spend credits. Execute only under an authorized asset request and applicable approvals; never execute during setup-only testing:

```sh
python3 "$SKILL_DIR/scripts/tripo_asset.py" submit --job "$ASSET_DIR/job.json" --stage generation --allow-charge
python3 "$SKILL_DIR/scripts/tripo_asset.py" resume --job "$ASSET_DIR/job.json" --stage generation --interval 10 --timeout 1800
python3 "$SKILL_DIR/scripts/tripo_asset.py" download --job "$ASSET_DIR/job.json" --stage generation
python3 "$SKILL_DIR/scripts/tripo_asset.py" submit --job "$ASSET_DIR/job.json" --stage glb --allow-charge
python3 "$SKILL_DIR/scripts/tripo_asset.py" resume --job "$ASSET_DIR/job.json" --stage glb
python3 "$SKILL_DIR/scripts/tripo_asset.py" download --job "$ASSET_DIR/job.json" --stage glb
```

Use `--stage fbx` for FBX conversion when available. If generation exceeds the range, use `--stage lowpoly`, resume/download/validate that result, then use `--parent lowpoly` for conversions. Never submit an unnecessary remesh to raise a low triangle count; report below-range results and decide whether a new generation is justified under the authorized budget.

```sh
python3 "$SKILL_DIR/scripts/validate_asset.py" --input "$ASSET_DIR/results/glb/model.glb" --report "$ASSET_DIR/validation.json"
# For an archive instead:
python3 "$SKILL_DIR/scripts/validate_asset.py" --input /actual/result.zip --report "$ASSET_DIR/archive-check.json" --extract-to "$ASSET_DIR/unpacked-v1"
# If local glTF or FBX packaging/inspection is needed:
blender --background --python "$SKILL_DIR/scripts/blender_asset.py" -- --input /actual/model.gltf --output "$ASSET_DIR/model.glb" --report "$ASSET_DIR/local-conversion.json"
python3 "$SKILL_DIR/scripts/package_asset.py" --job "$ASSET_DIR/job.json" --validation "$ASSET_DIR/validation.json" --output "$ASSET_DIR/asset-v1.zip"
```

Use actual downloaded filenames; `model.glb` above is an example. Validator exits: 0 = integrity and target range/4K/PBR/UV requirements met; 2 = integrity passed with target deviations; 1 = integrity unverified/failed. Unsupported required compression extensions, sparse accessors, or non-triangle primitives fail verification. Triangle counts include repeated mesh instances in the active scene. A target within the requested range can pass despite differing from exactly 12,500; report that difference.

Poll only existing IDs with `status` or `resume`. `resume` never submits. A durable `submission_uncertain` record is written before every paid POST, with file synchronization and a process lock. After a crash, timeout, ambiguous HTTP failure, or malformed task-ID response, submission is blocked rather than retried. No documented idempotency key or task-list reconciliation endpoint is assumed. Contact Tripo support if the ID was lost. Use `attach --stage ... --task-id ...` only after obtaining the real ID; it verifies task type and, for uncertain submissions, echoed input fields. Failed tasks also do not automatically resubmit. API error bodies are deliberately omitted from logs.

Keep `job.json` and references/results persistently for resumption, never in Git or a public bundle: job state contains upload identifiers and signed download URLs. Packaging exports only a sanitized task-ID/hash manifest, verified files, and references. This environment exposes local persistent download storage, not an external storage-upload connector. Return clickable absolute local links and state that storage location accurately; snapshot retention across new machines requires the environment's publication workflow.

## Validation boundary

Validated locally: offline tests covering mock HTTP/multipart contracts, view slots, reference hashes, duplicate/uncertain submissions, task resumption, explicit 4096 conversion payloads, unauthenticated result downloads, truncation handling, safe ZIP extraction, actual geometry/image decoding, synthetic 12,500-triangle 4K PBR model validation, texture extraction, and sanitized packaging. No mock test contacts Tripo or spends credits. Skill frontmatter/UI metadata passed the official skill-creator validation workflow.

Blender GLB import/export retained UVs and PBR map presence, but merged the synthetic fixture’s repeated overlapping triangles from 12,500 to 1. Revalidate triangle counts after every conversion; do not promise count preservation. Synthetic FBX import/export retained geometry/UVs but lost some PBR material links; the validator correctly reported missing maps. Treat FBX material fidelity as unverified until inspected for the actual API output; supply verified GLB and separate textures alongside it. Draco decoding is unavailable in this machine, so compressed models need an appropriate decoder before counts can be verified.

Not validated live: API credential authentication, provider acceptance of generation/remesh/conversion payloads, image-to-model artistic consistency, actual native 4K provider output, conversion costs, result CDN access, and Unreal Engine import. The image-generation capability is available in this chat but was not invoked to create an asset during setup. The runtime has a TRIPO_API_KEY binding, but readiness is unknown and the configured HTTP proxy was unreachable during setup. Restore the managed environment proxy and confirm secret readiness before a future authorized live request; add exact returned storage/CDN hosts if downloads are blocked. Do not mark the end-to-end workflow operational until these prerequisites and a live asset request succeed.
