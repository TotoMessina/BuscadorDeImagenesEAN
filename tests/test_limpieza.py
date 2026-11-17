"""
Pruebas de la limpieza de nombres, tamaños, EAN y claves del catálogo.

Correr desde la carpeta del proyecto:
    python -m pytest

Los nombres son reales, sacados de productos.xlsx. Si se cambia una regla de limpieza y alguna
prueba falla, revisar si el resultado nuevo es mejor (y actualizar la prueba) o si se rompió algo.
No usan internet: corren en un segundo.
"""

import pytest

from buscador_productos import (
    limpiar_nombre_producto,
    extraer_tamano,
    formatear_contenido,
    clave_catalogo,
    es_mismo_producto,
    ean_valido,
    es_ean_interno,
    normalizar_ean_celda,
    normalizar_marca,
    extraer_eans_de_texto,
)

# (nombre en la lista, nombre limpio esperado, tamaño esperado en g/ml)
NOMBRES_REALES = [
    # Formato típico "NOMBRE x<tamaño> <unidad>"
    ("ACETO BALSAMICO x250 ml", "aceto balsamico 250 ml", 250),
    ("AMARULA COFFE x750 ml", "amarula coffe 750 ml", 750),
    ("ACONDICIONADOR ESTRELLA EQUILIBRIO x350 ml", "acondicionador estrella equilibrio 350 ml", 350),
    ("ALOEVINE UVA x500 ml", "aloevine uva 500 ml", 500),
    ("AVENA TRADICIONAL NF x300 gr", "avena tradicional nf 300 gr", 300),
    ("BIZCOCHUELO VAINILLA CUADRADO x750 gr", "bizcochuelo vainilla cuadrado 750 gr", 750),
    ("CARAMELOS ACIDOS FRUTALES SURTIDOS x450 gr", "caramelos acidos frutales surtidos 450 gr", 450),
    ("CHOCOLATE EN TAZA BONAFIDE x100 gr", "chocolate en taza bonafide 100 gr", 100),
    ("COPOS DE MAIZ AZUCARADOS GAONA x200 gr", "copos de maiz azucarados gaona 200 gr", 200),
    ("DON MIGUEL BUDIN MARMOLADO x170 gr", "don miguel budin marmolado 170 gr", 170),
    ("FANTA MELON LATA x355 ml", "fanta melon lata 355 ml", 355),
    ("MARTINI BIANCO x1000 ml", "martini bianco 1000 ml", 1000),
    ("PAN LACTAL MULTIGRANOS MASA MADRE BAUDUC x390 gr", "pan lactal multigranos masa madre bauduc 390 gr", 390),
    ("PALITOS SALADOS JAMON SERRANO x120 gr", "palitos salados jamon serrano 120 gr", 120),
    ("TERMA CERO POMELO ROSADO PET x1350 ml", "terma cero pomelo rosado pet 1350 ml", 1350),
    ("TRES TORRES BLANCO PET x1500 ml", "tres torres blanco pet 1500 ml", 1500),
    ("TARAGUI x500 gr", "taragui 500 gr", 500),
    # Kilos y litros
    ("CELUSAL GRUESA SALERO x1 kg", "celusal gruesa salero 1 kg", 1000),
    ("CELUSAL ENTREFINA SALERO x1 kg", "celusal entrefina salero 1 kg", 1000),
    ("COCA COLA 1.5 LT", "coca cola 1.5 lt", 1500),
    # Tildes y eñes
    ("OKF SPARKLING PIÑA ESPUMOSA x350 ml", "okf sparkling pina espumosa 350 ml", 350),
    ("TURRÓN DE MANÍ CON FRUTAS x80 gr", "turron de mani con frutas 80 gr", 80),
    ("FLYNN PAFF CHUPETÍN TUTTI FRUTTI x24 un", "flynn paff chupetin tutti frutti", None),
    # Porcentajes y grados de alcohol
    ("DR LEMON VODKA POMELO 5% LATA x473 ml", "dr lemon vodka pomelo lata 473 ml", 473),
    ("DR LEMON LIMON 4% BOTELLA x1000 ml", "dr lemon limon botella 1000 ml", 1000),
    ("GANCIA LIMA LIMON ONE 3,5% x473 ml", "gancia lima limon one 473 ml", 473),
    ("SMUDIS NARANJA 100% x500 ml", "smudis naranja 500 ml", 500),
    ("AMARGO OBRERO 19° x950 ml", "amargo obrero 950 ml", 950),
    ("PRONTO SHAKE 4,5° LATA x473 ml", "pronto shake lata 473 ml", 473),
    ("FERNET CON POMELO 7° LATA x473 ml", "fernet con pomelo lata 473 ml", 473),
    # Bultos: "x20 un", "x 12 UNID", cantidades delante del tamaño
    ("COMBO CELUSAL x1 un", "combo celusal", None),
    ("FLOW CEREAL MANZANA LIGHT x20 un", "flow cereal manzana light", None),
    ("FLOW CEREAL AVELLANAS Y ARANDANOS X 30 G x20 un", "flow cereal avellanas y arandanos 30 g", 30),
    ("FLYNN PAFF GOMITAS SPORTS X 30 GR x12 un", "flynn paff gomitas sports 30 gr", 30),
    ("MANTECOL BOCADO BAJO SODIO X 26G x16 un", "mantecol bocado bajo sodio 26 g", 26),
    ("CANTABILE PIÑA X 10 UNIDADES x230 ml", "cantabile pina 230 ml", 230),
    ("CAPSULAS BONAFIDE ESPRESSO X10 x45 gr", "capsulas bonafide espresso 45 gr", 45),
    ("CAPSULAS NESPRESSO SELECCION 10 x50 gr", "capsulas nespresso seleccion 50 gr", 50),
    ("BUDIN GAONA CON CHIPS 15 x180 gr", "budin gaona con chips 180 gr", 180),
    ("NUGATON BLACK 24 x27 gr", "nugaton black 27 gr", 27),
    ("CHOCMAN BANANA SPLIT BONAFIDE X 18 x35 gr", "chocman banana split bonafide 35 gr", 35),
    ("JABON HUMECTANTE CREME CARE X 3 UNID x125 gr", "jabon humectante creme care 125 gr", 125),
    ("PIPAS C/C GIGANTES DISPLAY X 12 UNID x50 gr", "pipas con cascara gigantes 50 gr", 50),
    ("EXHIBIDOR PIE 2 ESTANTES GEORGALOS x1 un", "exhibidor pie 2 estantes georgalos", None),
    # Números que son parte del nombre y no se tienen que borrar
    ("FERNET 1882 x450 ml", "fernet 1882 450 ml", 450),
    ("CONITOS 5G QUESO SLICES x900 gr", "conitos 5 g queso slices 900 gr", 900),
    ("FLOW CEREAL GRANOLA CON 5 SEMILLAS x320 gr", "flow cereal granola con 5 semillas 320 gr", 320),
    # Tamaño repetido
    ("AMERICANO GANCIA X 950 ML x950 ml", "americano gancia 950 ml", 950),
    # Abreviaturas y nombres pegados con puntos
    ("ALF.MARLEYx80g.NEGRO x20", "alfajor marley 80 g negro", 80),
    ("FULL MANÍ ALFAJOR C/PASTA DE MANI x40 gr", "full mani alfajor con pasta de mani 40 gr", 40),
    ("MAGDALENA NARANJA C/ CHIPS x180 gr", "magdalena naranja con chips 180 gr", 180),
    ("VIZZIO CHOC C/LECHE Y ALMENDRAS x35 gr", "vizzio chocolate con leche y almendras 35 gr", 35),
    ("CREMA CORPORAL HIDRATACION EXP x125 ml", "crema corporal hidratacion express 125 ml", 125),
    ("DESODORANTE ROLL ON PROTEC & CARE x50 ml", "desodorante roll on protect care 50 ml", 50),
    ("TOKKE BOMBON RELL DULCE DE LECHE x30 un", "tokke bombon relleno dulce de leche", None),
    ("TABLETA CHOC VIZZIO 60%CACAO MINI x50 gr", "tableta chocolate vizzio cacao mini 50 gr", 50),
    # Caracteres raros
    ("SMUDIS BANANA/ANANA/FRUTILLA 100% x1000 ml", "smudis banana anana frutilla 1000 ml", 1000),
    ("TURRÓN DE ALMENDRAS &#34;B&#34; x90 gr", "turron de almendras b 90 gr", 90),
    ("PAPAS CORTE AMERICANO  SLICES x150 gr", "papas corte americano slices 150 gr", 150),
]


