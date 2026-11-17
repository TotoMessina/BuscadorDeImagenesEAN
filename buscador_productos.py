"""
=============================================================================
BUSCADOR AVANZADO DE CÓDIGOS EAN E IMÁGENES DE PRODUCTOS
=============================================================================
Desarrollado para catálogos comerciales y distribuidores (Argentina / Latam).

Modos de búsqueda (--modo):
  ambos   -> busca EAN e imagen a la vez (por defecto)
  ean     -> solo busca el código EAN
  imagen  -> solo busca la imagen (si la fila ya trae un EAN, lo usa para
             encontrar la foto exacta del producto)

Estrategia:
  1. Limpieza y normalización de nombres (abreviaturas, bultos, gramajes).
  2. Si ya hay un EAN conocido: búsqueda directa por EAN en catálogos VTEX.
  3. Búsqueda por nombre en catálogos VTEX (Carrefour, Jumbo, ChangoMás, Día,
     Farmacity, Disco, Vea) consultando todas las tiendas EN PARALELO.
  4. Validación anti-falsos positivos (marca, tokens clave, gramaje) y
     validación del dígito verificador del EAN.
  5. Fallback opcional con Serper.dev (Google) y gratuito con DuckDuckGo.
  6. Descarga opcional de imágenes nombradas por EAN (extensión real).
  7. Guardado incremental, reanudación automática y guardado seguro con Ctrl+C.

Uso rápido:
  python buscador_productos.py --input productos.xlsx --modo ambos
  python buscador_productos.py --input productos.xlsx --modo imagen --download-images
  python buscador_productos.py --producto "DR LEMON POMELO x473 ml"
  python buscador_productos.py --ean 7790895000997 --modo imagen
=============================================================================
"""

import os
import re
import sys
import time
import argparse
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests
from requests.adapters import HTTPAdapter
from rapidfuzz import fuzz

try:
    import pandas as pd
except ImportError:  # En Vercel no se instala pandas: solo hace falta para procesar Excel en local
    pd = None

# Configurar salida de consola segura para Windows
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

MODOS = ("ambos", "ean", "imagen")

# Score mínimo para aceptar un producto de VTEX, y score por debajo del cual se marca "Revisar"
SCORE_MINIMO = 65
SCORE_CONFIABLE = 75

# Unidades de medida reconocidas (regex)
_UNIDADES = r'(?:kgrs?|kgs?|grs?|g|mg|ml|cc|cm3|lts?|l)'

# Diccionario de abreviaturas frecuentes del comercio minorista y mayorista
ABREVIATURAS = {
    r'\balf\b': 'alfajor',
    r'\bbco\b': 'blanco',
    r'\bchoc\b': 'chocolate',
    r'\bc/c\b': 'con cascara',
    r'\bs/azucares\b': 'sin azucares',
    r'\bs/azucar\b': 'sin azucar',
    r'\bc/': 'con ',
    r'\bs/': 'sin ',
    r'\bddl\b': 'dulce de leche',
    r'\bdzno\b': 'durazno',
    r'\bfrut\b': 'frutilla',
    r'\bvain\b': 'vainilla',
    r'\bexp\b': 'express',
    r'\bprotec\b': 'protect',
    r'\bproctect\b': 'protect',
    r'\bext\b': 'extra',
    r'\benc\b': 'encendedor',
    r'\bdisp\b': 'display',
    r'\bunid\b': 'unidades',
    r'\btri\b': 'triple',
    r'\bmed\b': 'mediano',
    r'\bgde\b': 'grande',
    r'\bch\b': 'chico',
    r'\bfiamb\b': 'fiambre',
}

# Palabras genéricas que NO representan marcas ni características distintivas únicas
PALABRAS_GENERICAS = {
    'para', 'sabor', 'tipo', 'relleno', 'clasica', 'clasico', 'original', 'femenino',
    'antitranspirante', 'combo', 'promo', 'promocion', 'pack', 'display', 'caja',
    'unid', 'unidades', 'unidad', 'comun', 'surtido', 'surtidas', 'sobre', 'botella', 'lata',
    'tradicional', 'con', 'sin', 'palo', 'fino', 'negro', 'blanco', 'crema', 'roll', 'aerosol',
    'desodorante', 'jabon', 'galletitas', 'budin', 'pan', 'dulce', 'tostadas'
}

# Tiendas VTEX con catálogos públicos y fotos de estudio fondo blanco (orden = prioridad)
TIENDAS_VTEX = [
    ("Carrefour", "www.carrefour.com.ar"),
    ("Jumbo", "www.jumbo.com.ar"),
    ("ChangoMas", "www.masonline.com.ar"),
    ("Dia", "diaonline.supermercadosdia.com.ar"),
    ("Farmacity", "www.farmacity.com"),
    ("Disco", "www.disco.com.ar"),
    ("Vea", "www.vea.com.ar"),
]
PRIORIDAD_TIENDA = {nombre: i for i, (nombre, _) in enumerate(TIENDAS_VTEX)}

# Columnas de resultado que agrega el script
COLUMNAS_RESULTADO = [
    "EAN", "EAN_Valido", "Imagen_URL", "Imagen_Local", "Match_Nombre", "Marca",
    "Fuente_EAN", "Fuente_Imagen", "Score_Match", "Estado", "Revisar",
]

