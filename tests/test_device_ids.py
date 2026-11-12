"""Scenario and A/C devices: separate identifiers and the migration plan.

Scenario N and A/C N used to share the device identifier "<hub>-N", so
both entities ended up on one device. These tests pin the new identifier
formats and the decision made for every kind of pre-existing device.
"""

from device_ids import (
    REMOVE,
    climate_device_identifier,
    plan_shared_device,
    scene_device_identifier,
)

HUB = "192.168.1.50"


def test_scene_and_climate_identifiers_never_collide():
    assert scene_device_identifier(HUB, 1) != climate_device_identifier(HUB, 1)
    assert scene_device_identifier(HUB, 1) == f"{HUB}-scene-1"
    assert climate_device_identifier(HUB, 1) == f"{HUB}-ac-1"


def test_shared_device_stays_with_the_climate_entity():
    assert plan_shared_device(HUB, f"{HUB}-1", {"climate", "scene"}) == f"{HUB}-ac-1"


def test_climate_only_device_is_renamed():
    assert plan_shared_device(HUB, f"{HUB}-2", {"climate"}) == f"{HUB}-ac-2"


def test_scene_only_device_is_renamed():
    assert plan_shared_device(HUB, f"{HUB}-7", {"scene"}) == f"{HUB}-scene-7"


def test_empty_old_device_is_removed():
    assert plan_shared_device(HUB, f"{HUB}-3", set()) == REMOVE


def test_other_devices_are_left_alone():
    # Key devices ("<hub>-<node>-<key>"), already-migrated devices, the
    # multiway service device and another hub's devices must not match.
    for identifier in (
        f"{HUB}-1-1",
        f"{HUB}-ac-1",
        f"{HUB}-scene-1",
        f"{HUB}-multiway",
        "192.168.1.5-1",
        "192.168.1.500-1",
        "N001-1",
    ):
        assert plan_shared_device(HUB, identifier, {"climate", "scene"}) is None


def test_old_format_device_with_unexpected_entities_is_left_alone():
    assert plan_shared_device(HUB, f"{HUB}-4", {"light"}) is None


def test_migration_is_idempotent():
    target = plan_shared_device(HUB, f"{HUB}-1", {"climate", "scene"})
    assert plan_shared_device(HUB, target, {"climate"}) is None
