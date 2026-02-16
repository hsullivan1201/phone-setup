# Phone Setup - Nortel via Grandstream HT701 + Asterisk

## Hardware
- ThinkPad (Arch Linux) running Asterisk 23.2.2
- Grandstream HT701 ATA plugged into ThinkPad ethernet (enp0s31f6)
- Nortel analog phone plugged into HT701 FXS port

## Network
- ThinkPad ethernet: `192.168.10.1/24` (static, configured in `/etc/dhcpcd.conf`)
- HT701 gets IP via DHCP from dnsmasq (currently `192.168.10.126`)
- HT701 web UI: http://192.168.10.126 (password: `admin`)

## Services
`asterisk` and `dnsmasq` are system services (enabled at boot via systemd). `baresip` is a user service (enabled via `systemctl --user`). The static IP on `enp0s31f6` persists via dhcpcd.conf. The HT701 retains its config in flash.

After a reboot, everything should come up automatically. To verify:
```bash
sudo asterisk -rx 'pjsip show endpoints'   # should show 100 and 150 as "Not in use"
systemctl --user status baresip             # should show active (running)
```

## Extensions

| Dial | What it does |
|------|-------------|
| **0** | **AI operator** (Pipecat voice agent — see below) |
| 1 | Plays "hello world" (French) |
| 2 | Echo test (speak and hear yourself back) |
| 3 | DTMF test (enter 4 digits, hear them read back) |
| 4 | Music on hold (local files) |
| 5 | "Congratulations" demo message |
| 6 | CISM 89.3 Montreal (internet radio via ConfBridge) |
| 7 | KEXP Seattle (internet radio via ConfBridge) |
| 8 | The Gamut (internet radio via ConfBridge) |
| **\*5** | **Activate room speakers** (while listening to radio) |
| **\*6** | **Deactivate room speakers** |

Ring the phone from the laptop: `ring-phone`

## Room Speakers

Radio stations (6/7/8) now use ConfBridge, which allows routing audio to the ThinkPad's speakers via a local softphone (baresip, ext 150).

```
                    +-------------------------------------+
                    |          ThinkPad (same box)         |
                    |                                     |
JAZZ --- HT701 --> |  Asterisk PBX <--SIP--> baresip     | --> Speakers
  (analog)  (SIP)  |   (ext 100)              (ext 150)  |     (built-in)
                    |                                     |
                    +-------------------------------------+
```

### Usage

**Listen on handset only (default):** Dial 6/7/8 as usual.

**Add room speakers:** While listening to radio, press `*5`. Asterisk calls baresip, which auto-answers and joins the same ConfBridge. Audio plays through both the handset and the laptop speakers.

**Speakers only:** Press `*5`, then hang up the handset. Radio continues through speakers.

**Kill speakers:** Pick up the handset, dial `*6` (or restart baresip).

### How it works

Each radio station runs through a ConfBridge instead of direct MP3Player. A Local channel injects the stream into the bridge. When `*5` is pressed, Asterisk originates a call to baresip (ext 150), which auto-answers and joins the same bridge. The speaker has `wait_marked=yes`, so it only plays audio when the stream (the marked user) is present.

### baresip

`baresip` runs as a systemd user service, registered as ext 150 on localhost.

```bash
systemctl --user status baresip       # check status
systemctl --user restart baresip      # restart
journalctl --user -u baresip -f       # follow logs
```

Config lives in `~/.baresip/` (accounts, config). Audio output goes through PulseAudio to whatever the default output device is.

## Adding new extensions

Edit `/etc/asterisk/extensions.conf` and reload:
```bash
sudo asterisk -rx 'dialplan reload'
```

Extensions live in the `[internal]` context. Basic patterns:

**Play a sound file:**
```
exten => 9,1,Answer()
 same => n,Playback(some-sound-file)
 same => n,Hangup()
```

**Stream internet radio (needs mpg123):**
```
exten => 10,1,Answer()
 same => n,Set(VOLUME(TX)=6)
 same => n,MP3Player(http://some-stream-url/stream.mp3)
 same => n,Hangup()
```
`VOLUME(TX)` is gain in dB. Streams vary in loudness — 3-6 is a good starting range.

**Stream audio to an external program via AudioSocket:**
```
exten => 0,1,Answer()
 same => n,Wait(1)
 same => n,AudioSocket(00000000-0000-0000-0000-000000000000,127.0.0.1:9092)
 same => n,Hangup()
```
AudioSocket streams bidirectional raw audio (signed linear 16-bit, 8kHz mono) over TCP. This is how the AI operator works — see `~/operator/`.