# Sesión HTTP con reutilización de conexiones TLS (compartida entre hilos)
session = requests.Session()
_adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=1)
session.mount("https://", _adapter)
session.mount("http://", _adapter)
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
})

_pool_tiendas = ThreadPoolExecutor(max_workers=len(TIENDAS_VTEX))


# =============================================================================
# Utilidades de texto y EAN
# =============================================================================

def normalizar_texto(texto):
    """Elimina tildes, signos especiales y pasa a minúsculas."""
    if texto is None:
        return ""
    texto_norm = unicodedata.normalize('NFKD', str(texto))
    texto_sin_tildes = "".join([c for c in texto_norm if not unicodedata.combining(c)])
    return texto_sin_tildes.lower().strip()


def ean_valido(codigo):
    """Verifica largo (8/12/13/14) y dígito verificador GS1 de un código EAN/UPC/GTIN."""
    if not codigo:
        return False
    codigo = str(codigo).strip()
    if not codigo.isdigit() or len(codigo) not in (8, 12, 13, 14):
        return False
    digitos = [int(d) for d in codigo]
    cuerpo = digitos[:-1][::-1]
    suma = sum(d * 3 if i % 2 == 0 else d for i, d in enumerate(cuerpo))
    return (10 - suma % 10) % 10 == digitos[-1]


def es_ean_interno(codigo):
    """Los EAN-13 que empiezan con 2 son códigos internos de la tienda (pesables), no universales."""
    return bool(codigo) and len(str(codigo)) == 13 and str(codigo).startswith("2")


def normalizar_ean_celda(valor):
    """
    Convierte lo que venga de una celda Excel a un EAN en texto.
    Ej: 7790895000997.0 -> '7790895000997', '779 0895 000997' -> '7790895000997'.
    """
    if valor is None or valor != valor:  # None o NaN
        return None
    if isinstance(valor, float):
        if not valor.is_integer():
            return None
        valor = int(valor)
    texto = str(valor).strip()
    if re.fullmatch(r'\d+\.0+', texto):  # "7790895000997.0" leído como texto
        texto = texto.split('.')[0]
    texto = re.sub(r'[\s\-.]', '', texto)
    return texto if re.fullmatch(r'\d{8,14}', texto) else None


def extraer_eans_de_texto(texto):
    """Busca en un texto todos los EAN con dígito verificador válido, priorizando el prefijo argentino 779."""
    candidatos = re.findall(r'(?<!\d)(\d{13}|\d{8})(?!\d)', texto or "")
    validos = [c for c in candidatos if ean_valido(c) and not es_ean_interno(c)]
    validos.sort(key=lambda c: (not c.startswith("779"), len(c) != 13))
    return validos


def extraer_tamano(texto):
    """
    Extrae la cantidad en gramos o mililitros para comparar variantes.
    Retorna el valor numérico normalizado (1 kg = 1000 gr, 1,5 lt = 1500 ml).
    Funciona con formatos pegados como 'x473ml', 'x80g.', '1.5 LT', '150 Grs'.
    """
    t = normalizar_texto(texto)
    m = re.search(r'(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(' + _UNIDADES + r')(?![a-z])', t)
    if not m:
        return None
    try:
        val = float(m.group(1).replace(',', '.'))
        unidad = m.group(2)
        if unidad.startswith('k') or unidad.startswith('l'):
            val *= 1000
        elif unidad == 'mg':
            val /= 1000
        return int(round(val))
    except ValueError:
        return None


