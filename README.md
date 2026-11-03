# delaycam

Stream a phone camera to a Linux laptop, show it on screen N seconds late (to watch your shot right after you take it), and record everything for later analysis.

```
phone (Larix Broadcaster) --RTMP over Wi-Fi hotspot--> ffmpeg --+--> recordings/<timestamp>.mkv (original quality, no re-encode)
                                                                +--> delayed display window
```

## Requirements (laptop)

- A Wi-Fi adapter that supports access-point (AP) mode — check with `iw list | grep -A8 "Supported interface modes"` (look for `AP`)
- NetworkManager (`nmcli`), `ffmpeg`, Python 3 with `opencv-python` (with GUI support) and `numpy`
- Manjaro/Arch: `sudo pacman -S ffmpeg python-opencv python-numpy`

## Quick start

```
./delaycam.py --hotspot --delay 8 --fullscreen
```

This brings up the hotspot, then waits for the phone. Once the phone is streaming, the picture appears after the delay has elapsed.

## Phone setup

Uses **Larix Broadcaster** (free, Android and iOS). Menu names may differ slightly between app versions.

1. **Install** Larix Broadcaster from the Play Store / App Store.
2. **Join the Wi-Fi** network `DelayCam`, password `delaycam123` (or whatever you set via `SSID`/`PASS`).
   - The phone will warn that the network has no internet. Choose to **stay connected**.
   - Android: turn off *Switch to mobile data* / *Adaptive Wi-Fi* if it keeps dropping the network.
   - iPhone: turn off *Settings → Mobile Data → Wi-Fi Assist*.
3. **Add the connection** in Larix: *Settings → Connections → +*
   - Name: `delaycam`
   - URL: `rtmp://10.42.0.1:1935/live/bow`
   - Mode: Audio + Video
   - Save, and make sure it is the only connection ticked/active.
4. **Video settings** (*Settings → Video*), recommended for analysis:
   - Resolution: 1920×1080
   - Frame rate: 60 fps if the phone offers it (smoother slow-motion review), otherwise 30
   - Bitrate: 8–10 Mbps
   - Keyframe interval: 1–2 s (faster start after a reconnect)
5. **Position the phone** on a tripod, side-on to the shooting line, in landscape. Lock orientation so it doesn't flip mid-session.
6. **Press the record/stream button** in Larix. The laptop prints `connected: ...` and starts recording.
7. **Keep Larix in the foreground with the screen on.** Locking the phone or switching apps stops the stream. Plug the phone in for long sessions.

### Alternative: IP Webcam (Android)

If you prefer an app that serves the stream instead of pushing it, start the server in IP Webcam and run:

```
./delaycam.py -s http://PHONE_IP:8080/video
```

(`PHONE_IP` is shown in the IP Webcam app; it will be a `10.42.0.x` address on the hotspot.)

## Usage

```
./delaycam.py [-d DELAY] [-H HEIGHT] [-o OUTDIR] [-f] [--hotspot] [-s SOURCE]
```

| Option | Default | Meaning |
|---|---|---|
| `-d`, `--delay` | 8 | Display delay in seconds |
| `-H`, `--height` | 720 | Display height in px (recording is unaffected) |
| `-o`, `--outdir` | `recordings` | Where recordings are saved |
| `-f`, `--fullscreen` | off | Start fullscreen |
| `--hotspot` | off | Run `hotspot.sh up` first |
| `-s`, `--source` | `rtmp://0.0.0.0:1935/live/bow` | Stream URL. `rtmp://0.0.0.0:...` listens for a push; anything else is opened as a client |

### Keys

| Key | Action |
|---|---|
| `+` / `]` | Delay +0.5 s |
| `-` / `[` | Delay −0.5 s |
| `m` | Mark the shot currently on screen |
| `f` | Toggle fullscreen |
| `q` / `Esc` | Quit |

Raising the delay freezes the picture until the buffer catches up; lowering it skips forward.

## Hotspot

```
./hotspot.sh up       # start (prints the phone stream URL)
./hotspot.sh status
./hotspot.sh down     # stop and give the Wi-Fi adapter back
```

Override defaults with environment variables, e.g. `SSID=Range PASS=arrows1234 IFACE=wlan0 ./hotspot.sh up`. The password must be at least 8 characters.

While the hotspot is up, the laptop's Wi-Fi adapter is not available for other networks.

## Recordings

- Each phone connection produces `recordings/YYYYMMDD-HHMMSS.mkv` with the phone's original video and audio.
- Pressing `m` appends a timestamp to `recordings/YYYYMMDD-HHMMSS.marks.txt`. The timestamp is the position in that recording of the frame you were watching, so it lands on the shot, not on when you pressed the key.
- Jump to a mark: `mpv --start=00:01:23.450 recordings/20261103-150000.mkv`
- Frame-by-frame in mpv: `.` / `,` step forward / back, `[` / `]` change speed.

## Troubleshooting

- **Phone can't connect:** check the firewall. With ufw: `sudo ufw allow 1935/tcp`. With firewalld: `sudo firewall-cmd --add-port=1935/tcp`.
- **`no Wi-Fi device found`:** the machine has no Wi-Fi adapter, or NetworkManager doesn't manage it. Set `IFACE=` explicitly.
- **Hotspot fails to start:** the adapter may not support AP mode (see Requirements).
- **High memory use:** the delay buffer holds uncompressed frames, about 400 MB for 8 s at 720p30. Lower `-H` or the delay.
