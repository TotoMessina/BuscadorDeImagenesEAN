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
app.py                  Punto de entrada de Vercel: sirve index.html y las rutas /api/* (usa las clases de api/)
index.html              Página web (consulta individual + procesamiento de Excel en el navegador)
api/buscar.py           Función de Vercel: busca UN producto (la página la llama por cada fila)
api/imagen.py           Función de Vercel: descarga imágenes para el ZIP y las miniaturas del Excel
api/estado.py           Función de Vercel: pide clave / diagnóstico de las fuentes
api/candidatas.py       Función de Vercel: opciones de fotos y productos para la pantalla de revisión
api/catalogo.py         Función de Vercel: listar, confirmar y borrar productos del catálogo del equipo
catalogo_db.py          Conexión con Supabase (catálogo del equipo)
supabase_catalogo.sql   SQL para crear la tabla del catálogo (se ejecuta una vez en Supabase)
buscador_productos.py   Lógica de búsqueda (la usan la web, la consola y Gradio)
vercel.json             Configuración de Vercel (región São Paulo, tiempo máximo)
requirements.txt        Librerías que instala Vercel
requirements-local.txt  Librerías para usarlo en tu PC (consola / Gradio)
dev_server.py           Corre app.py en tu PC (http://localhost:3000) para probar antes de subir
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
- Columnas con datos del producto (de la tienda donde se encontró): `Categoria` (ej. "Bebidas > Gaseosas > Gaseosas cola"), `Contenido_Neto` (ej. "473 ml"), `Descripcion`, `Link_Producto`. La `Marca` sale normalizada ("CAMPO AUSTRAL" → "Campo Austral").
- Con **Miniaturas en el Excel** (activado por defecto), el Excel descargado trae una primera columna `Foto` con la imagen de cada producto.
- Con **Fotos listas para publicar** (activado por defecto), el ZIP trae cada foto recortada, centrada en un cuadrado de 1000×1000 con fondo blanco, en JPG y nombrada por EAN. Sirven directo para tienda online, MercadoLibre o catálogo.

## Catálogo del equipo (Supabase)

Cada producto confirmado queda guardado en una base de datos compartida, así nadie busca dos veces lo mismo:

- **Las búsquedas consultan el catálogo primero.** Si el producto ya está, la respuesta es instantánea (`Fuente: Catálogo del equipo`).
- **Se guarda solo:** todo resultado completo y confiable (EAN + foto, sin nada para revisar).
- **Lo que corrige una persona tiene prioridad:** las elecciones de la pantalla de revisión y el botón **💾 Guardar como correcto** de la consulta individual se guardan como *confirmados*, y ninguna búsqueda automática los pisa. Sirve también para productos de mayorista que no están en ninguna tienda (por ejemplo, solo con la foto).
- **Pestaña 📚 Catálogo:** buscar, ver cuántas veces se reutilizó cada producto, borrar y **exportar todo a Excel** (tu catálogo maestro).
- Casilla **Usar catálogo del equipo** para buscar ignorándolo (en consola: `--sin-catalogo`).

### Configuración (una sola vez)

1. **Crear la tabla:** en Supabase, *SQL Editor → New query*, pegar el contenido de [`supabase_catalogo.sql`](supabase_catalogo.sql) y *Run*.
2. **Vercel:** *Settings → Environment Variables*, agregar y hacer *Redeploy*:
   - `SUPABASE_URL` = `https://<tu-proyecto>.supabase.co`
   - `SUPABASE_KEY` = la clave secreta (`sb_secret_...`, en Supabase: *Project Settings → API Keys*)
3. **En tu PC (consola, Gradio, `dev_server.py`):** archivo `.env` en esta carpeta con esas dos líneas. Git lo ignora, así que la clave no se sube a GitHub.

La clave secreta da acceso total a la base: va solo en el servidor (Vercel o `.env`), nunca en la página ni en el código. La tabla tiene RLS activado, así que la clave pública de Supabase no puede leerla.

## Pantalla de revisión

La pestaña **🧐 Revisión** muestra solo los productos incompletos o marcados para revisar (el número al lado es cuántos quedan). Para cada uno:

- Aparecen las opciones de todas las tiendas (con su EAN, nombre y foto) y fotos de la web. **Un clic** en la correcta y queda aplicada, con su EAN y sus datos.
- Si ninguna sirve: **cargar el EAN a mano** (busca la foto y los datos de ese código) o **pegar la URL** de una imagen.
- **✓ Está bien así** lo marca como revisado sin cambiar nada.

Las correcciones se guardan en el navegador junto con el avance, salen en el Excel (columna `Revisado_Manual`) y en el ZIP.
En la consulta individual, el botón **🔄 Ver otras opciones** muestra las mismas alternativas.

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
| `--fotos-publicar` | Fotos 1000×1000, fondo blanco, nombradas por EAN, en `<images-dir>/publicar` |
| `--solo-oficiales` | Solo fotos de catálogos, nunca de la web |
| `--reintentar` | Volver a buscar las filas que quedaron incompletas |
| `--limit N` | Procesar solo las primeras N filas (para probar) |
