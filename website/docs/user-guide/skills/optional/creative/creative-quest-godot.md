---
title: "Quest Godot — Build and debug Quest 3 mixed-reality apps in Godot"
sidebar_label: "Quest Godot"
description: "Build and debug Quest 3 mixed-reality apps in Godot"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Quest Godot

Build and debug Quest 3 mixed-reality apps in Godot.

## Skill metadata

| | |
|---|---|
| Source | Optional — install with `hermes skills install official/creative/quest-godot` |
| Path | `optional-skills/creative/quest-godot` |
| Version | `0.1.0` |
| Author | Salt (Salt-555), Hermes Agent |
| License | MIT |
| Platforms | linux, macos, windows |
| Tags | `godot`, `quest3`, `xr`, `mixed-reality`, `openxr`, `passthrough`, `gamedev` |
| Related skills | [`unreal-mcp`](../../optional/creative/creative-unreal-mcp.md) |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Hermes loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# Quest-Godot Skill

Engineering discipline and platform facts for building mixed-reality apps on Meta Quest
headsets with Godot and the `godot_openxr_vendors` plugin. It covers what the engine and
silicon actually do — stereo, the compositor, tile-GPU rendering, vendor extension flags —
and the process that keeps you from shipping a build that only looks correct. It does not
cover general Godot usage, app sideloading mechanics, or non-Quest headsets.

The one load-bearing claim this skill makes: **a green test suite cannot tell you whether
anything rendered.** Every rule below exists because that gap cost real days.

## When to Use

- Building or debugging a Quest MR/AR app in Godot: passthrough, wall/room anchoring,
  portal or window-into-a-virtual-world effects, XR UI, spatial persistence.
- Deciding whether to hand-roll a rendering mechanism (clip planes, masks, stencil gating)
  or use something the platform already gives you.
- Before any device round: establishing which build is on the headset and what that build
  is supposed to prove.
- Auditing a Godot project for the silent-failure classes (missing vendor feature flags,
  shader compile errors, unawaited async suites).

**Don't use for:** installing or sideloading APKs onto a headset; Godot 2D or flat-screen
work; engine-agnostic XR design discussions with no Godot or Quest constraint in play.

## Prerequisites

- **Godot and the vendors plugin are pinned, and the pairing is a minimum, not a match.**
  One plugin release supports a range of engine minors ("for Godot 4.3 and later"), so
  equal minors are neither required nor sufficient. Pin both explicitly and check the
  plugin's declared *minimum* engine minor against yours. A floating version is the
  number one setup failure. See `references/version-matrix.md` for the format and for
  what each engine minor adds.
- Android SDK + `adb` on PATH, headset in developer mode, USB debugging authorized.
- A headset you can wear. Quest MR correctness lives in the compositor and in stereo, and
  neither is reachable from a test runner.
- Read `references/rendering-and-probes.md` before touching anything visual.

## How to Run

Start every Quest-Godot task with the preflight — it catches the silent-failure classes
before they cost a build (requires Python 3.10+):

```bash
python <skill_dir>/scripts/quest_preflight.py /path/to/godot/project
```

Through the `terminal` tool: `terminal(command="python <skill_dir>/scripts/quest_preflight.py .", timeout=60)`.

It exits non-zero on a hard failure (inert XR setting keys, a shader writing to `COLOR`,
an explicitly disabled OpenXR) and prints warnings for the soft ones. Treat its output as
the first line of any device-round status report.

Then follow the Procedure below. Use `read_file` and `search_files` to inspect project
settings and vendored plugin source — the vendored source is the authority, not docs, not
code comments.

## Quick Reference

| Question | Answer |
|---|---|
| Is it proven? | Only if a **worn gate** or a **real-GL probe** saw it |
| Can headless tests see shaders? | No. Never. Not one. |
| Spatial fragment `COLOR` | Read-only. Writing it fails compilation → opaque black |
| Why is my vendor feature dead? | A hidden project flag is unset. It fails *silently* |
| Should I hand-roll the crop? | No — see the Free Lunch Check |
| Eye-dependent effect | Per-eye (`VIEW_INDEX` / per-view transforms). Never mid-eye |
| Portrait/hand pointer off by ~90° | `XRController3D.pose` defaults to grip, not aim |
| Anchors empty at session focus | Normal. Components mature asynchronously — poll |
| Room Setup keeps popping | `request_scene_capture()` prompts every call |
| Passthrough renders black | Passthrough triplet: `transparent_bg`, bg alpha 0, `ALPHA_BLEND` |

## Procedure

Ordered, each step with a completion criterion. Do not start the next step early.

1. **LAW INTAKE.** Every requirement the user states goes into the brief verbatim, plus one
   line of "what this forbids." A later message that contradicts the brief wins
   immediately — stop and re-steer rather than finishing the superseded task.
   *Done when:* the brief carries the user's own words, not a paraphrase.

2. **FREE LUNCH CHECK.** For any new visual or interaction feature, ask in order: does the
   **headset** already do it (head is a camera, passthrough is the background, stereo is
   per-eye, ATW reprojection)? Does the **engine** (stencil, occluders, environment,
   `frame_pre_draw`)? Does the **vendor SDK** (scene mesh, anchors, environment depth,
   composition layers)? Does a **proven example** (vendor samples, an established XR
   toolkit, a community pattern with a working build)? Cite the source for each answer.
   *Done when:* all four are answered with a citation and the build is justified.