**Ring the phone and do something when answered:**

Add an extension in the `[incoming]` context:
```
exten => my-thing,1,Answer()
 same => n,Playback(hello-world)
 same => n,Hangup()
```
Then trigger it: `sudo asterisk -rx 'channel originate PJSIP/100 extension my-thing@incoming'`

## AI Operator (`~/operator/`)

Dial **0** to talk to an AI telephone operator. It can answer questions and transfer you to any extension.

### Stack
- **STT**: Deepgram Nova-2 (streaming via WebSocket)
- **LLM**: Claude Haiku 4.5 (Anthropic API)
- **TTS**: Kokoro 82M via DeepInfra, espeak-ng fallback
- **VAD**: Silero (via Pipecat)
- **Framework**: Pipecat 0.0.102 with custom AudioSocket transport

### Running
```bash
cd ~/operator
source .venv/bin/activate
export ANTHROPIC_API_KEY=...
export DEEPGRAM_API_KEY=...
export DEEPINFRA_API_KEY=...   # optional, for Kokoro TTS
python agent.py
```
The agent listens on `127.0.0.1:9092` for AudioSocket connections from Asterisk.

### How it works
Asterisk routes extension 0 through AudioSocket, which streams raw PCM audio over TCP to the Python agent. Pipecat manages the conversation pipeline: Silero VAD detects speech boundaries, Deepgram transcribes, Claude generates responses, and Kokoro synthesizes speech back. The agent can transfer calls by redirecting the Asterisk channel to another extension via the CLI.

### Files
| File | What |
|------|------|
| `agent.py` | Pipecat voice agent (current) |
| `agent_raw.py` | Pre-Pipecat version (backup, also works) |
| `voices/` | Piper TTS voice model (unused, was a fallback) |

## Config files
| File | Location |
|------|----------|
| `pjsip.conf` | `/etc/asterisk/pjsip.conf` |
| `extensions.conf` | `/etc/asterisk/extensions.conf` |
| `confbridge.conf` | `/etc/asterisk/confbridge.conf` |
| `dnsmasq.conf` | `/etc/dnsmasq.conf` |
| `indications.conf` | `/etc/asterisk/indications.conf` (country=fr) |
| `ring-phone` | `/usr/local/bin/ring-phone` |
| dhcpcd static IP | `/etc/dhcpcd.conf` (bottom of file) |
| baresip config | `~/.baresip/accounts`, `~/.baresip/config` |
| baresip service | `~/.config/systemd/user/baresip.service` |

Backups of Asterisk configs are in this directory (`~/phone-setup/`).

## HT701 Config (set via web UI)
- Primary SIP Server: `192.168.10.1`
- SIP User ID / Authenticate ID: `100`
- Authenticate Password: `changeme`
- Outbound Proxy: (empty)
- Failover SIP Server: (empty)
- Backup Outbound Proxy: (empty)
- NAT Traversal: Keep-Alive
- DTMF: RFC2833
- Call Progress Tones: French (440Hz patterns)

The HT701 CGI API for pushing config programmatically is unreliable for some fields — use the web UI for changes.

## French sounds
Installed from downloads.asterisk.org:
- `asterisk-core-sounds-fr-gsm-current.tar.gz`
- `asterisk-extra-sounds-fr-gsm-current.tar.gz`

Installed to `/var/lib/asterisk/sounds/fr/`. The endpoint has `language=fr` and `tone_zone=fr` set in `pjsip.conf`.

## Useful commands
```bash
ring-phone                                          # ring the Nortel
sudo asterisk -rx 'pjsip show endpoints'            # check registration
sudo asterisk -rx 'core show channels'              # see active calls
sudo asterisk -rx 'confbridge list'                 # see active ConfBridges
sudo asterisk -rx 'channel request hangup all'      # hang up all calls
sudo asterisk -rx 'dialplan reload'                 # reload extensions.conf
sudo asterisk -rx 'core reload'                     # reload everything
sudo asterisk -rvvv                                 # live Asterisk console (verbose)
systemctl --user restart baresip                    # restart speaker softphone
```

## Laptop notes
- Closing the lid **will suspend** the laptop (default behavior). Keep it open while using the phone.
- WiFi (`wlan0`) is managed by iwd, ethernet (`enp0s31f6`) is the phone link — they're independent.