def limpiar_nombre_producto(raw_name):
    """
    Limpia el nombre del producto eliminando bultos mayoristas y expandiendo abreviaturas.
    Ejemplo: 'DR LEMON VODKA POMELO 5% LATA x473 ml' -> 'dr lemon vodka pomelo lata 473 ml'
             'ALF.MARLEYx80g.NEGRO x20'             -> 'alfajor marley 80 g negro'
    """
    name = normalizar_texto(raw_name)

    # Puntos: separar palabras ("alf.marley") pero conservar decimales ("1.5")
    name = re.sub(r'(?<!\d)\.|\.(?!\d)', ' ', name)

    # Eliminar porcentajes de formulación/alcohol: "5%"
    name = re.sub(r'\d+(?:[.,]\d+)?\s*%', ' ', name)

    # Eliminar bultos "x20", "x 12 un", "x1 un" (pero NO "x473 ml" ni "x80g")
    name = re.sub(
        r'x\s*\d+(?![\d.,]|\s*' + _UNIDADES + r'(?![a-z]))\s*(?:unid|unidades|un|u|paq)?\b',
        ' ', name
    )
    # "x473" -> " 473", "80g" -> "80 g"
    name = re.sub(r'x\s*(\d)', r' \1', name)
    name = re.sub(r'(\d)(' + _UNIDADES + r')(?![a-z])', r'\1 \2', name)

    # Eliminar sufijos de empaque restantes
    name = re.sub(r'\b\d+\s*(?:unid|unidades|un|u)\b', ' ', name)
    name = re.sub(r'\btiras\s+troquel.*', ' ', name)
    name = re.sub(r'\bdisplay\b.*', ' ', name)
    name = re.sub(r'\(caja exhibidora\)', ' ', name)

    # Reemplazar abreviaturas
    for pat, rep in ABREVIATURAS.items():
        name = re.sub(pat, rep, name)

    # Limpiar caracteres especiales
    name = re.sub(r'[*&%#$@()_+\-=\[\]{}|;:<>?/"\']', ' ', name)
    name = re.sub(r'(?<!\d),|,(?!\d)', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


# =============================================================================
# Búsqueda en catálogos VTEX
# =============================================================================

def calcular_score_coincidencia(query_limpia, candidato, tamano_query=None, nombre_sku=None):
    """
    Score de 0 a 100 de relevancia entre la búsqueda y el producto encontrado en VTEX.
    Previene falsos positivos verificando tokens distintivos, marcas y gramaje.
    """
    c_name = normalizar_texto(candidato.get('productName', ''))
    c_brand = normalizar_texto(candidato.get('brand', ''))

    # Tokens distintivos (>= 3 letras que no sean stopwords genéricas ni números)
    tokens_query = [w for w in query_limpia.split()
                    if len(w) >= 3 and w not in PALABRAS_GENERICAS and not w.isdigit()]
    if not tokens_query:
        return 0

    coincidencias = [w for w in tokens_query if w in c_name or w in c_brand]
    pct_coincidencias = len(coincidencias) / len(tokens_query)
    if pct_coincidencias < 0.55:
        return 0

    # Regla anti-conflicto de marca: la tienda devolvió otra marca que no está en la query
    faltantes = [w for w in tokens_query if w not in c_name and w not in c_brand]
    if c_brand and len(c_brand) >= 4 and c_brand not in query_limpia and faltantes:
        return 0

    ratio_sort = fuzz.token_sort_ratio(query_limpia, c_name)
    ratio_set = fuzz.token_set_ratio(query_limpia, c_name)
    base_score = (ratio_sort * 0.4) + (ratio_set * 0.6)

    if pct_coincidencias >= 0.85:
        base_score += 10

    # Validación de gramaje/tamaño (usa el nombre del SKU si existe, que es más específico)
    if tamano_query:
        tamano_candidato = extraer_tamano(nombre_sku or '') or extraer_tamano(c_name)
        if tamano_candidato:
            if tamano_candidato == tamano_query:
                base_score += 10
            elif abs(tamano_candidato - tamano_query) / tamano_query > 0.35:
                base_score -= 25

    return max(0, min(100, round(base_score, 1)))


def _datos_sku(sku):
    """Extrae EAN e imagen de un SKU de VTEX."""
    ean_raw = str(sku.get('ean') or '').strip()
    ean = ean_raw if re.fullmatch(r'\d{8,14}', ean_raw) else None
    imgs = sku.get('images') or []
    img_url = imgs[0].get('imageUrl') if imgs else None
    if img_url:
        img_url = img_url.split('?')[0]
    return ean, img_url


def _elegir_sku(producto, tamano_query):
    """Entre las variantes (SKUs) de un producto, elige la que coincide con el gramaje buscado."""
    skus = producto.get('items') or []
    if not skus:
        return None
    if tamano_query and len(skus) > 1:
        for sku in skus:
            nombre = sku.get('nameComplete') or sku.get('name') or ''
            if extraer_tamano(nombre) == tamano_query:
                return sku
    return skus[0]


def _cumple_modo(ean, img_url, modo):
    if modo == "ean":
        return bool(ean)
    if modo == "imagen":
        return bool(img_url)
    return bool(ean or img_url)


def _buscar_en_tienda(nombre_tienda, dominio, queries, nombre_limpio, tamano_query, modo):
    """Busca en una tienda VTEX y devuelve su mejor candidato (o None)."""
    mejor = None
    for q in queries:
        url = f"https://{dominio}/api/catalog_system/pub/products/search/{requests.utils.quote(q)}"
        try:
            r = session.get(url, timeout=4)
            if r.status_code not in (200, 206):
                continue
            productos = r.json() or []
        except Exception:
            continue

        for prod in productos[:5]:
            sku = _elegir_sku(prod, tamano_query)
            if not sku:
                continue
            nombre_sku = sku.get('nameComplete') or sku.get('name')
            score = calcular_score_coincidencia(nombre_limpio, prod, tamano_query, nombre_sku)
            if score < SCORE_MINIMO:
                continue
            ean, img_url = _datos_sku(sku)
            if not _cumple_modo(ean, img_url, modo):
                continue
            if mejor is None or score > mejor["score"]:
                mejor = {
                    "ean": ean,
                    "imagen_url": img_url,
                    "match_nombre": nombre_sku or prod.get('productName'),
                    "marca": prod.get('brand'),
                    "tienda": nombre_tienda,
                    "score": score,
                }
        if mejor:  # si la primera query ya dio resultado, no hace falta la variante sin números
            break
    return mejor


def buscar_en_vtex(nombre_limpio, tamano_query=None, modo="ambos"):
    """
    Busca en todas las tiendas VTEX en paralelo y devuelve el mejor resultado:
    dict con ean, imagen_url, match_nombre, marca, tienda y score (o None).
    """
    # Variante sin números para búsquedas donde el gramaje exacto bloquea resultados
    query_sin_numeros = re.sub(r'\b\d+(?:[.,]\d+)?\s*(?:' + _UNIDADES + r')?\b', '', nombre_limpio)
    query_sin_numeros = re.sub(r'\s+', ' ', query_sin_numeros).strip()

    queries = [nombre_limpio]
    if query_sin_numeros and query_sin_numeros != nombre_limpio and len(query_sin_numeros.split()) >= 2:
        queries.append(query_sin_numeros)

    futuros = [
        _pool_tiendas.submit(_buscar_en_tienda, nt, dom, queries, nombre_limpio, tamano_query, modo)
        for nt, dom in TIENDAS_VTEX
    ]
    candidatos = [f.result() for f in futuros]
    candidatos = [c for c in candidatos if c]
    if not candidatos:
        return None

    def clave(c):
        completo = 5 if (modo == "ambos" and c["ean"] and c["imagen_url"]) else 0
        return (c["score"] + completo, -PRIORIDAD_TIENDA.get(c["tienda"], 99))

    return max(candidatos, key=clave)


def _buscar_ean_en_tienda(nombre_tienda, dominio, ean):
    url = f"https://{dominio}/api/catalog_system/pub/products/search?fq=alternateIds_Ean:{ean}"
    try:
        r = session.get(url, timeout=4)
        if r.status_code not in (200, 206):
            return None
        for prod in r.json() or []:
            for sku in prod.get('items') or []:
                sku_ean, img_url = _datos_sku(sku)
                if sku_ean == ean and img_url:
                    return {
                        "ean": ean,
                        "imagen_url": img_url,
                        "match_nombre": sku.get('nameComplete') or prod.get('productName'),
                        "marca": prod.get('brand'),
                        "tienda": nombre_tienda,
                        "score": 100,
                    }
    except Exception:
        pass
    return None


def buscar_por_ean_vtex(ean):
    """Búsqueda exacta por código EAN en todas las tiendas VTEX (en paralelo)."""
    futuros = [_pool_tiendas.submit(_buscar_ean_en_tienda, nt, dom, ean) for nt, dom in TIENDAS_VTEX]
    for f in futuros:  # respeta el orden de prioridad de tiendas
        res = f.result()
        if res:
            return res
    return None


# =============================================================================
# Fallbacks web (DuckDuckGo / Serper)
# =============================================================================

# Dominios, bancos de fotos y palabras clave asociadas a marcas de agua
PATRONES_EXCLUIDOS_IMAGEN = [
    "shutterstock", "alamy", "istockphoto", "istock", "gettyimages",
    "123rf", "depositphotos", "dreamstime", "freepik", "vectorstock",
    "canstockphoto", "adobe.stock", "stock.adobe", "bigstockphoto", "fotolia", "pond5",
    "mercadolibre", "mercadolivre", "mlstatic", "olx",
    "watermark", "marca-de-agua", "marcadeagua", "preview_watermark",
]

QUERY_IMG_SUFIJO = "producto fondo blanco -mercadolibre -shutterstock -alamy -istock -stock -watermark"


def es_imagen_limpia_sin_marca_de_agua(url, titulo=""):
    """Descarta imágenes de bancos de fotos con marca de agua o marketplaces de terceros."""
    if not url:
        return False
    texto_revisar = f"{url} {titulo}".lower()
    return not any(p in texto_revisar for p in PATRONES_EXCLUIDOS_IMAGEN)


def _importar_ddgs():
    try:
        from ddgs import DDGS
        return DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
            return DDGS
        except ImportError:
            return None


def buscar_en_duckduckgo(nombre_limpio, buscar_ean=True, buscar_imagen=True, ean_conocido=None):
    """Fallback gratuito sin API Key usando DuckDuckGo. Devuelve (ean, img_url)."""
    DDGS = _importar_ddgs()
    if DDGS is None:
        return None, None

    img_url = None
    ean_encontrado = None
    try:
        with DDGS() as dd:
            if buscar_imagen:
                base = ean_conocido or nombre_limpio
                for r in dd.images(f"{base} {QUERY_IMG_SUFIJO}", max_results=8):
                    if es_imagen_limpia_sin_marca_de_agua(r.get('image'), r.get('title', '')):
                        img_url = r.get('image')
                        break

            if buscar_ean:
                resultados = dd.text(f'"{nombre_limpio}" ean OR "codigo de barras" OR 779', max_results=6)
                texto = " ".join(f"{r.get('title', '')} {r.get('body', '')}" for r in resultados)
                eans = extraer_eans_de_texto(texto)
                ean_encontrado = eans[0] if eans else None
    except Exception:
        pass
    return ean_encontrado, img_url


def buscar_en_serper(nombre_limpio, api_key, buscar_ean=True, buscar_imagen=True, ean_conocido=None):
    """Fallback usando Google Search + Google Images a través de Serper.dev. Devuelve (ean, img_url)."""
    if not api_key or not api_key.strip():
        return None, None

    headers_serper = {"X-API-KEY": api_key.strip(), "Content-Type": "application/json"}
    ean_encontrado = None
    img_encontrada = None

    if buscar_ean:
        try:
            res = session.post(
                "https://google.serper.dev/search", headers=headers_serper,
                json={"q": f"{nombre_limpio} ean OR codigo de barras", "gl": "ar", "hl": "es"},
                timeout=8,
            ).json()
            texto = " ".join(o.get("snippet", "") + " " + o.get("title", "") for o in res.get("organic", []))
            eans = extraer_eans_de_texto(texto)
            ean_encontrado = eans[0] if eans else None
        except Exception:
            pass

    if buscar_imagen:
        try:
            base = ean_conocido or nombre_limpio
            res = session.post(
                "https://google.serper.dev/images", headers=headers_serper,
                json={"q": f"{base} {QUERY_IMG_SUFIJO}", "gl": "ar", "hl": "es"},
                timeout=8,
            ).json()
            for item in res.get("images", []):
                if es_imagen_limpia_sin_marca_de_agua(item.get("imageUrl"), item.get("title", "")):
                    img_encontrada = item.get("imageUrl")
                    break
        except Exception:
            pass

    return ean_encontrado, img_encontrada


# =============================================================================
# Descarga de imágenes
# =============================================================================

_EXTENSIONES = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
                "image/webp": ".webp", "image/gif": ".gif", "image/avif": ".avif"}


