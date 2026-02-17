# Spotify Integration — Phase 1: Playback & Control

Dial 730 to start Spotify on the laptop speakers. Dial 8xx for specific playlists. DTMF tones for skip, back, now-playing. Control also available from the Spotify app. Hang up to stop.

## Overview

```
730         → Start Spotify (speakers on, nothing playing yet — use the app or dial 8xx)
8xx         → Start a specific playlist on the speakers
DTMF 1     → Previous track
DTMF 3     → Next track
DTMF 4     → Now playing (TTS announcement of track + artist)
DTMF 2     → Pause / resume
DTMF 6     → Stop speakers
Hang up    → Kill librespot, speakers stop
```

The phone is a remote control. All audio plays through the laptop speakers at full quality (320kbps). No phone audio, no ConfBridge.

## Components

### 1. Spotify Web API setup (one-time)

Required for playlist control, skip/back, and now-playing. Librespot is a dumb receiver — the Web API is how you command it.

**Register an app:**
1. Go to https://developer.spotify.com/dashboard
2. Create an app (any name, e.g. "Telephone")
3. Set redirect URI to `http://localhost:8888/callback`
4. Note the Client ID and Client Secret

**Get a refresh token (one-time OAuth flow):**

Write a small script or use an existing tool to do the authorization code flow:

1. Open in browser: `https://accounts.spotify.com/authorize?client_id=CLIENT_ID&response_type=code&redirect_uri=http://localhost:8888/callback&scope=user-modify-playback-state%20user-read-playback-state%20user-read-currently-playing`
2. Authorize → redirects to localhost with a `code` param
3. Exchange the code for tokens:
   ```bash
   curl -X POST https://accounts.spotify.com/api/token \
     -d grant_type=authorization_code \
     -d code=CODE_FROM_REDIRECT \
     -d redirect_uri=http://localhost:8888/callback \
     -u CLIENT_ID:CLIENT_SECRET
   ```
4. Save the `refresh_token` — it doesn't expire unless revoked.

**Store credentials** in `/home/hazel/.config/spotify-telephone/config`:

```bash
SPOTIFY_CLIENT_ID=xxx
SPOTIFY_CLIENT_SECRET=xxx
SPOTIFY_REFRESH_TOKEN=xxx
SPOTIFY_DEVICE_NAME=Telephone
```

### 2. `spotify-connect` script

Deployed to `/usr/local/bin/spotify-connect`.

```
spotify-connect start               → launch librespot, write PID
spotify-connect stop                → kill librespot, clean up
spotify-connect play [playlist_uri] → start playback (optionally of a specific playlist)
spotify-connect pause               → pause/resume toggle
spotify-connect next                → skip to next track
spotify-connect prev                → previous track
spotify-connect now-playing          → output "Artist - Track" to stdout
```

**Librespot management (start/stop):**

```bash
# start
sudo -u hazel XDG_RUNTIME_DIR=/run/user/1000 \
  librespot -n "Telephone" -b 320 \
  --backend pulseaudio \
  -c /home/hazel/.cache/librespot &
echo $! > /tmp/spotify-connect.pid

# stop
kill $(cat /tmp/spotify-connect.pid 2>/dev/null) 2>/dev/null
rm -f /tmp/spotify-connect.pid
```

**API helpers (play/pause/next/prev/now-playing):**

All Web API calls need a fresh access token. The script should:
1. Read config from `/home/hazel/.config/spotify-telephone/config`
2. Use the refresh token to get an access token (they last 1 hour, cache it):
   ```bash
   curl -s -X POST https://accounts.spotify.com/api/token \
     -d grant_type=refresh_token \
     -d refresh_token=$SPOTIFY_REFRESH_TOKEN \
     -u $SPOTIFY_CLIENT_ID:$SPOTIFY_CLIENT_SECRET
   ```
3. Find the device ID by name from `GET /v1/me/player/devices`
4. Execute the command

**API calls:**

```bash
# Play a playlist on the Telephone device
curl -X PUT "https://api.spotify.com/v1/me/player/play?device_id=$DEVICE_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"context_uri":"spotify:playlist:PLAYLIST_ID"}'

# Resume / Pause
curl -X PUT "https://api.spotify.com/v1/me/player/play?device_id=$DEVICE_ID" \
  -H "Authorization: Bearer $TOKEN"
curl -X PUT "https://api.spotify.com/v1/me/player/pause?device_id=$DEVICE_ID" \
  -H "Authorization: Bearer $TOKEN"

# Next / Previous
curl -X POST "https://api.spotify.com/v1/me/player/next?device_id=$DEVICE_ID" \
  -H "Authorization: Bearer $TOKEN"
curl -X POST "https://api.spotify.com/v1/me/player/previous?device_id=$DEVICE_ID" \
  -H "Authorization: Bearer $TOKEN"

# Now playing
curl -s "https://api.spotify.com/v1/me/player/currently-playing" \
  -H "Authorization: Bearer $TOKEN"
# → parse .item.name and .item.artists[0].name from JSON response
```

**Token caching:** Access tokens last 1 hour. The script should cache the token and its expiry in `/tmp/spotify-token.json` and only refresh when expired. Avoids hitting the token endpoint on every DTMF press.

### 3. Playlist config

