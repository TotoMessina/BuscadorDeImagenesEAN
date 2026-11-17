"""
Catálogo compartido del equipo, guardado en Supabase (tabla productos_catalogo).

- Cada producto encontrado con buena confianza, o corregido por una persona, se guarda
  con su nombre normalizado como clave.
- Las búsquedas consultan el catálogo primero: si el producto ya está, la respuesta es instantánea.
- Lo que confirma una persona (pantalla de revisión) tiene prioridad y nunca lo pisa una búsqueda automática.

Configuración (variables de entorno, o archivo .env en esta carpeta para uso local):
  SUPABASE_URL  = https://xxxx.supabase.co
  SUPABASE_KEY  = clave secreta (sb_secret_...). Solo en el servidor: nunca en la página web ni en GitHub.
"""

import os
import re
import sys
import time

import requests

TABLA = "productos_catalogo"
CAMPOS = ("clave", "nombre_original", "ean", "imagen_url", "match_nombre", "marca", "categoria",
          "contenido_neto", "descripcion", "link_producto", "fuente_ean", "fuente_imagen", "score", "confirmado")
_TIMEOUT = 6


def _cargar_env_local():
    """Lee el archivo .env de esta carpeta (uso local). Las variables ya definidas tienen prioridad."""
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(ruta):
        return
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env_local()

_sesion = requests.Session()
_error_config = None   # si la tabla no existe o la clave es inválida, se pausa el catálogo un rato
_error_hasta = 0.0     # (momento hasta el que dura la pausa) para no reintentar en cada producto
_PAUSA_ERROR = 60      # segundos


def _base():
    return os.environ.get("SUPABASE_URL", "").strip().rstrip("/").removesuffix("/rest/v1")


def _headers(extra=None):
    clave = os.environ.get("SUPABASE_KEY", "").strip()
    h = {"apikey": clave, "Content-Type": "application/json"}
    if not clave.startswith("sb_"):  # claves JWT viejas (service_role) también van como Bearer
        h["Authorization"] = f"Bearer {clave}"
    if extra:
        h.update(extra)
    return h


def catalogo_disponible():
    global _error_config
    if _error_config and time.time() >= _error_hasta:
        _error_config = None  # pasó la pausa: se vuelve a intentar (por ej. si ya se creó la tabla)
    return bool(_base() and os.environ.get("SUPABASE_KEY", "").strip()) and _error_config is None


def estado_catalogo():
    """Para el diagnóstico: dict con ok, detalle y cantidad de productos."""
    if not (_base() and os.environ.get("SUPABASE_KEY", "").strip()):
        return {"ok": False, "detalle": "no configurado (faltan SUPABASE_URL / SUPABASE_KEY)", "productos": None}
    try:
        r = _sesion.get(f"{_base()}/rest/v1/{TABLA}", params={"select": "id", "limit": 1},
                        headers=_headers({"Prefer": "count=exact"}), timeout=_TIMEOUT)
        if r.status_code in (200, 206):
            global _error_config
            _error_config = None  # la conexión anda: se levanta cualquier pausa por error
            total = r.headers.get("Content-Range", "").split("/")[-1]
            return {"ok": True, "detalle": "conectado", "productos": int(total) if total.isdigit() else None,
                    "similares": similares_disponible()}
        return {"ok": False, "detalle": _explicar_error(r), "productos": None}
    except requests.RequestException as e:
        return {"ok": False, "detalle": f"sin conexión ({type(e).__name__})", "productos": None}


def _explicar_error(r):
    try:
        datos = r.json()
    except ValueError:
        datos = {}
    if datos.get("code") == "PGRST205":
        return "falta crear la tabla: ejecutá supabase_catalogo.sql en el SQL Editor de Supabase"
    if r.status_code in (401, 403):
        return "clave de Supabase inválida o sin permisos"
    return f"HTTP {r.status_code}: {datos.get('message') or r.text[:120]}"


def _registrar_error(r):
    """Errores de configuración: se pausa el catálogo por un minuto, con un aviso."""
    global _error_config, _error_hasta
    if r.status_code in (401, 403, 404):
        if not _error_config:
            print(f"[CATÁLOGO] Pausado: {_explicar_error(r)}", file=sys.stderr, flush=True)
        _error_config = _explicar_error(r)
        _error_hasta = time.time() + _PAUSA_ERROR


def clave_producto(nombre_limpio):
    """Clave para reconocer el mismo producto en distintas listas (nombre ya limpio por el buscador)."""
    return re.sub(r"\s+", " ", str(nombre_limpio or "")).strip().lower()[:300] or None


