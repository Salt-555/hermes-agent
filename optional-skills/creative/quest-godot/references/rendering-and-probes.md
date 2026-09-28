# Rendering, Probes, and What Tests Cannot See

Companion to the `quest-godot` skill. Read before touching anything that appears on
screen.

## The headless blindness law

A headless Godot run uses a dummy renderer. It **never compiles shaders** and **never
rasterizes**. Consequently:

- A shader that fails to compile is invisible to the suite and renders opaque black on
  device.
- A draw that produces zero pixels still passes every assertion you can write against
  scene state.
- A scene graph that is correct in every property can render nothing at all.

This is not a limitation to work around; it is a boundary between two kinds of proof.
Anything whose correctness lives in rendering, stereo, timing, or the compositor needs a
proof from outside the test runner.

## Two proofs that do work

**Real-GL windowed probe (host).** Run the project with a real GL driver in a windowed
context and read back pixels. This settles questions headless cannot: whether a fragment
program compiled, whether anything drew, whether a mask or clip produced the expected
region. It iterates far faster than a device round.

- Assert on **pixels**, not on a clean log. A logcat with zero script errors is not pixels.
- Make the assertion narrow and numeric ("this region is non-empty, that region is empty")
  rather than golden-image comparison; golden images churn with driver and resolution.
- Keep the probe scene minimal — the mechanism in your real configuration (same materials,
  same duplication, same wiring), not a bare demo. A mechanism that works in a bare probe
  can still die at the boundary where your materials get duplicated per instance.

**Worn gate (human in the headset).** The only proof that can see the compositor, stereo
reprojection, or frame timing. Protocol matters more than the check:

- Announce **which build** is on the headset and what it is meant to prove, before the
  headset goes on. A diagnostic build reported on as if it were the fix wastes the scarcest
  resource in the loop.
- Never gate-test something the user cannot see or feel. If a layer has no visual surface,
  it is not gate-ready.
- When the user reports behaviour, that report **is** the bug report. It does not need to
  be reconciled against log optimism first.

## Shader facts that bite

- **Spatial fragment `COLOR` is read-only.** Assigning to it fails compilation; the failed
  program draws opaque black with no useful error surfaced at runtime. Use `ALBEDO` and
  `ALPHA`. Pin this with a source audit in your own suite (ban the assignment pattern in
  all spatial shaders) and verify with a real-GL probe.
- Shader-language stencil operations arrived in later engine minors than the base
  scene-graph stencil state. Check which one you actually have before designing around it.
- A shader that compiles is not a shader that works. Compilation proves syntax; only pixels
  prove behaviour.

## Occlusion: let the compositor do it

"Show a virtual world through an opening in the real room" is a solved first-party problem.
The platform's projected-passthrough path lets you supply geometry that carries passthrough
imagery, and with hole punching enabled the **compositor** removes app-rendered content
behind that geometry. The architecture is: your real walls become passthrough geometry with
the opening cut out; the vista renders as ordinary world geometry *behind* them.

Do **not** hand-roll this with:

- world-plane clip fragments (sign/orientation bugs discard everything, and no test sees it),
- generated mask walls or tunnel shells (they occlude the view and read as a periscope),
- screen-space stencil gating (state may not survive per-instance material duplication).

All three have shipped green and rendered nothing. The one-line version: **the room-side
view is passthrough; the wall you see is the real wall; the hole is in the real wall.**

Mode caveat: reconstruction passthrough (`ALPHA_BLEND`) takes priority over projected
passthrough. Hole punching needs `transparent_bg == false` and a non-`ALPHA_BLEND` blend
mode, flipped once at runtime when the wall geometry exists — and a documented degradation
path when it does not.

## Stereo is not optional

Anything eye-dependent is **per-eye**: select by `VIEW_INDEX` in spatial shaders, or use
per-view transforms from the XR interface. A mid-eye approximation is not an approximation —
it produces visible per-eye edge defects, typically a keystone where a boundary crosses from
near to far. If the effect depends on where the eye is, compute it per eye.

Beware the trap of deriving eye or pose data in `_process` and feeding it to the render
path: at render time those poses are stale, and the symptom is an edge that swims with head
motion. Prefer renderer-provided per-view built-ins over hand-fed uniforms.

## Tile-GPU performance

Quest-class GPUs are tile-based. Each render-target break costs tile-memory flush bandwidth.

- Every active `SubViewport` is a separate full render pass. Avoid the class entirely where
  you can; if you cannot, drive update modes explicitly.
- `UPDATE_WHEN_VISIBLE` cannot work in XR — visibility is unknowable. Use explicit modes
  driven by session state.
- No glow, SSR, or screen-texture reads in XR content. These are frame-time killers here in
  a way they are not on desktop.
- Per-fragment discard can disable early-z reuse inside a fill. Bound the fill's geometry if
  you rely on discard.

## Debug visualisation doctrine

Debug overlays should be small, world-anchored, and off to the side. Never attach them to
the HMD and never place them in the centre of vision — that is how a diagnostic ends up
being mistaken for the feature. Every probe should free itself. Prefer numeric log output
over rendered probes when a number will do.

## Cautionary record

Keep your own list of mechanisms that were built and failed, with the reason. It is the
cheapest defence against re-inventing one six months later, and it turns "we tried that"
into a citation rather than an argument.
