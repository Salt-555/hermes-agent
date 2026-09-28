"""Behavior contracts for the quest-godot preflight helper.

These assert how the checks relate to the artifacts they inspect, not the current text
of any file. Authoring/frontmatter policy is enforced separately by
test_authoring_standards.py.

Setting-key spellings here are the real Godot 4 ProjectSettings paths (verified against
a 4.5.2 binary): XR settings live under `xr/...`, not at the top level.
"""
from pathlib import Path
import runpy

import pytest

SKILL_DIR = Path(__file__).resolve().parents[2] / "optional-skills/creative/quest-godot"
SCRIPT = SKILL_DIR / "scripts/quest_preflight.py"


def _load():
    return runpy.run_path(str(SCRIPT))


def _write(project: Path, settings: str = "", shaders: dict[str, str] | None = None,
           plugin: tuple[str, str] | None = None,
           addon_cfgs: dict[str, str] | None = None) -> Path:
    """Build a minimal Godot project tree and return its root."""
    project.mkdir(parents=True, exist_ok=True)
    (project / "project.godot").write_text(settings, encoding="utf-8")
    for rel, body in (shaders or {}).items():
        target = project / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    if plugin is not None:
        name, version = plugin
        addon = project / "addons" / name
        addon.mkdir(parents=True, exist_ok=True)
        (addon / "plugin.cfg").write_text(
            f'[plugin]\nname="{name}"\nversion="{version}"\n', encoding="utf-8"
        )
    for rel, body in (addon_cfgs or {}).items():
        target = project / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return project


def _codes(report, code):
    return [f for f in report.findings if f.code == code]


BASE = (
    'config/features=PackedStringArray("4.5", "GL Compatibility")\n'
    "xr/openxr/enabled=true\n"
)

SPATIAL_COLOR = "shader_type spatial;\nvoid fragment() {\n\tCOLOR = vec4(1.0);\n}\n"


def test_missing_project_godot_is_a_hard_failure(tmp_path):
    mod = _load()
    report = mod["run_preflight"](tmp_path / "nothing")
    assert _codes(report, "not-a-godot-project")
    assert report.worst == 1


def test_spatial_shader_writing_color_is_a_hard_failure(tmp_path):
    mod = _load()
    root = _write(tmp_path, BASE, shaders={"shaders/bad.gdshader": SPATIAL_COLOR})
    hits = _codes(mod["run_preflight"](root), "shader-color-write")
    assert hits and hits[0].severity == "FAIL"
    assert "bad.gdshader" in hits[0].message


def test_commented_out_color_write_is_not_flagged(tmp_path):
    mod = _load()
    root = _write(tmp_path, BASE, shaders={
        "shaders/ok.gdshader": (
            "shader_type spatial;\nvoid fragment() {\n"
            "\t// COLOR = vec4(1.0);\n"
            "\t/* COLOR = vec4(0.0); */\n"
            "\tALBEDO = vec3(1.0);\n}\n"
        ),
    })
    assert not _codes(mod["run_preflight"](root), "shader-color-write")


def test_member_write_on_an_unrelated_object_is_not_flagged(tmp_path):
    # `something.COLOR =` is a member write on an unrelated object, not the built-in.
    mod = _load()
    root = _write(tmp_path, BASE, shaders={
        "shaders/member.gdshader": (
            "shader_type spatial;\nvoid fragment() {\n"
            "\tmaterial.COLOR = vec4(1.0);\n}\n"
        ),
    })
    assert not _codes(mod["run_preflight"](root), "shader-color-write")


def test_canvas_item_color_write_is_legal_and_not_flagged(tmp_path):
    # COLOR is a writable output outside spatial shaders.
    mod = _load()
    root = _write(tmp_path, BASE, shaders={
        "shaders/ui.gdshader":
            "shader_type canvas_item;\nvoid fragment() {\n\tCOLOR = vec4(1.0);\n}\n",
    })
    assert not _codes(mod["run_preflight"](root), "shader-color-write")


def test_local_variable_named_color_is_not_flagged(tmp_path):
    mod = _load()
    root = _write(tmp_path, BASE, shaders={
        "shaders/local.gdshader": (
            "shader_type spatial;\nvoid fragment() {\n"
            "\tfloat COLOR = 1.0;\n\tALBEDO = vec3(COLOR);\n}\n"
        ),
    })
    assert not _codes(mod["run_preflight"](root), "shader-color-write")


@pytest.mark.parametrize("body", [
    "\tCOLOR.rgb = vec3(1.0);",
    "\tCOLOR.x = 0.5;",
    "\tCOLOR += vec4(0.1);",
])
def test_swizzled_and_compound_color_writes_are_flagged(tmp_path, body):
    mod = _load()
    root = _write(tmp_path, BASE, shaders={
        "shaders/subtle.gdshader":
            f"shader_type spatial;\nvoid fragment() {{\n{body}\n}}\n",
    })
    assert _codes(mod["run_preflight"](root), "shader-color-write")


def test_shader_include_files_are_audited(tmp_path):
    mod = _load()
    root = _write(tmp_path, BASE, shaders={
        "shaders/chunk.gdshaderinc": "void broken() {\n\tCOLOR = vec4(1.0);\n}\n",
    })
    assert _codes(mod["run_preflight"](root), "shader-color-write")