3. **CITE THE MECHANISM.** Write down where the approach comes from: a vendor sample, real
   code you read, or a measurement you took. "I believe" is not a citation. The vendored
   plugin's own manual and samples are read **before** community patterns or invention.
   *Done when:* the brief names the mechanism and its source.

4. **MECHANISM GATE (hard, before any feature code).** The chosen mechanism needs (a) a
   first-party or proven-example citation **and** (b) a smoke test of the mechanism *in
   your configuration* — same materials, same duplication, same wiring, roughly twenty
   lines. A mechanism proven only headless is **unproven**.
   *Done when:* a tiny probe has run and produced a visible result you actually saw.

5. **IMPLEMENT.** Brief the executor with the high-level goal, per-step best practices from
   steps 2–3, the verbatim law block from step 1, the citation, and the probe result.
   *Done when:* the feature is built against the probed mechanism, not a new one.

6. **REVIEW.** A spec pass and a quality pass. Review exists to catch what execution
   shipped, so expect it to be corrective — budget for findings, and pin the invariants it
   names (orthonormality, reachability, layer membership) rather than the check count.
   *Done when:* findings are fixed and the invariants they exposed are pinned by test.

7. **VERIFY — and say which kind of proof you have.** See `## Verification`.
   *Done when:* every claim is labelled `worn-verified`, `probe-verified`, or `unproven`.

**Loop discipline.** Two consecutive device-failed rounds on the same mechanism means stop
implementing: re-run step 4 and the first-party search. A third attempt is how teams lose
an afternoon to a mechanism that was documented in a manual they never opened.

## Pitfalls

- **Headless Godot never compiles shaders and never rasterizes.** The dummy renderer
  returns "all tests passed" for builds that draw nothing. Green certifies invariants,
  never appearance. If a claim is visual, a test cannot settle it.
- **Godot spatial fragment `COLOR` is read-only.** Assigning it fails compilation and the
  failed program renders opaque black on device, with no useful error. Use `ALBEDO`/`ALPHA`.
  Pin with a source audit; see `references/rendering-and-probes.md`.
- **Vendor extension wrappers fail silently when a project flag is unset.** Passthrough,
  scene, anchor, and spatial-entity features each need their flag enabled. A missing flag
  disables the wrapper with no error — you get a plausible-looking no-op.
- **Reconstruction passthrough outranks projected passthrough.** `ALPHA_BLEND` takes
  priority, so projected mode with hole punch needs `transparent_bg == false` and a
  non-`ALPHA_BLEND` blend mode, flipped once at runtime when the geometry exists.
- **Do not hand-roll occlusion the compositor already does.** App-side clip planes, mask
  strips, and stencil gating for "window into a virtual world" are a solved first-party
  problem. Three separate hand-rolled mechanisms have shipped green and rendered nothing
  before anyone read the vendor manual.
- **Anything eye-dependent is per-eye.** Mid-eye approximations are not approximations —
  they are visible per-eye edge defects. Use `VIEW_INDEX` in spatial shaders and per-view
  transforms.
- **`XRController3D.pose` is the grip pose, not the aim pose.** With controllers it is
  roughly right; with optical hand tracking it points perpendicular to the finger. Set
  `pose = &"aim"` and bind a hand interaction profile, or the runtime falls back to
  simple-controller emulation with undocumented conventions.
- **Anchor components mature asynchronously after session focus.** Labels and poses arrive
  late; a single query at focus returns empty after a headset reboot. Poll until mature
  before building anything from the data.
- **`request_scene_capture()` pops intrusive system UI every call.** At most once per run,
  only when the anchor set is empty. Never auto-prompt.
- **Persistence keys on stable UUIDs, not session handles.** `XrSpace` handles die with the
  session; anchor UUIDs survive. Flush saves synchronously on pause and stop — Android kills
  backgrounded processes, so a deferred save loses data.
- **Never poll XR state while unfocused.** It is a crash class. Gate every action sync and
  poll behind a session-focus flag.
- **Per-frame `SubViewport` redraw is a real tile-GPU cost**, and `UPDATE_WHEN_VISIBLE`
  cannot work in XR because visibility is unknowable. Drive update modes explicitly. No
  glow, SSR, or screen-texture reads in XR content.
- **Adreno pixel readback is a dead end.** Use in-world visual markers plus a worn
  observation, or a windowed real-GL probe on the host.
- **A test count is only real if the runner awaited every suite.** An async suite that is
  never awaited silently never runs, and the summary line still looks healthy.

## Verification

Three tiers. The label is part of the claim.

1. **`probe-verified`** — a real-GL windowed probe on the host confirmed rendered output
   (pixels read back, not just a clean logcat). This settles questions headless tests
   structurally cannot. A clean `logcat` with zero script errors is *not* pixels.
2. **`worn-verified`** — a human wore the headset and confirmed the behaviour. This is the
   only gate that can see the compositor, stereo, or timing. Before every worn gate,
   announce **which build** is on the headset and what it is meant to prove; never let
   someone report on a diagnostic build as though it were the fix.
3. **`unproven`** — everything else. Say so plainly in the status. "Tests pass" belongs
   here, not higher.

Completion criteria for a Quest-Godot task: every visual claim carries one of the three
labels; every mechanism traces to a citation; the preflight is clean; and the invariants
named during review are pinned by tests. If any item is missing, the task is not done.
