"""Synthetic isolated HTTP/WebSocket fixtures; not genuine JAR/game proof."""
import base64
from contextlib import contextmanager, redirect_stderr
import io
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import selectors
import re
import socket
import socketserver
import struct
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock
from urllib.parse import urlsplit
from typing import Any, Dict, Tuple

PROMPT = b"where to put the next CROSS? (0-8): "
TOKEN = "synthetic-test-token-PRIVATE"


def frame(payload, opcode=2, final=True):
    head = bytes([(0x80 if final else 0) | opcode])
    n = len(payload)
    if n < 126:
        return head + bytes([n]) + payload
    if n <= 65535:
        return head + b"\x7e" + struct.pack("!H", n) + payload
    return head + b"\x7f" + struct.pack("!Q", n) + payload


def client_frame(stream):
    def exact(n):
        data = stream.read(n)
        if len(data) != n:
            raise EOFError
        return data
    first, second = exact(2)
    assert first & 0x80, "client fragments unexpectedly"
    assert second & 0x80, "client frames must be masked"
    size = second & 127
    if size == 126:
        size = struct.unpack("!H", exact(2))[0]
    elif size == 127:
        size = struct.unpack("!Q", exact(8))[0]
    assert size < 32768, "unexpected client frame size"
    mask = exact(4)
    data = exact(size)
    return first & 15, bytes(c ^ mask[i % 4] for i, c in enumerate(data)), mask


