# EmptyEpsilon Home Assistant Integration

A custom Home Assistant integration for [Empty Epsilon](https://daid.github.io/EmptyEpsilon/), the open-source spaceship bridge simulator. Monitor game state, control the server, and manage scenarios from Home Assistant.

## Features

- **Real-time game state** via sACN/E1.31 (~20 Hz): hull, shields, energy, alerts, system health
- **HTTP API** for commands and supplementary data: pause, spawn, scenario time, callsigns
- **Server management** via SSH: start/stop EE, upload scenarios, deploy sACN config

## Installation

### Via HACS (recommended)

1. In HACS, go to **Integrations** → **⋮** → **Custom repositories**.
2. Add: `https://github.com/YOUR_GITHUB_USERNAME/ha-empty-epsilon` (use your actual GitHub username and repo name).
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

## Documentation

See [PROJECT.md](PROJECT.md) for full architecture, sensor list, and implementation phases.

## License

MIT
