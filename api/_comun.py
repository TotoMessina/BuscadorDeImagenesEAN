"""Utilidades compartidas por las funciones de Vercel (los archivos con _ no se publican como endpoint)."""

import hmac
import json
import os
import sys

# Permite importar buscador_productos.py desde la raíz del proyecto
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


def clave_requerida():
    """Si se define la variable CLAVE_ACCESO en Vercel, la API pide esa clave."""
    return os.environ.get("CLAVE_ACCESO", "").strip()


def autorizado(handler):
    clave = clave_requerida()
    if not clave:
        return True
    enviada = handler.headers.get("X-Clave", "")
    return hmac.compare_digest(enviada.encode(), clave.encode())


def responder_json(handler, datos, status=200):
    cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(cuerpo)))
    handler.end_headers()
    handler.wfile.write(cuerpo)


def leer_json(handler):
    largo = int(handler.headers.get("Content-Length") or 0)
    if largo <= 0 or largo > 100_000:
        return {}
    try:
        return json.loads(handler.rfile.read(largo).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
