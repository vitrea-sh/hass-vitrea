"""Device identifiers for scenarios and A/Cs.

Both used to be "<hub_id>-<number>", so scenario 1 and A/C 1 landed on the
same Home Assistant device. Each kind now has its own namespace. Entity
unique ids are unchanged (they never collided: they are scoped per entity
domain), so only devices need migrating.

Kept free of Home Assistant imports so the decision logic is unit-testable.
"""

import re

REMOVE = "remove"


def scene_device_identifier(hub_id: str, scene_id: int) -> str:
    """Device identifier of a scenario."""
    return f"{hub_id}-scene-{scene_id}"


def climate_device_identifier(hub_id: str, ac_id: int) -> str:
    """Device identifier of an A/C or thermostat."""
    return f"{hub_id}-ac-{ac_id}"


def plan_shared_device(
    hub_id: str, identifier: str, entity_domains: set[str]
) -> str | None:
    """Decide what happens to a device that uses the old shared format.

    Returns the identifier the device should be renamed to, REMOVE for an
    old-format device that no entity uses any more, or None when the
    identifier is not in the old shared format.

    A device holding both a climate and a scene entity stays with the
    climate entity; the scene gets a device of its own when it is set up.
    """
    match = re.fullmatch(re.escape(hub_id) + r"-(\d+)", identifier)
    if not match:
        return None
    number = int(match.group(1))
    if "climate" in entity_domains:
        return climate_device_identifier(hub_id, number)
    if "scene" in entity_domains:
        return scene_device_identifier(hub_id, number)
    if not entity_domains:
        return REMOVE
    return None
