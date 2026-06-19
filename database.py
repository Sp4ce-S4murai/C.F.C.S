import sqlite3
import os

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
                num_pessoas     INTEGER NOT NULL DEFAULT 1,
                canal_venda     TEXT    NOT NULL DEFAULT '',
                cidade_origem   TEXT    NOT NULL DEFAULT '',
                fotografo       TEXT    NOT NULL DEFAULT '',
                vendedor        TEXT    NOT NULL DEFAULT '',
                valor_venda     REAL    NOT NULL DEFAULT 0.0,
                forma_pagamento TEXT    NOT NULL DEFAULT 'DIN'
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