def test_shader_embedded_in_scene_file_is_audited(tmp_path):
    mod = _load()
    scene = (
        '[gd_scene format=3]\n\n'
        '[sub_resource type="Shader" id="1"]\n'
        'code = "shader_type spatial;\\nvoid fragment() {\\n\\tCOLOR = vec4(1.0);\\n}\\n"\n'
    )
    root = _write(tmp_path, BASE, shaders={"scenes/portal.tscn": scene})
    assert _codes(mod["run_preflight"](root), "shader-color-write")


def test_real_xr_setting_keys_pass(tmp_path):
    mod = _load()
    report = mod["run_preflight"](_write(tmp_path, BASE))
    assert not _codes(report, "stale-xr-setting")
    assert not _codes(report, "openxr-disabled")


def test_unprefixed_xr_key_is_flagged_as_inert(tmp_path):
    # Regression: a project.godot spelling `openxr/enabled` (missing the `xr/` prefix)
    # is never read by Godot. The setting looks configured but is inert.
    mod = _load()
    root = _write(
        tmp_path,
        'config/features=PackedStringArray("4.5")\nopenxr/enabled=true\n',
    )
    hits = _codes(mod["run_preflight"](root), "stale-xr-setting")
    assert hits and hits[0].severity == "FAIL"
    assert "xr/openxr/enabled" in hits[0].message


def test_openxr_explicitly_disabled_is_a_hard_failure(tmp_path):
    mod = _load()
    root = _write(
        tmp_path,
        'config/features=PackedStringArray("4.5")\nxr/openxr/enabled=false\n',
    )
    report = mod["run_preflight"](root)
    assert _codes(report, "openxr-disabled")
    assert report.worst == 1


def test_unrelated_addon_mentioning_vendor_in_prose_does_not_feed_pairing(tmp_path):
    mod = _load()
    root = _write(
        tmp_path,
        BASE,
        addon_cfgs={
            "addons/some_lib/plugin.cfg":
                '[plugin]\nname="some_lib"\n'
                'description="third-party vendor library"\nversion="9.9"\n',
        },
    )
    report = mod["run_preflight"](root)
    assert not [f for f in report.findings if "some_lib" in f.message]


def test_gdextension_vendor_addon_is_detected_without_plugin_cfg(tmp_path):
    # The Quest vendor addon commonly ships as a GDExtension with no plugin.cfg.
    # Detection keyed on plugin.cfg alone would silently skip the flag checks.
    mod = _load()
    root = _write(tmp_path, BASE, addon_cfgs={
        "addons/godotopenxrvendors/plugin.gdextension":
            '[configuration]\nentry_symbol = "library_init"\n',
    })
    report = mod["run_preflight"](root)
    assert _codes(report, "silent-flag-class")
    assert not _codes(report, "vendors-plugin-absent")


def test_vendors_addon_without_feature_flags_warns_about_silent_no_op(tmp_path):
    mod = _load()
    root = _write(tmp_path, BASE, plugin=("godot_openxr_vendors", "4.5.1"))
    report = mod["run_preflight"](root)
    assert _codes(report, "silent-flag-class")
    assert report.worst == 2


def test_feature_flags_are_checked_per_class(tmp_path):
    # One stray key must not mask another feature class still being absent.
    mod = _load()
    root = _write(
        tmp_path,
        BASE + "xr_features/enable_passthrough=true\n",
        plugin=("godot_openxr_vendors", "4.5.1"),
    )
    messages = " ".join(
        f.message for f in _codes(mod["run_preflight"](root), "silent-flag-class")
    )
    assert "scene" in messages and "anchor" in messages
    assert "passthrough" not in messages


def test_engine_plugin_pairing_is_reported_not_hard_failed(tmp_path):
    # One plugin release spans several engine minors, so a mismatch is not proof of
    # breakage. The relationship is surfaced for a human, never enforced as equality.
    mod = _load()
    root = _write(
        tmp_path,
        'config/features=PackedStringArray("4.7")\nxr/openxr/enabled=true\n',
        plugin=("godot_openxr_vendors", "4.5.1"),
    )
    report = mod["run_preflight"](root)
    assert _codes(report, "plugin-pairing")
    assert not [f for f in report.findings if f.severity == "FAIL"]


def test_clean_project_reports_no_failures_and_no_warnings(tmp_path):
    mod = _load()
    root = _write(
        tmp_path,
        BASE
        + "xr/openxr/default_action_map=ActionMap.tres\n"
        + "xr_features/enable_passthrough=true\n"
        + "xr_features/scene_api=true\n"
        + "xr_features/anchor_api=true\n"
        + "xr_features/spatial_entity=true\n",
        shaders={"shaders/good.gdshader":
                 "shader_type spatial;\nvoid fragment() {\n\tALBEDO = vec3(1.0);\n}\n"},
        plugin=("godot_openxr_vendors", "4.5.1"),
    )
    report = mod["run_preflight"](root)
    assert not [f for f in report.findings if f.severity in ("FAIL", "WARN")]
    assert report.worst == 0


def test_report_worst_severity_orders_fail_over_warn_over_info(tmp_path):
    mod = _load()
    report = mod["Report"]()
    assert report.worst == 0
    report.add("INFO", "x", "info only")
    assert report.worst == 0
    report.add("WARN", "y", "warn")
    assert report.worst == 2
    report.add("FAIL", "z", "hard")
    assert report.worst == 1