`/home/hazel/.config/spotify-telephone/playlists.conf` — maps 8xx extensions to Spotify URIs:

```bash
# extension=uri=label
800=spotify:playlist:37i9dQZF1DXcBWIGoYBM5M=Today's Top Hits
801=spotify:playlist:37i9dQZF1DX0XUsuxWHRQd=RapCaviar
802=spotify:playlist:37i9dQZF1DX4sWSpwq3LiO=Peaceful Piano
803=spotify:playlist:5bBSYFlBPCmHaFLPRfPJFA=Jazz
# ... etc
```

Also works with album URIs (`spotify:album:xxx`) or artist URIs (`spotify:artist:xxx`).

The `spotify-connect play` command reads this file when called with an extension number: `spotify-connect play 802` → looks up 802 → plays Peaceful Piano.

### 4. Now-playing TTS

When DTMF 4 is pressed:

1. `spotify-connect now-playing` fetches track + artist from the API
2. Pipe through existing TTS mechanism (same as radio `now-playing` script — espeak-ng, Deepgram, whatever it currently uses) to generate a wav
3. Asterisk plays it to the handset

Could reuse or adapt `/usr/local/bin/now-playing`, or build TTS generation into `spotify-connect now-playing-tts` as a convenience command that outputs a wav path.

### 5. Sudoers rule

`/etc/sudoers.d/spotify-connect`:

```
asterisk ALL=(hazel) SETENV: NOPASSWD: /usr/bin/librespot
```

The API calls don't need sudoers — they're just HTTP requests from the `asterisk` user. Only librespot needs to run as `hazel` for PulseAudio access.

### 6. Dialplan (`extensions.conf`)

**730 — Generic Spotify start (no playlist, use the app to pick):**

```ini
exten => 730,1,Answer()
same => n,System(/usr/local/bin/spotify-connect start)
same => n,Playback(beep)
same => n,Goto(spotify-listen,s,1)
```

**8xx — Playlist extensions:**

```ini
exten => _8XX,1,Answer()
same => n,System(/usr/local/bin/spotify-connect start)
same => n,Wait(2)                                      ; let librespot register
same => n,System(/usr/local/bin/spotify-connect play ${EXTEN})
same => n,Goto(spotify-listen,s,1)
```

**DTMF listening loop:**

```ini
[spotify-listen]
exten => s,1(loop),WaitExten(300)       ; sit here, wait for DTMF
same => n,Goto(loop)

exten => 1,1,System(/usr/local/bin/spotify-connect prev)
same => n,Playback(beep)
same => n,Goto(s,loop)

exten => 2,1,System(/usr/local/bin/spotify-connect pause)
same => n,Playback(beep)
same => n,Goto(s,loop)

exten => 3,1,System(/usr/local/bin/spotify-connect next)
same => n,Playback(beep)
same => n,Goto(s,loop)

exten => 4,1,System(/usr/local/bin/spotify-connect now-playing-tts)
same => n,Playback(/tmp/spotify-now-playing)
same => n,Goto(s,loop)

exten => 6,1,System(/usr/local/bin/spotify-connect stop)
same => n,Playback(beep)
same => n,Hangup()

exten => h,1,System(/usr/local/bin/spotify-connect stop)
```

**Note:** The `h` (hangup) extension ensures cleanup even if the caller just hangs up without pressing 6.

**Note on 730 vs 8xx:** Dialing 730 starts librespot but doesn't play anything — you pick from the Spotify app. Dialing 8xx starts librespot AND starts a playlist. Both land in the same DTMF listening loop. If you're already on 730 and want a playlist, pick it from the app (the device is already active) or hang up and dial the 8xx.

### 7. Operator integration

Update the operator's system prompt:

```
730 — Spotify. Starts Spotify on the room speakers. Control from the Spotify app.
8xx — Spotify playlists:
  800: Today's Top Hits
  801: RapCaviar
  802: Peaceful Piano
  803: Jazz
  [etc — match your playlists.conf]
While listening: 1 = previous, 2 = pause, 3 = next, 4 = now playing, 6 = stop.
```

## Install

```bash
# Arch Linux — librespot from AUR
yay -S librespot

# Or via cargo
cargo install librespot

# jq for JSON parsing in the script
sudo pacman -S jq

# Create config dirs
mkdir -p /home/hazel/.config/spotify-telephone
mkdir -p /home/hazel/.cache/librespot
```

## First-time setup

1. Install librespot, test manually: `librespot -n "Telephone" -b 320 --backend pulseaudio`
2. Open Spotify app → connect to "Telephone" → play something → confirm laptop audio
3. Register Spotify developer app at developer.spotify.com
4. Run OAuth flow, save refresh token to config
5. Test API calls: `spotify-connect next` should skip the track
6. Populate playlists.conf with your playlists
7. Deploy dialplan, sudoers rule, script
8. Test: dial 730, dial 802, press 3 to skip, press 4 for now-playing

## What you get

- 730 → Spotify on laptop speakers, browse and play from the app
- 8xx → Jump straight to a playlist from the phone
- DTMF 1/2/3/4/6 → prev / pause / next / now-playing / stop
- Hang up → auto-cleanup
- Full quality audio (320kbps OGG → PulseAudio → laptop speakers)
- ~20MB memory for librespot while active, 0 when idle
- Requires Spotify Premium
