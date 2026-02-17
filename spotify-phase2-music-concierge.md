# Spotify Integration — Phase 2: Music Concierge (LLM Operator)

A voice agent for music. Dial an extension, say what you're in the mood for, and it picks something and plays it. Same stack as the other agents (AudioSocket + Claude + Deepgram), but with Spotify API tools.

**Status: pin in it. Build after Phase 1 is solid and the playlist library is populated.**

## Concept

```
Dial 205 → "What do you want to listen to?"
"Something mellow, maybe jazz"
→ Agent searches/browses Spotify, picks a playlist or album, starts playback
→ "Playing Kind of Blue by Miles Davis. Enjoy."
```

The agent is another 2xx AI agent (e.g., 205 — Music Concierge) running the same Pipecat/AudioSocket stack as the others. It has tool access to the Spotify Web API, so it can search, browse, and control playback.

## Why this might not be overkill

The operator already recommends radio stations by mood ("I want something chill" → "Try KEXP or Peaceful Piano"). A dedicated music agent extends that to Spotify's full catalog. The LLM handles the fuzzy matching ("something like Radiohead but more electronic" → searches, finds a playlist or artist, starts it). This is genuinely hard to do with DTMF menus and genuinely easy for an LLM with tool access.

## Tools the agent would have

| Tool | What it does |
|------|-------------|
| `search_spotify` | Search tracks, albums, artists, playlists via `GET /v1/search` |
| `play_context` | Play an album/playlist/artist on the Telephone device via `PUT /v1/me/player/play` |
| `play_track` | Play a specific track |
| `get_recommendations` | Get recommendations based on seed artists/tracks/genres via `GET /v1/recommendations` |
| `now_playing` | Get current track info |
| `next_track` / `prev_track` | Skip controls |
| `pause` / `resume` | Playback control |

These are thin wrappers around the same `spotify-connect` script from Phase 1, or direct API calls from Python using the cached token.

## Architecture

Same as other agents — standalone AudioSocket server on its own port (e.g., 9205). Asterisk routes extension 205 to it. The agent runs the standard Pipecat pipeline (STT → LLM → TTS) with additional Spotify tools registered.

**Librespot lifecycle:** The agent starts librespot on call start (if not already running) and stops it on call end (or leaves it running if the caller just says "thanks, bye" — they might want music to keep playing after hanging up). This is a UX decision: does hanging up stop the music or leave it playing?

Probably: leave it playing. The caller can explicitly say "stop the music" or dial 730 and press 6 to kill it. This matches how you'd interact with a human — "put on some jazz" doesn't mean "and stop it when I walk away."

## System prompt sketch

```
You are the music concierge for the Telephone network. You help callers find
and play music on the room speakers via Spotify.

You have access to Spotify's full catalog. You can search for artists, albums,
tracks, and playlists, and start playback on the room speakers.

When a caller describes a mood, genre, or artist, search Spotify and pick
something good. Tell them what you're playing. Keep it conversational.

You can also:
- Skip to the next track, go back, pause, or resume
- Tell the caller what's currently playing
- Take requests: "play Coltrane" or "play the Discover Weekly playlist"
- Make recommendations: "if you like that, you might also enjoy..."

Playback continues after the call ends. If the caller says "stop" or "turn
it off," stop playback.

The caller can also control playback from the Spotify app on their phone,
or by dialing 730/8xx and using DTMF.
```

## Open questions

- **Extension number:** 205 fits the AI agent range. Or could be a special number like 731 (Spotify range). 205 is probably better — it's an agent, not a utility.
- **Persistent librespot:** If Phase 1 evolves to run librespot as a systemd service (always-on Connect target), the agent doesn't need to manage its lifecycle at all — just make API calls.
- **Operator handoff:** The main operator (ext 0) could handle simple music requests directly ("play some jazz") and only transfer to 205 for more complex interactions. Or the operator could just always transfer music requests to 205.
- **Memory:** Could be interesting to remember preferences across calls ("you usually like jazz in the evening"). Probably not worth building until the basics are solid.

## Dependencies

- Phase 1 complete and working (librespot, Web API auth, spotify-connect script)
- Spotify Web API search and recommendations endpoints
- Same agent infrastructure as other 2xx agents (Pipecat, AudioSocket, Claude Haiku 4.5, Deepgram)

## Also deferred: Phone audio via ConfBridge

Getting Spotify audio onto the handset (8kHz through the phone system) is a separate effort involving a PulseAudio null sink, parec capture, and an AudioSocket shim to inject into a ConfBridge. This can be Phase 3 if there's demand for it, but the laptop speakers are probably the better listening experience anyway.
