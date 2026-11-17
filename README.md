# Buscador de EAN e Imágenes

Busca códigos EAN e imágenes de productos en los catálogos de Carrefour, Jumbo, ChangoMás, Día, Farmacity, Disco y Vea, con DuckDuckGo (y opcionalmente Google vía Serper) como respaldo.

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
api/imagen.py           Función de Vercel: descarga imágenes para armar el ZIP
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

4. **Verificar**: entrar a la web y tocar **🩺 Estado de las fuentes**. Tiene que mostrar las tiendas en verde. Si alguna aparece en rojo, esa tienda bloquea los servidores de Vercel y sus productos se buscarán en las demás.

Cada `git push` a `main` vuelve a publicar la web automáticamente.

## Cómo funciona el procesamiento de Excel en la web

- El Excel **no se sube al servidor**: se lee en el navegador, y la página consulta los productos de a 3 en paralelo.
- El avance se guarda en el navegador: si se cierra la pestaña, al volver a cargar el mismo archivo continúa donde quedó.
- Se puede pausar y descargar el Excel parcial en cualquier momento.
- Si el archivo tiene una columna con EAN, se usa para buscar la imagen exacta por código.
- Columnas que agrega: `EAN`, `EAN_Valido`, `Imagen_URL`, `Match_Nombre`, `Marca`, `Fuente_EAN`, `Fuente_Imagen`, `Score_Match`, `Estado` (OK / Parcial / No encontrado) y `Revisar` (motivos para chequear a mano).
