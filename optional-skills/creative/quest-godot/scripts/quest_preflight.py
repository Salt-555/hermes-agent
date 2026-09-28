#!/usr/bin/env python3
"""Quest/Godot preflight: catch the silent-failure classes before a device round.

Checks a Godot project for the failure modes that produce a plausible-looking build
which renders nothing, or which silently loses a feature:

  1. Spatial shaders writing to COLOR (read-only in the spatial shader language; the
     assignment fails to compile and the program draws opaque black).
  2. Stale XR project-setting keys. Godot 4 stores these under `xr/...`; a key written
     without that prefix is INERT — nothing reads it and nothing errors.
  3. Vendor extension feature flags absent while the vendors addon is installed (the
     wrappers disable themselves with no error).
  4. Engine / vendor-plugin compatibility not established.

Stdlib only, cross-platform. Exit 0 = clean, 1 = hard failure, 2 = warnings only.

Shader scope: `*.gdshader`, `*.gdshaderinc`, and Shader `sub_resource` code blocks
embedded in `*.tscn` / `*.tres`. Only `shader_type spatial` is audited: `COLOR` is a
legal writable output in canvas_item, particles, and sky shaders.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HARD, WARN, INFO = "FAIL", "WARN", "INFO"

# A write to the built-in COLOR: plain, swizzled, or compound. The lookbehind excludes
# `something.COLOR =`, which is a member write on an unrelated object.
_COLOR_WRITE = re.compile(
    r"(?<!\.)\bCOLOR\b\s*(?:\.\s*(?:[rgba]{1,4}|[xyzw]{1,4})\s*)?(?:\+=|-=|\*=|/=|=)"
)

# A declaration introduces a name; it does not write the built-in.
_DECL_TYPE = re.compile(
    r"\b(?:float|half|double|int|uint|bool|vec[234]|ivec[234]|uvec[234]|bvec[234]"
    r"|mat[234]|mat[234]x[234]|sampler2D|samplerCube|sampler3D)\s+$"
)

_SHADER_TYPE = re.compile(r"\bshader_type\s+([A-Za-z_]+)\s*;")
_SUB_RESOURCE_SHADER = re.compile(r'sub_resource\s+type="Shader"')
_CODE_BLOCK = re.compile(r'\bcode\s*=\s*"((?:[^"\\]|\\.)*)"')
_SETTING = re.compile(r"^([A-Za-z0-9_/\.\-]+)\s*=\s*(.*)$")

# Feature families whose absence silently disables a vendor wrapper. Checked one by one
# so a stray key cannot mask another feature's absence.
_FEATURE_CLASSES = {
    "passthrough": re.compile(r"passthrough", re.I),
    "scene": re.compile(r"scene", re.I),
    "anchor": re.compile(r"anchor", re.I),
    "spatial_entity": re.compile(r"spatial_entity|spatial.?entity", re.I),
}

# Canonical Godot 4 XR keys (verified against ProjectSettings on a 4.5.2 binary) and
# the unprefixed spellings people write by mistake.
_XR_KEYS = {
    "enabled": "xr/openxr/enabled",
    "action_map": "xr/openxr/default_action_map",
    "blend_mode": "xr/openxr/environment_blend_mode",
}
_LEGACY_XR_KEYS = {
    "enabled": "openxr/enabled",
    "action_map": "openxr/action_map",
    "blend_mode": "openxr/environment_blend_mode",
}


@dataclass
class Finding:
    severity: str
    code: str
    message: str


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, severity: str, code: str, message: str) -> None:
        self.findings.append(Finding(severity, code, message))

    @property
    def worst(self) -> int:
        sev = {f.severity for f in self.findings}
        if HARD in sev:
            return 1
        if WARN in sev:
            return 2
        return 0


def _strip_shader_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _read_settings(project_file: Path) -> dict[str, str]:
    settings: dict[str, str] = {}
    if not project_file.is_file():
        return settings
    for line in project_file.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _SETTING.match(line.strip())
        if m:
            settings[m.group(1)] = m.group(2).strip()
    return settings


def _minor_of(value: str) -> str | None:
    # The version may sit inside a container value (e.g. a PackedStringArray).
    m = re.search(r"(\d+)\.(\d+)", value)
    return f"{m.group(1)}.{m.group(2)}" if m else None


_INCLUDE = re.compile(r'^\s*#include\s+"([^"]+)"', re.M)


def _shader_sources(root: Path) -> list[tuple[str, str, str | None]]:
    """Return (label, source, shader_type) for every shader reachable in the project.

    Include chunks (`*.gdshaderinc`) declare no shader_type of their own; the type is
    inherited from the shaders that include them. A chunk reached only by non-spatial
    shaders is not audited; one with no known includer is audited conservatively.
    """
    typed: list[tuple[str, str, str | None]] = []
    chunks: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*.gdshader")):
        typed.append((str(path.relative_to(root)),
                      path.read_text(encoding="utf-8", errors="replace"), None))
    for path in sorted(root.rglob("*.gdshaderinc")):
        chunks.append((str(path.relative_to(root)),
                       path.read_text(encoding="utf-8", errors="replace")))
    for pattern in ("*.tscn", "*.tres"):
        for path in sorted(root.rglob(pattern)):
            text = path.read_text(encoding="utf-8", errors="replace")
            if not _SUB_RESOURCE_SHADER.search(text):
                continue
            for i, m in enumerate(_CODE_BLOCK.finditer(text), 1):
                code = (m.group(1).replace("\\n", "\n").replace("\\t", "\t")
                        .replace('\\"', '"'))
                typed.append((f"{path.relative_to(root)}#shader{i}", code, None))

    resolved: list[tuple[str, str, str | None]] = []
    type_by_label: dict[str, str | None] = {}
    for label, source, forced in typed:
        body = _strip_shader_comments(source)
        m = _SHADER_TYPE.search(body)
        declared = forced or (m.group(1) if m else None)
        type_by_label[label] = declared
        resolved.append((label, source, declared))

    users_of: dict[str, set[str | None]] = {}
    for label, source, _ in typed:
        for inc in _INCLUDE.findall(_strip_shader_comments(source)):
            users_of.setdefault(inc.split("/")[-1], set()).add(type_by_label.get(label))

    for label, source in chunks:
        known = users_of.get(label.split("/")[-1], set())
        if not known or "spatial" in known:
            inherited = "spatial"       # unknown reachability: audit conservatively
        else:
            inherited = "non-spatial"
        resolved.append((label, source, inherited))
    return resolved


def audit_shaders(root: Path, report: Report) -> None:
    for label, source, shader_type in _shader_sources(root):
        if shader_type != "spatial":
            continue
        body = _strip_shader_comments(source)
        for i, line in enumerate(body.splitlines(), 1):
            m = _COLOR_WRITE.search(line)
            if not m:
                continue
            if _DECL_TYPE.search(line[: m.start()]):
                continue
            report.add(
                HARD,
                "shader-color-write",
                f"{label}:{i} writes to COLOR in a spatial shader "
                f"(read-only; compiles to an opaque-black program on device)",
            )


def audit_xr_settings(settings: dict[str, str], report: Report) -> None:
    for key, canonical in _XR_KEYS.items():
        legacy = _LEGACY_XR_KEYS[key]
        if canonical in settings or legacy not in settings:
            continue
        report.add(
            HARD,
            "stale-xr-setting",
            f"{legacy} is inert — Godot 4 reads {canonical}; this key is never consulted "
            f"and its value is silently ignored",
        )

    enabled = settings.get(_XR_KEYS["enabled"],
                           settings.get(_LEGACY_XR_KEYS["enabled"], ""))
    if not enabled:
        report.add(INFO, "openxr-not-declared",
                   "no xr/openxr/enabled key found in project.godot")
    elif enabled.lower() not in ("true", "1"):
        report.add(HARD, "openxr-disabled", f"{_XR_KEYS['enabled']} is not true")


def _vendor_addons(root: Path) -> list[tuple[str, str]]:
    """Identify vendor addons by their addon directory, not by prose in a cfg.

    An XR vendor addon may ship as an editor plugin (`plugin.cfg`) or as a
    GDExtension (`*.gdextension`); only the former carries a conventional version.
    """
    addons_dir = root / "addons"
    if not addons_dir.is_dir():
        return []
    found: list[tuple[str, str]] = []
    for addon in sorted(p for p in addons_dir.iterdir() if p.is_dir()):
        name = addon.name.lower()
        if "openxr" not in name and "vendor" not in name:
            continue
        version = ""
        cfg = addon / "plugin.cfg"
        if cfg.is_file():
            m = re.search(r'^\s*version\s*=\s*["\']?([^"\'\n]+)',
                          cfg.read_text(encoding="utf-8", errors="replace"), re.M)
            if m:
                version = m.group(1).strip()
        found.append((name, version))
    return found


def audit_compatibility(root: Path, settings: dict[str, str], report: Report) -> None:
    plugins = _vendor_addons(root)
    if not plugins:
        report.add(INFO, "vendors-plugin-absent", "no OpenXR vendor addon found")
        return

    # Engine/plugin pairing is a MINIMUM, not an equality: one plugin release supports
    # a range of engine minors. Without a declared minimum we must not fail hard on an
    # invented relationship.
    engine_minor = _minor_of(settings.get("config/features", ""))
    for addon_dir, version in plugins:
        if not version:
            report.add(INFO, "plugin-pairing-unverified",
                       f"addons/{addon_dir}: no version found; confirm its declared "
                       f"MINIMUM engine minor in the release notes")
        elif engine_minor is None:
            report.add(INFO, "plugin-pairing-unverified",
                       f"addons/{addon_dir} {version}: no engine minor to compare against")
        else:
            report.add(INFO, "plugin-pairing",
                       f"addons/{addon_dir} {version} on Godot {engine_minor} — confirm the "
                       f"plugin's declared MINIMUM engine minor in its release notes")


def audit_feature_flags(root: Path, settings: dict[str, str], report: Report) -> None:
    if not _vendor_addons(root):
        return
    for label, pattern in _FEATURE_CLASSES.items():
        if any(pattern.search(k) for k in settings):
            continue
        report.add(
            WARN,
            "silent-flag-class",
            f"vendors addon installed but no {label} project setting found — a missing "
            f"flag disables that wrapper with no error",
        )


def run_preflight(project_dir: Path) -> Report:
    report = Report()
    project_file = project_dir / "project.godot"
    if not project_file.is_file():
        report.add(HARD, "not-a-godot-project", f"no project.godot under {project_dir}")
        return report

    settings = _read_settings(project_file)
    audit_shaders(project_dir, report)
    audit_xr_settings(settings, report)
    audit_compatibility(project_dir, settings, report)
    audit_feature_flags(project_dir, settings, report)
    return report


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()[0] if __doc__ else "Quest/Godot preflight"
    parser = argparse.ArgumentParser(description=summary)
    parser.add_argument("project_dir", type=Path,
                        help="Godot project root (holds project.godot)")
    args = parser.parse_args(argv)

    report = run_preflight(args.project_dir)
    for f in report.findings:
        print(f"[{f.severity}] {f.code}: {f.message}")
    if not report.findings:
        print("[INFO] clean: no preflight findings")
    return report.worst


if __name__ == "__main__":
    sys.exit(main())
