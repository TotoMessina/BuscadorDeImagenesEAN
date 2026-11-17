"""
GET /api/imagen?url=<url de la imagen>
Descarga una imagen a través del servidor para poder meterla en el ZIP desde el navegador
(muchas tiendas no permiten descargarlas directo desde otra web por CORS).
Solo devuelve archivos que sean realmente imágenes y de menos de 4 MB.
"""

import ipaddress
import os
import socket
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _comun import autorizado, responder_json  # noqa: E402
from buscador_productos import session  # noqa: E402

TAMANO_MAXIMO = 4 * 1024 * 1024  # Vercel no permite respuestas de más de 4,5 MB


def _host_publico(host):
    """Evita que se use el endpoint para acceder a direcciones internas."""
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except (socket.gaierror, ValueError):
        return False


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not autorizado(self):
            return responder_json(self, {"error": "Clave de acceso incorrecta"}, 401)

        url = (parse_qs(urlparse(self.path).query).get("url") or [""])[0]

        try:
            # Sigue hasta 3 redirecciones, validando cada destino
            for _ in range(4):
                partes = urlparse(url)
                if partes.scheme not in ("http", "https") or not partes.hostname \
                        or not _host_publico(partes.hostname):
                    return responder_json(self, {"error": "URL no válida"}, 400)
                r = session.get(url, stream=True, timeout=12, allow_redirects=False)
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
                    url = requests.compat.urljoin(url, r.headers["Location"])
                    continue
                break
            tipo = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if r.status_code != 200 or not tipo.startswith("image/"):
                return responder_json(self, {"error": f"No es una imagen (HTTP {r.status_code})"}, 502)
            datos = bytearray()
            for chunk in r.iter_content(chunk_size=65536):
                datos.extend(chunk)
                if len(datos) > TAMANO_MAXIMO:
                    return responder_json(self, {"error": "Imagen demasiado grande"}, 413)
        except Exception as e:
            return responder_json(self, {"error": f"No se pudo descargar: {type(e).__name__}"}, 502)

        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(bytes(datos))
