"""
servicos/vendas.py — Lógica de negócio de vendas e pagamentos.

CRUD completo de vendas, parsing de pagamentos do formulário,
e consultas de subtotais por forma de pagamento.
"""

from flask import request as flask_request

from database import get_connection, get_pagamentos_da_venda
from helpers import FORMAS_VALIDAS, parse_money
from servicos.caixa import get_or_create_caixa, recalc_fechamento


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------

def get_vendas_do_dia(data_str: str) -> list[dict]:
    """Retorna todas as vendas do dia com seus pagamentos detalhados."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM vendas WHERE data_venda = ? ORDER BY id",
            (data_str,),
        ).fetchall()
    vendas = [dict(r) for r in rows]
    for v in vendas:
        v["pagamentos"] = get_pagamentos_da_venda(v["id"])
    return vendas


def get_subtotais(data_str: str) -> dict:
    """Soma vendas por forma de pagamento usando venda_pagamentos.

    Retorna dict com chaves DIN, CRE, DEB, PIX, VCH e seus totais.
    Funciona corretamente mesmo para vendas MIX (múltiplas formas).
    """
    formas = ["DIN", "CRE", "DEB", "PIX", "VCH"]
    resultado = {f: 0.0 for f in formas}
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT vp.forma_pagamento, COALESCE(SUM(vp.valor), 0) as subtotal
               FROM venda_pagamentos vp
               JOIN vendas v ON v.id = vp.venda_id
               WHERE v.data_venda = ?
               GROUP BY vp.forma_pagamento""",
            (data_str,),
        ).fetchall()
    for r in rows:
        if r["forma_pagamento"] in resultado:
            resultado[r["forma_pagamento"]] += r["subtotal"]
    return resultado


# ---------------------------------------------------------------------------
# Parsing de formulário
# ---------------------------------------------------------------------------

def parse_pagamentos_do_form() -> list[dict]:
    """Extrai as parcelas de pagamento do formulário submetido.

    Lê campos forma_pagamento_1, valor_pagamento_1, forma_pagamento_2, etc.
    Retorna lista de dicts {forma, valor}.
    Inclui fallback para campo único (quando JS está desabilitado).
    """
    pagamentos = []
    i = 1
    while True:
        forma_key = f"forma_pagamento_{i}"
        valor_key = f"valor_pagamento_{i}"
        if forma_key not in flask_request.form:
            break
        forma = flask_request.form.get(forma_key, "DIN").strip().upper()
        valor = parse_money(flask_request.form.get(valor_key, "0").strip())
        if forma in FORMAS_VALIDAS and valor > 0:
            pagamentos.append({"forma": forma, "valor": valor})
        i += 1

    # Fallback: campo único legado (JS desabilitado)
    if not pagamentos:
        forma = flask_request.form.get("forma_pagamento", "DIN").strip().upper()
        valor_raw = flask_request.form.get("valor_venda", "0").strip()
        valor = parse_money(valor_raw)
        if valor > 0:
            pagamentos.append({"forma": forma, "valor": valor})

    return pagamentos


# ---------------------------------------------------------------------------
# CRUD de vendas
# ---------------------------------------------------------------------------

def criar_venda(data_str: str, num_pessoas: int, canal_venda: str,
                cidade_origem: str, fotografo: str, vendedor: str,
                pagamentos: list[dict]):
    """Cria uma nova venda com seus pagamentos.

    Recalcula automaticamente o fechamento do caixa após a inserção.
    """
    valor_total = sum(p["valor"] for p in pagamentos)
    forma_principal = pagamentos[0]["forma"] if len(pagamentos) == 1 else "MIX"

    get_or_create_caixa(data_str)

    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO vendas
               (data_venda, num_pessoas, canal_venda, cidade_origem,
                fotografo, vendedor, valor_venda, forma_pagamento)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (data_str, num_pessoas, canal_venda, cidade_origem,
             fotografo, vendedor, valor_total, forma_principal),
        )
        venda_id = cursor.lastrowid
        conn.executemany(
            "INSERT INTO venda_pagamentos (venda_id, forma_pagamento, valor) VALUES (?, ?, ?)",
            [(venda_id, p["forma"], p["valor"]) for p in pagamentos],
        )

    recalc_fechamento(data_str)


def editar_venda(data_str: str, venda_id: int, num_pessoas: int,
                 canal_venda: str, cidade_origem: str, fotografo: str,
                 vendedor: str, pagamentos: list[dict]) -> bool:
    """Atualiza uma venda existente.

    Retorna True se a venda foi encontrada e atualizada, False caso contrário.
    Recalcula automaticamente o fechamento do caixa.
    """
    valor_total = sum(p["valor"] for p in pagamentos)
    forma_principal = pagamentos[0]["forma"] if len(pagamentos) == 1 else "MIX"

    with get_connection() as conn:
        existe = conn.execute(
            "SELECT 1 FROM vendas WHERE id = ? AND data_venda = ?", (venda_id, data_str)
        ).fetchone()
        if not existe:
            return False

        conn.execute(
            """UPDATE vendas SET
               num_pessoas=?, canal_venda=?, cidade_origem=?,
               fotografo=?, vendedor=?, valor_venda=?, forma_pagamento=?
               WHERE id=?""",
            (num_pessoas, canal_venda, cidade_origem,
             fotografo, vendedor, valor_total, forma_principal, venda_id),
        )
        conn.execute("DELETE FROM venda_pagamentos WHERE venda_id = ?", (venda_id,))
        conn.executemany(
            "INSERT INTO venda_pagamentos (venda_id, forma_pagamento, valor) VALUES (?, ?, ?)",
            [(venda_id, p["forma"], p["valor"]) for p in pagamentos],
        )

    recalc_fechamento(data_str)
    return True


def excluir_venda(data_str: str, venda_id: int):
    """Remove uma venda e seus pagamentos (cascade via FK).

    Recalcula automaticamente o fechamento do caixa.
    """
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM vendas WHERE id = ? AND data_venda = ?",
            (venda_id, data_str),
        )
    recalc_fechamento(data_str)
