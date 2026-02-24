import json
import socket
import threading
import time
import datetime
import unicodedata
import urllib.request
import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD

# ── Config ─────────────────────────────────────────────
THINKPAD_IP = '192.168.0.144'
AMI_PORT = 5038
AMI_USER = 'panel'
AMI_SECRET = 'panelpass'
NOWPLAYING_URL = f'http://{THINKPAD_IP}:8765'

LCD_ADDRESS = 0x27
BACKLIGHT_BRIGHTNESS = 15  # 0–100

PINS = {
    'LED_SYS':  8,
    'KEY':      23,
    'MISSILE':  6,
    'SPKR':     24,
    'SCHED':    25,
    'ENC_CLK':  17,
    'ENC_DT':   27,
    'ENC_SW':   22,
}

STATIONS = [
    ('700', 'CISM 89.3',  'Montreal'),
    ('701', 'CIUT 89.5',  'Toronto'),
    ('702', 'CKDU 88.1',  'Halifax'),
    ('703', 'WFMU 91.1',  'Jersey City'),
    ('704', 'New Sounds', 'NYC'),
    ('705', 'WNYC 93.9',  'NYC'),
    ('706', 'WMBR 88.1',  'Cambridge'),
    ('707', 'WBUR 90.9',  'Boston'),
    ('708', 'CHIRP 107.1','Chicago'),
    ('709', 'WBEZ 91.5',  'Chicago'),
    ('710', 'KEXP 90.3',  'Seattle'),
    ('711', 'KALX 90.7',  'Berkeley'),
    ('712', 'BFF.fm',     'San Francisco'),
    ('713', 'KQED 88.5',  'San Francisco'),
    ('714', 'KBOO 90.7',  'Portland'),
    ('715', 'XRAY.fm',    'Portland'),
    ('716', 'The Gamut',  'Washington DC'),
    ('717', 'WETA 90.9',  'Washington DC'),
    ('718', 'NPR',        'National'),
]

BRIDGE_NAMES = {
    'radio-cism':      'CISM 89.3',
    'radio-ciut':      'CIUT 89.5',
    'radio-ckdu':      'CKDU 88.1',
    'radio-wfmu':      'WFMU 91.1',
    'radio-newsounds': 'New Sounds',
    'radio-wnyc':      'WNYC 93.9',
    'radio-wmbr':      'WMBR 88.1',
    'radio-wbur':      'WBUR 90.9',
    'radio-chirp':     'CHIRP 107.1',
    'radio-wbez':      'WBEZ 91.5',
    'radio-kexp':      'KEXP 90.3',
    'radio-kalx':      'KALX 90.7',
    'radio-bff':       'BFF.fm',
    'radio-kqed':      'KQED 88.5',
    'radio-kboo':      'KBOO 90.7',
    'radio-xray':      'XRAY.fm',
    'radio-gamut':     'The Gamut',
    'radio-weta':      'WETA 90.9',
    'radio-npr':       'NPR',
}

REAL_EXTENSIONS = {str(i) for i in range(100, 106)} \
                | {str(i) for i in range(200, 206)} \
                | {str(i) for i in range(700, 719)} \
                | {str(i) for i in range(730, 812)} \
                | {'0'}

SPOTIFY_EXTS = {'205'} | {str(i) for i in range(730, 812)}

# ── GPIO Setup ──────────────────────────────────────────
GPIO.setmode(GPIO.BCM)
GPIO.setup(PINS['LED_SYS'], GPIO.OUT)
for pin in ['KEY', 'MISSILE', 'SPKR', 'SCHED', 'ENC_CLK', 'ENC_DT', 'ENC_SW']:
    GPIO.setup(PINS[pin], GPIO.IN, pull_up_down=GPIO.PUD_UP)

# ── LCD Setup ───────────────────────────────────────────
lcd = CharLCD('PCF8574', LCD_ADDRESS)

def _lcd_clean(text):
    """Strip accents/diacritics so HD44780 displays them cleanly."""
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')

