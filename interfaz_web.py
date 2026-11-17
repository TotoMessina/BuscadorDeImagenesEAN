"""
=============================================================================
INTERFAZ WEB INTERACTIVA - BUSCADOR DE CÓDIGOS EAN E IMÁGENES
=============================================================================
Ejecutar con: python interfaz_web.py
Abre un servidor local en tu navegador para procesar archivos Excel/CSV
o realizar consultas individuales (por nombre o por EAN).
=============================================================================
"""

import os
import time
import zipfile
import gradio as gr
from buscador_productos import (
    procesar_un_producto,
    procesar_dataframe,
    leer_tabla,
    guardar_tabla,
    detectar_columna,
    COLUMNAS_NOMBRE_POSIBLES,
    COLUMNAS_EAN_POSIBLES,
)

CARPETA_BASE = "resultados_web"
SIN_COLUMNA_EAN = "(ninguna)"

OPCIONES_MODO = {
    "EAN + Imagen": "ambos",
    "Solo EAN": "ean",
    "Solo Imagen": "imagen",
}


def _clave_serper(texto):
    texto = (texto or "").strip() or os.environ.get("SERPER_API_KEY", "")
    return texto or None


def buscar_individual(texto, modo_txt, serper_key, solo_oficiales=False):
    """Búsqueda rápida para un único producto (nombre o código EAN)."""
    if not texto or not texto.strip():
        return None, "Escribí el nombre de un producto o un código EAN."

    modo = OPCIONES_MODO.get(modo_txt, "ambos")
    res = procesar_un_producto(
        nombre_original=texto.strip(),
        modo=modo,
        serper_key=_clave_serper(serper_key),
        carpeta_imagenes=os.path.join(CARPETA_BASE, "individual") if modo != "ean" else None,
        solo_oficiales_vtex=solo_oficiales,
    )

    img = res["Imagen_Local"] or res["Imagen_URL"]
    score = f"{res['Score_Match']}%" if res["Score_Match"] is not None else "N/A"
    valido = {True: "✅ válido", False: "⚠️ dígito verificador inválido", None: ""}[res["EAN_Valido"]]
    filas = [
        f"**Estado:** {res['Estado']}",
        f"**Consulta:** {texto}",
        f"**Coincidencia:** {res['Match_Nombre'] or 'Sin coincidencia'}",
        f"**Marca:** {res['Marca'] or '-'}",
    ]
    if modo != "imagen" or res["EAN"]:
        filas.append(f"**EAN:** `{res['EAN'] or 'No encontrado'}` {valido} — _{res['Fuente_EAN'] or '-'}_")
    if modo != "ean":
        filas.append(f"**Imagen:** {res['Imagen_URL'] or 'No encontrada'} — _{res['Fuente_Imagen'] or '-'}_")
    filas.append(f"**Score de coincidencia:** {score}")
    if res["Revisar"]:
        filas.append(f"**⚠️ Revisar:** {res['Revisar']}")
    return img, "  \n".join(filas)


def previsualizar_archivo(archivo):
    """Muestra las primeras filas y sugiere columnas al subir un Excel o CSV."""
    vacio = gr.Dropdown(choices=[], value=None)
    if archivo is None:
        return None, vacio, vacio, "Subí un archivo para comenzar."
    try:
        df = leer_tabla(archivo)
    except Exception as e:
        return None, vacio, vacio, f"❌ Error al leer el archivo: {e}"

    columnas = list(df.columns)
    col_nombre = detectar_columna(df, COLUMNAS_NOMBRE_POSIBLES, columnas[0])
    col_ean = detectar_columna(df, COLUMNAS_EAN_POSIBLES, SIN_COLUMNA_EAN)
    mensaje = (f"✅ Archivo cargado: **{len(df)} filas**. Elegí la columna con los nombres de producto "
               f"y, si tenés, la columna con EAN ya conocidos (sirve para encontrar la foto exacta).")
    return (
        df.head(5),
        gr.Dropdown(choices=columnas, value=col_nombre),
        gr.Dropdown(choices=[SIN_COLUMNA_EAN] + columnas, value=col_ean),
        mensaje,
    )


