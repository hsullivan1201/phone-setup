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

All extensions use 3-digit codes. Dial **0** as a shortcut to the operator.

### Utility (1xx)

| Ext | What it does |
|-----|-------------|
| **0** | **AI operator** (shortcut to 100) |
| **100** | **AI operator** (Pipecat voice agent — see `~/operator/`) |
| 101 | Plays "hello world" |
| 102 | Echo test (speak and hear yourself back) |
| 103 | DTMF test (enter 4 digits, hear them read back) |
| 104 | Music on hold (local files) |
| 105 | "Congratulations" demo message |

### Radio (7xx)

| Ext | Station | City | Vibe |
|-----|---------|------|------|
| 700 | CISM 89.3 | Montreal | Francophone indie, electronic, experimental |
| 701 | CIUT 89.5 | Toronto | World music, jazz, spoken word, deep cuts |
| 702 | CKDU 88.1 | Halifax | East coast indie, punk, folk |
| 703 | WFMU 91.1 | Jersey City | Legendary freeform — noise, obscure vinyl, outsider music |
| 704 | New Sounds | NYC | Experimental, ambient, new classical, sound art |
| 705 | WNYC 93.9 | NYC | Public radio — news, talk, culture |
| 706 | WMBR 88.1 | Cambridge | MIT college radio — electronic, avant-garde, jazz |
| 707 | WBUR 90.9 | Boston | NPR — news, On Point, Here and Now |
| 708 | CHIRP 107.1 | Chicago | Independent — local music, indie, community |
| 709 | WBEZ 91.5 | Chicago | NPR — This American Life, storytelling |
| 710 | KEXP 90.3 | Seattle | Freeform — indie, world, hip-hop, live sessions |
| 711 | KALX 90.7 | Berkeley | College radio — punk, experimental, freeform |
| 712 | BFF.fm | San Francisco | Community — local SF music, indie pop, DJ sets |
| 713 | KQED 88.5 | San Francisco | NPR — Forum, California Report |
| 714 | KBOO 90.7 | Portland | Community — folk, world music, activism |
| 715 | XRAY.fm 91.1 | Portland | Freeform — indie, alternative |
| 716 | The Gamut | Oklahoma | Freeform — bluegrass to metal to jazz |
| 717 | WETA Classical 90.9 | Washington DC | Classical — symphonies, chamber music, opera |
| 718 | NPR | National | All Things Considered, Morning Edition |

### DTMF controls while listening to radio

| Key | Action |
|-----|--------|
| **4** | Now playing (TTS reads current track info) |
| **5** | Activate room speakers |
| **6** | Deactivate room speakers |

Ring the phone from the laptop: `ring-phone`

## Room Speakers

Radio stations use ConfBridge, which allows routing audio to the ThinkPad's speakers via a local softphone (baresip, ext 150).

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

**Listen on handset only (default):** Dial any 7xx extension.

**Add room speakers:** While listening to radio, press `5`. Asterisk calls baresip, which auto-answers and joins the same ConfBridge. Audio plays through both the handset and the laptop speakers.

**Kill speakers:** Press `6` while listening to turn off laptop audio.

**Hang up:** Hanging up the handset tears down everything — the stream stops and the speaker is kicked automatically.

### How it works

Each radio station runs through a ConfBridge instead of direct MP3Player. A Local channel injects the stream into the bridge (one leg plays MP3Player, the other sits in the ConfBridge as `radio_user`). When `5` is pressed, the ConfBridge DTMF menu triggers `dialplan_exec` which originates a call to baresip (ext 150/PJSIP). baresip auto-answers and joins the same bridge as `speaker_user`.

The handset is the `marked` user. The stream and speaker both have `end_marked=yes`, so when the handset hangs up (the last marked user leaves), the entire bridge tears down cleanly. Audio output goes to whatever PulseAudio's default sink is (headphones, speakers, etc.).

### Now Playing

Pressing `4` while listening to a station fetches the current track info (via ICY metadata or station API) and reads it aloud via TTS. Uses `/usr/local/bin/now-playing` (espeak-ng + ffmpeg for 8kHz wav generation).

Stations with dedicated APIs: KEXP, BFF.fm, WNYC. All others use ICY stream metadata.

### baresip

`baresip` runs as a systemd user service, registered as ext 150 on localhost.

```bash
systemctl --user status baresip       # check status
systemctl --user restart baresip      # restart
journalctl --user -u baresip -f       # follow logs
```

Config lives in `~/.baresip/` (accounts, config). Audio output goes through PulseAudio to whatever the default output device is.

**Troubleshooting:** If the speaker stops working (`#5` does nothing), baresip has probably lost its registration (403 Forbidden — usually caused by a network change). Fix:
```bash
sudo asterisk -rx 'pjsip reload'    # reload PJSIP first
systemctl --user restart baresip    # then restart baresip
```
Check `journalctl --user -u baresip -n 5` — you should see `200 OK`.

## AI Operator (`~/operator/`)

Dial **0** to talk to an AI telephone operator. It can answer questions, recommend radio stations based on your mood, and transfer you to any extension.

### Stack
- **STT**: Deepgram Nova-3 (streaming via WebSocket)
- **LLM**: Claude Haiku 4.5 (Anthropic API, prompt caching)
- **TTS**: Deepgram Aura 2
- **VAD**: Silero (via Pipecat)
- **Framework**: Pipecat 0.0.102 with custom AudioSocket transport

