#!/usr/bin/env python3
"""Delayed video mirror: receive a phone camera stream, show it N seconds late, record it.

ffmpeg receives the stream once and splits it:
  - output 1: stream copy (no re-encode) to recordings/<timestamp>.mkv
  - output 2: decoded yuv4mpeg frames on stdout -> buffered here and displayed after `delay`

Keys:  + / ]  delay +0.5s    - / [  delay -0.5s    m  mark shot (written next to the recording)
       f  toggle fullscreen   q / Esc  quit
"""
import argparse
import collections
import datetime
import os
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

import cv2
import numpy as np

WINDOW = "delaycam"


class Receiver(threading.Thread):
    """Runs ffmpeg in a loop (reconnecting when the phone drops) and buffers decoded frames."""

    def __init__(self, source, height, outdir):
        super().__init__(daemon=True)
        self.source = source
        self.height = height
        self.outdir = outdir
        self.lock = threading.Lock()
        self.frames = collections.deque()  # (arrival_monotonic, yuv_bytes)
        self.size = None  # (w, h)
        self.connected = False
        self.recording = None  # current .mkv path
        self.rec_start = None  # monotonic time of first frame in current recording
        self.proc = None
        self.stopping = False

    def ffmpeg_cmd(self, outfile):
        u = urlparse(self.source)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin"]
        if u.scheme == "rtmp" and u.hostname in ("0.0.0.0", "::"):
            cmd += ["-listen", "1"]
        cmd += ["-i", self.source,
                "-map", "0:v:0", "-map", "0:a?", "-c", "copy", "-f", "matroska", outfile,
                "-map", "0:v:0", "-vf", f"scale=-2:{self.height},format=yuv420p",
                "-f", "yuv4mpegpipe", "-"]
        return cmd

    def run(self):
        while not self.stopping:
            outfile = os.path.join(self.outdir, datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ".mkv")
            self.proc = subprocess.Popen(self.ffmpeg_cmd(outfile), stdout=subprocess.PIPE)
            try:
                self.read_stream(self.proc.stdout, outfile)
            finally:
                self.proc.stdout.close()
                self.proc.wait()
                self.connected = False
                self.rec_start = None
                if os.path.exists(outfile) and os.path.getsize(outfile) == 0:
                    os.remove(outfile)
            if not self.stopping:
                time.sleep(1)

    def read_stream(self, pipe, outfile):
        header = pipe.readline()  # blocks until the phone connects
        if not header.startswith(b"YUV4MPEG2"):
            return
        params = {p[:1]: p[1:] for p in header.split()[1:]}
        w, h = int(params[b"W"]), int(params[b"H"])
        framelen = w * h * 3 // 2
        with self.lock:
            self.frames.clear()
            self.size = (w, h)
        self.connected = True
        self.recording = outfile
        print(f"connected: {w}x{h}, recording to {outfile}", file=sys.stderr)
        while True:
            if not pipe.readline().startswith(b"FRAME"):
                return
            data = pipe.read(framelen)
            if len(data) < framelen:
                return
            now = time.monotonic()
            if self.rec_start is None:
                self.rec_start = now
            with self.lock:
                self.frames.append((now, data))

    def frame_for(self, target, keep_after):
        """Latest frame that arrived at or before `target`; drops frames older than it."""
        with self.lock:
            # discard frames that will never be shown again (keep one before target)
            while len(self.frames) > 1 and self.frames[1][0] <= min(target, keep_after):
                self.frames.popleft()
            best = None
            for f in self.frames:
                if f[0] > target:
                    break
                best = f
            return best, self.size

    def stop(self):
        self.stopping = True
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)  # lets ffmpeg finalise the mkv


def fmt_ts(seconds):
    m, s = divmod(max(seconds, 0), 60)
    h, m = divmod(int(m), 60)
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def put_text(img, text, org, color, scale=0.9):
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 5, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-d", "--delay", type=float, default=8.0, help="display delay in seconds (default 8)")
    ap.add_argument("-s", "--source", default="rtmp://0.0.0.0:1935/live/bow",
                    help="stream URL; rtmp://0.0.0.0:... listens for the phone to push (default), "
                         "anything else is opened as a client (e.g. http://PHONE:8080/video)")
    ap.add_argument("-H", "--height", type=int, default=720, help="display height in px (recording is untouched)")
    ap.add_argument("-o", "--outdir", default="recordings", help="recording directory (default ./recordings)")
    ap.add_argument("-f", "--fullscreen", action="store_true")
    ap.add_argument("--hotspot", action="store_true", help="bring up the Wi-Fi hotspot first (hotspot.sh up)")
    args = ap.parse_args()

    if args.hotspot:
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hotspot.sh")
        subprocess.run([script, "up"], check=True)

    os.makedirs(args.outdir, exist_ok=True)
    rx = Receiver(args.source, args.height, args.outdir)
    rx.start()

    delay = max(args.delay, 0.0)
    fullscreen = args.fullscreen
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, args.height * 16 // 9, args.height)
    if fullscreen:
        cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    blank = np.zeros((args.height, args.height * 16 // 9, 3), np.uint8)
    shown = None  # (arrival_time, bgr image)
    marks = 0
    print(f"waiting for stream on {args.source}", file=sys.stderr)

    try:
        while True:
            now = time.monotonic()
            frame, size = rx.frame_for(now - delay, now - delay)
            if frame is not None and (shown is None or frame[0] != shown[0]):
                w, h = size
                yuv = np.frombuffer(frame[1], np.uint8).reshape(h * 3 // 2, w)
                shown = (frame[0], cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420))

            img = shown[1].copy() if shown and rx.connected else blank.copy()
            if not rx.connected:
                put_text(img, f"Waiting for stream on {args.source}", (20, 50), (255, 255, 255), 0.7)
                shown = None
            elif shown is None:
                left = delay - (now - rx.rec_start) if rx.rec_start else delay
                put_text(img, f"Buffering... {left:4.1f}s", (20, 50), (0, 200, 255))
            put_text(img, f"DELAY {delay:.1f}s", (20, img.shape[0] - 20), (255, 255, 255))
            if rx.connected:
                cv2.circle(img, (img.shape[1] - 30, 30), 10, (0, 0, 255), -1)
                if marks:
                    put_text(img, f"marks: {marks}", (img.shape[1] - 200, img.shape[0] - 20), (0, 255, 0), 0.7)
            cv2.imshow(WINDOW, img)

            key = cv2.waitKey(5) & 0xFF
            if key in (ord("q"), 27) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
            elif key in (ord("+"), ord("="), ord("]")):
                delay += 0.5
            elif key in (ord("-"), ord("_"), ord("[")):
                delay = max(0.0, delay - 0.5)
            elif key == ord("f"):
                fullscreen = not fullscreen
                cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN,
                                      cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL)
            elif key == ord("m") and shown and rx.rec_start and rx.recording:
                # timestamp of the frame on screen, i.e. the shot you're currently watching
                ts = fmt_ts(shown[0] - rx.rec_start)
                with open(os.path.splitext(rx.recording)[0] + ".marks.txt", "a") as fh:
                    fh.write(ts + "\n")
                marks += 1
                print(f"mark {ts}", file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        rx.stop()
        rx.join(timeout=10)
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
