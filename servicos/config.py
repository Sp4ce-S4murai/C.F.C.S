"""
servicos/config.py — Lógica de negócio das configurações.

Gerencia canais de venda, cidades, equipe e número do WhatsApp.
"""

from database import get_connection


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------

def get_config(tipo: str) -> list[str]:
    """Retorna todos os valores de configuração de um tipo, ordenados."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT valor FROM configuracoes WHERE tipo = ? ORDER BY valor",
            (tipo,),
        ).fetchall()
    return [r["valor"] for r in rows]


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------

def autosave_config(tipo: str, valor: str):
    """Salva silenciosamente um novo valor de configuração, se não existir.

    Usado para auto-salvar fotógrafos, vendedores e cidades à medida
    que são informados nas vendas.
    """
    if not valor:
        return
    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO configuracoes (tipo, valor) VALUES (?, ?)",
                (tipo, valor),
            )
        except Exception:
            pass


def adicionar_config(tipo: str, valor: str) -> tuple[bool, str]:
    """Adiciona um novo valor de configuração.

    Retorna (sucesso: bool, mensagem: str).
    """
    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO configuracoes (tipo, valor) VALUES (?, ?)",
                (tipo, valor),
            )
            return True, f'"{valor}" adicionado com sucesso.'
        except Exception:
            return False, f'"{valor}" já existe nesta lista.'


def remover_config(tipo: str, valor: str):
    """Remove um valor de configuração pelo tipo e valor."""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM configuracoes WHERE tipo = ? AND valor = ?",
            (tipo, valor),
        )
