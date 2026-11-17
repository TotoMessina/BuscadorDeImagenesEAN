import os
import sys

# Permite importar los módulos del proyecto (buscador_productos, catalogo_db) desde las pruebas
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
