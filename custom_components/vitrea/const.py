"""Constants for the Vitrea integration."""

DOMAIN = "vitrea"

# Multiway link subentries
SUBENTRY_TYPE_SATELLITE_LINK = "satellite_link"
SUBENTRY_TYPE_SATELLITE_LIGHT_LINK = "satellite_light_link"
SUBENTRY_TYPE_CLIMATE_LINK = "climate_link"
SUBENTRY_TYPE_BLIND_LINK = "blind_link"
SUBENTRY_TYPE_TOGGLE_LINK = "toggle_link"
MULTIWAY_SUBENTRY_TYPES = (
    SUBENTRY_TYPE_SATELLITE_LINK,
    SUBENTRY_TYPE_SATELLITE_LIGHT_LINK,
    SUBENTRY_TYPE_CLIMATE_LINK,
    SUBENTRY_TYPE_BLIND_LINK,
    SUBENTRY_TYPE_TOGGLE_LINK,
)
CONF_SATELLITE_ID = "satellite_id"
CONF_TOGGLE_ID = "toggle_id"
CONF_KEY_ID = "key_id"  # climate links: satellite OR toggle source
CONF_UP_KEY_ID = "up_key_id"  # blind links: the pair of satellites
CONF_DOWN_KEY_ID = "down_key_id"
CONF_TILT_STEP = "tilt_step"
CONF_TRAVEL_TIME = "travel_time"  # assumed-motion window for one-way covers
CONF_TARGET_ENTITY = "target_entity"
CONF_TARGET_ENTITY_ID = "target_entity_id"
CONF_LONG_PRESS_SCENE = "long_press_scene"
CONF_MIN_BRIGHTNESS = "min_brightness"
CONF_MAX_BRIGHTNESS = "max_brightness"
CONF_STEP_PCT = "step_pct"
CONF_STEP_DELAY = "step_delay"