def nombre_archivo_seguro(texto, largo=60):
    return re.sub(r'[^a-zA-Z0-9]+', '_', normalizar_texto(texto)).strip('_')[:largo] or "producto"


def descargar_imagen(url, ruta_sin_extension):
    """
    Descarga la imagen verificando que realmente sea una imagen.
    Usa la extensión real según el Content-Type. Si ya existe, no la vuelve a bajar.
    Devuelve la ruta final o None.
    """
    base, ext_pedida = os.path.splitext(ruta_sin_extension)
    if ext_pedida.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ruta_sin_extension = base
    for ext in set(_EXTENSIONES.values()):
        if os.path.exists(ruta_sin_extension + ext):
            return ruta_sin_extension + ext
    try:
        carpeta = os.path.dirname(ruta_sin_extension)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        r = session.get(url, stream=True, timeout=12)
        tipo = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if r.status_code != 200 or not tipo.startswith("image/"):
            return None
        ruta = ruta_sin_extension + _EXTENSIONES.get(tipo, ".jpg")
        tmp = ruta + ".part"
        with open(tmp, 'wb') as f:
            for chunk in r.iter_content(chunk_size=16384):
                f.write(chunk)
        if os.path.getsize(tmp) < 1024:  # imágenes vacías o placeholders
            os.remove(tmp)
            return None
        os.replace(tmp, ruta)
        return ruta
    except Exception:
        return None


