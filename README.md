# Phone Setup

Asterisk configuration for a private PBX built around a vintage Nortel analog phone. The phone acts as a terminal into the local network; it can make calls, stream internet radio, control Spotify, talk to AI agents, and interface with other devices on the LAN. Source of truth for all Asterisk config, edit here, deploy to `/etc/asterisk/`.

The AI voice agents (operator, chef, librarian, DJ Cool, etc.) live in a separate repo: [hsullivan1201/operator](https://github.com/hsullivan1201/operator). This repo handles the Asterisk side (dialplan, SIP, radio streams, Spotify integration) and that one handles the voice agent side (Pipecat pipelines, LLM prompts, tools).

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

Each routes through AudioSocket to a standalone Python agent in `~/operator/agents/`.
The 2xx agents are now launched on demand by `agent-ondemand` and stopped when
the call ends, so they do not stay resident when idle.

Daily Briefing (204) supports an optional preference file at
`~/.config/infoline/briefing-profile.txt` (read by the `hazel` user). Keep it
short and specific, for example: topics to prioritize, topics to avoid, and
desired tone/length.

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

**baresip** is a headless SIP softphone running as a systemd user service on the ThinkPad. It's used to connect to the phone via confBridge

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
sudo cp now-playing radio-speaker stream-decode ring-phone alarm morning-briefing agent-ondemand nowplaying-server /usr/local/bin/
sudo chmod +x /usr/local/bin/{now-playing,radio-speaker,stream-decode,ring-phone,alarm,morning-briefing,agent-ondemand,nowplaying-server}
sudo systemctl restart nowplaying-server
```

## Helper scripts

| Script | Deployed to | What |
|--------|-------------|------|
| `now-playing` | `/usr/local/bin/now-playing` | Fetch track info (ICY metadata + KEXP/BFF/WNYC/CKDU APIs), generate TTS wav via Deepgram Aura 2 (falls back to espeak-ng). Also announces on laptop speakers when direct stream is active. |
| `nowplaying-server` | `/usr/local/bin/nowplaying-server` | HTTP server (port 8765) polled by the InfoLine panel. Exposes `/spotify` (track + artist), `/radio/<bridge>` (track), and `/status` (current call/radio state via Asterisk CLI). Runs as `hazel` via systemd (`nowplaying-server.service`). |
| `radio-speaker` | `/usr/local/bin/radio-speaker` | Direct webstream playback on laptop speakers via ffplay (`start <station>` / `stop`). Cleanup uses `pkill -x ffplay` (not PID file). |
| `spotify-connect` | `/usr/local/bin/spotify-connect` | Librespot lifecycle + Spotify Web API control (start, stop, play, pause, next, prev, now-playing). Used by 730/8xx dialplan and DJ Cool agent. |
| `agent-ondemand` | `/usr/local/bin/agent-ondemand` | Starts/stops specialist AI agents (200-205) on demand so those Python processes are only up during active calls. |
| `stream-decode` | `/usr/local/bin/stream-decode` | ffmpeg wrapper: any audio stream -> 8kHz slin16 for Asterisk |
| `ring-phone` | `/usr/local/bin/ring-phone` | Ring the Nortel |
| `alarm` | `/usr/local/bin/alarm` | Ring phone + play alarm clip |
| `morning-briefing` | `/usr/local/bin/morning-briefing` | Ring phone and connect straight to extension 204 (Daily Briefing) for scheduled wake-up briefings. |
| `panel6.py` | `~/panel6.py` on infoline.local | InfoLine panel script (Raspberry Pi). Connects to AMI for live call events, polls `nowplaying-server` for track info. Runs as a systemd service (`panel6.service`) on the Pi. |

Dialplan startup uses `sudo -u hazel` for `agent-ondemand` and `spotify-connect`.
If those commands prompt for a password, add matching `NOPASSWD` entries for the
`asterisk` user in sudoers.

Example user timer for weekday morning briefing:

```ini
# ~/.config/systemd/user/morning-briefing.service
[Unit]
Description=Morning phone briefing

[Service]
Type=oneshot
ExecStart=/usr/local/bin/morning-briefing
```

```ini
# ~/.config/systemd/user/morning-briefing.timer
[Unit]
Description=Weekday morning briefing at 8:00 AM

[Timer]
OnCalendar=Mon..Fri 08:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now morning-briefing.timer
```

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

**Spotify device missing (`DJ Cool` says "device not found")**: Run this one-liner to hard-reset librespot and re-register the `Telephone` device:

```bash
sudo -u hazel bash -lc 'XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus /usr/local/bin/spotify-connect stop >/dev/null 2>&1 || true; pkill -x librespot >/dev/null 2>&1 || true; sleep 1; XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus /usr/local/bin/spotify-connect start'
```

After that, call `205` again (or dial `730`/`8xx`) and playback should recover.

## Operations

### Laptop as a server

The ThinkPad runs Asterisk, dnsmasq, baresip, and Python voice agents. The
operator is always on; the 2xx specialist agents are started on demand and
stopped after each call. It is a server and must stay powered on with the
network interface active at all times.

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
| Operator process (always on) | ~80-100 MB RSS |
| Specialist 2xx agent process | ~80-100 MB RSS each, only while active |
| **Typical idle total** | **~130-170 MB RSS** |

During a call, a single agent spikes briefly for Silero VAD inference (~5ms per 30ms audio chunk on CPU) and for network I/O to Deepgram and Anthropic APIs. CPU usage during a call is under 10% of one core. Multiple simultaneous calls are possible but unlikely on a single handset.

The Silero VAD model (~2 MB) is loaded per-call and unloaded when the call ends. There's no GPU usage — everything runs on CPU.

### Further memory options

On-demand 2xx launch is now active. If you want to reduce footprint further:

- **Single multiplexed process.** Run one Python process that handles all 2xx extensions, selecting prompt/voice by extension. This shares runtime and VAD model across agents, further reducing memory. Tradeoff: bigger code refactor and less fault isolation.
- **Swap.** If memory pressure becomes an issue, ensure swap is configured. Rarely used pages will move out naturally.

### Network resilience

The ThinkPad-to-HT701 link is a direct Ethernet cable (`192.168.10.0/24`), so there's no router, switch, or Wi-Fi to fail. The main fragility is the HT701's RTP stack:

- The `qualify_frequency=30` keepalive (see above) reduces but may not eliminate RTP sync loss.
- If audio disappears, the first thing to try is always a HT701 power cycle.
- Asterisk itself is rock-solid — it doesn't need restarting. Avoid `core restart` unless absolutely necessary (e.g., loading a new module). Use `dialplan reload` for extensions.conf changes and `pjsip reload res_pjsip.so` for pjsip.conf changes.

### Call logging

All AI agents (operator + all 2xx agents) write a per-call log to `~/logs/calls/`. Each log file is named `{agent}-{date}-{time}-{uuid8}.log` and contains three sections:

**Events** — written in real time during the call:
```
[15:01:02] [USER] Hi. Can you tell me about extension seven thirty?
[15:02:23] [TOOL] transfer_call({"extension": "730"})
[15:02:23] [TOOL→] Transferring to extension 730.
```

**Transcript** — assembled in real time from frame processors (`TranscriptionFrame`,
LLM/TTS output, and tool callbacks). This stays complete even when prompt
history is trimmed for token control.

**Summary** — end time, duration, turn count.

The logging module is `~/operator/call_log.py`. It exposes:

- `CallLog(agent_name, call_uuid)` — creates the log file and writes events via `log_greeting()`, `log_assistant()`, `log_user()`, `log_tool_call()`, and `finalize()`.
- `make_transcript_logger(call_log)` — logs finalized user speech from `TranscriptionFrame`.
- `make_assistant_logger(call_log)` — logs assistant responses from LLM/TTS frames in real time.
- `make_context_window_guard(context, max_messages=12)` — bounds prompt history while preserving the system message.

`finalize()` is called from a `try/finally` block around `runner.run(task)`, so it always runs when the pipeline exits.

`finalize()` still accepts `context.messages` for best-effort backfill, but
normal operation no longer depends on context-role reconstruction behavior.

### Future improvements

- **Replace the HT701.** The Grandstream HT801 or HT802 are direct replacements with actively maintained firmware and a more reliable RTP stack. This is the single biggest improvement for stability.
- **Systemd hardening for agent lifecycle.** Keep operator as a persistent user service and use socket/template services for 2xx agents to avoid any shell/sudo dependency in dialplan startup.
- **Monitoring.** A simple health check script that calls `pjsip show contacts` and verifies the HT701 is `Reachable`, then optionally alerts (LED, buzzer, or notification) when it goes `Unavailable`.
- **TLP for battery health.** Install `tlp` and configure charge thresholds to protect the battery during long-term always-on operation.

## InfoLine panel (infoline.local / Raspberry Pi)

A Raspberry Pi connected to a 4-line I²C LCD, a rotary encoder, and several GPIO switches. It connects to the ThinkPad over the LAN and shows call/radio/Spotify status in real time.

- **Script:** `~/panel6.py` on the Pi
- **Communication:** AMI (Asterisk Manager Interface) on port 5038 — same connection the ThinkPad uses for dialplan events
- **Now-playing:** polls `nowplaying-server` (see below) on lines 3-4 of the LCD

**Display logic:**
- Idle: clock + "C&P TELEPHONE / INFOLINE"
- Regular call (1xx, 2xx non-Spotify): "EXT xxx / CALL IN PROGRESS"
- Spotify call (205, 730–811): "EXT xxx / SPOTIFY" + now-playing on lines 3-4 (polled every 15s, blank if nothing playing)
- Radio (700–718): "RADIO / Station Name" + now-playing on lines 3-4 (polled every 45s, blank if no metadata)
- ConfBridge leave or hangup: returns to idle

To update the panel script after edits, scp it to the Pi and restart `panel6.py` there.

### nowplaying-server (ThinkPad, always running)

`/usr/local/bin/nowplaying-server` is a tiny HTTP server on **port 8765** that the Pi panel polls for track info. It wraps `spotify-connect now-playing` and the `now-playing` script, with a short cache (15s Spotify, 60s radio) to avoid hammering the APIs.

| Endpoint | Returns |
|----------|---------|
| `GET /spotify` | `{"track": "Song, by Artist"}` or `{"track": null}` |
| `GET /radio/<bridge-id>` | `{"track": "Song, by Artist"}` or `{"track": null}` |

Managed by systemd: `sudo systemctl status nowplaying-server`

**Resource footprint:** ~10 MB RSS at idle. Subprocess calls to `spotify-connect` and `now-playing` are cached, so real work only happens every 15–60s during active sessions — not on every request.

```bash
sudo systemctl status nowplaying-server   # check
sudo systemctl restart nowplaying-server  # restart after script changes
```

## Useful commands

```bash
sudo asterisk -rx 'pjsip show endpoints'        # check SIP registration
sudo asterisk -rx 'core show channels'           # active calls
sudo asterisk -rx 'confbridge list'              # active ConfBridges
sudo asterisk -rx 'channel request hangup all'   # hang up everything
sudo asterisk -rx 'dialplan reload'              # reload after editing extensions.conf
sudo asterisk -rvvv                              # live console (verbose)
```
