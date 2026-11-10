# Vitrea Home Assistant Integration

> Note: This integration is experimental. APIs and behavior may change without notice. Use at your own risk

Vitrea integration for Home Assistant. Provides local control of Vitrea devices via the Vitrea controller.

- Entities: lights, covers/blinds, thermostats, scenarios, switches, binary sensors, sensors, numbers, satellite button events
- IO class: local_push
- Supports UI config flow

## Requirements
- Home Assistant 2025.3 or newer
- Network access from Home Assistant to the Vitrea controller (TCP port 11502 by default)
- Controller firmware: vBox Pro 7.99 or newer, VMax 8.63 or newer (9.x and 10.x are supported). LED indicators and Room-On keys need 9.5 or newer. Contact Vitrea support if your controller needs a firmware upgrade.

### One control system at a time
The controller accepts **a single control-system connection**, first come, first served. If another system is already connected to it — Control4, a HomeKit or Matter bridge, another Home Assistant instance — this integration gets a connection error until that system is disconnected from the controller.

## Multiway links
Bind physical Vitrea keys to any Home Assistant entity from the
integration page ("Add" menu on the Vitrea entry):
- **Satellite button link** — short press toggles the target entity,
  optional long-press scene; the button LED follows the target's state
  (controller firmware 9.5+).
- **Satellite dimmer link** — short press toggles a light, holding the
  button dims it up/down (direction alternates per hold; holding from
  off ramps up gently from the configured minimum), and the LED follows
  the light. Brightness range, step size and speed are configurable.
- **Climate link** — a satellite button or toggle key bound to a climate
  device: on (or a short press) recalls the device's last active HVAC
  mode, off turns it off. Toggle keys stay in sync with the device;
  button LEDs show whether it is running.
- **Blind link** — a pair of satellite buttons (up/down) bound to a
  cover: hold to move in the key's direction, hold again to stop; the
  moving direction's LED is lit while the cover reports motion. A short
  press tilts by a configurable step on tilt-capable covers, otherwise
  it stops the cover.
- **Toggle key link** — keeps a regular toggle key in sync with a target
  entity. The HA entity is the master and the key is the slave: the key
  always follows the entity, and pressing the key forwards the command
  to the entity. Loop-safe by design: command echoes are suppressed,
  reconciliation never writes to the master, and a safety breaker cuts
  any residual on/off oscillation.

When any link is configured, a **Multiway Links** kill-switch entity
appears (on the "Vitrea Multiway" service device). Turning it off
instantly pauses every link — no key press, LED write, or service call
can leak through while paused — and the state survives restarts.
Turning it back on rebuilds the links without switching anything: a key
that was changed while the links were paused stays as it is until the
next press or entity change.

## Installation

### Option A: HACS (Custom Repository)
1. In Home Assistant, go to HACS → Integrations → ⋮ → Custom repositories
2. Add URL `https://github.com/vitrea-sh/hass-vitrea` with Category `Integration`
3. Search for "Vitrea" in HACS Integrations and install
4. Restart Home Assistant

### Option B: Manual Install
1. Download the latest release or copy this repository
2. Copy the `custom_components/vitrea` directory to your Home Assistant config: `<config>/custom_components/vitrea`
3. Restart Home Assistant

### Other Vitrea integrations
This is the official integration from Vitrea and installs into `custom_components/vitrea`. Any other custom integration that uses the same `vitrea` folder cannot be installed at the same time; remove it (and restart Home Assistant) before installing this one.

## Configuration
1. Go to Settings → Devices & Services → Add Integration
2. Search for "Vitrea"
3. Follow the on-screen steps

## Troubleshooting & Logging
Enable debug logging to capture detailed diagnostics:

```yaml
logger:
  default: warning
  logs:
    custom_components.vitrea: debug
```

After enabling, restart Home Assistant and check the logs for entries from `custom_components.vitrea` (the bundled protocol library logs under the same prefix).

## Support
- Issues: https://github.com/vitrea-sh/hass-vitrea/issues
- Releases: https://github.com/vitrea-sh/hass-vitrea/releases

## License
Apache-2.0. See `LICENSE`.