@pytest.mark.parametrize("nombre, limpio, _tamano", NOMBRES_REALES, ids=[n for n, _, _ in NOMBRES_REALES])
def test_limpiar_nombre(nombre, limpio, _tamano):
    assert limpiar_nombre_producto(nombre) == limpio


@pytest.mark.parametrize("nombre, _limpio, tamano", NOMBRES_REALES, ids=[n for n, _, _ in NOMBRES_REALES])
def test_extraer_tamano(nombre, _limpio, tamano):
    assert extraer_tamano(nombre) == tamano


@pytest.mark.parametrize("texto, esperado", [
    # Nombres como vienen de las tiendas
    ("Aperitivo con alcohol pomelo vodka Dr Lemon lata 473 cc.", 473),
    ("Bondiola de Cerdo Feteada 150 Grs Campo Austral", 150),
    ("Gaseosa cola Coca Cola sabor original 2,25 lts", 2250),
    ("Alfajor Simple Negro X 80 Grs Marley", 80),
    ("Shampoo Pantene restauración 400 ml", 400),
    ("Sin tamaño", None),
])
def test_extraer_tamano_nombres_de_tienda(texto, esperado):
    assert extraer_tamano(texto) == esperado


@pytest.mark.parametrize("texto, esperado", [
    ("Dr Lemon lata 473 cc.", "473 ml"),
    ("Coca Cola 2,25 lts", "2,25 l"),
    ("COCA COLA 1.5 LT", "1,5 l"),
    ("Alfajor X 80 Grs", "80 g"),
    ("CELUSAL x1 kg", "1 kg"),
    ("CONITOS 5G QUESO SLICES x900 gr", "900 g"),
    ("COMBO CELUSAL x1 un", None),
])
def test_formatear_contenido(texto, esperado):
    assert formatear_contenido(texto) == esperado


