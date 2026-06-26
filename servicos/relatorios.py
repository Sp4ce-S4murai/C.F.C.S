"""
servicos/relatorios.py — Lógica de consulta para relatórios e exportações.

Queries de agregação para visão mensal (calendário), anual (relatórios)
e exportação CSV. Pronto para ser reutilizado por futuras visualizações.
"""

import csv
import io
import calendar
from datetime import date

from database import get_connection


# ---------------------------------------------------------------------------
# Dados mensais (calendário)
# ---------------------------------------------------------------------------

def get_dados_mensais(ano: int, mes: int) -> dict:
    """Retorna os dados consolidados do mês para exibição no calendário.

    Retorna dict com:
      - dia_map: {data_str: {data, abertura, fechamento, total_vendas, num_vendas}}
      - cal: grade do calendário (semanas × dias)
      - month_name: nome do mês
    """
    mes = max(1, min(12, mes))

    cal = calendar.monthcalendar(ano, mes)
    month_name = calendar.month_name[mes]

    primeiro_dia = date(ano, mes, 1).isoformat()
    ultimo_dia = date(ano, mes, calendar.monthrange(ano, mes)[1]).isoformat()

    # Dados do caixa_diario com vendas associadas
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT c.data,
                      c.abertura_caixa,
                      c.fechamento_caixa,
                      COALESCE(SUM(v.valor_venda), 0) as total_vendas,
                      COUNT(v.id) as num_vendas
               FROM caixa_diario c
               LEFT JOIN vendas v ON v.data_venda = c.data
               WHERE c.data >= ? AND c.data <= ?
               GROUP BY c.data""",
            (primeiro_dia, ultimo_dia),
        ).fetchall()

    dia_map = {r["data"]: dict(r) for r in rows}

    # Complementar com dias que têm vendas mas não têm caixa_diario
    with get_connection() as conn:
        vrows = conn.execute(
            """SELECT data_venda as data,
                      COALESCE(SUM(valor_venda),0) as total_vendas,
                      COUNT(*) as num_vendas
               FROM vendas WHERE data_venda >= ? AND data_venda <= ?
               GROUP BY data_venda""",
            (primeiro_dia, ultimo_dia),
        ).fetchall()

    for r in vrows:
        key = r["data"]
        if key not in dia_map:
            dia_map[key] = {
                "data": key,
                "abertura_caixa": 0.0,
                "fechamento_caixa": r["total_vendas"],
                "total_vendas": r["total_vendas"],
                "num_vendas": r["num_vendas"],
            }

    return {
        "cal": cal,
        "month_name": month_name,
        "dia_map": dia_map,
    }


# ---------------------------------------------------------------------------
# Dados anuais (relatórios)
# ---------------------------------------------------------------------------

def get_anos_disponiveis() -> list[int]:
    """Retorna os anos que possuem dados de vendas, em ordem decrescente."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT strftime('%Y', data_venda) as a FROM vendas WHERE a IS NOT NULL ORDER BY a DESC"
        ).fetchall()
    return [int(r["a"]) for r in rows if r["a"]]


def get_todos_fotografos() -> list[str]:
    """Retorna a lista de todos os fotógrafos que possuem vendas registradas."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT fotografo FROM vendas WHERE fotografo != '' ORDER BY fotografo"
        ).fetchall()
    return [r["fotografo"] for r in rows]


def get_todos_vendedores() -> list[str]:
    """Retorna a lista de todos os vendedores que possuem vendas registradas."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT vendedor FROM vendas WHERE vendedor != '' ORDER BY vendedor"
        ).fetchall()
    return [r["vendedor"] for r in rows]


