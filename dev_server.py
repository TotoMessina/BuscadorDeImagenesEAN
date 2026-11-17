"""
Servidor local que imita a Vercel, para probar la web antes de subirla.
  python dev_server.py        -> abre http://localhost:3000
Sirve index.html y ejecuta las funciones de la carpeta api/ igual que Vercel.
(Opcional) set CLAVE_ACCESO=algo para probar la pantalla de clave.
"""

import importlib.util
import os
import sys
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

RAIZ = os.path.dirname(os.path.abspath(__file__))
API = os.path.join(RAIZ, "api")
PUERTO = int(os.environ.get("PORT", 3000))
sys.path.insert(0, RAIZ)
sys.path.insert(0, API)

_modulos = {}


def cargar_funcion(nombre):
    if nombre not in _modulos:
        ruta = os.path.join(API, f"{nombre}.py")
        if nombre.startswith("_") or not os.path.isfile(ruta):
            return None
        spec = importlib.util.spec_from_file_location(f"api_{nombre}", ruta)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        _modulos[nombre] = modulo.handler
    return _modulos[nombre]


class Despachador(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=RAIZ, **kwargs)

    def _api(self):
        ruta = self.path.split("?")[0]
        if not ruta.startswith("/api/"):
            return False
        clase = cargar_funcion(ruta[len("/api/"):].strip("/"))
        if clase is None:
            self.send_error(404)
            return True
        metodo = getattr(clase, f"do_{self.command}", None)
        if metodo is None:
            self.send_error(405)
            return True
        metodo(self)  # ejecuta el método de la función de Vercel sobre esta misma petición
        return True

    def do_GET(self):
        if not self._api():
            super().do_GET()

    def do_POST(self):
        if not self._api():
            self.send_error(405)

    def log_message(self, formato, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {formato % args}\n")


if __name__ == "__main__":
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), Despachador)
    url = f"http://localhost:{PUERTO}"
    print(f"Servidor local en {url}  (Ctrl+C para cortar)")
    if "--no-abrir" not in sys.argv:
        webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
