"""
GET /api/estado
  -> {"requiere_clave", "ia_disponible", "modelo_ia", "tiendas"}  (configuración para la página)
GET /api/estado?diagnostico=1
  -> prueba si cada tienda VTEX y DuckDuckGo responden desde el servidor de Vercel.
"""

import os
import sys
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _comun import autorizado, clave_requerida, responder_json  # noqa: E402
from buscador_productos import TIENDAS_VTEX, session, _pool_tiendas, _importar_ddgs, ia_disponible, MODELO_VISION  # noqa: E402

EAN_PRUEBA = "7790895000997"  # Coca-Cola 2,25 L, presente en casi todos los supermercados


def _probar_tienda(nombre, dominio):
    t = time.time()
    try:
        r = session.get(
            f"https://{dominio}/api/catalog_system/pub/products/search?fq=alternateIds_Ean:{EAN_PRUEBA}",
            timeout=6,
        )
        ok = r.status_code in (200, 206)
        detalle = f"HTTP {r.status_code}"
        if ok:
            detalle += f", {len(r.json() or [])} producto(s)"
    except Exception as e:
        ok, detalle = False, type(e).__name__
    return {"fuente": nombre, "ok": ok, "detalle": detalle, "ms": int((time.time() - t) * 1000)}


def _probar_ddg():
    t = time.time()
    DDGS = _importar_ddgs()
    if DDGS is None:
        return {"fuente": "DuckDuckGo", "ok": False, "detalle": "librería no instalada", "ms": 0}
    try:
        with DDGS() as dd:
            n = len(dd.images("coca cola 2.25 lt", max_results=3))
        ok, detalle = n > 0, f"{n} imagen(es)"
    except Exception as e:
        ok, detalle = False, type(e).__name__
    return {"fuente": "DuckDuckGo", "ok": ok, "detalle": detalle, "ms": int((time.time() - t) * 1000)}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        if "diagnostico" not in params:
            return responder_json(self, {
                "requiere_clave": bool(clave_requerida()),
                "ia_disponible": ia_disponible(),
                "modelo_ia": MODELO_VISION,
                "tiendas": [n for n, _ in TIENDAS_VTEX],
            })

        if not autorizado(self):
            return responder_json(self, {"error": "Clave de acceso incorrecta"}, 401)

        futuros = [_pool_tiendas.submit(_probar_tienda, n, d) for n, d in TIENDAS_VTEX]
        resultados = [f.result() for f in futuros] + [_probar_ddg()]
        return responder_json(self, {
            "region": os.environ.get("VERCEL_REGION", "local"),
            "serper_configurado": bool(os.environ.get("SERPER_API_KEY")),
            "ia_disponible": ia_disponible(),
            "modelo_ia": MODELO_VISION,
            "resultados": resultados,
        })
