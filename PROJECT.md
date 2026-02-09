# EmptyEpsilon Home Assistant Integration

## Project Overview

A custom Home Assistant integration for [Empty Epsilon](https://daid.github.io/EmptyEpsilon/), the open-source spaceship bridge simulator. This integration enables monitoring game state, controlling the game server, and managing scenarios directly from Home Assistant — turning HA into a Game Master dashboard or automation hub.

**Goals:**
- Publish to HACS (Home Assistant Community Store)
- Follow official HA integration standards (targeting Bronze+ on the Integration Quality Scale)
- Real-time game state via sACN/E1.31 push (~20Hz) + HTTP API for commands and supplementary queries
- Provide sensor data and controls that replicate core GM functionality

---

## Architecture Overview

### How It Works

The integration uses a **hybrid communication architecture** combining two data paths:

1. **sACN/E1.31 (real-time push):** EE has a built-in DMX system originally designed to control stage lighting, fog machines, etc. during gameplay. It can broadcast game state values (hull, shields, alerts, etc.) as sACN packets over UDP at ~20Hz. We repurpose this as a **data transport** — the integration generates a `hardware.ini` config file that maps every game variable we care about to a specific DMX channel number, deploys it to the EE server, and then listens for the resulting UDP packets. Since we control the mapping, we know exactly what each channel means: channel 1 = hull %, channel 2 = front shields, etc. No physical DMX hardware is involved — it's just EE broadcasting game state over the network and our integration listening. Once received, the values become normal HA sensor entities that can drive any automation (flash Hue lights on red alert, send a notification when hull is low, display gauges on a dashboard, etc.).
2. **HTTP API (commands + supplementary queries):** EE's HTTP server evaluates arbitrary Lua expressions. The integration uses this for sending commands (spawn, pause, modify) and querying data not available via sACN (callsigns, positions, object counts, etc.). sACN is output-only — we cannot send commands back through it.

```
┌──────────────────┐                               ┌──────────────────────┐
│  Home Assistant   │         HTTP (Lua API)        │  EmptyEpsilon Server │
│                   │ ──────────────────────────────▶│  (httpserver=PORT)   │
│  custom_components│    POST /exec.lua              │                      │
│  /empty_epsilon/  │    (Lua code in body)          │  headless or GUI     │
│                   │ ◀────────────────────────────  │                      │
│                   │                                │  hardware.ini:       │
│                   │     sACN/E1.31 UDP (push)      │  [hardware]          │
│                   │ ◀──────────────────────────────│  device=sACNDevice   │
│                   │    ~20Hz real-time game state   │  universe=2          │
└──────────────────┘                                └──────────────────────┘
         │
         │ SSH/SCP (server mgmt, scenario upload, hardware.ini deploy)
         ▼
   ┌────────────┐
   │ EE Server  │
   │ filesystem │
   │ scripts/   │
   └────────────┘
```

### sACN Real-Time Data Feed

EE's DMX hardware system was built so game hosts could wire up real stage lights and effects to react to gameplay. We exploit the same system purely as a network data feed:

1. **We generate a `hardware.ini`** that tells EE: "map hull % to channel 1, front shields to channel 2, red alert to channel 5..." using the `variable` effect for clean 0.0–1.0 linear values (no blink/glow effects).
2. **We deploy it** to the EE server via SSH during setup.
3. **EE broadcasts those values** as UDP packets on the local network (~20 times/second). No physical hardware needed.
4. **Our integration listens** (`sacn_listener.py`) and decodes the channels back into meaningful sensor values — because we generated the mapping, we know exactly what each channel means.
5. **They become normal HA sensors** — `sensor.empty_epsilon_hull`, `binary_sensor.empty_epsilon_red_alert`, etc. — available for dashboards, automations, and notifications like any other HA entity.

**Available game state variables for sACN output:**

| Category | Variables |
|---|---|
| **Ship vitals** | Hull, FrontShield/RearShield (Shield0-7), Energy |
| **Ship state** | ShieldsUp, Docking, Docked, InNebula, IsJammed, Jumping, Jumped |
| **Alerts** | Alert, YellowAlert, RedAlert, SelfDestruct, SelfDestructCountdown |
| **Drive systems** | Impulse (-1 to 1), Warp (0-4) |
| **Per-system health** | reactorHealth, beamweaponsHealth, missilesystemHealth, maneuveringHealth, impulseHealth, warpHealth, jumpdriveHealth, frontshieldHealth, rearshieldHealth |
| **Per-system detail** | {system}Power, {system}Heat, {system}Coolant, {system}Hacked |
| **Weapon tubes** | TubeLoaded0-15, TubeLoading0-15, TubeUnloading0-15, TubeFiring0-15 |
| **Meta** | Always (constant 1.0), HasShip (player ship exists) |

**Example generated `hardware.ini`:**

```ini
[hardware]
device = sACNDevice
universe = 2
channels = 50
resend_delay = 50

[channel]
name = hull
channel = 1

[channel]
name = frontShield
channel = 2

[channel]
name = rearShield
channel = 3

[channel]
name = energy
channel = 4

[state]
condition = Always
target = hull
effect = variable
input = Hull
min_input = 0
max_input = 100
min_output = 0.0
max_output = 1.0

[state]
condition = Always
target = frontShield
effect = variable
input = Shield0
min_input = 0
max_input = 100
min_output = 0.0
max_output = 1.0
```

The integration uses a dedicated sACN universe (default: universe 2) to avoid conflicts with any existing DMX lighting setup on universe 1.

**Transport details:**
- Protocol: E1.31 sACN over UDP, port 5568
- Update rate: ~20Hz (configurable via `resend_delay`)
- Python library: `sacn` (PyPI) provides an async-compatible receiver
- Supports both broadcast and multicast

### EE HTTP API Summary

**Important:** In the current EE codebase (as of 2025), the `/get.lua` and `/set.lua` endpoints are **stubbed out** (they return `"TODO"`). Only `/exec.lua` is functional:

| Endpoint | Method | Purpose | Status |
|---|---|---|---|
| `/exec.lua` | POST | Execute arbitrary Lua code (body = Lua), return result as string | **Working** |
| `/get.lua` | GET | Was designed for structured key=value queries | **Stubbed (returns "TODO")** |
| `/set.lua` | POST | Was designed for object method calls | **Stubbed (returns "TODO")** |

**All HTTP communication uses `/exec.lua`** with Lua code in the POST body. Successful responses return the Lua result as a plain string. Errors return JSON: `{"ERROR": "Script error: ..."}`. If no game is running: `{"ERROR": "No game"}`.

**Example queries via `/exec.lua`:**

```lua
-- Get hull percentage
POST /exec.lua
Body: return getPlayerShip(-1):getHull()

-- Pause the game
POST /exec.lua
Body: pauseGame()

-- Get multiple values (return as Lua table string)
POST /exec.lua
Body: local s=getPlayerShip(-1); return s:getHull()..","..s:getCallSign()..","..s:getTypeName()
```

Because `/exec.lua` evaluates arbitrary Lua, **any** function available in the EE scripting environment can be called — giving the integration the same power as the GM console.

### Key Lua Functions (verified from source)

| Function | Description |
|---|---|
| `pauseGame()` | Pause the game (sets game speed to 0.0) |
| `unpauseGame()` | Unpause the game (sets game speed to 1.0) |
| `victory("faction_name")` | End the game with specified faction as winner |
| `getScenarioTime()` | Elapsed time since scenario start (seconds) |
| `getPlayerShip(index)` | Get player ship by index (1-indexed; -1 = first ship) |
| `getAllObjects()` | Get all game objects |
| `globalMessage(text)` | Display message to all players |
| `PlayerSpaceship()` | Create a new player ship |
| `CpuShip()` | Create a new AI ship |
| `SpaceStation()` | Create a new station |

**Game state detection via Lua:**

```lua
-- Is game paused? (game speed == 0 AND no victory faction)
POST /exec.lua
Body: return tostring(getScenarioTime() ~= nil and getPlayerShip(-1) ~= nil)

-- Check for victory/defeat
POST /exec.lua
Body: return tostring(gameGlobalInfo:getVictoryFaction())
```

### What Uses Which Data Path

| Data Path | Used For |
|---|---|
| **sACN (push, ~20Hz)** | Hull, shields, energy, alerts, system health/power/heat/coolant, weapon tube states, impulse/warp levels, docking/jumping state |
| **HTTP API (poll, 5-10s)** | Game status, player ship count, callsigns, ship types, positions/sectors, object counts, scenario time, reputation, ammo counts |
| **HTTP API (on-demand)** | All commands: spawn, pause, modify, comms, Lua execution |
| **SSH** | Server start/stop, scenario upload, `hardware.ini` deployment, firewall configuration |

---

## Sensors

### Required Sensors

| Sensor | Entity Type | Description | Lua Query |
|---|---|---|---|
| **Game Status** | `sensor` | One of: `setup`, `playing`, `paused`, `game_over_victory`, `game_over_defeat` | Derived from multiple queries (see below) |
| **Number of Player Ships** | `sensor` | Count of active player ships | Custom Lua counting loop |

### Recommended Additional Sensors

#### Server-Level Sensors

| Sensor | Entity Type | Source | Description |
|---|---|---|---|
| **Server Running** | `binary_sensor` | sACN+HTTP | Whether the EE server is reachable (sACN packets arriving, HTTP responding) |
| **Has Ship** | `binary_sensor` | sACN | Whether a player ship exists in the game |
| **Game Paused** | `binary_sensor` | HTTP | Whether the game is currently paused |
| **Scenario Time** | `sensor` | HTTP | Elapsed time since scenario start (seconds) |
| **Active Scenario** | `sensor` | HTTP | Name of the currently loaded scenario |
| **Total Objects** | `sensor` | HTTP | Count of all game objects (ships, stations, etc.) |
| **Enemy Ship Count** | `sensor` | HTTP | Number of hostile ships remaining |
| **Friendly Station Count** | `sensor` | HTTP | Number of friendly stations |

#### Per-Player-Ship Sensors (dynamically created per ship)

| Sensor | Entity Type | Source | Description |
|---|---|---|---|
| **Hull** | `sensor` | sACN | Current hull percentage |
| **Energy** | `sensor` | sACN | Current energy level |
| **Front Shields** | `sensor` | sACN | Front shield percentage |
| **Rear Shields** | `sensor` | sACN | Rear shield percentage |
| **Alert Level** | `sensor` | sACN | Normal, Yellow Alert, or Red Alert |
| **Shields Up** | `binary_sensor` | sACN | Whether shields are raised |
| **Impulse Level** | `sensor` | sACN | Current impulse engine output |
| **Warp Level** | `sensor` | sACN | Current warp drive level |
| **Docked** | `binary_sensor` | sACN | Whether the ship is docked at a station |
| **Docking** | `binary_sensor` | sACN | Whether the ship is currently docking |
| **In Nebula** | `binary_sensor` | sACN | Ship is inside a nebula |
| **Jumping** | `binary_sensor` | sACN | Jump drive countdown active |
| **Self Destruct** | `binary_sensor` | sACN | Self-destruct activated |
| **Reactor Health** | `sensor` | sACN | Reactor system health |
| **Impulse Health** | `sensor` | sACN | Impulse engine system health |
| **Warp/Jump Health** | `sensor` | sACN | Warp or jump drive health |
| **Beam Weapons Health** | `sensor` | sACN | Beam weapon system health |
| **Missile System Health** | `sensor` | sACN | Missile system health |
| **Maneuvering Health** | `sensor` | sACN | Maneuvering thruster health |
| **Front Shield Health** | `sensor` | sACN | Front shield generator health |
| **Rear Shield Health** | `sensor` | sACN | Rear shield generator health |
| **Reactor Heat** | `sensor` | sACN | Reactor heat level |
| **Impulse Heat** | `sensor` | sACN | Impulse engine heat level |
| **Weapon Tube States** | `sensor` | sACN | Per-tube loaded/loading/firing state (up to 16 tubes) |
| **Callsign** | `sensor` | HTTP | Ship's callsign |
| **Ship Type** | `sensor` | HTTP | Ship template/class name |
| **Position (Sector)** | `sensor` | HTTP | Grid sector (e.g., "A1") |
| **Homing Missiles** | `sensor` | HTTP | Remaining homing missiles |
| **Nukes** | `sensor` | HTTP | Remaining nukes |
| **EMPs** | `sensor` | HTTP | Remaining EMPs |
| **Mines** | `sensor` | HTTP | Remaining mines |
| **HVLIs** | `sensor` | HTTP | Remaining HVLIs |
| **Reputation** | `sensor` | HTTP | Reputation points |

**Note on dynamic entities:** Player ships can be spawned/destroyed during gameplay. The integration should handle dynamic entity creation and removal as ships appear and disappear.

---

## Controls

### Server Lifecycle Controls

#### Start Server

A HA service call (`empty_epsilon.start_server`) that launches the EE process on the target machine.

**Start Options (presented as a form with toggles/selects):**

| Option | Type | Default | Description |
|---|---|---|---|
| **Scenario** | `select` | *(required)* | Choose from uploaded scenarios |
| **Variation** | `select` | `Default` | Scenario variation (if applicable) |
| **Headless** | `toggle` | `true` | Run without GUI (`headless` flag) |
| **HTTP Server Port** | `number` | `8080` | Port for the HTTP API (`httpserver=PORT`) — **always enabled** |
| **Server Name** | `text` | `"EmptyEpsilon"` | Game name (`name=`) |
| **Server Password** | `text` | *(empty)* | Client connection password (`password=`) |
| **GM Password** | `text` | *(empty)* | GM station password (`gmpassword=`) |
| **Localhost Only** | `toggle` | `false` | Restrict game server connections to localhost (`localhost` flag) |

**Implementation:** The integration builds a command line from the selected options and executes it on the EE server host via SSH:

```
EmptyEpsilon headless httpserver=8080 scenario=scenario_05_fleet.lua name="Friday Game" gmpassword=secret
```

The `httpserver` option is **always enabled** because the integration requires it to communicate with the game. The UI should make this clear but still allow the user to change the port.

#### Stop Server

A button entity or service to stop the running EE process (via SSH `kill` or similar).

### Scenario Management

#### Scenario Upload & Selection

**Workflow:**
1. Game writers upload `.lua` scenario files to a designated location in Home Assistant (e.g., `/config/empty_epsilon/scenarios/`)
2. The integration presents these as selectable options in a `select` entity
3. When starting a game, the selected scenario is transferred to the EE server's `scripts/` directory
4. The transfer mechanism uses **SCP/SFTP over SSH** (the integration stores SSH credentials configured during setup)

**Config Flow Fields for Scenario Management:**
- Path to EE installation on the remote server (e.g., `/opt/EmptyEpsilon/`)
- SSH host, port, username, and key/password for the EE server
- Local scenario storage path (defaults to `/config/empty_epsilon/scenarios/`)

**Alternative approaches considered:**
- **Shared filesystem (NFS/SMB):** Simpler but requires network filesystem setup
- **SCP/SFTP:** Most portable, works over any network
- **Git-based:** Scenario repo that both HA and EE pull from — more complex but versioned

The integration should support SCP as the primary method, with the option to configure a shared filesystem path as an alternative.

### Game Controls

| Control | Entity Type | Description | Lua Command |
|---|---|---|---|
| **Pause** | `button` | Pause the game | `pauseGame()` via `/exec.lua` |
| **Unpause** | `button` | Resume the game | `unpauseGame()` via `/exec.lua` |
| **Pause Toggle** | `switch` | Toggle pause state | Combined `pauseGame()`/`unpauseGame()` |
| **Spawn Player Ship** | `service` | Add a new player ship to the game | `PlayerSpaceship():setFaction("Human Navy"):setTemplate(TEMPLATE):setCallSign(CALLSIGN):setPosition(X,Y)` via `/exec.lua` |

### Recommended Additional Controls

#### GM-Style Object Controls (Services)

| Control | Entity Type | Description |
|---|---|---|
| **Spawn Enemy Ship** | `service` | Create an AI enemy ship (params: template, faction, position, orders) |
| **Spawn Station** | `service` | Create a space station (params: template, faction, position) |
| **Spawn Nebula** | `service` | Create a nebula at position |
| **Spawn Asteroid Field** | `service` | Create asteroids in an area |
| **Destroy Object** | `service` | Remove a game object |
| **Send Comms Message** | `service` | Send a message to a player ship (appears as incoming hail) |
| **Global Message** | `service` | Display a message to all players |
| **Set Victory** | `service` | End the game with a specified winning faction |
| **Execute Lua** | `service` | Execute arbitrary Lua on the server (advanced/debug use) |

#### GM-Style Ship Controls (Services)

| Control | Entity Type | Description |
|---|---|---|
| **Set Ship Orders** | `service` | Set AI ship behavior (attack, defend, roam, idle, fly to, dock) |
| **Modify Hull** | `service` | Set a ship's hull value |
| **Modify Shields** | `service` | Set shield values |
| **Damage System** | `service` | Damage a specific ship system |
| **Repair System** | `service` | Repair a specific ship system |
| **Change Faction** | `service` | Reassign an object to a different faction |
| **Give Weapons** | `service` | Add ammunition to a player ship |

#### Quick-Access Controls (Buttons)

| Control | Entity Type | Description |
|---|---|---|
| **Red Alert All Ships** | `button` | Set all player ships to red alert |
| **Resupply All Ships** | `button` | Refill ammo/energy for all player ships |
| **Repair All Ships** | `button` | Restore all player ships to full health |

### Can the HTTP API Replace the GM Screen?

**Yes, almost entirely.** Because the HTTP API evaluates arbitrary Lua — the same environment the GM console uses — the integration can perform virtually everything the in-game GM screen does:

- Creating/destroying/moving any game object
- Modifying ship properties (hull, shields, systems, weapons)
- Sending comms messages to player ships
- Setting AI orders for NPC ships
- Triggering scenario events and GM functions
- Changing faction relationships
- Pausing/unpausing the game
- Ending the game (victory/defeat)

**What the HTTP API cannot do:**
- Visual map interaction (dragging objects) — but position can be set programmatically
- Real-time visual overview of the game map — would need a separate visualization
- Interactive comm dialogues with branching responses — possible but complex via API

**Conclusion:** The game can be launched with the GUI (for players to use their stations), while HA provides full GM control via the HTTP API. The GUI and HTTP API operate on the same game state simultaneously. A player could even run the GM station in a browser alongside HA controls.

---

## Platform Requirements

**Initial release: Linux only.** The EE server must run on a Linux machine because the integration relies on SSH for server management (start/stop, scenario upload) and firewall rules (`ufw`/`iptables`) for securing the HTTP API. Windows and macOS server support will be added in a future phase (see roadmap).

The Home Assistant instance itself can run on any platform (HAOS, Docker, etc.) — only the EmptyEpsilon server host must be Linux.

---

## Security Considerations

### The Problem

Empty Epsilon's HTTP API has **no built-in authentication, authorization, or encryption**. Anyone who can reach the HTTP port can execute arbitrary Lua code, which means full control over the game.

### Mitigation Strategy: Firewall IP Restriction

The primary security mechanism is **firewall rules on the EE server** that restrict which IP addresses can reach the HTTP API port. The integration will configure these rules automatically during setup (via SSH).

#### How It Works

1. During config flow, the user provides the EE server's SSH credentials
2. The integration determines the HA server's IP address
3. The integration creates firewall rules on the EE server that **only allow the HA server's IP** to connect to the HTTP API port
4. All other IPs are denied access to that port

```bash
# Rules the integration will apply on the EE server:
ufw allow from 192.168.1.10 to any port 8080 proto tcp comment "HomeAssistant EE integration"
ufw deny 8080 comment "Block all other EE HTTP access"
```

If the HA server and EE server are on the same machine, the integration will use the `localhost` flag instead, restricting the HTTP API to `127.0.0.1` only.

#### Additional Safeguards

- The "Execute Lua" service should be **disabled by default** and require explicit opt-in during configuration
- The config flow should warn users about the security implications of the HTTP API
- All sensitive configuration (SSH keys, passwords) should use HA's built-in credential storage

#### Config Flow Security Fields

| Field | Description |
|---|---|
| **EE HTTP Host** | Hostname/IP of the EE server |
| **EE HTTP Port** | HTTP API port (default 8080) |
| **SSH Host** | SSH server for management commands |
| **SSH Port** | SSH port (default 22) |
| **SSH Username** | SSH login user |
| **SSH Auth Method** | Password or key file |
| **SSH Password/Key** | Credentials for SSH |

---

## Home Assistant Integration Structure

### File Layout

```
custom_components/
  empty_epsilon/
    __init__.py              # Integration setup, service registration
    manifest.json            # Integration metadata
    config_flow.py           # UI-based configuration (connection, SSH, options)
    const.py                 # Constants (DOMAIN, defaults, system names)
    coordinator.py           # DataUpdateCoordinator — polls EE HTTP API
    entity.py                # Base entity class with shared DeviceInfo
    sensor.py                # Game state sensors (hull, energy, shields, etc.)
    binary_sensor.py         # Boolean sensors (paused, docked, server reachable)
    switch.py                # Toggle controls (pause/unpause)
    button.py                # One-shot actions (red alert, resupply, repair)
    select.py                # Selection entities (scenario, ship template)
    number.py                # Numeric controls (game speed, power levels)
    services.yaml            # Service definitions (start server, spawn, comms)
    strings.json             # UI strings and translations
    translations/
      en.json                # English translations
    diagnostics.py           # Debug/diagnostics data export
    ee_api.py                # EmptyEpsilon HTTP API client library
    sacn_listener.py         # sACN/E1.31 UDP receiver for real-time game state
    ssh_manager.py           # SSH/SCP connection manager
```

### manifest.json

```json
{
  "domain": "empty_epsilon",
  "name": "EmptyEpsilon",
  "codeowners": ["@YOUR_GITHUB_USERNAME"],
  "config_flow": true,
  "documentation": "https://github.com/YOUR_USERNAME/ha-empty-epsilon",
  "iot_class": "local_push",
  "issue_tracker": "https://github.com/YOUR_USERNAME/ha-empty-epsilon/issues",
  "requirements": ["asyncssh>=2.14.0", "sacn>=1.9.0"],
  "version": "0.1.0",
  "integration_type": "hub"
}
```

### Key Design Patterns

- **Dual-Source Coordinator:** The coordinator combines two data sources: an sACN listener that receives real-time push updates (~20Hz) for ship vitals and system state, and an HTTP API poller (5-10s interval) for metadata like callsigns, positions, and object counts. All sensor entities read from the coordinator's shared data dict.
- **Config Flow:** Multi-step UI flow: Step 1 = EE HTTP connection, Step 2 = SSH credentials (optional, for server management), Step 3 = Options (polling interval, enabled features).
- **Options Flow:** Allow changing polling interval, enabling/disabling advanced features (Execute Lua service, per-system sensors) after initial setup.
- **Dynamic Entities:** Player ship entities are created/removed dynamically as ships are spawned/destroyed. The coordinator tracks active ships each poll cycle.
- **Device Hierarchy:** One parent device ("EmptyEpsilon Server") with optional child devices per player ship.

### HACS Requirements

To be listed in HACS, the repository must include:

| Requirement | Details |
|---|---|
| **hacs.json** | Metadata file in repo root |
| **GitHub repository** | Public repo with the integration code |
| **Releases** | Tagged GitHub releases |
| **README** | Documentation in the repo |
| **Directory structure** | Code in `custom_components/empty_epsilon/` |
| **manifest.json** | Valid manifest with version field |
| **Brands** | Logo and icon (optional but recommended) |

**hacs.json:**
```json
{
  "name": "EmptyEpsilon",
  "render_readme": true,
  "homeassistant": "2024.1.0"
}
```

### Official HA Integration Quality Scale Targets

For potential inclusion in HA core, the integration should meet at least **Bronze** tier:

| Tier | Key Requirements | Status |
|---|---|---|
| **Bronze** | Config flow, unique IDs, proper entity setup, coordinator pattern | Target for v1.0 |
| **Silver** | Device info, diagnostics, reconfiguration flow, options flow | Target for v1.1 |
| **Gold** | Full test coverage, entity translations, service descriptions | Target for v2.0 |

**Additional requirement for core inclusion:** The API client library (`ee_api.py`) should be extracted into a separate PyPI package (e.g., `pyemptyepsilon`) that the integration depends on via `requirements` in manifest.json.

---

## Implementation Phases

### Phase 1: Core Foundation
- Config flow (HTTP connection + SSH credentials for EE server)
- sACN listener for real-time game state (hull, shields, energy, alerts)
- Generate and deploy `hardware.ini` to EE server via SSH (sACN output config)
- HTTP API poller for supplementary data (game status, player ship count, scenario time)
- Basic sensors from both data sources
- Binary sensor: server reachable
- Base entity with DeviceInfo
- HACS-compatible repository structure

### Phase 2: Player Ship Sensors
- Dynamic per-ship entity creation
- Hull, shields, energy, alert level sensors
- System health sensors (reactor, impulse, warp, weapons, etc.)
- Weapon ammo sensors
- Position/sector sensor

### Phase 3: Game Controls
- Pause/unpause switch
- Spawn player ship service
- Global message service
- Victory/defeat service
- Execute Lua service (opt-in)

### Phase 4: Server Management
- SSH connection configuration
- Start server service with full option form
- Stop server button
- Scenario upload and selection
- Scenario file management (local storage in HA)

### Phase 5: Advanced GM Controls
- Spawn enemy ships, stations, environment objects
- Ship order management
- Send comms messages to player ships
- Modify ship properties (hull, shields, systems)
- Faction management
- Quick-action buttons (red alert all, resupply all, repair all)

### Phase 6: Polish & Official Standards
- Full test coverage (pytest, pytest-homeassistant-custom-component)
- Diagnostics support
- Options flow for runtime configuration
- Reconfiguration flow
- Entity translations (strings.json)
- Extract API client to PyPI package
- Logo and branding

### Phase 7: Windows & macOS Server Support
- Windows support: Replace SSH/SCP with WinRM or SSH-on-Windows, replace ufw firewall rules with Windows Firewall (`netsh`) commands, handle Windows process management (start/stop EE)
- macOS support: SSH works natively, replace ufw with macOS `pf` (packet filter) firewall rules, handle macOS process management (launchctl or direct)
- Platform auto-detection during config flow (query the remote host's OS)
- Platform-specific documentation and setup guides

### Phase 8: Multi-Server Support (Possible)
- Support managing multiple EE servers from a single HA instance
- The config flow pattern naturally supports this via multiple config entries — each config entry represents one EE server
- Separate device hierarchy per server
- Evaluate whether there is actual user demand before implementing

### Phase 9: Game Map Visualization
- Lovelace custom card that renders a simplified 2D game map
- Display player ships, enemy ships, stations, nebulae, asteroids from sensor data
- Click-to-select objects for inspection or GM actions
- This would close the last gap between the integration and the in-game GM screen

---

## Resolved Design Decisions

### 1. Scenario Variation Discovery
Parse scenario `.lua` file headers to extract `-- Variation[Name]: Description` lines. This allows the integration to present available variations in the start server form without requiring the user to know them in advance.

### 2. Hybrid Push + Poll Architecture (sACN + HTTP)
EE's built-in DMX/sACN system provides a **real-time push data feed** at ~20Hz over UDP. The integration listens for sACN packets to receive ship vitals (hull, shields, energy, alerts, system health, weapon tube states, drive levels) with no polling delay. The HTTP API is still used for: (a) data not available via sACN — callsigns, positions, object counts, scenario time, ammo counts, reputation; and (b) all commands — spawn, pause, modify, comms, Lua execution. The HTTP API is polled at a slower interval (5-10s) since it only covers supplementary data. This hybrid approach gives the integration `local_push` classification for HA, with the best of both worlds: real-time responsiveness for critical game state and full GM control via HTTP.

**sACN in headless mode (verified from source):** The `HardwareController` is created unconditionally — it runs in both GUI and headless mode. In headless mode, the global `my_spaceship` is null, but the hardware controller has a fallback: it queries the ECS for the first entity with a `PlayerControl` component. So sACN **works in headless mode** and reports data for the first player ship found.

**sACN single-ship limitation:** The sACN feed only reports data for **one** player ship (the first one found). For multi-ship games, per-ship data beyond the first ship must come from the HTTP API. The sACN data is still valuable for the "primary" ship's real-time vitals and for server-level binary states (HasShip, alerts).

### 2a. HTTP API Uses `/exec.lua` Only
Verified from the current EE source code: the `/get.lua` and `/set.lua` endpoints are **stubbed out** (they return the string `"TODO"`). Only `/exec.lua` is functional. All HTTP communication uses `POST /exec.lua` with Lua code in the request body. Successful responses return the Lua result as a plain text string. Errors return JSON: `{"ERROR": "Script error: ..."}`. If no game is running: `{"ERROR": "No game"}`.

### 3. Player Ship Identification
Ships need a stable identity so the GM can track and modify them across polling cycles. Recommended approach:

- **Primary key: Ship index + callsign composite.** EE assigns each player ship an index (`getPlayerShip(0)`, `getPlayerShip(1)`, etc.). The integration uses the index to query and the callsign as the human-readable identifier.
- **HA unique ID:** `{config_entry_id}_ship_{callsign}` — since callsigns are unique within a game session, this provides stable entity IDs.
- **Cross-session persistence:** Ship entities are tied to the current game session. When a new scenario starts, old ship entities are removed and new ones are created. The integration does not attempt to track ships across game restarts.
- **GM modification:** Because each ship has a stable entity, the GM can target specific ships for modification (e.g., `empty_epsilon.modify_hull` with `callsign: "Epsilon"` as a parameter). The integration resolves the callsign back to the ship index when sending commands.
- **Ship destruction mid-game:** If a ship is destroyed, its entities become unavailable. The coordinator detects missing ships each poll cycle and marks their entities accordingly.

### 4. Full GM Mode in HA (No Add-on Needed)
The HTTP API can functionally replicate **everything** the in-game GM screen does:
- Spawn/destroy/move any game object
- Modify ship properties (hull, shields, systems, weapons, ammo)
- Send comms messages and global messages
- Set AI orders, change factions, trigger scenario events
- Pause/unpause, set victory/defeat
- Execute arbitrary Lua (same as the GM console)

The only gap is the **visual game map** — the GM screen shows a real-time 2D map where you can click and drag objects. This is addressed in Phase 9 (Game Map Visualization Lovelace card). Until then, all GM actions are available but must be invoked by callsign/coordinates rather than visual selection.

Because full GM functionality is available via the API, there is no need for an HA Add-on that runs EE locally. The EE server runs on its own Linux host (with GUI for player stations if desired), and HA provides GM control remotely.

---

## Open Questions

1. **Polling interval tuning:** Should the default polling interval be configurable per-entity-type? (e.g., poll ship sensors every 2s but server status every 10s)
2. **Scenario file validation:** Should the integration validate uploaded `.lua` scenario files before transferring them to the EE server? (Basic syntax check, header parsing, etc.)
3. **GM action confirmations:** Should destructive GM actions (destroy object, set victory, self-destruct) require confirmation in the HA UI, or rely on standard HA service call behavior?
