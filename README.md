# Phone Setup

Asterisk configuration for a private PBX built around a vintage Nortel analog phone. The phone acts as a terminal into the local network; it can make calls, stream internet radio, control Spotify, talk to AI agents, and interface with other devices on the LAN. Source of truth for all Asterisk config, edit here, deploy to `/etc/asterisk/`.

## Hardware

Nortel analog phone -> Grandstream HT701 ATA -> Asterisk 23.2.2 on ThinkPad (Arch Linux)

## Network

- ThinkPad ethernet (`enp0s31f6`): `192.168.10.1/24` (static, in `/etc/dhcpcd.conf`)
- HT701 gets IP via DHCP from dnsmasq (currently `192.168.10.126`)
- HT701 web UI: http://192.168.10.126 (password: `admin`)

## Extensions

3-digit dial plan. Dial **0** as a shortcut to the operator.

### Utility (1xx)

| Ext | What |
|-----|------|
| 0 / 100 | AI operator (AudioSocket -> `~/operator/`, port 9092) |
| 101 | Hello world |
| 102 | Echo test |
| 103 | DTMF test (4 digits) |
| 104 | Music on hold |
| 105 | Congrats message |

### AI Agents (2xx)

| Ext | Agent | Port |
|-----|-------|------|
| 200 | Chef | 9200 |
| 201 | Fun Facts | 9201 |
| 202 | Librarian | 9202 |
| 203 | French Tutor | 9203 |
| 204 | Daily Briefing | 9204 |
| 205 | DJ Cool (Music Concierge) | 9205 |

Each routes through AudioSocket to a standalone Python agent in `~/agents/`.

### Radio (7xx) -- 19 stations

| Ext | Station | Region |
|-----|---------|--------|
| 700 | CISM 89.3 | Montreal |
| 701 | CIUT 89.5 | Toronto |
| 702 | CKDU 88.1 | Halifax |
| 703 | WFMU 91.1 | Jersey City |
| 704 | New Sounds | NYC |
| 705 | WNYC 93.9 | NYC |
| 706 | WMBR 88.1 | MIT |
| 707 | WBUR 90.9 | Boston |
| 708 | CHIRP 107.1 | Chicago |
| 709 | WBEZ 91.5 | Chicago |
| 710 | KEXP 90.3 | Seattle |
| 711 | KALX 90.7 | Berkeley |
| 712 | BFF.fm | San Francisco |
| 713 | KQED 88.5 | San Francisco |
| 714 | KBOO 90.7 | Portland |
| 715 | XRAY.fm 91.1 | Portland |
| 716 | The Gamut (WWFD 820 AM) | Washington DC |
| 717 | WETA Classical 90.9 | Washington DC |
| 718 | NPR | National |

DTMF while listening: **4** = now playing, **5** = speakers on (ConfBridge/baresip), **6** = all speakers off, **7** = speakers on (direct stream).

### Spotify (730, 8xx)

Dial **730** to start Spotify on the laptop speakers (pick music from the app). Dial an **8xx** extension to start a specific playlist. All audio plays through the laptop speakers at full quality via librespot.

DTMF while listening: **1** = previous, **2** = pause/resume, **3** = next, **4** = now playing (TTS), **6** = stop.

Playlist mappings are in `spotify-playlists.conf` (deployed to `/etc/asterisk/spotify-playlists.conf`):

| Ext | Playlist |
|-----|----------|
| 800 | radio 2 |
| 801 | 140+ |
| 802 | noise |
| 803 | folksy |
| 804 | Country |
| 805 | Actually good Classical |
| 806 | songs I like from radio |
| 807 | RAP |
| 808 | Québécois music |
| 809 | Cool beans |
| 810 | My playlist #24 |
| 811 | tunes |

Alternatively, dial **205** for DJ Cool — a voice AI music concierge that searches Spotify, takes requests, and controls playback by conversation.

## Config files

| File | Purpose |
|------|---------|
| `extensions.conf` | Dialplan -- all extensions, stream injection, now-playing, speaker control |
| `pjsip.conf` | SIP endpoints: 100 (HT701 phone), 150 (baresip speaker) |
| `confbridge.conf` | ConfBridge profiles for radio + DTMF menu |
| `musiconhold.conf` | AAC stream decoding for CIUT and WETA (via ffmpeg) |
| `spotify-playlists.conf` | Maps 8xx extensions to Spotify playlist URIs |
| `dnsmasq.conf` | DHCP/DNS for the HT701 |
| `/etc/asterisk/deepgram.env` | Deepgram API key for now-playing TTS (readable by asterisk user only) |
| `/etc/sudoers.d/radio-speaker` | Lets asterisk user run ffplay/aplay as hazel for speaker audio |

### How radio works

Each station uses a ConfBridge so the handset and room speakers can share one stream. When you dial a 7xx extension:

