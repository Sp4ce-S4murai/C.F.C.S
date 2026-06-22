import sqlite3
import os
import shutil
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS vendas (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                data_venda      DATE    NOT NULL,
                hora_venda      TEXT    NOT NULL DEFAULT '',
                num_pessoas     INTEGER NOT NULL DEFAULT 1,
                canal_venda     TEXT    NOT NULL DEFAULT '',
                cidade_origem   TEXT    NOT NULL DEFAULT '',
                fotografo       TEXT    NOT NULL DEFAULT '',
                vendedor        TEXT    NOT NULL DEFAULT '',
                valor_venda     REAL    NOT NULL DEFAULT 0.0,
                forma_pagamento TEXT    NOT NULL DEFAULT 'DIN'
            );

            CREATE TABLE IF NOT EXISTS venda_pagamentos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                venda_id        INTEGER NOT NULL REFERENCES vendas(id) ON DELETE CASCADE,
                forma_pagamento TEXT    NOT NULL DEFAULT 'DIN',
                valor           REAL    NOT NULL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS retiradas_caixa (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                data            DATE    NOT NULL,
                valor           REAL    NOT NULL DEFAULT 0.0,
                motivo          TEXT    NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS caixa_diario (
                data            DATE    PRIMARY KEY,
                abertura_caixa  REAL    NOT NULL DEFAULT 0.0,
                fechamento_caixa REAL   NOT NULL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS configuracoes (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo  TEXT    NOT NULL,
                valor TEXT    NOT NULL,
                UNIQUE(tipo, valor)
            );
        """)
        # Migration: add hora_venda column to existing databases
        try:
            conn.execute("ALTER TABLE vendas ADD COLUMN hora_venda TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass  # Column already exists — safe to ignore


def backup_db() -> str:
    """Create a timestamped backup of the database. Keeps the last 30 backups.
    Returns the path of the backup file created (empty string if DB not found)."""
    if not os.path.exists(DB_PATH):
        return ""
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"database_{timestamp}.db")
    shutil.copy2(DB_PATH, backup_path)
    # Prune: keep only the 30 most recent backups
    backups = sorted(
        f for f in os.listdir(backup_dir)
        if f.startswith("database_") and f.endswith(".db")
    )
    for old in backups[:-30]:
        try:
            os.remove(os.path.join(backup_dir, old))
        except OSError:
            pass
    return backup_path


def seed_defaults():
    """Insert default config values if the table is empty."""
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM configuracoes").fetchone()[0]
        if count == 0:
            defaults = [
                ("canal", "Instagram"),
                ("canal", "Facebook"),
                ("canal", "Indicação"),
                ("canal", "Google"),
                ("canal", "Panfleto"),
                ("cidade", "Gramado-RS"),
                ("cidade", "Canela-RS"),
                ("cidade", "Caxias do Sul-RS"),
                ("cidade", "Porto Alegre-RS"),
                ("equipe", "Fotógrafo 1"),
                ("equipe", "Fotógrafo 2"),
                ("equipe", "Vendedor 1"),
            ]
            conn.executemany(
                "INSERT OR IGNORE INTO configuracoes (tipo, valor) VALUES (?, ?)",
                defaults,
            )


# ---------------------------------------------------------------------------
# Payment helpers
# ---------------------------------------------------------------------------

def get_pagamentos_da_venda(venda_id: int) -> list[dict]:
    """Return list of payment slices for a given venda_id."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT forma_pagamento, valor FROM venda_pagamentos WHERE venda_id = ? ORDER BY id",
            (venda_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_venda_by_id(venda_id: int) -> dict | None:
    """Return a single venda row (with payment slices) as dict, or None."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM vendas WHERE id = ?", (venda_id,)).fetchone()
    if not row:
        return None
    v = dict(row)
    v["pagamentos"] = get_pagamentos_da_venda(venda_id)
    return v


# ---------------------------------------------------------------------------
# WhatsApp configuration helpers
# ---------------------------------------------------------------------------

def get_whatsapp_numero() -> str | None:
    """Return the configured WhatsApp phone number or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT valor FROM configuracoes WHERE tipo = 'whatsapp_numero' LIMIT 1"
        ).fetchone()
    return row["valor"] if row else None


def set_whatsapp_numero(numero: str):
    """Overwrite the WhatsApp phone number. Pass empty string to clear."""
    with get_connection() as conn:
        conn.execute("DELETE FROM configuracoes WHERE tipo = 'whatsapp_numero'")
        numero = numero.strip()
        if numero:
            conn.execute(
                "INSERT INTO configuracoes (tipo, valor) VALUES ('whatsapp_numero', ?)",
                (numero,),
            )