def lcd_show(lines):
    lcd.clear()
    for i, line in enumerate(lines[:4]):
        lcd.cursor_pos = (i, 0)
        lcd.write_string(_lcd_clean(line)[:20])

# ── Backlight dimmer (I2C software PWM) ─────────────────
def backlight_loop():
    period = 0.005  # 200Hz
    while True:
        on_time = period * (BACKLIGHT_BRIGHTNESS / 100)
        off_time = period - on_time
        if on_time > 0:
            lcd.backlight_enabled = True
            time.sleep(on_time)
        if off_time > 0:
            lcd.backlight_enabled = False
            time.sleep(off_time)

# ── State ───────────────────────────────────────────────
state = {
    'active_ext':      None,
    'active_bridge':   None,
    'display_top':     ('', ''),
    'station_index':   0,
    'ami_connected':   False,
    'ami_sock':        None,
    'ami_lock':        threading.Lock(),
    'nowplaying_stop': None,
    'bottom_label':    '',
}

# ── Display helpers ──────────────────────────────────────
def wrap_for_lcd(text, width=20):
    if not text:
        return '', ''
    if len(text) <= width:
        return text, ''
    idx = text.rfind(' ', 0, width + 1)
    if idx <= 0:
        idx = width
    return text[:idx].rstrip(), text[idx:].lstrip()[:width]

def show_active(l1, l2, nowplaying=None):
    state['display_top'] = (l1, l2)
    l3, l4 = wrap_for_lcd(nowplaying) if nowplaying else ('', '')
    lcd_show([l1, l2, l3, l4])

def update_nowplaying(track):
    l1, l2 = state['display_top']
    label = state.get('bottom_label', '')
    if label:
        l3, l4 = (track[:20] if track else ''), label
    else:
        l3, l4 = wrap_for_lcd(track) if track else ('', '')
    lcd_show([l1, l2, l3, l4])

# ── Now-playing poll thread ──────────────────────────────
def _nowplaying_poll(stop_event, url_path, interval):
    quick_retry = True
    while not stop_event.is_set():
        try:
            with urllib.request.urlopen(
                f'{NOWPLAYING_URL}{url_path}', timeout=5
            ) as resp:
                data = json.loads(resp.read())
            # Spotify returns {track, artist}; radio returns {track}
            if 'artist' in data:
                l1, l2 = state['display_top']
                l3 = (data.get('track') or '')[:20]
                l4 = (data.get('artist') or '')[:20]
                lcd_show([l1, l2, l3, l4])
            else:
                track = data.get('track') or ''
                l1, l2 = state['display_top']
                if ' - ' in track:
                    artist, song = track.split(' - ', 1)
                    lcd_show([l1, l2, song[:20], artist[:20]])
                elif ' by ' in track:
                    song, artist = track.split(' by ', 1)
                    lcd_show([l1, l2, song[:20], artist[:20]])
                else:
                    update_nowplaying(track)
        except Exception:
            pass
        # On start, do a quick follow-up after 5s in case playback
        # hadn't reported yet on the immediate first poll.
        wait = 5 if quick_retry else interval
        quick_retry = False
        stop_event.wait(wait)

def start_nowplaying(url_path, interval):
    stop_nowplaying()
    ev = threading.Event()
    state['nowplaying_stop'] = ev
    threading.Thread(
        target=_nowplaying_poll, args=(ev, url_path, interval), daemon=True
    ).start()

def stop_nowplaying():
    ev = state.get('nowplaying_stop')
    if ev:
        ev.set()
    state['nowplaying_stop'] = None