1. Asterisk originates a Local channel into `[stream-inject]`, which plays the station's stream (MP3Player for MP3, MusicOnHold+ffmpeg for AAC).
2. That Local channel joins the ConfBridge as `radio_user`.
3. The handset joins the same bridge as `handset_user` (marked -- bridge tears down when you hang up).
4. Pressing 5 originates a call to baresip (ext 150), which joins as `speaker_user`.

### Room speakers (DTMF 5/6/7)

While listening to a radio station, there are two ways to play audio through the ThinkPad's speakers:

- **5** — Pipe ConfBridge audio to speakers via baresip. Audio passes through the phone system at 8kHz.
- **7** — Play the station's original webstream directly on the speakers via ffplay. Full quality, bypasses the phone system entirely.

Press **6** to stop all speaker output (kills both baresip and direct stream). Hanging up also stops the direct stream automatically.

**DTMF 5 (ConfBridge/baresip):** Pressing 5 triggers the `[speaker-control]` context, which originates a SIP call to endpoint 150 (baresip). baresip auto-answers, joins the same ConfBridge as `speaker_user`, and routes audio to PulseAudio's default output.

**DTMF 7 (direct stream):** Pressing 7 triggers the `[speaker-stream]` context, which runs `/usr/local/bin/radio-speaker start <bridge>`. The script uses `setsid` to launch `ffplay` as the `hazel` user in a new session (so it survives Asterisk's process cleanup), playing the station's webstream directly through PulseAudio.

**DTMF 4 (now playing) on speakers:** When ffplay is running (detected via `pgrep -x ffplay`), pressing 4 also plays the TTS announcement on the laptop speakers using `paplay`. The music is ducked to 45% volume via `pactl set-sink-input-volume` during the announcement and restored to 100% after. (Previously used SIGSTOP/SIGCONT to pause ffplay, but some stream servers drop the connection when the client stops reading.) TTS uses Deepgram Aura 2 (`aura-2-asteria-en`) for natural-sounding voice, with espeak-ng as fallback.

**Cleanup (hangup and DTMF 6):** Both use `System(sudo -u hazel pkill -f 'ffplay.*-nodisp')` to kill the direct stream. The `-f` flag matches the full command line, which kills both the `ffplay` child and its `sudo` parent wrapper (since `sudo`'s cmdline also contains "ffplay"). Without this, `pkill -x ffplay` only kills the child, leaving zombie `sudo` processes that accumulate over time. The `sudo -u hazel` is required because Asterisk runs as the `asterisk` user which can't signal hazel-owned processes. The `[internal]` context has an `h` extension for hangup cleanup, and `[speaker-control]` off also kills ffplay alongside the baresip `SoftHangup`.

**Note on audio from Asterisk `System()`:** Asterisk runs as the `asterisk` user, which has no access to PulseAudio and cannot signal other users' processes. All audio commands must go through `sudo -u hazel` with `XDG_RUNTIME_DIR=/run/user/1000`. Authorized by `/etc/sudoers.d/radio-speaker` (`SETENV` + `NOPASSWD` for `/usr/bin/ffplay`, `/usr/bin/paplay`, `/usr/bin/pkill`, and `/usr/bin/pactl`).

**Gotcha — backgrounding processes from `System()`:** Asterisk's `System()` kills backgrounded child processes when the parent shell exits. The fix is `setsid` — it creates a new process session that Asterisk can't clean up. The `radio-speaker` script calls `System()` synchronously (no `&` in the dialplan); `setsid` handles the detach internally. PID file writes after `setsid ... &` are unreliable because the script may be killed before the write — use `pgrep`/`pkill` instead.

**Gotcha — ALSA vs PulseAudio for concurrent audio:** `aplay` uses ALSA directly and can't play while ffplay has the device open (`Device or resource busy`). Use `paplay` instead — it goes through PulseAudio which handles mixing multiple audio streams.

**Gotcha — file permissions for `asterisk` user:** The asterisk user cannot traverse `/home/hazel/`, so any files it needs (like API keys) must be placed somewhere accessible. The Deepgram API key lives at `/etc/asterisk/deepgram.env` (owner: asterisk, mode: 600). If the key in `~/operator/.env` is rotated, update the copy: `grep DEEPGRAM_API_KEY ~/operator/.env | sudo tee /etc/asterisk/deepgram.env`

**baresip** is a headless SIP softphone running as a systemd user service on the ThinkPad.

| | |
|---|---|
| Service | `~/.config/systemd/user/baresip.service` |
| Config dir | `~/.baresip/` |
| SIP account | `150@127.0.0.1` (password: `speakerpass`, auto-answer) |
| Audio | PulseAudio default output (`audio_player pulse,default`) |
| Codec | G.711 (ulaw/alaw) via `g711.so` |
| PJSIP endpoint | `150` in `pjsip.conf` (matched by `direct_media=no`) |

```bash
systemctl --user status baresip      # check if running
systemctl --user restart baresip     # restart after config changes
systemctl --user enable baresip      # auto-start on login (already enabled)
```

## Deploy

Asterisk config:
```bash
sudo cp extensions.conf pjsip.conf confbridge.conf musiconhold.conf /etc/asterisk/
sudo asterisk -rx "dialplan reload"
```

For pjsip.conf changes: `sudo asterisk -rx "module reload res_pjsip"`

For confbridge.conf changes (menu, profiles): `sudo asterisk -rx "module reload app_confbridge"` — `dialplan reload` alone won't pick up ConfBridge menu changes.

Helper scripts:
```bash
sudo cp now-playing radio-speaker stream-decode ring-phone alarm /usr/local/bin/
sudo chmod +x /usr/local/bin/{now-playing,radio-speaker,stream-decode,ring-phone,alarm}
```

## Helper scripts

| Script | Deployed to | What |
|--------|-------------|------|
| `now-playing` | `/usr/local/bin/now-playing` | Fetch track info (ICY metadata + KEXP/BFF/WNYC/CKDU APIs), generate TTS wav via Deepgram Aura 2 (falls back to espeak-ng). Also announces on laptop speakers when direct stream is active. |
| `radio-speaker` | `/usr/local/bin/radio-speaker` | Direct webstream playback on laptop speakers via ffplay (`start <station>` / `stop`). Cleanup uses `pkill -x ffplay` (not PID file). |
| `spotify-connect` | `/usr/local/bin/spotify-connect` | Librespot lifecycle + Spotify Web API control (start, stop, play, pause, next, prev, now-playing). Used by 730/8xx dialplan and DJ Cool agent. |
| `stream-decode` | `/usr/local/bin/stream-decode` | ffmpeg wrapper: any audio stream -> 8kHz slin16 for Asterisk |
| `ring-phone` | `/usr/local/bin/ring-phone` | Ring the Nortel |
| `alarm` | `/usr/local/bin/alarm` | Ring phone + play alarm clip |

## HT701 config (via web UI)

- SIP server: `192.168.10.1`, user/auth ID: `100`, password: `changeme`
- DTMF: RFC2833
- Dial plan: `{0|xxx|*x+}` -- 0 dials instantly, 3-digit codes dial on last digit, `*` prefixes for ConfBridge DTMF
- Call progress tones: French (440Hz)
- Use Random RTP Port: Yes (prevents RTP state reuse across calls)
- Use Random SIP Port: No
- Enable SIP OPTIONS Keep Alive: Yes (interval 30s, max lost 3)
- Unregister on Reboot: Yes (clean SIP teardown when ATA restarts)
- NAT Traversal: Keep-Alive
- Config changes sometimes need a power cycle, not just Apply

## Troubleshooting

**Silence on all or some extensions after restart/sleep**: The HT701 loses RTP sync when Asterisk restarts, the ThinkPad sleeps, or after a fast redial. SIP signaling still works (calls connect, Asterisk sees them) but audio is silently dropped. Can affect native Asterisk audio, AudioSocket agents, or both. Fix: power cycle the HT701 (unplug power, wait 5s, plug back in). Web UI reboot is not sufficient. Note: `dialplan reload` can also trigger this — any Asterisk reload risks an RTP desync. Mitigations: "Use Random RTP Port" on the HT701 (avoids stale RTP port reuse), `rtp_timeout=30` in pjsip.conf (detects dead RTP and fires hangup cleanup within 30s), and "Unregister on Reboot" / "SIP OPTIONS Keep Alive" on the HT701 for cleaner SIP state.

**PJSIP qualify keepalive**: The AOR for endpoint 100 has `qualify_frequency=30`, which sends SIP OPTIONS pings to the HT701 every 30 seconds. This serves two purposes: (1) keeps the NAT/RTP path alive so the ATA doesn't lose sync during idle periods, and (2) lets Asterisk detect when the ATA becomes unreachable (contact status changes from `Reachable` to `Unavailable`). Check status with `sudo asterisk -rx 'pjsip show aors'`.

**RTP timeout**: Endpoint 100 has `rtp_timeout=30` — if no RTP is received for 30 seconds (e.g., HT701 power cycled mid-call), Asterisk hangs up the channel. This fires the `h` extension which cleans up ffplay speaker processes.

## Operations

### Laptop as a server

The ThinkPad runs Asterisk, dnsmasq, baresip, and up to 6 Python agent processes (operator + 5 agents). It is a server and must stay powered on with the network interface active at all times.

**Suspend is disabled.** Closing the lid blanks the screen (DPMS) but the system stays awake. This was necessary because the HT701 loses RTP sync every time the laptop sleeps, requiring a physical power cycle of the ATA to recover.

```bash
# What was changed
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
# /etc/systemd/logind.conf: HandleLidSwitch=ignore, HandleLidSwitchExternalPower=ignore

# To re-enable suspend later
sudo systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target
# Then in /etc/systemd/logind.conf, revert to:
#   #HandleLidSwitch=suspend
#   #HandleLidSwitchExternalPower=suspend
# and run: sudo systemctl restart systemd-logind
```

### Power and thermal considerations

With the lid closed and suspend disabled, the ThinkPad idles at low power but never enters deep sleep states. Keep in mind:

- **Always on AC power.** The laptop should stay plugged in. Running 24/7 on battery will drain it and eventually shut down, which is the same as a sleep event from the HT701's perspective.
- **Ventilation.** The lid is closed, so the built-in keyboard area doesn't help with airflow. The ThinkPad's bottom vents do the heavy lifting. Don't set it on a blanket or pillow — a hard flat surface or a laptop stand with clearance underneath is ideal.
- **Battery longevity.** Lithium-ion batteries degrade faster when held at 100% charge continuously. ThinkPads support charge thresholds via `tlp` or the BIOS — setting a stop threshold of 80% (`START_CHARGE_THRESH_BAT0=75`, `STOP_CHARGE_THRESH_BAT0=80` in `/etc/tlp.conf`) will extend battery lifespan significantly. Not critical, but worth doing if this setup runs for months.

### Resource usage

When idle (no active calls), the system is very light:

| Component | Idle footprint |
|-----------|---------------|
| Asterisk | ~30 MB RSS, near-zero CPU |
| dnsmasq | ~2 MB RSS |
| baresip | ~15 MB RSS |
| Each Python agent | ~80-100 MB RSS (Python runtime + Pipecat + Silero VAD model) |
| **Total (6 agents)** | **~550-650 MB RSS** |

During a call, a single agent spikes briefly for Silero VAD inference (~5ms per 30ms audio chunk on CPU) and for network I/O to Deepgram and Anthropic APIs. CPU usage during a call is under 10% of one core. Multiple simultaneous calls are possible but unlikely on a single handset.

The Silero VAD model (~2 MB) is loaded per-call and unloaded when the call ends. There's no GPU usage — everything runs on CPU.

### Reducing memory footprint

The 6 agent processes account for most of the memory. Options to reduce this:

- **On-demand agents.** Instead of running all 6 agents at all times, start them only when called and stop them after the call ends. This would require a launcher script or systemd socket activation. Tradeoff: ~1-2 seconds of cold-start latency on the first call while Python loads and the VAD model initializes.
- **Single multiplexed process.** Run one Python process that handles all extensions, selecting the system prompt and voice based on the AudioSocket UUID. This would share the Python runtime, Pipecat framework, and Silero model across all agents, cutting memory from ~600 MB to ~150 MB. Tradeoff: more complex code, a crash takes down all agents, and you lose per-agent process isolation.
- **Swap.** If memory pressure becomes an issue, ensure swap is configured. The idle agents' memory will page out naturally since it's not accessed between calls.

### Network resilience

The ThinkPad-to-HT701 link is a direct Ethernet cable (`192.168.10.0/24`), so there's no router, switch, or Wi-Fi to fail. The main fragility is the HT701's RTP stack:

- The `qualify_frequency=30` keepalive (see above) reduces but may not eliminate RTP sync loss.
- If audio disappears, the first thing to try is always a HT701 power cycle.
- Asterisk itself is rock-solid — it doesn't need restarting. Avoid `core restart` unless absolutely necessary (e.g., loading a new module). Use `dialplan reload` for extensions.conf changes and `pjsip reload res_pjsip.so` for pjsip.conf changes.

### Future improvements

- **Replace the HT701.** The Grandstream HT801 or HT802 are direct replacements with actively maintained firmware and a more reliable RTP stack. This is the single biggest improvement for stability.
- **Systemd services for agents.** Currently the agents are started manually. Wrapping them in systemd user services would give auto-restart on crash, proper logging via journald, and clean startup on boot.
- **Monitoring.** A simple health check script that calls `pjsip show contacts` and verifies the HT701 is `Reachable`, then optionally alerts (LED, buzzer, or notification) when it goes `Unavailable`.
- **TLP for battery health.** Install `tlp` and configure charge thresholds to protect the battery during long-term always-on operation.

## Useful commands

```bash
sudo asterisk -rx 'pjsip show endpoints'        # check SIP registration
sudo asterisk -rx 'core show channels'           # active calls
sudo asterisk -rx 'confbridge list'              # active ConfBridges
sudo asterisk -rx 'channel request hangup all'   # hang up everything
sudo asterisk -rx 'dialplan reload'              # reload after editing extensions.conf
sudo asterisk -rvvv                              # live console (verbose)
```
