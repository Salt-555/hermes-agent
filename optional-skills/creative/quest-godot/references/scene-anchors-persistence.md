# Scene Data, Anchors, and Persistence

Companion to the `quest-godot` skill: how room and anchor data actually arrives, and how to
keep placements across sessions.

## Establish access before designing around it

Spike the gating question with a real device measurement first. Third-party access to scene
and depth data is gated in ways that forum lore gets wrong, and an assumed *yes* costs a
week of rework when the answer is *no*. Measure it on a sideloaded build before committing
a design.

Use the vendored engine plugin rather than hand-written bindings — the established OpenXR
vendor plugin already wraps passthrough, scene management, and spatial anchor management.
Hand-writing those bindings is almost never the right call.

## The silent-flag class

Vendor extension features are gated behind project settings. **A missing flag disables the
wrapper with no error** — you get a plausible-looking no-op instead of a failure. This has
cost more debugging time than any real bug in this space.

Before debugging "why does my scene query return nothing", check that every extension you
depend on is actually enabled in project settings. Run the preflight script from the skill;
it warns when the vendors addon is installed but the expected flag class is absent.

## Components mature asynchronously

Anchor components — poses, semantic labels, bounds — populate **after** session focus, not
at it. A single query issued at focus returns empty data, particularly after a headset
reboot. Poll on an interval until the anchor set is mature before building anything from
it. Anything derived from an immature set looks like a geometry bug and is not one.

Maturity is also a stability question: wait for a stable poll count before treating the
room as final, and degrade visibly (log it) rather than silently when it never stabilises.

## Room capture has a user-visible cost

Requesting a scene capture pops the system's room-setup UI. It fires on **every** call. At
most once per run, and only when the anchor set is actually empty. Never auto-prompt the
user as a side effect of a retry loop — a retry that re-prompts becomes a nag loop the user
has to kill.

## Semantic labels

Labels arrive lowercase and machine-ish (`wall_face`, `couch`, `table`, `screen`). Do not
assume a casing convention you have not read from the data. Note also that room *structure*
(walls, floor, ceiling, window and door frames) and *furniture semantics* can have different
access gating — structure is often available to a plain sideloaded install while richer
labels may need a registered app identity. Verify which one you actually need before
registering anything.

## Persistence

- **Key placements on stable UUIDs, never session handles.** An XR space handle dies with
  the session; an anchor UUID survives. Detect room changes by UUID mismatch rather than by
  fingerprinting the guardian origin.
- **Persist relative to a floor-relative reference**, not a raw local one, so a recentre does
  not scatter every placement.
- **Flush saves synchronously** on both session stop and application pause. Android kills
  backgrounded processes; a deferred save loses data.
- Treat JSON-relative poses as *approximate* persistence. True spatial-anchor persistence is
  a separate, narrower capability — check whether your plugin exposes it before promising
  it, and otherwise ship approximate persistence with a re-anchor prompt.
- Anchor resolution failure is a user-visible state. Design it (untracked, re-snap,
  ephemeral) rather than improvising it.

## Degradation ladder

When room data is unavailable, fall back in a defined order — OS scene planes, then
controller-traced planes, then free space — and **log which rung you are on**. A silent
fallback is indistinguishable from a bug. Note the accuracy difference: a hand-traced plane
is centimetre-scale, which is fine for monitors and visibly wrong for anything that touches
a wall at close range.

## Session focus is a gate

Never poll XR state while the session is unfocused — it is a crash class. Gate every action
sync and state poll behind a session-focus flag. Likewise, set physics tick rate from the
HMD refresh rate when the session begins rather than assuming a desktop default.

## Read the vendored source, not the docs or the comments

Engine capability questions are settled by the vendored plugin's source and sample projects.
Comments in your own codebase have been wrong about this ("no stencil on GLES3" was wrong),
and documentation trails the source. When a mechanism matters, the sample project is the
citation — read it in full before designing.
