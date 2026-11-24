#!/usr/bin/env python3
"""Bounded, private ttyd 1.7.7 startup probe (Python 3.9+ stdlib only).

Primary protocol reference: https://github.com/tsl0922/ttyd/tree/1.7.7
  html/src/components/terminal/xterm/index.ts: refreshToken/onSocketOpen,
      binary AuthToken/columns/rows JSON, tty subprotocol and '0' OUTPUT.
  src/http.c and src/server.c: token JSON (empty without credentials),
      /token and /ws endpoints, -b prefix and -O origin checks.
  src/protocol.c: initial JSON spawns a NEW process; WS close frees its
      client slot and kills that process. No attach/reconnect or INPUT here.
The full prompt comes from HumanPlayer.java, not HTTP version metadata.
HTTPS uses certificate/hostname validation; redirects and proxies are unused.
"""
import argparse
import base64
import hashlib
import json
import os
import queue
import re
import socket
import ssl
import struct
import sys
import threading
import time
from urllib.parse import unquote, urlsplit

PROMPT = b"where to put the next CROSS? (0-8): "
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_HTTP = 16384
MAX_MESSAGE = 1048576
MAX_TOTAL = 4194304


class _Deadline:
    def __init__(self, seconds):
        if (isinstance(seconds, bool) or not isinstance(seconds, (float, int))
                or not 0 < seconds <= 86400):
            raise ValueError("timeout must be positive finite seconds (at most 86400)")
        self.end = time.monotonic() + seconds
        self.received = 0

    def remaining(self):
        left = self.end - time.monotonic()
        if left <= 0:
            raise TimeoutError("console startup deadline exceeded")
        return left


def _bounded_setup(operation, deadline, failure):
    # Only setup belongs here: stdlib has no cancellation for trust-store
    # loading or DNS. A timed-out daemon must never open a console socket
    # or begin a TLS handshake.
    result = queue.Queue(maxsize=1)
    def run():
        try:
            value = operation()
        except Exception:
            result.put((None, True))
        else:
            result.put((value, False))
    deadline.remaining()
    threading.Thread(target=run, daemon=True).start()
    try:
        value, failed = result.get(timeout=deadline.remaining())
    except queue.Empty:
        raise TimeoutError("console startup deadline exceeded") from None
    deadline.remaining()
    if failed:
        raise RuntimeError(failure)
    return value


def _connect(parsed, deadline):
    # The daemon only resolves; it cannot connect after the caller times out.
    addresses = _bounded_setup(lambda: socket.getaddrinfo(parsed.hostname, parsed.port or
        (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM),
        deadline, "console address resolution failed")
    if not addresses or len(addresses) > 16:
        raise RuntimeError("console address limit exceeded or resolution failed")
    for family, kind, protocol, _, address in addresses:
        sock = socket.socket(family, kind, protocol)
        try:
            sock.settimeout(deadline.remaining())
            sock.connect(address)
            return sock
        except BaseException as exc:
            sock.close()
            if not isinstance(exc, OSError):
                raise
    deadline.remaining()
    raise RuntimeError("console TCP connection failed")


class _Peer:
    def __init__(self, parsed, deadline):
        self.deadline = deadline
        self.buffer = bytearray()
        context = (_bounded_setup(ssl.create_default_context, deadline, "console TLS setup failed")
                   if parsed.scheme == "https" else None)
        self.sock = _connect(parsed, deadline)
        try:
            if context is not None:
                self.sock.settimeout(deadline.remaining())
                self.sock = context.wrap_socket(self.sock, server_hostname=parsed.hostname,
                                                do_handshake_on_connect=False)
                self.sock.settimeout(deadline.remaining())
                self.sock.do_handshake()
        except BaseException:
            self.sock.close()
            raise

    def send(self, data):
        self.sock.settimeout(self.deadline.remaining())
        self.sock.sendall(data)

    def read(self, n):
        self.deadline.remaining()
        while len(self.buffer) < n:
            self.sock.settimeout(self.deadline.remaining())
            data = self.sock.recv(4096)
            self.deadline.received += len(data)
            if self.deadline.received > MAX_TOTAL:
                raise RuntimeError("console total receive limit exceeded")
            if not data:
                raise RuntimeError("console connection closed before startup prompt")
            self.buffer.extend(data)
        result = bytes(self.buffer[:n])
        del self.buffer[:n]
        return result

    def headers(self):
        raw = bytearray()
        while not raw.endswith(b"\r\n\r\n"):
            raw.extend(self.read(1))
            if len(raw) > MAX_HTTP:
                raise RuntimeError("console HTTP header limit exceeded")
        lines = raw.decode("iso-8859-1").split("\r\n")
        if not re.fullmatch(r"HTTP/1\.[01] [0-9]{3}(?: [\x20-\x7e]*)?", lines[0]):
            raise RuntimeError("invalid console HTTP status")
        self.http_version = lines[0].split()[0]
        headers = {}
        for line in lines[1:-2]:
            key, separator, value = line.partition(":")
            if (not separator or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key)
                    or not re.fullmatch(r"[\t\x20-\x7e]*", value) or key.lower() in headers):
                raise RuntimeError("invalid console HTTP headers")
            headers[key.lower()] = value.strip(" \t")
        return int(lines[0].split()[1]), headers

    def frame(self, opcode, payload):
        mask = os.urandom(4)
        size = len(payload)
        length = bytes([0x80 | size]) if size < 126 else (
            b"\xfe" + struct.pack("!H", size) if size <= 65535 else b"\xff" + struct.pack("!Q", size))
        self.send(bytes([0x80 | opcode]) + length + mask +
                  bytes(c ^ mask[i % 4] for i, c in enumerate(payload)))

    def receive_frame(self):
        first, second = self.read(2)
        final, opcode = bool(first & 128), first & 15
        if first & 0x70 or second & 128 or opcode not in (0, 1, 2, 8, 9, 10):
            raise RuntimeError("invalid WebSocket frame")
        marker = size = second & 127
        if marker == 126:
            size = struct.unpack("!H", self.read(2))[0]
            if size < 126:
                raise RuntimeError("invalid WebSocket frame length")
        elif marker == 127:
            size = struct.unpack("!Q", self.read(8))[0]
            if size < 65536 or size >= 2 ** 63:
                raise RuntimeError("invalid WebSocket frame length")
        if opcode >= 8 and (not final or size > 125):
            raise RuntimeError("invalid WebSocket control frame")
        if size > MAX_MESSAGE:
            raise RuntimeError("WebSocket frame limit exceeded")
        data = self.read(size)
        if opcode == 8:
            if len(data) == 1:
                raise RuntimeError("invalid WebSocket close frame")
            if data:
                code = struct.unpack("!H", data[:2])[0]
                if not (code in (1000, 1001, 1002, 1003, 1007, 1008, 1009, 1010, 1011, 1012, 1013, 1014)
                        or 3000 <= code <= 4999):
                    raise RuntimeError("invalid WebSocket close code")
                _utf8(data[2:])
        return final, opcode, data

    def close(self):
        self.sock.close()


