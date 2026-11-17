"""
POST /api/candidatas
Body JSON: {"texto": "nombre del producto", "ean": "opcional", "incluir_web": true}
Devuelve {"candidatas": [...]}: productos parecidos de todas las tiendas (con EAN, foto y datos)
y fotos de la web, para que una persona elija la correcta en la pantalla de revisión.
"""

import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _comun import autorizado, responder_json, leer_json  # noqa: E402
from buscador_productos import buscar_candidatas  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not autorizado(self):
            return responder_json(self, {"error": "Clave de acceso incorrecta"}, 401)

        datos = leer_json(self)
        texto = str(datos.get("texto") or "").strip()[:300]
        ean = str(datos.get("ean") or "").strip()[:20] or None
        if not texto and not ean:
            return responder_json(self, {"error": "Falta el nombre del producto o el EAN"}, 400)
        try:
            candidatas = buscar_candidatas(texto, ean=ean, incluir_web=datos.get("incluir_web", True) is not False)
        except Exception as e:
            return responder_json(self, {"error": f"Error interno: {e}"}, 500)
        return responder_json(self, {"candidatas": candidatas})

    def do_GET(self):
        return responder_json(self, {"error": "Usá POST"}, 405)