# =============================================================================
# Pipeline por producto
# =============================================================================

def procesar_un_producto(
    nombre_original,
    modo="ambos",
    ean_conocido=None,
    serper_key=None,
    carpeta_imagenes=None,
    solo_oficiales_vtex=False,
):
    """
    Ejecuta el pipeline de búsqueda para un único producto.

    modo: 'ambos' | 'ean' | 'imagen'
    ean_conocido: si ya se tiene el EAN (o el texto ingresado ES un EAN), se usa para
                  buscar la imagen exacta por código, que es mucho más preciso que por nombre.
    solo_oficiales_vtex: si es True, solo acepta imágenes de catálogos oficiales VTEX.
    """
    if modo not in MODOS:
        raise ValueError(f"modo debe ser uno de {MODOS}")

    nombre_original = str(nombre_original or "").strip()
    # Si lo que se ingresó es directamente un código, usarlo como EAN conocido
    if not ean_conocido and re.fullmatch(r'\d{8,14}', nombre_original):
        ean_conocido = nombre_original
    ean_conocido = normalizar_ean_celda(ean_conocido)

    necesita_ean = modo in ("ambos", "ean") and not ean_conocido
    necesita_img = modo in ("ambos", "imagen")

    ean = ean_conocido
    img_url = match_nom = marca = score = None
    fuente_ean = "Dato de entrada" if ean_conocido else None
    fuente_img = None

    # 1. Si hay EAN conocido y se necesita imagen: búsqueda exacta por código
    if ean_conocido and necesita_img:
        res = buscar_por_ean_vtex(ean_conocido)
        if res:
            img_url, match_nom, marca, score = res["imagen_url"], res["match_nombre"], res["marca"], 100
            fuente_img = f"VTEX ({res['tienda']}) por EAN"

    # 2. Búsqueda por nombre en VTEX
    nombre_limpio = limpiar_nombre_producto(nombre_original) if not nombre_original.isdigit() else ""
    tamano = extraer_tamano(nombre_original) if nombre_limpio else None
    falta_ean = necesita_ean and not ean
    falta_img = necesita_img and not img_url

    if nombre_limpio and (falta_ean or falta_img):
        modo_vtex = "ambos" if (falta_ean and falta_img) else ("ean" if falta_ean else "imagen")
        res = buscar_en_vtex(nombre_limpio, tamano, modo_vtex)
        if res:
            match_nom, marca, score = res["match_nombre"], res["marca"], res["score"]
            fuente = f"VTEX ({res['tienda']})"
            if falta_ean and res["ean"]:
                ean, fuente_ean = res["ean"], fuente
            if falta_img and res["imagen_url"]:
                img_url, fuente_img = res["imagen_url"], fuente

    # 3. Fallbacks web para lo que siga faltando
    falta_ean = necesita_ean and not ean
    falta_img = necesita_img and not img_url and not solo_oficiales_vtex
    consulta_web = nombre_limpio or (ean_conocido or "")

    if consulta_web and (falta_ean or falta_img) and serper_key:
        ean_s, img_s = buscar_en_serper(consulta_web, serper_key, falta_ean and bool(nombre_limpio),
                                        falta_img, ean_conocido)
        if falta_ean and ean_s:
            ean, fuente_ean = ean_s, "Google (Serper)"
        if falta_img and img_s:
            img_url, fuente_img = img_s, "Google (Serper)"
        falta_ean = necesita_ean and not ean
        falta_img = falta_img and not img_url

    if consulta_web and (falta_ean or falta_img):
        ean_d, img_d = buscar_en_duckduckgo(consulta_web, falta_ean and bool(nombre_limpio),
                                            falta_img, ean_conocido)
        if falta_ean and ean_d:
            ean, fuente_ean = ean_d, "DuckDuckGo"
        if falta_img and img_d:
            img_url, fuente_img = img_d, "DuckDuckGo"

    # 4. Descarga local de la imagen
    ruta_local = None
    if img_url and carpeta_imagenes:
        nombre_archivo = ean if ean else nombre_archivo_seguro(nombre_original)
        ruta_local = descargar_imagen(img_url, os.path.join(carpeta_imagenes, nombre_archivo))

    # 5. Estado y control de calidad
    tiene_ean, tiene_img = bool(ean), bool(img_url)
    objetivo = {"ambos": tiene_ean and tiene_img, "ean": tiene_ean, "imagen": tiene_img}[modo]
    if objetivo:
        estado = "OK"
    elif tiene_ean or tiene_img:
        estado = "Parcial"
    else:
        estado = "No encontrado"

    motivos = []
    if score is not None and score < SCORE_CONFIABLE:
        motivos.append(f"score bajo ({score})")
    if ean and not ean_valido(ean):
        motivos.append("EAN con dígito verificador inválido")
    if ean and es_ean_interno(ean):
        motivos.append("EAN interno de tienda (empieza con 2)")
    if fuente_ean in ("DuckDuckGo", "Google (Serper)"):
        motivos.append("EAN tomado de la web")
    if fuente_img in ("DuckDuckGo", "Google (Serper)"):
        motivos.append("imagen tomada de la web")

    return {
        "EAN": ean,
        "EAN_Valido": ean_valido(ean) if ean else None,
        "Imagen_URL": img_url,
        "Imagen_Local": ruta_local,
        "Match_Nombre": match_nom,
        "Marca": marca,
        "Fuente_EAN": fuente_ean,
        "Fuente_Imagen": fuente_img,
        "Score_Match": score,
        "Estado": estado,
        "Revisar": "; ".join(motivos) if motivos else None,
    }