# ----------------------------------------------------------------------------- claves del catálogo

@pytest.mark.parametrize("a, b", [
    ("CELUSAL GRUESA SALERO x1 kg", "Celusal gruesa salero 1000 gr"),
    ("COCA COLA 1.5 LT", "COCA COLA x1500 ml"),
    ("DR LEMON VODKA 5% LATA x473 ml", "Dr Lemon Vodka lata 473cc"),
    ("AVENA TRADICIONAL NF x300 gr", "avena tradicional nf 300g"),
])
def test_misma_clave_aunque_este_escrito_distinto(a, b):
    assert clave_catalogo(a) == clave_catalogo(b)


def test_clave_conserva_cantidad_de_unidades():
    # En el té, "x25 un" son los saquitos: x25 y x50 son productos distintos
    assert clave_catalogo("TE TARAGUI S/E x25 un") != clave_catalogo("TE TARAGUI S/E x50 un")


def test_clave_de_un_codigo_es_none():
    assert clave_catalogo("7790895000997") is None
    assert clave_catalogo("") is None


@pytest.mark.parametrize("a, b", [
    ("CAFE SENSACIONES INTENSO BONAF x500 gr", "Cafe Sensaciones Intenso Bonafide 500g"),  # abreviatura de marca
    ("CELUSAL GRUESA SALERO x1 kg", "CELUSAL GRUESA SALERO x1000 gr"),
    ("DR LEMON VODKA LATA x473 ml", "DR LEMON VODKA x473 ml"),  # "lata" no distingue
])
def test_es_mismo_producto(a, b):
    assert es_mismo_producto(clave_catalogo(a), clave_catalogo(b))


@pytest.mark.parametrize("a, b", [
    ("ALF.MARLEYx80g.NEGRO x20", "ALF.MARLEYx80g.BLANCO x20"),           # otra variante
    ("TOSTADA DE ARROZ SIN SAL x150 gr", "TOSTADA DE ARROZ CON SAL x150 gr"),
    ("FANTA MELON LATA x355 ml", "FANTA NARANJA LATA x355 ml"),          # otro sabor
    ("BUDIN GAONA VAINILLA x180 gr", "BUDIN GAONA VAINILLA x200 gr"),    # otro tamaño
    ("ARROZ LUCATO 4 CEROS (NARANJA) x500 gr", "ARROZ LUCATO 0000 500G"),  # parecido: solo se sugiere
    ("TE TARAGUI S/E x25 un", "TE TARAGUI S/E x50 un"),
])
def test_no_es_mismo_producto(a, b):
    assert not es_mismo_producto(clave_catalogo(a), clave_catalogo(b))


# ----------------------------------------------------------------------------- EAN

@pytest.mark.parametrize("codigo, valido", [
    ("7790895000997", True),    # Coca-Cola 2,25 L
    ("7790950140859", True),    # Dr Lemon
    ("7798359560445", True),    # Marley
    ("96385074", True),         # EAN-8
    ("7790895000998", False),   # dígito verificador mal
    ("123", False),
    ("", False),
    (None, False),
    ("77908950009AB", False),
])
def test_ean_valido(codigo, valido):
    assert ean_valido(codigo) is valido


def test_ean_interno_de_tienda():
    assert es_ean_interno("2051160000000")
    assert not es_ean_interno("7790895000997")


@pytest.mark.parametrize("celda, esperado", [
    (7790895000997.0, "7790895000997"),      # Excel lo guarda como número
    ("7790895000997.0", "7790895000997"),
    ("779 0895 000997", "7790895000997"),
    ("779-0895-000997", "7790895000997"),
    (float("nan"), None),
    (None, None),
    ("sin ean", None),
    ("2.05116e+12", None),                    # notación científica: el número ya se perdió
])
def test_normalizar_ean_celda(celda, esperado):
    assert normalizar_ean_celda(celda) == esperado


def test_extraer_eans_de_texto_prioriza_779_y_descarta_invalidos():
    texto = "Código 1234567890123, también 4005900847058 y el nuestro 7790895000997"
    assert extraer_eans_de_texto(texto) == ["7790895000997", "4005900847058"]


@pytest.mark.parametrize("marca, esperado", [
    ("CAMPO AUSTRAL", "Campo Austral"),
    ("MARLEY", "Marley"),
    ("Dr. Lemon", "Dr. Lemon"),
    ("tía maruca", "Tía Maruca"),
    ("", None),
    (None, None),
])
def test_normalizar_marca(marca, esperado):
    assert normalizar_marca(marca) == esperado
