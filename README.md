# EmptyEpsilon Home Assistant Integration

A custom Home Assistant integration for [Empty Epsilon](https://daid.github.io/EmptyEpsilon/), the open-source spaceship bridge simulator. Monitor game state, control the server, and manage scenarios from Home Assistant.

## Features

- **Real-time game state** via sACN/E1.31 (~20 Hz): hull, shields, energy, alerts, system health
- **HTTP API** for commands and supplementary data: pause, spawn, scenario time, callsigns
- **Server management** via SSH: start/stop EE, upload scenarios, deploy sACN config

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

- Empty Epsilon server with HTTP API enabled (`httpserver=PORT` on the command line).
- For server management (start/stop, scenario upload): SSH access to the EE server (Linux).
- Home Assistant 2024.1 or newer.

## Documentation

See [PROJECT.md](PROJECT.md) for full architecture, sensor list, and implementation phases.

## Publishing this repo on GitHub

1. **Set your GitHub username in the integration**  
   In `custom_components/empty_epsilon/manifest.json`, replace `YOUR_GITHUB_USERNAME` with your GitHub username (e.g. `johndoe`) in all three places (codeowners, documentation URL, issue tracker URL).

2. **Initialize git and push** (from the project root):

   ```bash
   cd path/to/HomeAssistant-Integration   # your project folder
   git init
   git add .
   git commit -m "Initial commit: EmptyEpsilon Home Assistant integration"
   ```

3. **Create the repo on GitHub**  
   - Go to [github.com/new](https://github.com/new).  
   - Repository name: `ha-empty-epsilon` (or any name you like).  
   - Public, no need to add README/.gitignore (you already have them).  
   - Create repository.

4. **Connect and push** (use your username and repo name):

   ```bash
   git remote add origin https://github.com/YOUR_GITHUB_USERNAME/ha-empty-epsilon.git
   git branch -M main
   git push -u origin main
   ```

5. **Optional: first release for HACS**  
   - On GitHub: **Releases** → **Create a new release**.  
   - Tag: `v0.1.0`, title e.g. `v0.1.0`.  
   - Publish. HACS will use this tag for installation.

## License

MIT
