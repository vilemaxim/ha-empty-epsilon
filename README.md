# EmptyEpsilon Home Assistant Integration

A custom Home Assistant integration for [Empty Epsilon](https://daid.github.io/EmptyEpsilon/), the open-source spaceship bridge simulator. Monitor game state, control the server, and manage scenarios from Home Assistant.

## Features

- **Real-time game state** via sACN/E1.31 (~20 Hz): hull, shields, energy, alerts, system health
- **HTTP API** for commands and supplementary data: pause, spawn, scenario time, callsigns
- **Server management** via SSH: start/stop EE, upload scenarios, deploy sACN config
- **Start paused** by default — use the Pause switch or `unpauseGame()` to begin

## Sensor data sources

| Source | Sensors |
|--------|---------|
| **HTTP API** (polled) | Game status, Player ship count, Scenario time, Active scenario, Total objects, Enemy ships, Friendly stations, Game paused, Callsign, Ship type, Sector, Homing/Nuke/EMP/Mine/HVLI ammo, Reputation |
| **sACN** (real-time push) | Hull, Front shields, Rear shields, Energy, Impulse, Warp, Has ship, Shields up, Docked, Docking |

## Installation

### Via HACS (recommended)

1. In HACS, go to **Integrations** → **⋮** → **Custom repositories**.
2. Add: `https://github.com/vilemaxim/ha-empty-epsilon` (use your actual GitHub username and repo name).
3. Search for **EmptyEpsilon** and install.
4. Restart Home Assistant, then **Settings → Devices & services → Add integration** → **EmptyEpsilon**.

### Manual

1. Copy the `custom_components/empty_epsilon` folder into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. **Settings → Devices & services → Add integration** → search **EmptyEpsilon** and complete the config flow.

## Requirements

- Empty Epsilon server with HTTP API enabled. The integration deploys `options.ini` and `hardware.ini` to `~/.emptyepsilon/` on the EE host. The EE server is expected to be an Ubuntu system with the latest Empty Epsilon installed via the official `.deb` package (typically at `/usr/local/bin/EmptyEpsilon`). For game clients to connect, open port **35666** (TCP) on your firewall per the [Headless Dedicated Server](https://github.com/daid/EmptyEpsilon/wiki/Headless-Dedicated-Server) guide.
- For server management (start/stop, scenario upload): SSH access to the EE server.
- Home Assistant 2024.1 or newer.

## Configuration

To change integration settings (EE Install Path, poll interval, sACN universe, etc.):

1. Go to **Settings** → **Devices & services**
2. Find the **EmptyEpsilon** integration and click on it
3. Open the **⋮** (three dots) menu on the integration card
4. Select **Configure** or **Options** (label varies by Home Assistant version)
5. Adjust **EE Install Path** (directory containing the EmptyEpsilon binary, e.g. `/usr/local/bin` for .deb installs) and other options
6. Click **Submit**

## Logo

The Empty Epsilon logo is included in `custom_components/empty_epsilon/images/` (icon.png, logo.png). To have it appear in the Home Assistant frontend (Settings → Integrations), submit the images to the [Home Assistant brands repository](https://github.com/home-assistant/brands) by adding `custom_integrations/empty_epsilon/` with `icon.png` and `logo.png`.

## Deploying updates

**The integration runs from HA's config folder, not your project folder.** After changing code, you must copy files to your Home Assistant instance:

- **HA OS path:** `/config/custom_components/empty_epsilon/` (use the **File Editor** add-on or **Samba** share)
- **Manual:** Copy the entire `custom_components/empty_epsilon` folder from this repo into HA's `custom_components` directory
- **After updating:** Restart Home Assistant (Configuration → System → Restart), not just reload

**Verify deployment:** After restart, check **Settings** → **System** → **Logs**. Search for `EmptyEpsilon: integration loading`. If you see that WARNING, the updated code is running. If you don't, the old code is still in use.

## Debugging

The integration logs to **Settings** → **System** → **Logs** in the main **Home Assistant** log (not a separate dropdown). Select the main/core log view and search for `empty_epsilon` or `EmptyEpsilon` to find entries.

**Enable logging via configuration.yaml** (most reliable):

1. Add or merge this into `configuration.yaml` in your config folder:

```yaml
logger:
  default: info
  logs:
    custom_components.empty_epsilon: debug
```

2. Restart Home Assistant.

**Or use the integration menu** (if available): **Settings** → **Devices & services** → EmptyEpsilon → **⋮** → **Enable debug logging**.

**What you'll see:**

- `EmptyEpsilon setup: EE API at http://...` — confirms the integration loaded and which host:port it uses
- `EmptyEpsilon HTTP poll: has_game=... url=...` — every poll cycle (default every 10s)
- `get_has_game: EE returned ... -> has_game=...` — raw response from the EE server
- WARNING lines when the HTTP API fails (connection error, EE error response)

If you see no EmptyEpsilon lines at all, the integration may be failing before it starts (check for errors mentioning `empty_epsilon` or `binary_sensor`).

## Documentation

See [PROJECT.md](PROJECT.md) for full architecture, sensor list, and implementation phases.

## License

MIT