# ── Initial state restore (via HTTP /status) ─────────────
def restore_state():
    """Ask the ThinkPad what's currently active and update display."""
    # Don't override if we already know what's happening
    if state['active_ext'] or state['active_bridge']:
        return
    try:
        with urllib.request.urlopen(f'{NOWPLAYING_URL}/status', timeout=5) as resp:
            data = json.loads(resp.read())
        kind = data.get('type', 'idle')
        if kind == 'radio':
            bridge = data['bridge']
            state['active_bridge'] = bridge
            show_active('RADIO', BRIDGE_NAMES.get(bridge, bridge))
            start_nowplaying(f'/radio/{bridge}', 45)
            print(f"Restored: radio {bridge}")
        elif kind == 'call':
            exten = data['ext']
            state['active_ext'] = exten
            if exten in SPOTIFY_EXTS:
                state['bottom_label'] = 'SPOTIFY'
                show_active(f'EXT {exten}', 'CALL IN PROGRESS')
                start_nowplaying('/spotify', 15)
            else:
                show_active(f'EXT {exten}', 'CALL IN PROGRESS')
            print(f"Restored: call {exten}")
        else:
            print("Restored: idle")
    except Exception as e:
        print(f"Status restore failed: {e}")

# ── AMI Originate ────────────────────────────────────────
def ami_originate(ext):
    action = (
        f'Action: Originate\r\n'
        f'Channel: PJSIP/100\r\n'
        f'Exten: {ext}\r\n'
        f'Context: internal\r\n'
        f'Priority: 1\r\n'
        f'Timeout: 30000\r\n\r\n'
    )
    with state['ami_lock']:
        sock = state['ami_sock']
        if sock:
            try:
                sock.send(action.encode())
                print(f"Originate sent: {ext}")
            except Exception as e:
                print(f"Originate error: {e}")
        else:
            print("Originate failed: no AMI connection")

# ── LCD idle display ─────────────────────────────────────
def show_idle():
    now = datetime.datetime.now()
    lcd_show([
        'C&P TELEPHONE',
        'INFOLINE',
        '',
        now.strftime('%H:%M  %a %b %-d'),
    ])

def clock_loop():
    while True:
        time.sleep(30)
        if state['active_ext'] is None and state['active_bridge'] is None:
            show_idle()

# ── AMI Event Handler ────────────────────────────────────
def parse_event(raw):
    event = {}
    for line in raw.strip().split('\r\n'):
        if ': ' in line:
            k, v = line.split(': ', 1)
            event[k] = v
    return event

def handle_event(event):
    etype = event.get('Event', '')
    exten = event.get('Exten', '')

    if etype == 'Newchannel' and exten in REAL_EXTENSIONS:
        state['active_ext'] = exten
        state['active_bridge'] = None
        if exten in SPOTIFY_EXTS:
            show_active(f'EXT {exten}', 'CALL IN PROGRESS')
            start_nowplaying('/spotify', 15)
        else:
            show_active(f'EXT {exten}', 'CALL IN PROGRESS')
            stop_nowplaying()
        print(f"Call: {exten}")

    elif etype == 'Newexten' and event.get('Priority') == '1' \
            and exten in REAL_EXTENSIONS \
            and state['active_ext'] != exten \
            and not (exten == '100' and state['active_ext'] in {'0', '100'}):
        state['active_ext'] = exten
        state['active_bridge'] = None
        if exten in SPOTIFY_EXTS:
            show_active(f'EXT {exten}', 'CALL IN PROGRESS')
            start_nowplaying('/spotify', 15)
        else:
            show_active(f'EXT {exten}', 'CALL IN PROGRESS')
            stop_nowplaying()
        print(f"Transfer: {exten}")

    elif etype == 'Hangup':
        stop_nowplaying()
        state['bottom_label'] = ''
        state['active_ext'] = None
        state['active_bridge'] = None
        show_idle()

    elif etype == 'ConfbridgeJoin':
        bridge = event.get('Conference', '')
        state['active_bridge'] = bridge
        station_name = BRIDGE_NAMES.get(bridge, bridge)
        show_active('RADIO', station_name)
        start_nowplaying(f'/radio/{bridge}', 45)

    elif etype == 'ConfbridgeLeave':
        stop_nowplaying()
        state['active_bridge'] = None
        show_idle()

