"""
Punto de entrada único para Vercel (y para el servidor local dev_server.py).

Vercel detecta este proyecto como "app de Python" y espera un archivo app.py con una
variable `app` (WSGI). Esta app:
  - sirve la página index.html en "/"
  - atiende /api/buscar, /api/estado y /api/imagen usando las clases `handler`
    que están en la carpeta api/ (cada una sigue siendo un archivo independiente).
"""

import importlib.util
import io
import os
import sys
from http.client import parse_headers

RAIZ = os.path.dirname(os.path.abspath(__file__))
CARPETA_API = os.path.join(RAIZ, "api")
for ruta in (RAIZ, CARPETA_API):
    if ruta not in sys.path:
        sys.path.insert(0, ruta)

FUNCIONES = ("buscar", "estado", "imagen", "candidatas", "catalogo")
_handlers = {}


def _cargar_handler(nombre):
    if nombre not in FUNCIONES:
        return None
    if nombre not in _handlers:
        spec = importlib.util.spec_from_file_location(f"api_{nombre}", os.path.join(CARPETA_API, f"{nombre}.py"))
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        _handlers[nombre] = modulo.handler
    return _handlers[nombre]


def _ejecutar_handler(clase, environ):
    """Ejecuta una clase BaseHTTPRequestHandler sobre una petición WSGI y devuelve (status, headers, body)."""
    metodo_http = environ.get("REQUEST_METHOD", "GET").upper()
    try:
        largo = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        largo = 0
    cuerpo = environ["wsgi.input"].read(largo) if largo > 0 else b""

    ruta = environ.get("PATH_INFO") or "/"
    if environ.get("QUERY_STRING"):
        ruta += "?" + environ["QUERY_STRING"]

    lineas = []
    for clave, valor in environ.items():
        if clave.startswith("HTTP_"):
            lineas.append(f"{clave[5:].replace('_', '-').title()}: {valor}")
    if environ.get("CONTENT_TYPE"):
        lineas.append(f"Content-Type: {environ['CONTENT_TYPE']}")
    lineas.append(f"Content-Length: {len(cuerpo)}")
    texto_headers = ("\r\n".join(lineas) + "\r\n\r\n").encode("latin-1", "replace")

    h = clase.__new__(clase)  # sin socket: se completan a mano los atributos que usa el handler
    h.rfile = io.BytesIO(cuerpo)
    h.wfile = io.BytesIO()
    h.headers = parse_headers(io.BytesIO(texto_headers))
    h.command = metodo_http
    h.path = ruta
    h.request_version = "HTTP/1.1"
    h.requestline = f"{metodo_http} {ruta} HTTP/1.1"
    h.client_address = (environ.get("REMOTE_ADDR", "0.0.0.0"), 0)
    h.server = None
    h.close_connection = True
    h.log_message = lambda *args: None

    metodo = getattr(h, f"do_{metodo_http}", None)
    if metodo is None:
        return "405 Method Not Allowed", [("Content-Type", "text/plain; charset=utf-8")], "Método no permitido".encode()
    metodo()

    crudo = h.wfile.getvalue()
    cabecera, _, body = crudo.partition(b"\r\n\r\n")
    lineas_resp = cabecera.decode("latin-1").split("\r\n")
    status = lineas_resp[0].split(" ", 1)[1] if " " in lineas_resp[0] else "500 Internal Server Error"
    headers = []
    for linea in lineas_resp[1:]:
        if ": " in linea:
            k, v = linea.split(": ", 1)
            if k.lower() not in ("connection", "server", "date", "transfer-encoding"):
                headers.append((k, v))
    return status, headers, body


def _archivo_estatico(nombre, tipo):
    with open(os.path.join(RAIZ, nombre), "rb") as f:
        datos = f.read()
    return "200 OK", [("Content-Type", tipo), ("Content-Length", str(len(datos))), ("Cache-Control", "no-cache")], datos


def app(environ, start_response):
    ruta = environ.get("PATH_INFO") or "/"
    try:
        if ruta.startswith("/api/"):
            clase = _cargar_handler(ruta[len("/api/"):].strip("/"))
            if clase is None:
                status, headers, body = "404 Not Found", [("Content-Type", "text/plain; charset=utf-8")], b"No encontrado"
            else:
                status, headers, body = _ejecutar_handler(clase, environ)
        elif ruta in ("/", "/index.html"):
            status, headers, body = _archivo_estatico("index.html", "text/html; charset=utf-8")
        else:
            status, headers, body = "404 Not Found", [("Content-Type", "text/plain; charset=utf-8")], b"No encontrado"
    except Exception as e:  # nunca dejar la petición sin respuesta
        status = "500 Internal Server Error"
        headers = [("Content-Type", "application/json; charset=utf-8")]
        body = ('{"error": "Error interno: %s"}' % str(e).replace('"', "'")).encode("utf-8")

    if not any(k.lower() == "content-length" for k, _ in headers):
        headers.append(("Content-Length", str(len(body))))
    start_response(status, headers)
    return [body]
