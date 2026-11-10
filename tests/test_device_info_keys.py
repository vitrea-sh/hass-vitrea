"""Guard: every _attr_device_info dict must use only valid DeviceInfo keys.

Home Assistant passes device_info straight into
DeviceRegistry.async_get_or_create(**device_info); an unknown key (e.g.
"icon") raises TypeError at entity-add time and silently kills every
entity of that platform. The platform modules import homeassistant and
cannot be imported here, so this validates the source via AST.
"""

import ast
from pathlib import Path

COMPONENT_DIR = (
    Path(__file__).resolve().parents[1] / "custom_components" / "vitrea"
)

# Keys accepted by homeassistant.helpers.device_registry DeviceInfo.
VALID_DEVICE_INFO_KEYS = {
    "configuration_url",
    "connections",
    "default_manufacturer",
    "default_model",
    "default_name",
    "entry_type",
    "hw_version",
    "identifiers",
    "manufacturer",
    "model",
    "model_id",
    "name",
    "serial_number",
    "suggested_area",
    "sw_version",
    "translation_key",
    "translation_placeholders",
    "via_device",
}


def iter_device_info_dicts():
    for path in sorted(COMPONENT_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr == "_attr_device_info"
                    and isinstance(node.value, ast.Dict)
                ):
                    yield path.name, node.lineno, node.value


def test_device_info_dicts_use_only_valid_keys():
    found_any = False
    problems = []
    for filename, lineno, dict_node in iter_device_info_dicts():
        found_any = True
        for key in dict_node.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if key.value not in VALID_DEVICE_INFO_KEYS:
                    problems.append(f"{filename}:{lineno} invalid key {key.value!r}")
    assert found_any, "no _attr_device_info dicts found — did the pattern change?"
    assert not problems, "invalid DeviceInfo keys:\n" + "\n".join(problems)
