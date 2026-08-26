"""Repository-level contract checks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "reolink_sip_gateway"


def _key_tree(value):
    if isinstance(value, dict):
        return {key: _key_tree(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_key_tree(child) for child in value]
    return type(value).__name__


def test_manifest_and_hacs_metadata():
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert manifest["domain"] == "reolink_sip_gateway"
    assert manifest["version"] == "1.2.0"
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "local_push"
    assert hacs["name"] == manifest["name"]
    assert (INTEGRATION / "brand" / "icon.png").is_file()


def test_translation_files_have_identical_keys():
    english = json.loads((INTEGRATION / "translations" / "en.json").read_text())
    german = json.loads((INTEGRATION / "translations" / "de.json").read_text())
    assert _key_tree(english) == _key_tree(german)
    assert set(english["entity"]["sensor"]["status"]["state"]) == {
        "bereit",
        "eingehend",
        "ausgehend",
        "verbunden",
        "fehler",
    }


def test_custom_integration_uses_runtime_translation_files():
    assert not (INTEGRATION / "strings.json").exists()
    assert (INTEGRATION / "translations" / "en.json").is_file()
    assert (INTEGRATION / "translations" / "de.json").is_file()