def buscar(clave=None, ean=None):
    """Devuelve la fila del catálogo para esa clave (o, si no hay, para ese EAN), o None."""
    if not catalogo_disponible() or not (clave or ean):
        return None
    intentos = []
    if clave:
        intentos.append({"clave": f"eq.{clave}"})
    if ean:
        intentos.append({"ean": f"eq.{ean}", "order": "confirmado.desc,usos.desc"})
    for filtro in intentos:
        try:
            r = _sesion.get(f"{_base()}/rest/v1/{TABLA}", params={"select": "*", "limit": 1, **filtro},
                            headers=_headers(), timeout=_TIMEOUT)
        except requests.RequestException:
            return None
        if r.status_code != 200:
            _registrar_error(r)
            return None
        filas = r.json()
        if filas:
            return filas[0]
    return None


_similares_pausa_hasta = 0.0  # si falta la función en Supabase, no reintentar en cada producto


def similares(clave, limite=5, umbral=0.4):
    """
    Productos del catálogo con nombre parecido (función catalogo_similares, ver supabase_similares.sql).
    Devuelve una lista de filas con el campo extra "similitud" (0 a 1), o [] si no está disponible.
    """
    global _similares_pausa_hasta
    if not catalogo_disponible() or not clave or time.time() < _similares_pausa_hasta:
        return []
    try:
        r = _sesion.post(f"{_base()}/rest/v1/rpc/catalogo_similares",
                         json={"p_clave": clave, "p_limite": int(limite), "p_umbral": float(umbral)},
                         headers=_headers(), timeout=_TIMEOUT)
    except requests.RequestException:
        return []
    if r.status_code != 200:
        if r.status_code == 404:
            if time.time() >= _similares_pausa_hasta:
                print("[CATÁLOGO] Falta la búsqueda de parecidos: ejecutá supabase_similares.sql en Supabase",
                      file=sys.stderr, flush=True)
            _similares_pausa_hasta = time.time() + _PAUSA_ERROR
        return []
    return r.json() or []


def similares_disponible():
    """Para el diagnóstico: ¿está instalada la función de búsqueda de parecidos?"""
    if not catalogo_disponible():
        return False
    try:
        r = _sesion.post(f"{_base()}/rest/v1/rpc/catalogo_similares",
                         json={"p_clave": "prueba", "p_limite": 1, "p_umbral": 0.99},
                         headers=_headers(), timeout=_TIMEOUT)
        return r.status_code == 200
    except requests.RequestException:
        return False


def sumar_uso(id_fila):
    if not catalogo_disponible() or id_fila is None:
        return
    try:
        _sesion.post(f"{_base()}/rest/v1/rpc/catalogo_sumar_uso", json={"p_id": id_fila},
                     headers=_headers(), timeout=_TIMEOUT)
    except requests.RequestException:
        pass


def guardar(registro, confirmado=False):
    """
    Guarda un producto. registro: dict con los CAMPOS (clave obligatoria).
    confirmado=True (lo eligió una persona): crea o reemplaza la fila.
    confirmado=False (búsqueda automática): solo crea; si ya existe, no la toca.
    Devuelve True si se guardó.
    """
    if not catalogo_disponible() or not registro.get("clave"):
        return False
    fila = {k: registro.get(k) for k in CAMPOS}
    fila["confirmado"] = bool(confirmado)
    resolucion = "merge-duplicates" if confirmado else "ignore-duplicates"
    try:
        r = _sesion.post(f"{_base()}/rest/v1/{TABLA}", params={"on_conflict": "clave"}, json=[fila],
                         headers=_headers({"Prefer": f"resolution={resolucion},return=minimal"}), timeout=_TIMEOUT)
    except requests.RequestException:
        return False
    if r.status_code not in (200, 201, 204):
        _registrar_error(r)
        return False
    return True


def listar(texto="", pagina=0, por_pagina=50, solo_confirmados=False):
    """Lista el catálogo (para la pestaña Catálogo y la exportación). Devuelve (filas, total)."""
    if not catalogo_disponible():
        return [], 0
    params = {"select": "*", "order": "actualizado.desc",
              "offset": max(0, int(pagina)) * por_pagina, "limit": por_pagina}
    texto = re.sub(r"[,()*%]", " ", str(texto or "")).strip()
    if texto:
        params["or"] = (f"(nombre_original.ilike.*{texto}*,match_nombre.ilike.*{texto}*,"
                        f"ean.ilike.*{texto}*,marca.ilike.*{texto}*,clave.ilike.*{texto}*)")
    if solo_confirmados:
        params["confirmado"] = "eq.true"
    r = _sesion.get(f"{_base()}/rest/v1/{TABLA}", params=params,
                    headers=_headers({"Prefer": "count=exact"}), timeout=_TIMEOUT * 2)
    if r.status_code not in (200, 206):
        raise RuntimeError(_explicar_error(r))
    total = r.headers.get("Content-Range", "").split("/")[-1]
    return r.json(), int(total) if total.isdigit() else len(r.json())


def borrar(id_fila):
    if not catalogo_disponible():
        return False
    r = _sesion.delete(f"{_base()}/rest/v1/{TABLA}", params={"id": f"eq.{int(id_fila)}"},
                       headers=_headers(), timeout=_TIMEOUT)
    return r.status_code in (200, 204)
