# Phone Setup

Asterisk configuration for a voice AI phone system. Source of truth for all Asterisk config -- edit here, deploy to `/etc/asterisk/`.

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
| 716 | The Gamut | Oklahoma |
| 717 | WETA Classical 90.9 | Washington DC |
| 718 | NPR | National |

DTMF while listening: **4** = now playing, **5** = speakers on, **6** = speakers off.

## Config files

| File | Purpose |
|------|---------|
| `extensions.conf` | Dialplan -- all extensions, stream injection, now-playing, speaker control |
| `pjsip.conf` | SIP endpoints: 100 (HT701 phone), 150 (baresip speaker) |
| `confbridge.conf` | ConfBridge profiles for radio + DTMF menu |
| `musiconhold.conf` | AAC stream decoding for CIUT and WETA (via ffmpeg) |
| `dnsmasq.conf` | DHCP/DNS for the HT701 |

### How radio works

Each station uses a ConfBridge so the handset and room speakers can share one stream. When you dial a 7xx extension:

1. Asterisk originates a Local channel into `[stream-inject]`, which plays the station's stream (MP3Player for MP3, MusicOnHold+ffmpeg for AAC).
2. That Local channel joins the ConfBridge as `radio_user`.
3. The handset joins the same bridge as `handset_user` (marked -- bridge tears down when you hang up).
4. Pressing 5 originates a call to baresip (ext 150), which joins as `speaker_user`.

### Room speakers

baresip runs as a systemd user service on the ThinkPad, registered as SIP endpoint 150. It auto-answers and routes audio to PulseAudio's default output.

```bash
systemctl --user status baresip
systemctl --user restart baresip
```

## Deploy

```bash
sudo cp extensions.conf pjsip.conf confbridge.conf musiconhold.conf /etc/asterisk/
sudo asterisk -rx "dialplan reload"
```

For pjsip.conf changes: `sudo asterisk -rx "pjsip reload res_pjsip.so"`

## Helper scripts

| Script | Deployed to | What |
|--------|-------------|------|
| `now-playing` | `/usr/local/bin/now-playing` | Fetch track info (ICY metadata + KEXP/BFF/WNYC APIs), generate TTS wav |
| `stream-decode` | `/usr/local/bin/stream-decode` | ffmpeg wrapper: any audio stream -> 8kHz slin16 for Asterisk |
| `ring-phone` | `/usr/local/bin/ring-phone` | Ring the Nortel |
| `alarm` | `/usr/local/bin/alarm` | Ring phone + play alarm clip |

## HT701 config (via web UI)

- SIP server: `192.168.10.1`, user/auth ID: `100`, password: `changeme`
- DTMF: RFC2833
- Dial plan: `{0|xxx|*x+}` -- 0 dials instantly, 3-digit codes dial on last digit, `*` prefixes for ConfBridge DTMF
- Call progress tones: French (440Hz)
- Config changes sometimes need a power cycle, not just Apply

## Troubleshooting

**Silence on all or some extensions after restart/sleep**: The HT701 loses RTP sync when Asterisk restarts or the ThinkPad sleeps. SIP signaling still works (calls connect, Asterisk sees them) but audio is silently dropped. Can affect native Asterisk audio, AudioSocket agents, or both. Fix: power cycle the HT701 (unplug power, wait 5s, plug back in). Web UI reboot is not sufficient.

**Laptop suspend disabled**: The ThinkPad must stay awake for Asterisk and the agents. Suspend/hibernate is masked and lid close is set to ignore (screen blanks but system stays up).

```bash
# What was changed
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
# /etc/systemd/logind.conf: HandleLidSwitch=ignore, HandleLidSwitchExternalPower=ignore

# To re-enable suspend later
sudo systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target
# Then revert logind.conf lines back to #HandleLidSwitch=suspend etc. and run:
# sudo systemctl restart systemd-logind
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
