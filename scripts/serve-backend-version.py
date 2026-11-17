#!/usr/bin/env python3
"""Serve release-derived version.txt locally with an explicit CORS allowlist."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def create_server(version_file, bind, port, allowed_origins):
    class VersionHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?", 1)[0] != "/version.txt":
                self.send_error(404)
                return
            try:
                body = version_file.read_bytes()
            except OSError:
                self.send_error(503, "Version file unavailable")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Vary", "Origin")
            origin = self.headers.get("Origin")
            if origin and origin in allowed_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer((bind, port), VersionHandler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version_file", type=Path)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7682)
    parser.add_argument("--allow-origin", action="append", default=[])
    args = parser.parse_args()
    with create_server(args.version_file, args.bind, args.port, args.allow_origin) as server:
        print(f"Version endpoint: http://{args.bind}:{server.server_port}/version.txt", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
