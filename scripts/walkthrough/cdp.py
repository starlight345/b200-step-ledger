"""Minimal Chrome DevTools Protocol client built on the standard library only.

This machine has no node, no npm and no full ffmpeg, so the walkthrough cannot
be recorded with playwright. Chrome itself is present, and Chrome speaks CDP
over a WebSocket, so this module implements just enough of RFC 6455 to drive a
headless tab and collect screencast frames.
"""

import base64
import json
import os
import socket
import struct
import subprocess
import time
import urllib.request
from urllib.parse import urlparse

CHROME = os.environ.get(
    "CHROME_BIN", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)


class ProtocolError(RuntimeError):
    pass


class WebSocket:
    """Text-frame WebSocket client. Enough for CDP: no extensions, no TLS."""

    def __init__(self, url, timeout=30.0):
        parts = urlparse(url)
        self.sock = socket.create_connection((parts.hostname, parts.port), timeout=10.0)
        self.sock.settimeout(timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._buffer = bytearray()
        key = base64.b64encode(os.urandom(16)).decode()
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parts.hostname}:{parts.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.sock.sendall(request.encode())
        header = self._read_until(b"\r\n\r\n")
        if b"101" not in header.split(b"\r\n", 1)[0]:
            raise ProtocolError(f"WebSocket upgrade refused: {header[:200]!r}")

    def _read_until(self, marker):
        while marker not in self._buffer:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ProtocolError("connection closed during handshake")
            self._buffer.extend(chunk)
        index = self._buffer.index(marker) + len(marker)
        header = bytes(self._buffer[:index])
        del self._buffer[:index]
        return header

    def _read_exactly(self, count):
        while len(self._buffer) < count:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise ProtocolError("connection closed")
            self._buffer.extend(chunk)
        data = bytes(self._buffer[:count])
        del self._buffer[:count]
        return data

    def send(self, text):
        payload = text.encode()
        length = len(payload)
        header = bytearray([0x81])
        if length < 126:
            header.append(0x80 | length)
        elif length < (1 << 16):
            header.append(0x80 | 126)
            header.extend(struct.pack(">H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack(">Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def recv(self):
        """Return the next complete text message, reassembling fragments."""
        message = bytearray()
        while True:
            first, second = self._read_exactly(2)
            final = bool(first & 0x80)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read_exactly(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read_exactly(8))[0]
            mask = self._read_exactly(4) if masked else None
            payload = self._read_exactly(length)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x8:
                raise ProtocolError("websocket closed by peer")
            if opcode == 0x9:
                self.sock.sendall(bytes([0x8A, 0x80]) + os.urandom(4))
                continue
            if opcode == 0xA:
                continue
            message.extend(payload)
            if final:
                return message.decode()

    def close(self):
        try:
            self.sock.sendall(bytes([0x88, 0x80]) + os.urandom(4))
        except OSError:
            pass
        self.sock.close()


class Chrome:
    """A headless Chrome process plus one attached page."""

    def __init__(self, port=9333, window=(1280, 720), profile_dir=None, log_path=None):
        self.port = port
        self.window = window
        self.profile_dir = profile_dir or f"/tmp/ledger3d-chrome-{port}"
        self.log_path = log_path
        self.process = None
        self.ws = None
        self._next_id = 0
        self.events = []
        self.handlers = {}

    def start(self):
        os.makedirs(self.profile_dir, exist_ok=True)
        log = open(self.log_path, "wb") if self.log_path else subprocess.DEVNULL
        self.process = subprocess.Popen(
            [
                CHROME,
                "--headless=new",
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.profile_dir}",
                f"--window-size={self.window[0]},{self.window[1]}",
                "--force-device-scale-factor=1",
                "--hide-scrollbars",
                "--mute-audio",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--enable-unsafe-swiftshader",
                "about:blank",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        target = self._await_page()
        self.ws = WebSocket(target["webSocketDebuggerUrl"])
        return self

    def _await_page(self, timeout=25.0):
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/json/list", timeout=2
                ) as response:
                    targets = json.loads(response.read().decode())
                pages = [t for t in targets if t.get("type") == "page"]
                if pages:
                    return pages[0]
            except Exception as error:  # chrome is still booting
                last_error = error
            time.sleep(0.25)
        raise ProtocolError(f"no debuggable page appeared: {last_error}")

    def call(self, method, params=None, timeout=60.0):
        self._next_id += 1
        message_id = self._next_id
        self.ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise ProtocolError(f"timed out waiting for {method}")
            self.ws.sock.settimeout(remaining)
            message = json.loads(self.ws.recv())
            if message.get("id") == message_id:
                if "error" in message:
                    raise ProtocolError(f"{method}: {message['error']}")
                return message.get("result", {})
            self._dispatch(message)

    def _dispatch(self, message):
        method = message.get("method")
        if not method:
            return
        handler = self.handlers.get(method)
        if handler:
            handler(message.get("params", {}))
        else:
            self.events.append(message)

    def pump(self, seconds):
        """Read events for a fixed wall-clock span. Screencast frames arrive here."""
        deadline = time.time() + seconds
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return
            self.ws.sock.settimeout(remaining)
            try:
                message = json.loads(self.ws.recv())
            except socket.timeout:
                return
            self._dispatch(message)

    def stop(self):
        if self.ws:
            self.ws.close()
            self.ws = None
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
