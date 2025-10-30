"""Constants for the Vitrea integration."""

from enum import StrEnum


DOMAIN = "vitrea"


class VitreaFeatures(StrEnum):
    """Vitrea features."""

    TIMER_ON = "timer_on"
    RECALL_LAST_STATE = "recall_last_state"
    SET_KEY_LED = "set_key_led"
