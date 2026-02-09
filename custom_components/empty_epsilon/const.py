"""Constants for the EmptyEpsilon integration."""

DOMAIN = "empty_epsilon"

# Defaults
DEFAULT_HTTP_PORT = 8080
DEFAULT_SSH_PORT = 22
DEFAULT_POLL_INTERVAL = 10
DEFAULT_SACN_UNIVERSE = 2
DEFAULT_SACN_CHANNELS = 50
DEFAULT_RESEND_DELAY_MS = 50  # ~20 Hz

# Config keys
CONF_EE_HOST = "ee_host"
CONF_EE_PORT = "ee_port"
CONF_SSH_HOST = "ssh_host"
CONF_SSH_PORT = "ssh_port"
CONF_SSH_USERNAME = "ssh_username"
CONF_SSH_PASSWORD = "ssh_password"
CONF_SSH_KEY = "ssh_key"
CONF_SSH_KNOWN_HOSTS = "ssh_known_hosts"
CONF_SSH_SKIP_HOST_KEY_CHECK = "ssh_skip_host_key_check"

# Paths for generated files (under /config)
EE_CONFIG_DIR = "empty_epsilon"
EE_KEY_PATH = f"/config/{EE_CONFIG_DIR}/id_rsa"
EE_PUBKEY_PATH = f"/config/{EE_CONFIG_DIR}/ee_ssh_public_key.pub"
EE_KNOWN_HOSTS_PATH = f"/config/{EE_CONFIG_DIR}/known_hosts"
CONF_POLL_INTERVAL = "poll_interval"
CONF_SACN_UNIVERSE = "sacn_universe"
CONF_EE_INSTALL_PATH = "ee_install_path"
CONF_SCENARIO_PATH = "scenario_path"
CONF_ENABLE_EXEC_LUA = "enable_exec_lua"

# sACN channel mapping (channel number 1-based -> key in payload)
# Used by sacn_listener to decode and by hardware.ini generator to build config.
# Format: (channel_index_0based, ee_variable, min_in, max_in, min_out, max_out)
# For variable effect: min_output/max_output typically 0.0/1.0
SACN_CHANNEL_SPEC = [
    (1, "Hull", 0, 100, 0.0, 1.0),
    (2, "Shield0", 0, 100, 0.0, 1.0),   # front
    (3, "Shield1", 0, 100, 0.0, 1.0),   # rear
    (4, "Energy", 0, 100, 0.0, 1.0),
    (5, "RedAlert", 0, 1, 0.0, 1.0),
    (6, "YellowAlert", 0, 1, 0.0, 1.0),
    (7, "ShieldsUp", 0, 1, 0.0, 1.0),
    (8, "Docked", 0, 1, 0.0, 1.0),
    (9, "Docking", 0, 1, 0.0, 1.0),
    (10, "HasShip", 0, 1, 0.0, 1.0),
    (11, "Impulse", -1, 1, 0.0, 1.0),  # EE may output -1..1; we map to 0..1
    (12, "Warp", 0, 4, 0.0, 1.0),
]

# Names for each channel (for hardware.ini [channel] name and for entity keys)
SACN_CHANNEL_NAMES = [
    "hull",
    "frontShield",
    "rearShield",
    "energy",
    "redAlert",
    "yellowAlert",
    "shieldsUp",
    "docked",
    "docking",
    "hasShip",
    "impulse",
    "warp",
]

# Game status values
GAME_STATUS_SETUP = "setup"
GAME_STATUS_PLAYING = "playing"
GAME_STATUS_PAUSED = "paused"
GAME_STATUS_GAME_OVER_VICTORY = "game_over_victory"
GAME_STATUS_GAME_OVER_DEFEAT = "game_over_defeat"

# HTTP API
EE_EXEC_PATH = "/exec.lua"

# Simplest built-in EE scenario for init start-server (proves we have full control)
DEFAULT_INIT_SCENARIO = "scenario_jump_00.lua"
