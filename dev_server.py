"""
Servidor local para probar la web antes de subirla.
  python dev_server.py        -> abre http://localhost:3000
Usa exactamente la misma app (app.py) que se publica en Vercel.
(Opcional) set CLAVE_ACCESO=algo para probar la pantalla de clave.
"""

import os
import sys
import webbrowser
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server

from app import app

PUERTO = int(os.environ.get("PORT", 3000))


class ServidorConHilos(ThreadingMixIn, WSGIServer):
    daemon_threads = True  # varias búsquedas a la vez, como en Vercel


class Registro(WSGIRequestHandler):
    def log_message(self, formato, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {formato % args}\n")


if __name__ == "__main__":
    servidor = make_server("127.0.0.1", PUERTO, app, server_class=ServidorConHilos, handler_class=Registro)
    url = f"http://localhost:{PUERTO}"
    print(f"Servidor local en {url}  (Ctrl+C para cortar)")
    if "--no-abrir" not in sys.argv:
        webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
