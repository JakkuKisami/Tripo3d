# Model-ready reference method

Use one asset specification for every view. Support characters, outfits, creatures, props, and modular environment assets. Derive an explicit list of retained integral features and excluded detachable items from the user request. Maintain the same measurements, body ratios, material assignments, colors, scars, closures, seams, patterns, and silhouette landmarks across views. Never silently change asymmetrical designs to make them symmetrical.

When supplied an existing reference or mannequin, inspect it first and preserve its proportions and pose exactly. Its pose overrides neutral defaults. For outfits, retain the mannequin's shape/pose and garment fit; clarify only when it matters whether the requested deliverable is an outfit-only mesh or a dressed character. Generate the reference around the chosen subject consistently and report mannequin geometry retained by the API; do not promise garment separation without verifying it.

Use neutral T-pose or A-pose for characters by default, with separated limbs/fingers where reasonable and no self-occlusion. Use an appropriate stable neutral pose for creatures; do not force nonhumanoids into a human T-pose. For props, select a stable axis convention and keep it fixed. For environment modules, choose fixed dimensions/grid spacing, straight connection edges, consistent orientation, and no decorative scenery beyond integral features. Record intended world scale; image scale and `auto_size=false` do not guarantee physical dimensions. Confirm import dimensions separately when scale matters.

Generate a complete centered subject, fully visible, with comfortable margins, matching camera scale, neutral plain background, and even diffuse lighting without dramatic shadows. Preserve integral design features. For a clean base model, exclude unwanted weapons, scabbards, accessories, scenery, aura, particles, and VFX. Make detachable equipment separate jobs where appropriate. A spectral creature can have spectral colors/materials without external aura or particles; avoid transparency that hides the geometry.

Generate separate orthographic front, back, left, and right images. Preserve pose and turn only the camera. Left means looking at the subject's left side; do not mirror a right-side picture. Add a three-quarter view only when it resolves ambiguity or helps review, never as a substitute for a cardinal API slot. A multi-view reference set is one asset/model. For review sheets, show no more than two assets per page at a size suitable for detailed screenshots; API uploads must remain individual images.

Use a available image-generation tool to generate the front design, then use that front and the original user reference as image-edit inputs for subsequent views. Follow the actual tool schema for image paths or recent conversation images; do not claim seed-lock or camera-lock options unless the tool supports them. Prompts are constraints, not guarantees: inspect the results.

Before upload, view every reference and compare:

- Pose, limb angles, body/build proportions, width/height ratios, and footing.
- Identical framing, margins, subject scale, and background/lighting.
- Silhouette and integral features on the front/back/side boundaries.
- Correct left/right placement of asymmetric details and no invented equipment.
- Matching palette, material finish, pattern continuity, and garment closures.
- Complete unobstructed geometry with no cropping, VFX, scenes, or extra subjects.

Regenerate incorrect views anchored to the approved design. If the generator cannot resolve inconsistencies, report that limitation before a chargeable model submission. `refs --inspected` records your review; the script only verifies image decoding, minimum size, shared canvas dimensions, and content hashes.