def procesar_lote(archivo, columna, columna_ean, modo_txt, descargar_fotos, serper_key, max_filas,
                  solo_oficiales=False, progress=gr.Progress()):
    """Procesa el lote completo con barra de progreso."""
    if archivo is None:
        raise gr.Error("Tenés que cargar un archivo Excel o CSV.")

    df = leer_tabla(archivo)
    if not columna or columna not in df.columns:
        columna = df.columns[0]
    if columna_ean == SIN_COLUMNA_EAN or columna_ean not in df.columns:
        columna_ean = None
    modo = OPCIONES_MODO.get(modo_txt, "ambos")

    # Cada corrida en su propia carpeta: el ZIP solo trae las imágenes de esta corrida
    carpeta_corrida = os.path.join(CARPETA_BASE, time.strftime("%Y%m%d_%H%M%S"))
    carpeta_imgs = os.path.join(carpeta_corrida, "imagenes")
    os.makedirs(carpeta_corrida, exist_ok=True)
    nombre_base = os.path.splitext(os.path.basename(archivo))[0]
    ruta_excel = os.path.join(carpeta_corrida, f"{nombre_base}_resultados.xlsx")

    progress(0, desc="Iniciando...")

    def on_progreso(i, total, nombre, res):
        progress(i / total, desc=f"[{i}/{total}] {nombre[:35]}")

    df, stats = procesar_dataframe(
        df, columna, modo=modo, columna_ean=columna_ean,
        serper_key=_clave_serper(serper_key),
        carpeta_imagenes=carpeta_imgs if (descargar_fotos and modo != "ean") else None,
        solo_oficiales_vtex=solo_oficiales,
        max_filas=int(max_filas) if max_filas and int(max_filas) > 0 else None,
        on_progreso=on_progreso,
        on_guardar=lambda d: guardar_tabla(d, ruta_excel),
    )

    zip_ruta = None
    if os.path.isdir(carpeta_imgs) and os.listdir(carpeta_imgs):
        zip_ruta = os.path.join(carpeta_corrida, f"{nombre_base}_imagenes.zip")
        with zipfile.ZipFile(zip_ruta, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for archivo_img in os.listdir(carpeta_imgs):
                zipf.write(os.path.join(carpeta_imgs, archivo_img), arcname=archivo_img)

    procesadas = stats["OK"] + stats["Parcial"] + stats["No encontrado"]
    pct = round(stats["OK"] / procesadas * 100, 1) if procesadas else 0
    fuentes = ", ".join(f"{k}: {v}" for k, v in sorted(stats["fuentes"].items(), key=lambda x: -x[1]))
    resumen = (
        f"🎉 **Listo.** {procesadas} productos procesados en modo **{modo_txt}**.  \n"
        f"✅ Completos: **{stats['OK']}** ({pct}%) · 🟡 Parciales: {stats['Parcial']} · "
        f"❌ No encontrados: {stats['No encontrado']} · ⚠️ Para revisar: {stats['revisar']}  \n"
        f"Fuentes: {fuentes or '-'}"
    )

    columnas_mostrar = [columna, "Estado", "EAN", "Score_Match", "Fuente_EAN", "Fuente_Imagen",
                        "Match_Nombre", "Revisar", "Imagen_URL"]
    if modo == "ean":
        columnas_mostrar.remove("Fuente_Imagen")
        columnas_mostrar.remove("Imagen_URL")
    columnas_existentes = [c for c in columnas_mostrar if c in df.columns]

    return ruta_excel, zip_ruta, df[columnas_existentes].head(50), resumen


with gr.Blocks(title="Buscador de EAN e Imágenes") as demo:
    gr.Markdown("""
    # 🔍 Buscador de Códigos EAN e Imágenes de Producto
    Busca en catálogos oficiales de **Carrefour, Jumbo, ChangoMás, Día, Farmacity, Disco y Vea**
    (todas a la vez), con fallback web y filtros anti-marcas de agua.
    Podés buscar **EAN + imagen**, **solo EAN** o **solo imagen**.
    """)

    with gr.Tabs():
        # PESTAÑA 1: CONSULTA INDIVIDUAL
        with gr.Tab("🔎 Consulta individual"):
            with gr.Row():
                with gr.Column():
                    prod_nombre = gr.Textbox(
                        label="Nombre del producto o código EAN",
                        placeholder="Ej: TOSTADITAS DE ARROZ TIA MARUCA x120 gr  —  o  7790895000997",
                    )
                    modo_individual = gr.Radio(list(OPCIONES_MODO), value="EAN + Imagen", label="¿Qué buscar?")
                    solo_oficiales_individual = gr.Checkbox(label="🛡️ Solo catálogos oficiales (0% marcas de agua)",
                                                            value=False)
                    serper_individual = gr.Textbox(label="Serper API Key (opcional)", type="password")
                    btn_buscar_uno = gr.Button("Buscar", variant="primary")
                with gr.Column():
                    imagen_preview = gr.Image(label="Imagen encontrada", type="filepath")
                    detalles_md = gr.Markdown("Escribí un producto para ver la información.")

            entradas = [prod_nombre, modo_individual, serper_individual, solo_oficiales_individual]
            btn_buscar_uno.click(fn=buscar_individual, inputs=entradas, outputs=[imagen_preview, detalles_md])
            prod_nombre.submit(fn=buscar_individual, inputs=entradas, outputs=[imagen_preview, detalles_md])

        # PESTAÑA 2: PROCESAMIENTO POR LOTES
        with gr.Tab("📁 Procesar Excel / CSV"):
            with gr.Row():
                with gr.Column(scale=1):
                    archivo_input = gr.File(label="Subir archivo (.xlsx o .csv)",
                                            file_types=[".xlsx", ".xls", ".csv"], type="filepath")
                    columna_dropdown = gr.Dropdown(label="Columna con el nombre del producto", choices=[],
                                                   interactive=True)
                    columna_ean_dropdown = gr.Dropdown(label="Columna con EAN existente (opcional)", choices=[],
                                                       interactive=True)
                    modo_lote = gr.Radio(list(OPCIONES_MODO), value="EAN + Imagen", label="¿Qué buscar?")
                    descargar_check = gr.Checkbox(label="Descargar imágenes (ZIP)", value=True)
                    solo_oficiales_check = gr.Checkbox(
                        label="🛡️ Modo estricto: solo catálogos oficiales (0% marcas de agua)", value=False,
                        info="Si el producto no está en un catálogo oficial, no trae fotos dudosas de la web.",
                    )
                    max_filas_input = gr.Number(label="Límite de filas (0 = todas)", value=0, precision=0)
                    serper_key_input = gr.Textbox(label="API Key de Serper.dev (opcional)", type="password")
                    btn_procesar = gr.Button("🚀 Comenzar búsqueda", variant="primary", size="lg")

                with gr.Column(scale=2):
                    estado_info = gr.Markdown("Subí un archivo para previsualizarlo.")
                    preview_input_table = gr.Dataframe(label="Vista previa del archivo", interactive=False)
                    gr.Markdown("### 📊 Resultados")
                    resumen_texto = gr.Markdown("")
                    tabla_resultados = gr.Dataframe(label="Primeros 50 resultados", interactive=False)
                    with gr.Row():
                        descarga_excel = gr.File(label="📥 Excel con resultados")
                        descarga_zip = gr.File(label="📦 ZIP con imágenes")

            archivo_input.change(
                fn=previsualizar_archivo, inputs=[archivo_input],
                outputs=[preview_input_table, columna_dropdown, columna_ean_dropdown, estado_info],
            )
            btn_procesar.click(
                fn=procesar_lote,
                inputs=[archivo_input, columna_dropdown, columna_ean_dropdown, modo_lote, descargar_check,
                        serper_key_input, max_filas_input, solo_oficiales_check],
                outputs=[descarga_excel, descarga_zip, tabla_resultados, resumen_texto],
            )

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, inbrowser=True, theme=gr.themes.Soft())