# =============================================================================
# Procesamiento por lotes
# =============================================================================

COLUMNAS_NOMBRE_POSIBLES = ["NOMBRE", "Nombre", "nombre", "PRODUCTO", "Producto", "producto",
                            "DESCRIPCION", "Descripcion", "descripcion", "Title", "Name"]
COLUMNAS_EAN_POSIBLES = ["EAN", "ean", "Ean", "EAN13", "CODIGO_BARRAS", "Codigo_Barras",
                         "CODIGO DE BARRAS", "Codigo de barras", "GTIN", "UPC"]


def detectar_columna(df, posibles, por_defecto=None):
    for p in posibles:
        if p in df.columns:
            return p
    return por_defecto


def leer_tabla(ruta):
    if ruta.lower().endswith('.csv'):
        return pd.read_csv(ruta, dtype=str, sep=None, engine="python")
    return pd.read_excel(ruta, dtype=str)


def guardar_tabla(df, ruta):
    base, ext = os.path.splitext(ruta)
    tmp = f"{base}.tmp{ext}"  # se escribe aparte y se reemplaza: si se corta, no se corrompe el archivo
    if ruta.lower().endswith('.csv'):
        df.to_csv(tmp, index=False, encoding="utf-8-sig")
    else:
        df.to_excel(tmp, index=False, engine="openpyxl")
    os.replace(tmp, ruta)


def _fila_pendiente(row, modo, reintentar):
    """Decide si una fila hay que procesarla (para reanudar sin repetir trabajo)."""
    estado = row.get("Estado")
    if pd.isna(estado) or str(estado).strip() == "":
        return True
    if not reintentar:
        return False
    tiene_ean = pd.notna(row.get("EAN")) and str(row.get("EAN")).strip() != ""
    tiene_img = pd.notna(row.get("Imagen_URL")) and str(row.get("Imagen_URL")).strip() != ""
    return not {"ambos": tiene_ean and tiene_img, "ean": tiene_ean, "imagen": tiene_img}[modo]