def _utf8(data):
    try:
        data.decode("utf-8")
    except UnicodeError:
        raise RuntimeError("invalid WebSocket UTF-8") from None


def _request(peer, parsed, path, extra=""):
    peer.send(("GET " + path + " HTTP/1.1\r\nHost: " + parsed.netloc +
               "\r\n" + extra + "\r\n").encode("ascii"))
    return peer.headers()


def _url(base_url):
    if (not isinstance(base_url, str) or len(base_url) > 2048
            or any(ord(c) <= 32 or ord(c) >= 127 for c in base_url)):
        raise ValueError("invalid console URL")
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
        host = parsed.hostname
    except ValueError:
        raise ValueError("invalid console URL") from None
    decoded = unquote(base_url)
    if (parsed.scheme not in ("http", "https") or not host or parsed.username is not None
            or parsed.password is not None or "#" in decoded or "?" in decoded or "%" in decoded
            or port == 0 or parsed.netloc.endswith(":")
            or not re.fullmatch(r"[A-Za-z0-9.:-]+", host)
            or any(part in (".", "..") for part in unquote(parsed.path).split("/"))
            or "\\" in decoded or any(ord(c) <= 32 or ord(c) >= 127 for c in decoded)):
        raise ValueError("invalid console URL")
    # ASCII names still pass through getaddrinfo's IDNA codec. Reject invalid
    # DNS lengths/empty labels here instead of leaking a worker codec failure.
    # Keep bracketed IPv6 literals out of DNS-label validation; a trailing root
    # dot on a DNS name is valid and does not count toward its 253-byte limit.
    if ":" not in host:
        name = host[:-1] if host.endswith(".") else host
        if len(name) > 253 or any(not 0 < len(label) <= 63 for label in name.split(".")):
            raise ValueError("invalid console URL")
    # Browsers omit default ports in Origin. ttyd's -O compares its parsed
    # Origin authority against Host, so both headers must use that form.
    if port == (443 if parsed.scheme == "https" else 80):
        authority = "[" + host + "]" if ":" in host else host
        parsed = parsed._replace(netloc=authority)
    return parsed


def probe_console(base_url, timeout=10.0):
    """Return None after a fresh session reaches the full CROSS input prompt.

    ValueError: invalid caller URL/timeout; TimeoutError: shared deadline;
    RuntimeError: transport, HTTP, WebSocket, or application startup failure.
    Diagnostics deliberately exclude URLs, tokens, headers and terminal output.
    """
    parsed = _url(base_url)
    deadline = _Deadline(timeout)
    try:
        return _probe(parsed, deadline)
    except TimeoutError:
        raise TimeoutError("console startup deadline exceeded") from None
    except OSError:
        raise RuntimeError("console transport failed before startup prompt") from None


