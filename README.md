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

- Empty Epsilon server with HTTP API enabled (`httpserver=PORT` on the command line).
- For server management (start/stop, scenario upload): SSH access to the EE server (Linux).
- Home Assistant 2024.1 or newer.

## Documentation

See [PROJECT.md](PROJECT.md) for full architecture, sensor list, and implementation phases.

## License

MIT
