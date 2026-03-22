# Host Setup

This is the current host workflow for `Pseudo-OnBlivion`.

## 1. Server prerequisites

- Windows machine with either Python 3.12+ or the packaged `PseudoOnBlivionRelay.exe`
- TCP port `7777` available, or another chosen port
- Optional: a VPN overlay like Tailscale if you do not want to expose a home router port

## 2. Start the relay

Copy the example config:

```powershell
Copy-Item server\relay_config.example.json server\relay_config.json
```

Edit `server\relay_config.json` and set:

- `host` to `0.0.0.0` if remote peers need to reach you
- `port` to your chosen port
- `require_token` to `true` for private sessions
- `server_token` to a shared secret if private sessions are enabled
- `host_player_id` to the player id that should own quest and loot state writes
- `state_root` to the folder where room state snapshots should be persisted

Start the relay:

```powershell
& 'C:\Users\harry\AppData\Local\Programs\Python\Python312\python.exe' server\relay_server.py --config server\relay_config.json
```

Or, if you built the relay executable:

```powershell
server\PseudoOnBlivionRelay.exe --config server\relay_config.json
```

## 3. Local firewall

Allow inbound TCP for the chosen relay port in Windows Defender Firewall.

Minimum rule:

- Protocol: TCP
- Port: `7777`
- Scope: your chosen network profile

## 4. External connectivity options

Choose one:

### Option A: Tailscale

- Install Tailscale on both host and joiner machines
- Sign in and ensure the machines can ping each other on the Tailscale IPs
- Put the host machine's Tailscale IP into each plugin config

This is the easiest way to test with a friend.

### Option B: Home router port forwarding

- Forward external TCP `7777` to your PC's internal IPv4 address on TCP `7777`
- Give the joiner your public IP or DNS name
- Keep in mind your public IP may change unless you use dynamic DNS

### Option C: VPS relay

- Run the Python relay on a cloud VM
- Open the port in the cloud firewall/security group
- Point both game clients at the VPS hostname

This is usually the cleanest long-term setup.

## 5. Game-side host config

Install xOBSE first if it is not already present:

```powershell
powershell -ExecutionPolicy Bypass -File plugin\install_xobse.ps1 -GamePath "C:\Games\Oblivion"
```

Once the xOBSE plugin is built, you can package it with:

```powershell
powershell -ExecutionPolicy Bypass -File plugin\package_plugin.ps1 -Configuration Debug
```

Then copy:

- the plugin DLL to `Oblivion\Data\OBSE\Plugins\`
- `PseudoOnBlivion.ini` beside it or in the plugin's expected config path

Or deploy directly if you know the game path:

```powershell
powershell -ExecutionPolicy Bypass -File plugin\deploy_plugin.ps1 -GamePath "C:\Games\Oblivion" -Configuration Debug -IniPath plugin\profiles\PseudoOnBlivion.host.ini
```

If your install is in a common Steam/GOG location, the deploy script can also try to detect it automatically:

```powershell
powershell -ExecutionPolicy Bypass -File plugin\deploy_plugin.ps1 -Configuration Debug
```

Use a config like:

```ini
[network]
server_host=100.64.10.20
server_port=7777
room=session-1
player_id=host-player
character_name=HostHero
host_authority=true
server_token=replace-this-if-private
send_interval_ms=100

[logging]
log_path=PseudoOnBlivion.log
```

## Current limitation

The relay is ready. The game plugin is still a scaffold and does not yet spawn remote player avatars or drive real quest replication. Host setup here is the networking side plus the plugin layout needed for the next integration pass.