def get_dados_anuais(ano: int, fotografo: str = None, vendedor: str = None) -> dict:
    """Retorna todos os dados consolidados do ano para o relatório.

    Retorna dict com:
      - monthly_data: lista de 12 meses com total e num_vendas
      - total_ano, total_vendas_ano, ticket_medio, melhor_mes
      - canais_data, cidades_data, formas_data, equipe_data, vendedores_data
    """
    ano_str = str(ano)

    # Totais mensais
    query_monthly = """SELECT CAST(strftime('%m', data_venda) AS INTEGER) as mes,
                              COALESCE(SUM(valor_venda), 0) as total,
                              COUNT(*) as num_vendas
                       FROM vendas
                       WHERE strftime('%Y', data_venda) = ?"""
    params_monthly = [ano_str]
    if fotografo:
        query_monthly += " AND fotografo = ?"
        params_monthly.append(fotografo)
    if vendedor:
        query_monthly += " AND vendedor = ?"
        params_monthly.append(vendedor)
    query_monthly += " GROUP BY mes ORDER BY mes"

    with get_connection() as conn:
        monthly_rows = conn.execute(query_monthly, params_monthly).fetchall()

    monthly_map = {r["mes"]: dict(r) for r in monthly_rows}
    monthly_data = []
    for m in range(1, 13):
        info = monthly_map.get(m, {"total": 0.0, "num_vendas": 0})
        monthly_data.append({
            "mes":        m,
            "nome":       calendar.month_abbr[m].upper(),
            "total":      float(info["total"]),
            "num_vendas": int(info["num_vendas"]),
        })

    total_ano = sum(m["total"] for m in monthly_data)
    total_vendas_ano = sum(m["num_vendas"] for m in monthly_data)
    ticket_medio = total_ano / total_vendas_ano if total_vendas_ano else 0.0
    melhor_mes = (
        max(monthly_data, key=lambda x: x["total"])
        if any(m["total"] for m in monthly_data)
        else None
    )

    # Ranking por canal de venda
    query_canais = """SELECT canal_venda, COUNT(*) as num, COALESCE(SUM(valor_venda), 0) as total
                      FROM vendas
                      WHERE strftime('%Y', data_venda) = ? AND canal_venda != ''"""
    params_canais = [ano_str]
    if fotografo:
        query_canais += " AND fotografo = ?"
        params_canais.append(fotografo)
    if vendedor:
        query_canais += " AND vendedor = ?"
        params_canais.append(vendedor)
    query_canais += " GROUP BY canal_venda ORDER BY total DESC LIMIT 10"

    with get_connection() as conn:
        canais_rows = conn.execute(query_canais, params_canais).fetchall()
    canais_data = [dict(r) for r in canais_rows]

    # Ranking por cidade (top 10)
    query_cidades = """SELECT cidade_origem, COUNT(*) as num, COALESCE(SUM(valor_venda), 0) as total
                       FROM vendas
                       WHERE strftime('%Y', data_venda) = ? AND cidade_origem != ''"""
    params_cidades = [ano_str]
    if fotografo:
        query_cidades += " AND fotografo = ?"
        params_cidades.append(fotografo)
    if vendedor:
        query_cidades += " AND vendedor = ?"
        params_cidades.append(vendedor)
    query_cidades += " GROUP BY cidade_origem ORDER BY total DESC LIMIT 10"

    with get_connection() as conn:
        cidades_rows = conn.execute(query_cidades, params_cidades).fetchall()
    cidades_data = [dict(r) for r in cidades_rows]

    # Breakdown por forma de pagamento
    query_formas = """SELECT vp.forma_pagamento, COALESCE(SUM(vp.valor), 0) as total
                      FROM venda_pagamentos vp
                      JOIN vendas v ON v.id = vp.venda_id
                      WHERE strftime('%Y', v.data_venda) = ?"""
    params_formas = [ano_str]
    if fotografo:
        query_formas += " AND v.fotografo = ?"
        params_formas.append(fotografo)
    if vendedor:
        query_formas += " AND v.vendedor = ?"
        params_formas.append(vendedor)
    query_formas += " GROUP BY vp.forma_pagamento ORDER BY total DESC"

    with get_connection() as conn:
        formas_rows = conn.execute(query_formas, params_formas).fetchall()
    formas_data = [dict(r) for r in formas_rows]

    # Ranking por fotógrafo/equipe
    query_equipe = """SELECT fotografo, COUNT(*) as num, COALESCE(SUM(valor_venda), 0) as total
                      FROM vendas
                      WHERE strftime('%Y', data_venda) = ? AND fotografo != ''"""
    params_equipe = [ano_str]
    if fotografo:
        query_equipe += " AND fotografo = ?"
        params_equipe.append(fotografo)
    if vendedor:
        query_equipe += " AND vendedor = ?"
        params_equipe.append(vendedor)
    query_equipe += " GROUP BY fotografo ORDER BY total DESC LIMIT 10"

    with get_connection() as conn:
        equipe_rows = conn.execute(query_equipe, params_equipe).fetchall()
    equipe_data = [dict(r) for r in equipe_rows]

    # Ranking por vendedor
    query_vendedores = """SELECT vendedor, COUNT(*) as num, COALESCE(SUM(valor_venda), 0) as total
                          FROM vendas
                          WHERE strftime('%Y', data_venda) = ? AND vendedor != ''"""
    params_vendedores = [ano_str]
    if fotografo:
        query_vendedores += " AND fotografo = ?"
        params_vendedores.append(fotografo)
    if vendedor:
        query_vendedores += " AND vendedor = ?"
        params_vendedores.append(vendedor)
    query_vendedores += " GROUP BY vendedor ORDER BY total DESC LIMIT 10"

    with get_connection() as conn:
        vendedores_rows = conn.execute(query_vendedores, params_vendedores).fetchall()
    vendedores_data = [dict(r) for r in vendedores_rows]

    return {
        "monthly_data": monthly_data,
        "total_ano": total_ano,
        "total_vendas_ano": total_vendas_ano,
        "ticket_medio": ticket_medio,
        "melhor_mes": melhor_mes,
        "canais_data": canais_data,
        "cidades_data": cidades_data,
        "formas_data": formas_data,
        "equipe_data": equipe_data,
        "vendedores_data": vendedores_data,
    }


