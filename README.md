# Vitrea Home Assistant Integration

> Note: This integration is experimental. APIs and behavior may change without notice. Use at your own risk

Vitrea integration for Home Assistant. Provides local control of Vitrea devices via the Vitrea controller.

- Entities: lights, covers/blinds, fans, thermostats, scenarios, binary sensors, sensors, switches
- IO class: local_push
- Supports UI config flow

## Requirements
- Home Assistant 2023.8 or newer
- Network access from Home Assistant to the Vitrea controller

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
    vitrea_integration: debug
```

After enabling, restart Home Assistant and check the logs for entries from `custom_components.vitrea` and `vitrea_integration`.

## Support
- Issues: https://github.com/vitrea-sh/hass-vitrea/issues
- Releases: https://github.com/vitrea-sh/hass-vitrea/releases

## License
Apache-2.0. See `LICENSE`.
