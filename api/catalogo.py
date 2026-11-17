"""
Catálogo del equipo (Supabase).

GET  /api/catalogo?q=texto&pagina=0&confirmados=1
     -> {"filas": [...], "total": N, "por_pagina": 50}
POST /api/catalogo  {"accion": "confirmar", "nombre": "nombre en la lista", "resultado": {...columnas del buscador}}
     -> guarda el producto como confirmado por una persona (reemplaza lo que hubiera)
POST /api/catalogo  {"accion": "borrar", "id": 123}
"""

import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _comun import autorizado, responder_json, leer_json  # noqa: E402
import catalogo_db as catalogo  # noqa: E402
from buscador_productos import confirmar_en_catalogo  # noqa: E402

POR_PAGINA = 50


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not autorizado(self):
            return responder_json(self, {"error": "Clave de acceso incorrecta"}, 401)
        if not catalogo.catalogo_disponible():
            return responder_json(self, {"error": catalogo.estado_catalogo()["detalle"]}, 503)
        p = parse_qs(urlparse(self.path).query)
        try:
            pagina = int((p.get("pagina") or ["0"])[0])
        except ValueError:
            pagina = 0
        try:
            filas, total = catalogo.listar(
                texto=(p.get("q") or [""])[0][:100], pagina=pagina, por_pagina=POR_PAGINA,
                solo_confirmados=(p.get("confirmados") or ["0"])[0] == "1",
            )
        except Exception as e:
            return responder_json(self, {"error": str(e)}, 502)
        return responder_json(self, {"filas": filas, "total": total, "por_pagina": POR_PAGINA})

    def do_POST(self):
        if not autorizado(self):
            return responder_json(self, {"error": "Clave de acceso incorrecta"}, 401)
        if not catalogo.catalogo_disponible():
            return responder_json(self, {"error": catalogo.estado_catalogo()["detalle"]}, 503)
        datos = leer_json(self)
        accion = datos.get("accion")

        if accion == "confirmar":
            resultado = datos.get("resultado") or {}
            if not isinstance(resultado, dict):
                return responder_json(self, {"error": "resultado inválido"}, 400)
            nombre = str(datos.get("nombre") or "").strip()[:300]
            ok = confirmar_en_catalogo(nombre, resultado)
            if not ok:
                return responder_json(self, {"error": "No se pudo guardar (falta el nombre, o EAN/foto)"}, 400)
            return responder_json(self, {"ok": True})

        if accion == "borrar":
            try:
                ok = catalogo.borrar(int(datos.get("id")))
            except (TypeError, ValueError):
                return responder_json(self, {"error": "id inválido"}, 400)
            return responder_json(self, {"ok": ok}, 200 if ok else 502)

        return responder_json(self, {"error": "acción desconocida"}, 400)
