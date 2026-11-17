# Buscador de EAN e Imágenes

Busca códigos EAN e imágenes de productos en los catálogos de 16 tiendas argentinas, todas a la vez, con DuckDuckGo (y opcionalmente Google vía Serper) como respaldo:

- **Supermercados:** Carrefour, Jumbo, ChangoMás, Día, Disco, Vea, Josimar, Cordiez, Toledo
- **Farmacias y perfumerías:** Farmacity, Farmaonline, Farmacias del Pueblo, Simplicity, Get The Look, Pigmento, Juleriaque

Para sumar o quitar tiendas se edita la lista `TIENDAS_VTEX` en `buscador_productos.py` (tienen que ser tiendas VTEX con catálogo público).
Las grandes mayoristas (Vital, Diarco, Makro, Maxiconsumo, Yaguar) no exponen ese catálogo, por eso no están.

Se puede usar de tres formas:

| Forma | Para qué | Cómo |
|---|---|---|
| **Web (Vercel)** | Uso diario del equipo, desde cualquier navegador | Ver "Publicar en Vercel" |
| Consola | Procesar Excel grandes en tu PC | `python buscador_productos.py --input productos.xlsx --modo ambos` |
| Interfaz Gradio | Alternativa local con interfaz | `python interfaz_web.py` |

## Estructura

```
index.html              Página web (consulta individual + procesamiento de Excel en el navegador)
api/buscar.py           Función de Vercel: busca UN producto (la página la llama por cada fila)
api/imagen.py           Función de Vercel: descarga imágenes para el ZIP y las miniaturas del Excel
api/estado.py           Función de Vercel: pide clave / diagnóstico de las fuentes
buscador_productos.py   Lógica de búsqueda (la usan la web, la consola y Gradio)
vercel.json             Configuración de Vercel (región São Paulo, tiempo máximo)
requirements.txt        Librerías que instala Vercel
requirements-local.txt  Librerías para usarlo en tu PC (consola / Gradio)
dev_server.py           Simula Vercel en tu PC para probar antes de subir
```

## Probar en tu PC antes de subir

```bash
pip install -r requirements-local.txt
python dev_server.py
```

Se abre `http://localhost:3000` con la misma web que se va a publicar.

## Publicar en Vercel

1. **Subir a GitHub** (repositorio **privado** recomendado). Desde esta carpeta:
   ```bash
   git init
   git add .
   git commit -m "Buscador de EAN e imágenes"
   git branch -M main
   git remote add origin https://github.com/TU-USUARIO/buscador-ean.git
   git push -u origin main
   ```
   El `.gitignore` ya excluye los Excel, ZIP e imágenes, así que tus listas de productos no se suben.

2. **Importar en Vercel**: *Add New → Project* → elegir el repositorio → *Deploy*. No hace falta tocar nada de la configuración: Vercel detecta solo la página y las funciones de Python.

3. **Variables de entorno** (*Project → Settings → Environment Variables*), después hacer *Redeploy*:
   - `CLAVE_ACCESO` (recomendada): una contraseña para el equipo. Sin ella, cualquiera que tenga el link puede usar la herramienta.
   - `SERPER_API_KEY` (opcional): para usar Google como respaldo extra.
   - `ANTHROPIC_API_KEY` (opcional): activa la **validación de fotos con IA** (ver más abajo).
   - `CLAUDE_MODELO_VISION` (opcional): modelo para la validación. Por defecto `claude-opus-5-5`.

4. **Verificar**: entrar a la web y tocar **🩺 Estado de las fuentes**. Tiene que mostrar las tiendas en verde. Si alguna aparece en rojo, esa tienda bloquea los servidores de Vercel y sus productos se buscarán en las demás.

Cada `git push` a `main` vuelve a publicar la web automáticamente.

## Cómo funciona el procesamiento de Excel en la web

- El Excel **no se sube al servidor**: se lee en el navegador, y la página consulta los productos de a 3 en paralelo.
- El avance se guarda en el navegador: si se cierra la pestaña, al volver a cargar el mismo archivo continúa donde quedó.
- Se puede pausar y descargar el Excel parcial en cualquier momento.
- Si el archivo tiene una columna con EAN, se usa para buscar la imagen exacta por código.
- Columnas que agrega: `EAN`, `EAN_Valido`, `Imagen_URL`, `Match_Nombre`, `Marca`, `Fuente_EAN`, `Fuente_Imagen`, `Score_Match`, `Validacion_IA`, `Estado` (OK / Parcial / No encontrado) y `Revisar` (motivos para chequear a mano).
- Con **Miniaturas en el Excel** (activado por defecto), el Excel descargado trae una primera columna `Foto` con la imagen de cada producto.

## Validación de fotos con IA

Opcional. Usa Claude (con visión) para revisar cada foto candidata y descartar las que:

- muestran **otro producto** (otra marca, otro sabor o variante, otro tamaño visible),
- tienen **marcas de agua** o sellos de bancos de imágenes o vendedores,
- **no sirven como foto de catálogo** (banners con precios, collages, personas usando el producto, íconos).

Si una foto se descarta, prueba con la siguiente candidata (hasta 3 por producto).

| Opción | Qué valida |
|---|---|
| No validar | Nada (como antes) |
| Solo fotos de la web | Las de DuckDuckGo / Google, que son las más dudosas |
| Todas las fotos | También las de los catálogos. Si la IA dice que la foto del catálogo no coincide, el producto queda marcado para revisar el EAN también |

Para activarla hace falta una API key de Anthropic (console.anthropic.com):
- **Vercel:** variable de entorno `ANTHROPIC_API_KEY` y *Redeploy*.
- **Consola / Gradio en tu PC:** `set ANTHROPIC_API_KEY=sk-ant-...` antes de ejecutar.

**Costo:** cada foto validada es una consulta a la API. Con el modelo por defecto (`claude-opus-5-5`) conviene validar "Solo fotos de la web". Para validar listas grandes se puede bajar mucho el costo con `CLAUDE_MODELO_VISION=claude-haiku-5-5`, revisando antes algunos resultados para confirmar que la calidad alcanza.

## Consola

```bash
python buscador_productos.py --input productos.xlsx --modo ambos --miniaturas
python buscador_productos.py --input productos.xlsx --modo imagen --validar-ia web --download-images
python buscador_productos.py --producto "DR LEMON POMELO x473 ml" --validar-ia todas
```

| Opción | Para qué |
|---|---|
| `--modo ambos\|ean\|imagen` | Qué buscar |
| `--miniaturas` | Columna `Foto` con la miniatura de cada imagen en el Excel |
| `--validar-ia web\|todas` | Validar fotos con IA (requiere `ANTHROPIC_API_KEY`) |
| `--download-images` | Guardar las imágenes en la carpeta `--images-dir` |
| `--solo-oficiales` | Solo fotos de catálogos, nunca de la web |
| `--reintentar` | Volver a buscar las filas que quedaron incompletas |
| `--limit N` | Procesar solo las primeras N filas (para probar) |
