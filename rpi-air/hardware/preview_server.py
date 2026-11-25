"""
Podgląd kamery po sieci: GET /foto.jpg → bieżąca klatka JPEG.

Tylko do użytku na ziemi (w locie nie ma sieci i serwer po prostu czeka).
Odpowiada wyłącznie adresom Tailscale (100.64.0.0/10) i temu komputerowi.
"""
import ipaddress
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger(__name__)

_ALLOWED = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("127.0.0.0/8"))


def start_preview_server(camera, port: int) -> ThreadingHTTPServer | None:
    class Handler(BaseHTTPRequestHandler):
        timeout = 5

        def do_GET(self):
            ip = ipaddress.ip_address(self.client_address[0])
            if not any(ip in net for net in _ALLOWED):
                self.send_error(403)
                return
            if self.path.split("?")[0] != "/foto.jpg":
                self.send_error(404)
                return
            jpeg = camera.snapshot_jpeg()
            if jpeg is None:
                self.send_error(503)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpeg)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(jpeg)

        def log_message(self, *args):
            pass

    try:
        srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    except OSError as exc:
        log.warning("Podgląd kamery niedostępny: %s", exc)
        return None
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True, name="preview").start()
    log.info("Podgląd kamery: port %d, /foto.jpg (tylko Tailscale)", port)
    return srv