### Running
```bash
cd ~/operator
source .venv/bin/activate
export ANTHROPIC_API_KEY=...
export DEEPGRAM_API_KEY=...
python agent.py
```
The agent listens on `127.0.0.1:9092` for AudioSocket connections from Asterisk.

### How it works
Asterisk routes extension 0/100 through AudioSocket, which streams raw PCM audio over TCP to the Python agent. Pipecat manages the conversation pipeline: Silero VAD detects speech boundaries, Deepgram transcribes, Claude generates responses, and Deepgram synthesizes speech back. The agent can transfer calls by redirecting the Asterisk channel to another extension via the CLI.

### Files
| File | What |
|------|------|
| `agent.py` | Pipecat voice agent |
| `agent_raw.py` | Pre-Pipecat version (backup) |

## Helper scripts

| Script | Location | What |
|--------|----------|------|
| `ring-phone` | `/usr/local/bin/ring-phone` | Ring the Nortel |
| `now-playing` | `/usr/local/bin/now-playing` | Fetch track info + generate TTS wav |
| `stream-decode` | `/usr/local/bin/stream-decode` | Decode AAC/AAC+ streams to raw PCM for Asterisk |

## Config files
| File | Location |
|------|----------|
| `pjsip.conf` | `/etc/asterisk/pjsip.conf` |
| `extensions.conf` | `/etc/asterisk/extensions.conf` |
| `confbridge.conf` | `/etc/asterisk/confbridge.conf` |
| `musiconhold.conf` | `/etc/asterisk/musiconhold.conf` |
| `dnsmasq.conf` | `/etc/dnsmasq.conf` |
| `indications.conf` | `/etc/asterisk/indications.conf` (country=fr) |
| `ring-phone` | `/usr/local/bin/ring-phone` |
| dhcpcd static IP | `/etc/dhcpcd.conf` (bottom of file) |
| baresip config | `~/.baresip/accounts`, `~/.baresip/config` |
| baresip service | `~/.config/systemd/user/baresip.service` |

Backups of Asterisk configs are in this directory (`~/phone-setup/`).

## Adding new extensions

Edit `~/phone-setup/extensions.conf`, deploy, and reload:
```bash
sudo cp ~/phone-setup/extensions.conf /etc/asterisk/extensions.conf
sudo asterisk -rx 'dialplan reload'
```

## Adding new AI agents

AI agents connect to Asterisk via AudioSocket — a bidirectional raw PCM stream over TCP. This is how the operator (`~/operator/`) works, and the same pattern can be used for any voice AI agent.

### Architecture

```
Phone --> Asterisk --> AudioSocket (TCP) --> Your Agent
                   <-- AudioSocket (TCP) <--
```

AudioSocket sends/receives signed linear 16-bit, 8kHz mono PCM. Each TCP message has a 3-byte header: 1 byte type + 2 bytes length (big-endian). Types: `0x00` = hangup, `0x01` = UUID, `0x10` = audio, `0x11` = error.

### Steps

1. **Write the agent.** Listen on a TCP port for AudioSocket connections. On connect, read the UUID message first, then exchange audio frames. See `~/operator/agent.py` for a full Pipecat-based example, or `~/operator/agent_raw.py` for a minimal version without a framework.

2. **Pick an extension.** Choose an unused 3-digit code (1xx for utility, or a new range).

3. **Add a dialplan entry** in `~/phone-setup/extensions.conf`:
   ```
   exten => 106,1,Answer()
    same => n,Wait(1)
    same => n,AudioSocket(00000000-0000-0000-0000-000000000000,127.0.0.1:PORT)
    same => n,Hangup()
   ```
   The UUID can be any valid UUID (or all zeros). `PORT` is whatever your agent listens on.

4. **Deploy and reload:**
   ```bash
   sudo cp ~/phone-setup/extensions.conf /etc/asterisk/extensions.conf
   sudo asterisk -rx 'dialplan reload'
   ```

5. **Update the operator** if you want the AI operator to know about the new agent. Edit `SYSTEM_PROMPT` and `valid` extensions in `~/operator/agent.py`, then restart the operator.

### Tips

- Audio is raw PCM — no codec negotiation needed. Your agent receives and sends 8kHz 16-bit mono samples directly.
- The `Wait(1)` before `AudioSocket()` gives the channel a moment to fully set up. Without it, the first audio frame can be garbled.
- For call transfer from inside an agent, use `sudo asterisk -rx 'channel redirect CHANNEL internal,EXT,1'`. See `do_transfer()` in `~/operator/agent.py`.
- Multiple agents can run on different ports simultaneously. Each gets its own extension.
- If using Pipecat, the custom `AudioSocketTransport` class in `~/operator/agent.py` handles all the protocol details — copy it into your new agent.

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
- Dial Plan: `{0|xxx|*x+}` — `0` dials immediately, 3-digit extensions dial on last digit, `*` sequences for ConfBridge DTMF

The HT701 CGI API for pushing config programmatically is unreliable for some fields — use the web UI for changes.

If you add extensions outside the `0`/`xxx`/`*x+` patterns, update the HT701 dial plan to match.

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
