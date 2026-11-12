"""Debug attribution for actuation service calls.

Every command HA asks us to send carries a Context identifying its
origin (a user, an automation via parent_id, or an integration such as
HomeKit with neither). Logging it next to the TX makes 'ghost' actuation
reports self-identifying: grep this logger around the incident time.
"""

import logging

_LOGGER = logging.getLogger(__name__)


def log_actuation(entity, action: str) -> None:
    """Log who requested an actuation on this entity."""
    context = getattr(entity, "_context", None)
    _LOGGER.debug(
        "%s requested for %s (context=%s user=%s parent=%s)",
        action,
        getattr(entity, "entity_id", entity.name),
        getattr(context, "id", None),
        getattr(context, "user_id", None),
        getattr(context, "parent_id", None),
    )