def procesar_dataframe(
    df,
    columna_producto,
    modo="ambos",
    columna_ean=None,
    serper_key=None,
    carpeta_imagenes=None,
    solo_oficiales_vtex=False,
    max_filas=None,
    reintentar=False,
    on_progreso=None,
    on_guardar=None,
    pausa=0.1,
):
    """
    Procesa un DataFrame fila por fila. Lo usan tanto la línea de comandos como la interfaz web.
    on_progreso(i, total, nombre, resultado) se llama después de cada fila.
    on_guardar(df) se llama cada 10 filas para guardado incremental.
    Devuelve (df, estadisticas).
    """
    for c in COLUMNAS_RESULTADO:
        if c not in df.columns:
            df[c] = None
        df[c] = df[c].astype(object)

    if "EAN" in df.columns:
        df["EAN"] = df["EAN"].map(normalizar_ean_celda).astype(object)
    if columna_ean and columna_ean != "EAN" and columna_ean in df.columns:
        df[columna_ean] = df[columna_ean].map(lambda v: normalizar_ean_celda(v) or v)

    total = len(df) if not max_filas else min(len(df), int(max_filas))
    cache = {}
    stats = Counter()
    fuentes = Counter()

    try:
        for i, idx in enumerate(df.index[:total]):
            row = df.loc[idx]
            nombre = str(row[columna_producto]).strip() if pd.notna(row[columna_producto]) else ""
            ean_entrada = normalizar_ean_celda(row[columna_ean]) if columna_ean else None
            if not ean_entrada:
                ean_entrada = normalizar_ean_celda(row.get("EAN")) if modo == "imagen" else None

            if not nombre and not ean_entrada:
                stats["vacias"] += 1
                continue
            if not _fila_pendiente(row, modo, reintentar):
                stats["ya_procesadas"] += 1
                continue

            clave = (limpiar_nombre_producto(nombre), ean_entrada)
            if clave in cache:
                res = dict(cache[clave])
                stats["duplicados"] += 1
            else:
                res = procesar_un_producto(
                    nombre_original=nombre or ean_entrada,
                    modo=modo,
                    ean_conocido=ean_entrada,
                    serper_key=serper_key,
                    carpeta_imagenes=carpeta_imagenes,
                    solo_oficiales_vtex=solo_oficiales_vtex,
                )
                cache[clave] = res
                time.sleep(pausa)

            for c in COLUMNAS_RESULTADO:
                df.at[idx, c] = res[c]

            stats[res["Estado"]] += 1
            if res["Revisar"]:
                stats["revisar"] += 1
            for f in (res["Fuente_EAN"], res["Fuente_Imagen"]):
                if f:
                    fuentes[f] += 1

            if on_progreso:
                on_progreso(i + 1, total, nombre or ean_entrada, res)
            if on_guardar and (i + 1) % 10 == 0:
                on_guardar(df)
    finally:
        if on_guardar:
            on_guardar(df)

    stats["fuentes"] = dict(fuentes)
    return df, stats


def procesar_archivo(
    archivo_entrada="productos.xlsx",
    archivo_salida="productos_completos.xlsx",
    columna_producto=None,
    columna_ean=None,
    modo="ambos",
    descargar_fotos=False,
    carpeta_imagenes="imagenes",
    serper_key=None,
    max_filas=None,
    solo_oficiales_vtex=False,
    reintentar=False,
):
    """Procesa un Excel/CSV con guardado incremental y reanudación automática."""
    if not os.path.exists(archivo_entrada):
        print(f"[ERROR] El archivo '{archivo_entrada}' no existe.")
        return

    df = leer_tabla(archivo_entrada)

    if not columna_producto or columna_producto not in df.columns:
        columna_producto = detectar_columna(df, COLUMNAS_NOMBRE_POSIBLES, df.columns[0])
    if columna_ean and columna_ean not in df.columns:
        print(f"[AVISO] La columna EAN '{columna_ean}' no existe. Se ignora.")
        columna_ean = None
    if not columna_ean:
        columna_ean = detectar_columna(df, COLUMNAS_EAN_POSIBLES)

    print(f"[INFO] Archivo de entrada: {archivo_entrada} ({len(df)} filas)", flush=True)
    print(f"[INFO] Columna de producto: '{columna_producto}'", flush=True)
    if columna_ean:
        print(f"[INFO] Columna con EAN existente: '{columna_ean}' (se usa para buscar imagen exacta)", flush=True)
    print(f"[INFO] Modo: {modo.upper()}", flush=True)
    print(f"[INFO] Archivo de salida: {archivo_salida}", flush=True)
    if solo_oficiales_vtex:
        print("[INFO] Filtro estricto: solo imágenes de catálogos oficiales VTEX", flush=True)
    if descargar_fotos:
        print(f"[INFO] Descarga de imágenes en carpeta: '{carpeta_imagenes}'", flush=True)

    # Reanudar desde un archivo de salida previo
    if os.path.exists(archivo_salida):
        try:
            df_existente = leer_tabla(archivo_salida)
            if len(df_existente) == len(df) and columna_producto in df_existente.columns:
                print("[INFO] Se detectó un archivo previo. Reanudando desde los registros pendientes...", flush=True)
                df = df_existente
        except Exception:
            pass

    print("-" * 75, flush=True)
    t_inicio = time.time()

    def progreso(i, total, nombre, res):
        transcurrido = time.time() - t_inicio
        print(f"[{i}/{total}] {nombre[:50]}", flush=True)
        if res["Estado"] == "No encontrado":
            print("     [--] No encontrado", flush=True)
        else:
            score = f"{res['Score_Match']}%" if res['Score_Match'] is not None else "N/A"
            ean = res['EAN'] or '-'
            img = "sí" if res['Imagen_URL'] else "no"
            aviso = f" | REVISAR: {res['Revisar']}" if res['Revisar'] else ""
            print(f"     [{res['Estado']}] EAN: {ean} | Imagen: {img} | Score: {score} | "
                  f"{res['Fuente_EAN'] or res['Fuente_Imagen']}{aviso}", flush=True)
        if i % 25 == 0:
            print(f"     ... {round(transcurrido)} s transcurridos", flush=True)

    try:
        df, stats = procesar_dataframe(
            df, columna_producto, modo=modo, columna_ean=columna_ean,
            serper_key=serper_key,
            carpeta_imagenes=carpeta_imagenes if descargar_fotos else None,
            solo_oficiales_vtex=solo_oficiales_vtex, max_filas=max_filas,
            reintentar=reintentar, on_progreso=progreso,
            on_guardar=lambda d: guardar_tabla(d, archivo_salida),
        )
    except KeyboardInterrupt:
        print("\n[PAUSA] Interrumpido. El avance quedó guardado; volvé a ejecutar para continuar.", flush=True)
        return

    print("-" * 75, flush=True)
    print("[FINALIZADO] PROCESO COMPLETADO", flush=True)
    print(f"Tiempo total: {round(time.time() - t_inicio, 1)} segundos", flush=True)
    print(f"OK: {stats['OK']} | Parciales: {stats['Parcial']} | No encontrados: {stats['No encontrado']} | "
          f"Para revisar: {stats['revisar']} | Ya procesadas antes: {stats['ya_procesadas']} | "
          f"Duplicados reutilizados: {stats['duplicados']}", flush=True)
    if stats["fuentes"]:
        print("Fuentes: " + ", ".join(f"{k}: {v}" for k, v in sorted(stats["fuentes"].items(), key=lambda x: -x[1])))
    print(f"Archivo guardado: {archivo_salida}", flush=True)


