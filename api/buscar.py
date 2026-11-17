"""
POST /api/buscar
Body JSON: {"texto": "nombre o EAN", "ean": "opcional", "modo": "ambos|ean|imagen",
            "solo_oficiales": false, "validar_ia": null | "web" | "todas"}
Devuelve el resultado de un único producto. La página web llama a este endpoint una vez por producto.
"""

import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _comun import autorizado, responder_json, leer_json  # noqa: E402
from buscador_productos import procesar_un_producto, MODOS, VALIDAR_IA_OPCIONES  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not autorizado(self):
            return responder_json(self, {"error": "Clave de acceso incorrecta"}, 401)

        datos = leer_json(self)
        texto = str(datos.get("texto") or "").strip()[:300]
        ean = str(datos.get("ean") or "").strip()[:20] or None
        modo = datos.get("modo") if datos.get("modo") in MODOS else "ambos"
        if not texto and not ean:
            return responder_json(self, {"error": "Falta el nombre del producto o el EAN"}, 400)

        try:
            res = procesar_un_producto(
                nombre_original=texto or ean,
                modo=modo,
                ean_conocido=ean,
                serper_key=os.environ.get("SERPER_API_KEY") or None,
                carpeta_imagenes=None,
                solo_oficiales_vtex=bool(datos.get("solo_oficiales")),
                validar_ia=datos.get("validar_ia") if datos.get("validar_ia") in VALIDAR_IA_OPCIONES else None,
            )
        except Exception as e:  # nunca devolver un 500 sin explicación a la página
            return responder_json(self, {"error": f"Error interno: {e}"}, 500)

        res.pop("Imagen_Local", None)
        return responder_json(self, res)

    def do_GET(self):
        return responder_json(self, {"error": "Usá POST"}, 405)
