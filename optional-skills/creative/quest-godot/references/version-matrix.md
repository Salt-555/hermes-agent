# Version Pinning and the Capability Matrix

Companion to the `quest-godot` skill. Version drift here is the single most common setup
failure, and capability differences between minors are the most common cause of building a
workaround for something the engine now does.

## The minimum-version rule

Engine minor and OpenXR vendor-plugin version are **related by a minimum, not an
equality**. One plugin release spans several engine minors (its release notes say things
like "for Godot 4.3 and later"), so matching minor numbers prove nothing — and a mismatch
is not proof of breakage. What matters is that your engine meets the plugin's declared
*minimum*.

Pin both explicitly, in the repo, with the source URL:

| Component | Pin | Source |
|---|---|---|
| Godot | `X.Y.Z.stable` | release URL |
| godot_openxr_vendors | `X.Y.Z-stable` | release URL |

Write the pin where the agent will read it before doing device work, and never let one
float "just for this build". The preflight script in this skill surfaces the pairing for
you to confirm against the plugin's release notes; it deliberately does not fail hard on
the relationship, because the honest answer is a range and the range lives in the plugin's
documentation.

## Check what the next minor adds before building a workaround

The expensive mistake is hand-rolling a mechanism the engine gained support for one minor
later. Before committing to a workaround, read the changelog for minors above your pin and
answer: *does a newer version already do this?*

Observed capability steps in this area (re-verify against current changelogs — engine
capability moves):

- **3.x → 4.3:** the built-in Rooms & Portals PVS system was removed. Do not design around
  it.
- **Later minors** added shader-language stencil operations, composition-layer depth
  testing, and vendor wrappers for environment depth on the main projection layer.

Each of those deletes a whole class of hand-rolled workaround. A short upgrade spike — new
editor plus export templates, the test suite, and one device round, with explicit kill
criteria — is typically about half a day and can remove far more code than it costs.

## When to upgrade

Upgrade deliberately, never as a side effect:

1. Name the workaround class the upgrade deletes. If you cannot name it, do not upgrade yet.
2. Do the upgrade in a worktree with the suite green before and after.
3. Risk-review each commit being carried forward.
4. Leave the mainline untouched until a worn gate passes on the new version.
5. Keep rollback by construction — the upgrade branch is not merged until the gate lands.

A "zero-regression migration" is one where the suite count matches the pre-migration
baseline exactly *and* the behaviours you actually cared about are re-confirmed, not one
where the suite is merely green.

## Reading the version you actually have

Do not trust the docs, and do not trust comments in your own code — both drift. Read:

- the vendored plugin's `plugin.cfg` and changelog for the version actually on disk;
- the engine's own source or class reference for the minor you are pinned to;
- the plugin's **sample projects**, which are the authoritative demonstration of how a
  feature is meant to be wired.

If the sample wires a feature under a particular node or with particular mode settings,
mirror it exactly before concluding the feature is broken. A mechanism that fails in your
app but works in the sample has a plumbing difference, not a capability problem.

## Recording what you learn

Keep two lists in your repo, and keep them honest:

- **Mechanism status:** for each mechanism, whether it is `worn-verified`, `probe-verified`,
  or `unproven`, and since when. Label design history explicitly as history — an abandoned
  mechanism still sitting in a doc reads as shipped truth to the next reader.
- **Cautionary record:** mechanisms built and failed, with the reason. This is what stops
  the same idea being re-invented later.

Mark the boundary between them loudly. The most dangerous document is one where a design
note and a shipped fact look identical.
