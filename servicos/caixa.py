"""
servicos/caixa.py — Lógica de negócio do caixa diário.

Gerencia abertura/fechamento do caixa, retiradas e propagação
em cascata dos valores entre dias consecutivos.
"""

from database import get_connection


# ---------------------------------------------------------------------------
# Caixa diário
# ---------------------------------------------------------------------------

def get_or_create_caixa(data_str: str) -> dict:
    """Retorna o registro do caixa_diario para a data informada.

    Se não existir, cria automaticamente usando o fechamento do
    dia anterior como abertura.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM caixa_diario WHERE data = ?", (data_str,)
        ).fetchone()
        if row:
            return dict(row)

        # Buscar fechamento do dia anterior mais recente
        prev = conn.execute(
            "SELECT fechamento_caixa FROM caixa_diario WHERE data < ? ORDER BY data DESC LIMIT 1",
            (data_str,),
        ).fetchone()
        abertura = prev["fechamento_caixa"] if prev else 0.0

        conn.execute(
            "INSERT INTO caixa_diario (data, abertura_caixa, fechamento_caixa) VALUES (?, ?, ?)",
            (data_str, abertura, abertura),
        )
        return {"data": data_str, "abertura_caixa": abertura, "fechamento_caixa": abertura}


def set_abertura(data_str: str, valor: float):
    """Define manualmente o valor de abertura do caixa para o dia.

    Se o registro não existir, cria um novo.
    """
    with get_connection() as conn:
        existe = conn.execute(
            "SELECT 1 FROM caixa_diario WHERE data = ?", (data_str,)
        ).fetchone()
        if existe:
            conn.execute(
                "UPDATE caixa_diario SET abertura_caixa = ? WHERE data = ?",
                (valor, data_str),
            )
        else:
            conn.execute(
                "INSERT INTO caixa_diario (data, abertura_caixa, fechamento_caixa) VALUES (?, ?, ?)",
                (data_str, valor, valor),
            )


# ---------------------------------------------------------------------------
# Recálculo de fechamento (com propagação em cascata)
# ---------------------------------------------------------------------------

def _recalc_dia_unico(conn, data_str: str) -> float:
    """Recalcula o fechamento de um único dia.

    fechamento = abertura + entradas em dinheiro - retiradas
    Retorna o novo valor de fechamento.
    """
    caixa = conn.execute(
        "SELECT abertura_caixa FROM caixa_diario WHERE data = ?", (data_str,)
    ).fetchone()
    abertura = caixa["abertura_caixa"] if caixa else 0.0

    # Total de pagamentos em dinheiro (DIN) do dia
    total_dinheiro = conn.execute(
        """SELECT COALESCE(SUM(vp.valor), 0) as total
           FROM venda_pagamentos vp
           JOIN vendas v ON v.id = vp.venda_id
           WHERE v.data_venda = ? AND vp.forma_pagamento = 'DIN'""",
        (data_str,),
    ).fetchone()["total"]

    # Total de retiradas do dia
    total_retiradas = conn.execute(
        "SELECT COALESCE(SUM(valor),0) as total FROM retiradas_caixa WHERE data = ?",
        (data_str,),
    ).fetchone()["total"]

    fechamento = abertura + total_dinheiro - total_retiradas
    conn.execute(
        "UPDATE caixa_diario SET fechamento_caixa = ? WHERE data = ?",
        (fechamento, data_str),
    )
    return fechamento


def recalc_fechamento(data_str: str):
    """Recalcula o fechamento do dia E propaga para todos os dias futuros.

    Quando uma retirada (ou venda) é alterada em um dia passado, o
    fechamento daquele dia muda. Como a abertura do dia seguinte depende
    do fechamento anterior, precisamos propagar a atualização em cascata
    por todos os dias futuros já existentes no caixa_diario.
    """
    with get_connection() as conn:
        # 1. Recalcular o dia alvo
        fechamento = _recalc_dia_unico(conn, data_str)

        # 2. Buscar todos os dias futuros existentes (ordem cronológica)
        dias_futuros = conn.execute(
            "SELECT data FROM caixa_diario WHERE data > ? ORDER BY data ASC",
            (data_str,),
        ).fetchall()

        # 3. Cascata: abertura de cada dia = fechamento do dia anterior
        fechamento_anterior = fechamento
        for row in dias_futuros:
            proxima_data = row["data"]
            conn.execute(
                "UPDATE caixa_diario SET abertura_caixa = ? WHERE data = ?",
                (fechamento_anterior, proxima_data),
            )
            fechamento_anterior = _recalc_dia_unico(conn, proxima_data)


# ---------------------------------------------------------------------------
# Retiradas de caixa
# ---------------------------------------------------------------------------

def get_retiradas_do_dia(data_str: str) -> list[dict]:
    """Retorna todas as retiradas do dia, ordenadas por ID."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM retiradas_caixa WHERE data = ? ORDER BY id",
            (data_str,),
        ).fetchall()
    return [dict(r) for r in rows]


def criar_retirada(data_str: str, valor: float, motivo: str):
    """Insere uma nova retirada de caixa no dia informado."""
    get_or_create_caixa(data_str)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO retiradas_caixa (data, valor, motivo) VALUES (?, ?, ?)",
            (data_str, valor, motivo),
        )
    recalc_fechamento(data_str)


def excluir_retirada(data_str: str, retirada_id: int):
    """Remove uma retirada de caixa pelo ID."""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM retiradas_caixa WHERE id = ? AND data = ?",
            (retirada_id, data_str),
        )
    recalc_fechamento(data_str)