def _token_body(peer, headers):
    length = headers.get("content-length")
    transfer = headers.get("transfer-encoding")
    if headers.get("content-encoding", "identity").lower() != "identity" or (length is not None and transfer):
        raise RuntimeError("invalid console token response framing")
    if transfer is None:
        if length is None or not re.fullmatch(r"[0-9]{1,8}", length):
            raise RuntimeError("invalid console token response length")
        size = int(length)
        if size > MAX_HTTP:
            raise RuntimeError("console token response limit exceeded")
        return peer.read(size)
    if transfer.lower() != "chunked":
        raise RuntimeError("invalid console token transfer encoding")

    def line():
        data = bytearray()
        while not data.endswith(b"\r\n"):
            data.extend(peer.read(1))
            if len(data) > 1024:
                raise RuntimeError("console token chunk header limit exceeded")
        return bytes(data[:-2])

    body = bytearray()
    while True:
        chunk = line().split(b";", 1)[0]
        if not re.fullmatch(b"[0-9a-fA-F]{1,8}", chunk):
            raise RuntimeError("invalid console token chunk")
        size = int(chunk, 16)
        if size > MAX_HTTP - len(body):
            raise RuntimeError("console token response limit exceeded")
        if size == 0:
            trailers = 0
            while True:
                trailer = line()
                trailers += len(trailer) + 2
                if trailers > MAX_HTTP:
                    raise RuntimeError("console token trailer limit exceeded")
                if not trailer:
                    return bytes(body)
        body.extend(peer.read(size))
        if peer.read(2) != b"\r\n":
            raise RuntimeError("invalid console token chunk terminator")


def _probe(parsed, deadline):
    prefix = parsed.path.rstrip("/") + "/"
    peer = _Peer(parsed, deadline)
    try:
        status, headers = _request(peer, parsed, prefix + "token", "Connection: close\r\n")
        if status != 200:
            raise RuntimeError("console token request failed (no redirects allowed)")
        try:
            token = json.loads(_token_body(peer, headers))["token"]
            if not isinstance(token, str):
                raise ValueError
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
            raise RuntimeError("invalid console token response") from None
    finally:
        peer.close()
    peer = _Peer(parsed, deadline)
    upgraded = False
    try:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        status, headers = _request(peer, parsed, prefix + "ws",
            "Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: " + key +
            "\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: tty\r\nOrigin: " +
            parsed.scheme + "://" + parsed.netloc + "\r\n")
        expected = base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")
        if (peer.http_version != "HTTP/1.1" or status != 101 or headers.get("upgrade", "").lower() != "websocket"
                or "upgrade" not in [s.strip().lower() for s in headers.get("connection", "").split(",")]
                or headers.get("sec-websocket-accept") != expected
                or headers.get("sec-websocket-protocol") != "tty"
                or "sec-websocket-extensions" in headers):
            raise RuntimeError("invalid WebSocket upgrade")
        upgraded = True
        peer.frame(2, json.dumps({"AuthToken": token, "columns": 80, "rows": 24}).encode())
        stdout = b""
        message = bytearray()
        message_opcode = 2
        fragmented = False
        while True:
            final, opcode, data = peer.receive_frame()
            if opcode == 8:
                peer.frame(8, data)
                upgraded = False
                raise RuntimeError("console connection closed before startup prompt")
            if opcode == 9:
                peer.frame(10, data)
                continue
            if opcode == 10:
                continue
            if opcode in (1, 2):
                if fragmented:
                    raise RuntimeError("invalid WebSocket fragmentation")
                message_opcode = opcode
                message = bytearray(data)
                fragmented = not final
            elif opcode == 0 and fragmented:
                if len(data) > MAX_MESSAGE - len(message):
                    raise RuntimeError("WebSocket message limit exceeded")
                message.extend(data)
                fragmented = not final
            else:
                raise RuntimeError("invalid WebSocket fragmentation")
            if not final:
                continue
            data = bytes(message)
            if message_opcode == 1:
                _utf8(data)
            if data.startswith(b"0"):
                stdout += data[1:]
                if PROMPT in stdout:
                    deadline.remaining()
                    return None
                stdout = stdout[-(len(PROMPT) - 1):]
    finally:
        if upgraded:
            try:
                peer.frame(8, b"\x03\xe8")
            except (OSError, TimeoutError):
                pass
        peer.close()


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes arbitrary argument contents, including secrets.
        self.exit(2, "console smoke: invalid command line (use --help)\n")


def main(argv=None):
    """CLI: 0 prompt observed; 1 startup/transport/deadline; 2 bad input."""
    parser = _Parser(description="Probe one fresh ttyd session without sending game moves.")
    parser.add_argument("url", metavar="URL")
    parser.add_argument("--timeout", type=float, default=10.0, metavar="SECONDS")
    args = parser.parse_args(argv)
    try:
        probe_console(args.url, args.timeout)
    except ValueError as exc:
        print("console smoke: " + str(exc), file=sys.stderr)
        return 2
    except (RuntimeError, TimeoutError) as exc:
        print("console smoke: " + str(exc), file=sys.stderr)
        return 1
    print("console startup prompt observed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