# ── AMI Listener Thread ───────────────────────────────────
def ami_loop():
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((THINKPAD_IP, AMI_PORT))
            sock.recv(1024)  # banner

            sock.send(
                f'Action: Login\r\nUsername: {AMI_USER}\r\nSecret: {AMI_SECRET}\r\n\r\n'
                .encode()
            )
            # Drain login response (+ possible FullyBooted event)
            sock.settimeout(3)
            login_buf = ''
            try:
                while 'Authentication accepted' not in login_buf:
                    data = sock.recv(4096).decode(errors='replace')
                    if not data:
                        break
                    login_buf += data
            except socket.timeout:
                pass
            finally:
                sock.settimeout(None)

            if 'Authentication accepted' not in login_buf:
                raise RuntimeError("AMI login failed")

            # Restore display if a call/radio was already active
            restore_state()

            sock.send(b'Action: Events\r\nEventMask: call,system,dtmf,dialplan\r\n\r\n')

            with state['ami_lock']:
                state['ami_sock'] = sock
            state['ami_connected'] = True
            print("AMI connected")

            buffer = ''
            while True:
                data = sock.recv(4096).decode(errors='replace')
                if not data:
                    raise RuntimeError("AMI connection closed")
                buffer += data
                while '\r\n\r\n' in buffer:
                    event_str, buffer = buffer.split('\r\n\r\n', 1)
                    handle_event(parse_event(event_str))

        except Exception as e:
            print(f"AMI error: {e}")
            state['ami_connected'] = False
            with state['ami_lock']:
                state['ami_sock'] = None
            time.sleep(5)

# ── Encoder Thread ───────────────────────────────────────
def encoder_loop():
    last_clk = GPIO.input(PINS['ENC_CLK'])
    last_press = 0
    GPIO.add_event_detect(PINS['ENC_CLK'], GPIO.BOTH)

    while True:
        if GPIO.event_detected(PINS['ENC_CLK']):
            clk = GPIO.input(PINS['ENC_CLK'])
            dt  = GPIO.input(PINS['ENC_DT'])
            if clk != last_clk:
                if dt != clk:
                    state['station_index'] = (state['station_index'] + 1) % len(STATIONS)
                else:
                    state['station_index'] = (state['station_index'] - 1) % len(STATIONS)
                ext, name, city = STATIONS[state['station_index']]
                lcd_show([f'> {name}', city, 'Press to tune', ''])
                last_clk = clk

        if GPIO.input(PINS['ENC_SW']) == GPIO.LOW:
            now = time.time()
            if now - last_press > 0.3:
                last_press = now
                ext, name, city = STATIONS[state['station_index']]
                print(f"Dialing {ext} — {name}")
                lcd_show(['TUNING...', name, city, ''])
                threading.Thread(target=ami_originate, args=(ext,), daemon=True).start()

        time.sleep(0.001)

# ── SYS LED heartbeat ────────────────────────────────────
def heartbeat_loop():
    while True:
        if state['ami_connected']:
            GPIO.output(PINS['LED_SYS'], GPIO.HIGH)
            time.sleep(0.1)
            GPIO.output(PINS['LED_SYS'], GPIO.LOW)
            time.sleep(1.9)
        else:
            GPIO.output(PINS['LED_SYS'], GPIO.HIGH)
            time.sleep(0.1)
            GPIO.output(PINS['LED_SYS'], GPIO.LOW)
            time.sleep(0.1)

# ── Main ─────────────────────────────────────────────────
show_idle()

threading.Thread(target=ami_loop, daemon=True).start()
threading.Thread(target=encoder_loop, daemon=True).start()
threading.Thread(target=heartbeat_loop, daemon=True).start()
threading.Thread(target=backlight_loop, daemon=True).start()
threading.Thread(target=clock_loop, daemon=True).start()

print("InfoLine panel running. Ctrl+C to stop.")

try:
    while True:
        missile = GPIO.input(PINS['MISSILE']) == GPIO.LOW
        if missile:
            lcd_show(['!! EMERGENCY !!', 'SHUTDOWN', 'INITIATED', ''])
            print("MISSILE SWITCH THROWN")
        time.sleep(0.1)

except KeyboardInterrupt:
    lcd.clear()
    GPIO.cleanup()
    print("Stopped.")