def imprimir_resultado(nombre, res):
    print("-" * 60)
    print(f"Producto:      {nombre}")
    for c in COLUMNAS_RESULTADO:
        if res.get(c) not in (None, ""):
            print(f"{c + ':':<15}{res[c]}")
    print("-" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Buscador de códigos EAN e imágenes para catálogos.")
    parser.add_argument("--modo", choices=MODOS, default="ambos",
                        help="Qué buscar: ambos (EAN + imagen), ean, o imagen")
    parser.add_argument("--producto", default=None, help="Buscar un único producto por nombre (sin archivo)")
    parser.add_argument("--ean", default=None, help="Buscar un único producto por código EAN (sin archivo)")
    parser.add_argument("--input", default="productos.xlsx", help="Archivo Excel o CSV de entrada")
    parser.add_argument("--output", default=None, help="Archivo de salida (.xlsx o .csv). Por defecto: <input>_completos.xlsx")
    parser.add_argument("--col", default=None, help="Columna con el nombre del producto")
    parser.add_argument("--col-ean", default=None, help="Columna con EAN ya conocidos (para buscar la imagen exacta)")
    parser.add_argument("--download-images", action="store_true", help="Descargar imágenes localmente")
    parser.add_argument("--images-dir", default="imagenes", help="Carpeta destino para las imágenes")
    parser.add_argument("--serper-key", default=os.environ.get("SERPER_API_KEY"),
                        help="API Key de Serper.dev (opcional; también se lee de la variable SERPER_API_KEY)")
    parser.add_argument("--limit", type=int, default=None, help="Límite de filas a procesar (para pruebas)")
    parser.add_argument("--solo-oficiales", action="store_true",
                        help="Solo aceptar imágenes de catálogos oficiales VTEX (0 marcas de agua)")
    parser.add_argument("--reintentar", action="store_true",
                        help="Volver a buscar las filas que en una corrida previa quedaron incompletas")

    args = parser.parse_args()

    if args.producto or args.ean:
        entrada = args.producto or args.ean
        res = procesar_un_producto(
            nombre_original=entrada, modo=args.modo, ean_conocido=args.ean,
            serper_key=args.serper_key,
            carpeta_imagenes=args.images_dir if args.download_images else None,
            solo_oficiales_vtex=args.solo_oficiales,
        )
        imprimir_resultado(entrada, res)
        sys.exit(0)

    salida = args.output or f"{os.path.splitext(args.input)[0]}_completos.xlsx"
    procesar_archivo(
        archivo_entrada=args.input,
        archivo_salida=salida,
        columna_producto=args.col,
        columna_ean=args.col_ean,
        modo=args.modo,
        descargar_fotos=args.download_images,
        carpeta_imagenes=args.images_dir,
        serper_key=args.serper_key,
        max_filas=args.limit,
        solo_oficiales_vtex=args.solo_oficiales,
        reintentar=args.reintentar,
    )