@contextmanager
def synthetic_server(on_ws=None, token_status=200, token_body=None, upgrade=None, token_delay=0.0,
                     token_headers=None, ws_status="HTTP/1.1 101 Switching Protocols", upgrade_delay=0.0):
    """Real loopback sockets, synthetic ttyd wire peer (never an app proof)."""
    state = {"requests": [], "frames": [], "errors": [], "closed": threading.Event()}
    response_body = json.dumps({"token": TOKEN}).encode() if token_body is None else token_body

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.request.settimeout(2)
            request = self.rfile.readline().decode("ascii").strip().split()
            if not request:
                return
            path = request[1]
            headers = {}
            while True:
                line = self.rfile.readline()
                if line == b"\r\n" or not line:
                    break
                key, value = line.decode("ascii").split(":", 1)
                headers[key.lower()] = value.strip()
            state["requests"].append((path, headers))
            try:
                if path.endswith("/token"):
                    time.sleep(token_delay)
                    extra = token_headers or {"Content-Length": str(len(response_body))}
                    response = "HTTP/1.1 %d Test\r\n" % token_status
                    response += "".join("%s: %s\r\n" % pair for pair in extra.items())
                    self.wfile.write(response.encode() + b"\r\n" + response_body)
                elif path.endswith("/ws"):
                    accept = base64.b64encode(hashlib.sha1((headers["sec-websocket-key"] +
                        "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
                    reply = {"Upgrade": "websocket", "Connection": "Upgrade",
                             "Sec-WebSocket-Accept": accept, "Sec-WebSocket-Protocol": "tty"}
                    if upgrade:
                        reply.update(upgrade)
                    time.sleep(upgrade_delay)
                    response = (ws_status + "\r\n").encode() + "".join(
                        "%s: %s\r\n" % pair for pair in reply.items()).encode() + b"\r\n"
                    self.wfile.write(response)
                    state["frames"].append(client_frame(self.rfile))
                    if on_ws:
                        on_ws(self, state)
                    else:
                        self.wfile.write(frame(b"0synthetic fixture\r\n" + PROMPT))
                        state["frames"].append(client_frame(self.rfile))
                else:
                    # Correct metadata never establishes WebSocket/JVM health.
                    self.wfile.write(b"HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\nv9.9.9")
            except (BrokenPipeError, ConnectionResetError, EOFError):
                pass
            except Exception as exc:
                state["errors"].append(repr(exc))
            finally:
                if path.endswith("/ws"):
                    state["closed"].set()

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = False
        allow_reuse_address = True
    with Server(("127.0.0.1", 0), Handler) as server:
        state["url"] = "http://127.0.0.1:%d/console/" % server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield state
        finally:
            server.shutdown()
            thread.join(2)
    if state["errors"]:
        raise AssertionError(state["errors"])

@contextmanager
def silent_tcp_server():
    """Synthetic TLS-handshake stall: real socket, no certificate or key files."""
    closed = threading.Event()
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(2)
            try:
                while self.request.recv(4096):
                    pass
            except OSError:
                pass
            finally:
                closed.set()
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield "https://127.0.0.1:%d/console/" % server.server_address[1], closed
        finally:
            server.shutdown()
            thread.join(2)


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "console-smoke.py"


def load_client():
    assert SCRIPT.is_file(), "console smoke library is missing"
    spec = importlib.util.spec_from_file_location("console_smoke", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


client = load_client()


class ConsoleSmokeTests(unittest.TestCase):
    def test_prompt_opens_private_fresh_session_then_closes_without_moves(self):
        with synthetic_server() as state:
            self.assertIsNone(client.probe_console(state["url"], timeout=1))
            self.assertTrue(state["closed"].wait(1), "client did not close its own session")
            self.assertEqual([p for p, _ in state["requests"]], ["/console/token", "/console/ws"])
            parsed = urlsplit(state["url"])
            self.assertEqual(state["requests"][1][1]["origin"], parsed.scheme + "://" + parsed.netloc)
            self.assertEqual(state["requests"][1][1]["sec-websocket-protocol"], "tty")
            self.assertEqual(state["frames"][0][0], 2)
            self.assertEqual(json.loads(state["frames"][0][1]), {"AuthToken": TOKEN, "columns": 80, "rows": 24})
            self.assertEqual(state["frames"][1][:2], (8, b"\x03\xe8"))
            self.assertNotEqual(state["frames"][0][2], state["frames"][1][2])

    def test_startup_failure_close_wins_over_correct_metadata_or_later_bytes(self):
        def failing(handler, state):
            handler.wfile.write(frame(b"1" + PROMPT) + frame(b"0Error: bad Java exit\r\n") +
                                frame(b"\x03\xf3", opcode=8) + frame(b"0" + PROMPT))
            state["frames"].append(client_frame(handler.rfile))
        with synthetic_server(on_ws=failing) as state:
            parsed = urlsplit(state["url"])
            for path in ("/version.txt", "/backend/version.txt"):
                connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=1)
                try:
                    connection.request("GET", path)
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read(), b"v9.9.9")
                finally:
                    connection.close()
            with self.assertRaisesRegex(RuntimeError, "closed before startup prompt"):
                client.probe_console(state["url"], timeout=1)
            self.assertTrue(state["closed"].wait(1))
            self.assertEqual(state["frames"][-1][:2], (8, b"\x03\xf3"))

    def test_rejects_invalid_websocket_upgrade_before_sending_private_token(self):
        for changed in ({"Upgrade": "h2c"}, {"Connection": "close"},
                        {"Sec-WebSocket-Accept": "wrong"}, {"Sec-WebSocket-Protocol": "other"},
                        {"Sec-WebSocket-Protocol": ""}, {"Sec-WebSocket-Extensions": "permessage-deflate"}):
            with self.subTest(changed=changed), synthetic_server(upgrade=changed) as state:
                with self.assertRaisesRegex(RuntimeError, "invalid WebSocket upgrade"):
                    client.probe_console(state["url"], timeout=1)
                self.assertTrue(state["closed"].wait(1))
                self.assertEqual(state["frames"], [])

    def test_token_failure_never_upgrades_or_follows_redirects(self):
        for status, body in ((302, json.dumps({"token": TOKEN}).encode()),
                             (401, b"unauthorized"), (200, b"not-json-" + TOKEN.encode()),
                             (200, b"{}"), (200, b'{"token": 123}')):
            with self.subTest(status=status, body=body), synthetic_server(token_status=status, token_body=body) as state:
                with self.assertRaisesRegex(RuntimeError, "token") as caught:
                    client.probe_console(state["url"], timeout=1)
                self.assertNotIn(TOKEN, str(caught.exception))
                self.assertLess(len(str(caught.exception)), 200)
                self.assertEqual([p for p, _ in state["requests"]], ["/console/token"])

    def test_fragmented_prompt_with_interleaved_ping_requires_masked_pong(self):
        def fragmented(handler, state):
            handler.wfile.write(frame(b"0" + PROMPT[:17], final=False) +
                                frame(b"0" + PROMPT, opcode=9))
            state["frames"].append(client_frame(handler.rfile))
            if state["frames"][-1][:2] == (10, b"0" + PROMPT):
                handler.wfile.write(frame(PROMPT[17:25], opcode=0, final=False) +
                                    frame(PROMPT[25:], opcode=0))
                state["frames"].append(client_frame(handler.rfile))
        with synthetic_server(on_ws=fragmented) as state:
            client.probe_console(state["url"], timeout=1)
            self.assertTrue(state["closed"].wait(1))
            self.assertEqual([f[0] for f in state["frames"]], [2, 10, 8])
            self.assertEqual(state["frames"][1][1], b"0" + PROMPT)

    def test_extended_frame_lengths_and_prompt_across_stdout_messages(self):
        def extended(handler, state):
            handler.wfile.write(frame(b"0" + b"x" * state["size"] + PROMPT[:16]) +
                                frame(b"2" + PROMPT) + frame(b"0" + PROMPT[16:]))
            state["frames"].append(client_frame(handler.rfile))
        for size in (130, 70000):
            body = json.dumps({"token": "x" * 200}).encode()
            with self.subTest(size=size), synthetic_server(on_ws=extended, token_body=body) as state:
                state["size"] = size
                client.probe_console(state["url"], timeout=1)
                self.assertTrue(state["closed"].wait(1))
                self.assertEqual(json.loads(state["frames"][0][1])["AuthToken"], "x" * 200)

    def test_invalid_websocket_frames_cannot_establish_health(self):
        malformed = [b"\xc2\x00", b"\x82\x80" + b"abcd", frame(b"", opcode=3),
                     frame(b"", opcode=9, final=False), frame(b"x" * 126, opcode=9),
                     frame(b"", opcode=0), frame(b"0first", final=False) + frame(b"0second"),
                     b"\x82\x7e\x00\x01x", b"\x82\x7f" + struct.pack("!Q", 1) + b"x",
                     b"\x82\x7f" + struct.pack("!Q", 2 ** 63),
                     b"\x82\x7f" + struct.pack("!Q", 1048577),
                     frame(b"x", opcode=8), frame(b"\x03\xee", opcode=8),
                     frame(b"\x03\xe8\xff", opcode=8), frame(b"\xff", opcode=1)]
        for wire in malformed:
            def invalid(handler, state):
                handler.wfile.write(wire + frame(b"0" + PROMPT))
                state["frames"].append(client_frame(handler.rfile))
            with self.subTest(wire=wire[:20]), synthetic_server(on_ws=invalid) as state:
                with self.assertRaisesRegex(RuntimeError, "invalid WebSocket|WebSocket .*limit"):
                    client.probe_console(state["url"], timeout=0.3)
                self.assertTrue(state["closed"].wait(1))

    def test_response_header_token_message_and_total_caps(self):
        cases: Tuple[Dict[str, Any], ...] = (
            {"token_headers": {"Content-Length": "0", "X-Large": "x" * 17000}},
            {"token_body": json.dumps({"token": "x" * 17000}).encode()})
        for options in cases:
            with self.subTest(kind=list(options)), synthetic_server(**options) as state:
                with self.assertRaisesRegex(RuntimeError, "limit"):
                    client.probe_console(state["url"], timeout=1)
        for kind in ("message", "total"):
            def excessive(handler, state):
                if kind == "message":
                    wire = frame(b"0" + b"x" * 600000, final=False) + frame(b"x" * 600000, opcode=0)
                else:
                    wire = frame(b"0" + b"x" * 100000) * 43
                handler.wfile.write(wire + frame(b"0" + PROMPT))
                state["frames"].append(client_frame(handler.rfile))
            with self.subTest(kind=kind), synthetic_server(on_ws=excessive) as state:
                with self.assertRaisesRegex(RuntimeError, "limit"):
                    client.probe_console(state["url"], timeout=2)
                self.assertTrue(state["closed"].wait(1))

    def test_one_deadline_covers_token_and_continuous_nonprompt_output_and_cleanup(self):
        def noisy(handler, state):
            for _ in range(100):
                handler.wfile.write(frame(b"0synthetic noise\r\n"))
                time.sleep(0.01)
        with synthetic_server(on_ws=noisy, token_delay=0.06) as state:
            start = time.monotonic()
            with self.assertRaisesRegex(TimeoutError, "deadline exceeded"):
                client.probe_console(state["url"], timeout=0.16)
            elapsed = time.monotonic() - start
            self.assertGreater(elapsed, 0.13)
            self.assertLess(elapsed, 0.3)
            self.assertTrue(state["closed"].wait(1), "deadline leaked a client")
        with synthetic_server(token_delay=0.3) as state:
            with self.assertRaisesRegex(TimeoutError, "deadline exceeded"):
                client.probe_console(state["url"], timeout=0.05)
            self.assertEqual([p for p, _ in state["requests"]], ["/console/token"])

    def test_invalid_timeout_is_valueerror_before_network(self):
        with synthetic_server() as state:
            for seconds in (0, -1, float("nan"), float("inf"), 1e300, "1", None, True):
                with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                    client.probe_console(state["url"], timeout=seconds)
            self.assertEqual(state["requests"], [])

    def test_dns_resolution_is_inside_deadline_without_late_connection(self):
        original = socket.getaddrinfo
        finished = threading.Event()
        def slow_dns(*args, **kwargs):
            try:
                time.sleep(0.2)
                return original(*args, **kwargs)
            finally:
                finished.set()
        with synthetic_server() as state, mock.patch.object(client.socket, "getaddrinfo", slow_dns):
            start = time.monotonic()
            with self.assertRaises(TimeoutError):
                client.probe_console(state["url"].replace("127.0.0.1", "localhost"), timeout=0.04)
            self.assertLess(time.monotonic() - start, 0.15)
            self.assertTrue(finished.wait(1))
            self.assertEqual(state["requests"], [])

    def test_dns_worker_errors_are_prompt_private_cli_failures_without_tracebacks(self):
        errors = (UnicodeEncodeError("idna", TOKEN, 0, len(TOKEN), "private-" + TOKEN),
                  ValueError(TOKEN * 100), OSError(TOKEN * 100))
        for error in errors:
            with self.subTest(error=type(error).__name__), \
                    mock.patch.object(client.socket, "getaddrinfo", side_effect=error), \
                    mock.patch.object(client.socket, "socket") as create_socket:
                stderr = io.StringIO()
                start = time.monotonic()
                with redirect_stderr(stderr):
                    code = client.main(["http://localhost/console/", "--timeout", "0.4"])
                self.assertEqual(code, 1)
                self.assertEqual(stderr.getvalue(), "console smoke: console address resolution failed\n")
                self.assertLess(time.monotonic() - start, 0.15)
                create_socket.assert_not_called()

    def test_overlong_dns_names_are_rejected_before_network_with_private_cli_error(self):
        host = "a" * 64 + ".example"
        result = subprocess.run([sys.executable, str(SCRIPT), "http://" + host + "/", "--timeout", "0.4"],
                                capture_output=True, timeout=2)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"console smoke: invalid console URL\n")
        hosts = (host, ".".join(["a" * 63] * 4), "localhost..", ".localhost")
        with mock.patch.object(client, "_connect", side_effect=AssertionError("invalid DNS name reached transport")):
            for host in hosts:
                with self.subTest(host=host), self.assertRaisesRegex(ValueError, "invalid console URL"):
                    client.probe_console("http://" + host + "/")
        for url, expected_host, expected_authority in (
                ("http://127.0.0.1:80/", "127.0.0.1", "127.0.0.1"),
                ("https://[::1]:443/", "::1", "[::1]"),
                ("http://[::1]:8080/", "::1", "[::1]:8080"),
                ("https://localhost.:443/", "localhost.", "localhost.")):
            with self.subTest(url=url):
                parsed = client._url(url)
                self.assertEqual(parsed.hostname, expected_host)
                self.assertEqual(parsed.netloc, expected_authority)

    def test_malformed_http_headers_are_safe_runtime_failures(self):
        cases = ({"Sec-WebSocket-Accept": "wrong\r\nSec-WebSocket-Accept: second"},
                 {"X-Bad": "x\nBare: injected"}, {" Folded": "bad"},
                 {"X-Bad": "secret-" + TOKEN + "\x00"},
                 {"Connection": "Upgrade\r\nConnection: Upgrade"})
        for headers in cases:
            with self.subTest(headers=headers), synthetic_server(upgrade=headers) as state:
                with self.assertRaisesRegex(RuntimeError, "HTTP") as caught:
                    client.probe_console(state["url"], timeout=1)
                self.assertNotIn(TOKEN, str(caught.exception))
                self.assertTrue(state["closed"].wait(1))
                self.assertEqual(state["frames"], [])

    def test_cli_exit_codes_and_diagnostics_are_bounded_and_private(self):
        for args in (["http://u:" + TOKEN + "@localhost/"], ["http://localhost/", "--timeout", TOKEN],
                     ["http://localhost/", "--unknown-" + TOKEN]):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, str(SCRIPT)] + args, capture_output=True, timeout=2)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                self.assertNotIn(TOKEN.encode(), result.stderr)
                self.assertNotIn(b"Traceback", result.stderr)
                self.assertLess(len(result.stderr), 256)
        for failure in (False, True):
            with self.subTest(failure=failure), synthetic_server(token_status=401 if failure else 200) as state:
                result = subprocess.run([sys.executable, str(SCRIPT), state["url"], "--timeout", "0.5"],
                                        capture_output=True, timeout=2)
                self.assertEqual(result.returncode, 1 if failure else 0)
                self.assertNotIn(TOKEN.encode(), result.stdout + result.stderr)
                self.assertLess(len(result.stdout + result.stderr), 256)
                if not failure:
                    self.assertIn(b"prompt observed", result.stdout)
                    self.assertTrue(state["closed"].wait(1))

    def test_chunked_token_body_is_bounded_and_rejects_ambiguous_framing(self):
        body = json.dumps({"token": TOKEN}).encode()
        chunks = b"%x\r\n" % 9 + body[:9] + b"\r\n%x\r\n" % (len(body) - 9) + body[9:] + b"\r\n0\r\n\r\n"
        with self.subTest(kind="chunked success"), synthetic_server(token_body=chunks, token_headers={"Transfer-Encoding": "chunked"}) as state:
            client.probe_console(state["url"], timeout=1)
            self.assertTrue(state["closed"].wait(1))
            self.assertEqual(json.loads(state["frames"][0][1])["AuthToken"], TOKEN)
        for headers, response in (({"Transfer-Encoding": "chunked", "Content-Length": str(len(body))}, body),
                                  ({"Content-Encoding": "gzip", "Content-Length": str(len(body))}, body),
                                  ({"Transfer-Encoding": "chunked"}, b"100000\r\n"),
                                  ({"Transfer-Encoding": "chunked"}, b"nothex\r\n")):
            with self.subTest(headers=headers), synthetic_server(token_body=response, token_headers=headers) as state:
                with self.assertRaisesRegex(RuntimeError, "token"):
                    client.probe_console(state["url"], timeout=1)
                self.assertEqual([p for p, _ in state["requests"]], ["/console/token"])

    def test_tls_context_over_budget_returns_off_main_thread_without_late_network(self):
        context = client.ssl.create_default_context()
        factory_threads = []
        outcomes = []
        def slow_context():
            factory_threads.append(threading.current_thread())
            time.sleep(0.2)
            return context
        def probe():
            start = time.monotonic()
            try:
                client.probe_console("https://127.0.0.1/console/", timeout=0.04)
            except Exception as exc:
                outcomes.append((exc, time.monotonic() - start))
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        with mock.patch.object(client.ssl, "create_default_context", slow_context), \
                mock.patch.object(client.socket, "getaddrinfo", return_value=addresses), \
                mock.patch.object(client.socket, "socket") as create_socket, \
                mock.patch.object(context, "wrap_socket") as wrap_socket:
            caller = threading.Thread(target=probe)
            caller.start()
            try:
                caller.join(1)
                self.assertFalse(caller.is_alive(), "probe did not return")
                self.assertEqual(len(outcomes), 1)
                error, elapsed = outcomes[0]
                self.assertIsInstance(error, TimeoutError)
                self.assertLess(elapsed, 0.15, "TLS context setup exceeded the shared deadline")
            finally:
                caller.join(1)
                for worker in factory_threads:
                    if worker is not caller:
                        worker.join(1)
            create_socket.assert_not_called()
            wrap_socket.assert_not_called()

    def test_tls_setup_and_handshake_share_remaining_deadline_and_close_tcp(self):
        context = client.ssl.create_default_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, client.ssl.CERT_REQUIRED)
        def slow_context():
            time.sleep(0.09)
            return context
        with silent_tcp_server() as (url, closed), mock.patch.object(client.ssl, "create_default_context", slow_context):
            start = time.monotonic()
            with self.assertRaises(TimeoutError):
                client.probe_console(url, timeout=0.12)
            self.assertLess(time.monotonic() - start, 0.18)
            self.assertTrue(closed.wait(1), "TLS failure leaked TCP socket")

    def test_rejects_ambiguous_or_oversized_url_without_connecting(self):
        urls = ("http://localhost:0/", "http://localhost:/", "http://local%68ost/console/",
                "http://localhost/%zz", "http://localhost/%250d%250a", "http://localhost/a/../console/",
                "http://localhost/%2e%2e/console/", "http://[::1]junk/console/", "http://localhost/" + "x" * 4096)
        with mock.patch.object(client, "_connect", side_effect=AssertionError("unsafe URL reached transport")):
            for url in urls:
                with self.subTest(url=url[:80]), self.assertRaisesRegex(ValueError, "invalid console URL"):
                    client.probe_console(url)

    def test_upgrade_requires_http11_status101_not_redirect_or_metadata200(self):
        for status in ("HTTP/1.0 101 Switching Protocols", "HTTP/1.1 302 Found", "HTTP/1.1 200 OK"):
            with self.subTest(status=status), synthetic_server(ws_status=status) as state:
                with self.assertRaisesRegex(RuntimeError, "invalid WebSocket upgrade"):
                    client.probe_console(state["url"], timeout=1)
                self.assertTrue(state["closed"].wait(1))
                self.assertEqual(state["frames"], [])

    def test_default_port_authority_matches_browser_origin_for_ttyd_O_check(self):
        for url, expected in (("http://example.test:80/nested/console/", "example.test"),
                              ("https://example.test:443/console/", "example.test"),
                              ("http://example.test:8080/console/", "example.test:8080")):
            with self.subTest(url=url):
                parsed = client._url(url)
                self.assertEqual(parsed.netloc, expected)
                self.assertEqual(parsed.path, url[url.index("/", url.index("://") + 3):])

    def test_cli_is_directly_executable(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK), "smoke CLI must be executable")
        result = subprocess.run([str(SCRIPT), "ftp://invalid.example/"], capture_output=True, timeout=2)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(b"Traceback", result.stderr)

    def test_eof_without_full_stdout_prompt_always_fails_safely(self):
        for output in (b"0synthetic Java failure " + TOKEN.encode() * 1000,
                       b"0" + PROMPT[:-1], b"1" + PROMPT, b"2" + PROMPT):
            def eof(handler, state):
                handler.wfile.write(frame(output))
            with self.subTest(prefix=output[:20]), synthetic_server(on_ws=eof) as state:
                with self.assertRaisesRegex(RuntimeError, "closed before startup prompt") as caught:
                    client.probe_console(state["url"], timeout=1)
                self.assertNotIn(TOKEN, str(caught.exception))
                self.assertLess(len(str(caught.exception)), 200)
                self.assertTrue(state["closed"].wait(1))

    def test_nested_prefix_and_proxy_environment_do_not_change_target(self):
        proxies = {key: "http://127.0.0.1:9" for key in
                   ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")}
        proxies.update({"NO_PROXY": "", "no_proxy": ""})
        with mock.patch.dict(os.environ, proxies):
            for prefix in ("/nested/console", "/nested/console/", "/"):
                with self.subTest(prefix=prefix), synthetic_server() as state:
                    parsed = urlsplit(state["url"])
                    url = parsed._replace(path=prefix).geturl()
                    client.probe_console(url, timeout=1)
                    self.assertTrue(state["closed"].wait(1))
                    expected = prefix.rstrip("/") + "/"
                    self.assertEqual([p for p, _ in state["requests"]], [expected + "token", expected + "ws"])
                    self.assertEqual(state["requests"][-1][1]["origin"], "http://" + parsed.netloc)

    def test_upgrade_and_slow_frame_bytes_cannot_refresh_deadline(self):
        with synthetic_server(token_delay=0.04, upgrade_delay=0.2) as state:
            start = time.monotonic()
            with self.assertRaises(TimeoutError):
                client.probe_console(state["url"], timeout=0.1)
            self.assertLess(time.monotonic() - start, 0.2)
            self.assertTrue(state["closed"].wait(1))
            self.assertEqual(state["frames"], [])
        def drip(handler, state):
            for byte in frame(b"0" + PROMPT):
                handler.wfile.write(bytes([byte]))
                time.sleep(0.01)
        with synthetic_server(on_ws=drip) as state:
            start = time.monotonic()
            with self.assertRaises(TimeoutError):
                client.probe_console(state["url"], timeout=0.07)
            self.assertLess(time.monotonic() - start, 0.16)
            self.assertTrue(state["closed"].wait(1))

    def test_untrusted_http_redirect_locations_are_never_contacted(self):
        for phase in ("token", "websocket"):
            with self.subTest(phase=phase), synthetic_server() as trap:
                location = trap["url"] + "token?private=" + TOKEN
                body = json.dumps({"token": TOKEN}).encode()
                options: Dict[str, Any] = ({"token_status": 302, "token_body": body,
                            "token_headers": {"Content-Length": str(len(body)), "Location": location}}
                           if phase == "token" else {"ws_status": "HTTP/1.1 302 Found",
                                                     "upgrade": {"Location": location}})
                with synthetic_server(**options) as state:
                    with self.assertRaises(RuntimeError) as caught:
                        client.probe_console(state["url"], timeout=1)
                    self.assertNotIn(TOKEN, str(caught.exception))
                    self.assertEqual(trap["requests"], [])
                    if phase == "websocket":
                        self.assertTrue(state["closed"].wait(1))
                        self.assertEqual(state["frames"], [])

    def test_rejects_unsafe_urls_before_network(self):
        for url in ("ftp://localhost/console/", "http://u:p@localhost/", "http://localhost/#secret",
                    "http://localhost/\r\nInjected: x", "http://localhost/%0d%0aX", "http://localhost/?arg=evil",
                    "http://localhost/\\evil", "http:///console/", "http://localhost:bad/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                client.probe_console(url)


PINNED_TTYD = Path("/home/phil/.local/share/tictactest-webconsole/ttyd.x86_64")
PINNED_SHA256 = "8a217c968aba172e0dbf3f34447218dc015bc4d5e59bf51db2f2cd12b7be4f55"


def ttyd_logs_until(state, predicate):
    end = time.monotonic() + 3
    with selectors.DefaultSelector() as selector:
        selector.register(state["process"].stderr, selectors.EVENT_READ)
        while not predicate(bytes(state["logs"])):
            if time.monotonic() >= end:
                raise AssertionError("owned ttyd fixture log deadline exceeded")
            if not selector.select(end - time.monotonic()):
                continue
            data = os.read(state["process"].stderr.fileno(), 4096)
            if not data or len(state["logs"]) + len(data) > 65536:
                raise AssertionError("owned ttyd fixture exited or exceeded log cap")
            state["logs"].extend(data)


@contextmanager
def owned_pinned_ttyd(command):
    """Pinned real ttyd, synthetic Python command; NOT genuine published-JAR proof."""
    if hashlib.sha256(PINNED_TTYD.read_bytes()).hexdigest() != PINNED_SHA256:
        raise AssertionError("pinned ttyd SHA256 mismatch; refusing execution")
    process = subprocess.Popen([str(PINNED_TTYD), "-p", "0", "-i", "127.0.0.1", "-W", "-O",
                                "-m", "4", "-b", "/console"] + command,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert process.stderr is not None
    state = {"process": process, "logs": bytearray()}
    try:
        ttyd_logs_until(state, lambda logs: b"Listening on port:" in logs)
        match = re.search(rb"Listening on port: ([0-9]+)", state["logs"])
        assert match is not None
        port = int(match[1])
        if port in (7681, 7682, 8000):
            raise AssertionError("owned ttyd unexpectedly selected reserved preview port")
        state["url"] = "http://127.0.0.1:%d/console/" % port
        yield state
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        process.stderr.close()


@unittest.skipUnless(PINNED_TTYD.is_file(), "optional verified ttyd binary is not installed")
class PinnedTtydProtocolTests(unittest.TestCase):
    def test_real_pinned_ttyd_fresh_prompt_sessions_release_all_four_slots(self):
        command = [sys.executable, "-u", "-c", "import time; print(%r, flush=True); time.sleep(30)" % PROMPT.decode()]
        with owned_pinned_ttyd(command) as state:
            for _ in range(6):
                self.assertIsNone(client.probe_console(state["url"], timeout=2))
            ttyd_logs_until(state, lambda logs: logs.count(b"WS closed from") == 6)
            self.assertIn(b"clients: 0", bytes(state["logs"]).split(b"WS closed from")[-1])
            self.assertIn(b"check origin: true", state["logs"])
            self.assertIn(b"ttyd 1.7.7", state["logs"])

    def test_real_pinned_ttyd_bad_command_exit_fails_without_prompt(self):
        with owned_pinned_ttyd([sys.executable, "-c", "print('synthetic startup failure'); raise SystemExit(7)"]) as state:
            with self.assertRaises(RuntimeError):
                client.probe_console(state["url"], timeout=2)
            ttyd_logs_until(state, lambda logs: b"clients: 0" in logs)


if __name__ == "__main__":
    unittest.main()
