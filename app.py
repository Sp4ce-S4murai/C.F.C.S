"""
app.py — Entry point do C.F.C.S (Cash Flow Control System)

Ponto de entrada da aplicação Flask. Cria a app, registra blueprints,
configura filtros Jinja2 e inicia o servidor.

by OCTO
"""

import os
import secrets
import threading
import webbrowser
import time

from flask import Flask

from database import init_db, seed_defaults, backup_db
from helpers import fmt_brl


# ---------------------------------------------------------------------------
# Factory da aplicação
# ---------------------------------------------------------------------------

def criar_app() -> Flask:
    """Cria e configura a instância Flask com todos os blueprints."""
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False

    # Chave secreta persistente e única por instalação (nunca hardcoded)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    secret_file = os.path.join(base_dir, ".secret_key")
    if not os.path.exists(secret_file):
        with open(secret_file, "w") as f:
            f.write(secrets.token_hex(32))
    with open(secret_file) as f:
        app.secret_key = f.read().strip()

    # Registrar filtro Jinja2 global para formatação monetária
    # Uso nos templates: {{ valor|brl }}
    app.jinja_env.filters["brl"] = fmt_brl

    # Registrar blueprints (rotas)
    from rotas.diario import bp as diario_bp
    from rotas.calendario import bp as calendario_bp
    from rotas.relatorios import bp as relatorios_bp
    from rotas.admin import bp as admin_bp
    from rotas.api import bp as api_bp
    from rotas.mapa import bp as mapa_bp

    app.register_blueprint(diario_bp)
    app.register_blueprint(calendario_bp)
    app.register_blueprint(relatorios_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(mapa_bp)

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = criar_app()
    init_db()
    seed_defaults()
    bk = backup_db()

    print("\n" + "=" * 60)
    print("  C.F.C.S  //  CASH FLOW CONTROL SYSTEM")
    print("  BY OCTO")
    print("=" * 60)
    if bk:
        print(f"  BACKUP   >>  backups/{os.path.basename(bk)}")
    print("  SYSTEM ONLINE  >>  http://127.0.0.1:5000")
    print("  CTRL+C TO TERMINATE")
    print("=" * 60 + "\n")

    def abrir_navegador():
        """Abre o navegador após 1.5s para dar tempo do servidor iniciar."""
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:5000")

    threading.Thread(target=abrir_navegador, daemon=True).start()

    app.run(debug=False, host="127.0.0.1", port=5000)