# ---------------------------------------------------------------------------
# Exportação CSV
# ---------------------------------------------------------------------------

def gerar_csv_mensal(ano: int, mes: int) -> tuple[str, str]:
    """Gera conteúdo CSV das vendas do mês (delimitado por ponto-e-vírgula).

    Retorna (conteudo_csv, nome_arquivo).
    O conteúdo inclui BOM UTF-8 para compatibilidade com Excel.
    """
    mes = max(1, min(12, mes))
    primeiro_dia = date(ano, mes, 1).isoformat()
    ultimo_dia = date(ano, mes, calendar.monthrange(ano, mes)[1]).isoformat()

    with get_connection() as conn:
        rows = conn.execute(
            """SELECT v.data_venda, v.num_pessoas, v.canal_venda,
                      v.cidade_origem, v.fotografo, v.vendedor,
                      v.valor_venda, v.forma_pagamento
               FROM vendas v
               WHERE v.data_venda >= ? AND v.data_venda <= ?
               ORDER BY v.data_venda, v.id""",
            (primeiro_dia, ultimo_dia),
        ).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([
        "Data", "Pessoas", "Canal", "Cidade",
        "Fotógrafo", "Vendedor", "Valor (R$)", "Pagamento",
    ])
    for r in rows:
        writer.writerow([
            r["data_venda"],
            r["num_pessoas"],
            r["canal_venda"],
            r["cidade_origem"],
            r["fotografo"],
            r["vendedor"],
            f"{r['valor_venda']:.2f}".replace(".", ","),
            r["forma_pagamento"],
        ])

    month_abbr = calendar.month_abbr[mes].upper()
    filename = f"CFCS_{ano}_{mes:02d}_{month_abbr}.csv"

    # BOM UTF-8 para compatibilidade com Excel
    conteudo = "\ufeff" + buf.getvalue()

    return conteudo, filename
