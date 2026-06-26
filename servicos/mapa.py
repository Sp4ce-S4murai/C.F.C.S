"""
servicos/mapa.py — Lógica de agregação para o Mapa de Calor.

Queries SQL para consolidar atendimentos e faturamento agrupados por UF
e por município, alimentando de forma eficiente e modular o mapa interativo.
"""

from database import get_connection


def get_dados_mapa(ano: int = None, mes: int = None) -> dict[str, dict]:
    """Retorna dados consolidados de vendas por Unidade Federativa (UF).

    Filtra opcionalmente por ano e mês.
    Retorna um dicionário estruturado como:
    {
        'RS': {'vendas': 12, 'faturamento': 2500.0, 'clientes': 18},
        'SP': {'vendas': 5, 'faturamento': 900.0, 'clientes': 8},
        ...
    }
    """
    query = """
        SELECT
            SUBSTR(cidade_origem, -2) as uf,
            COUNT(*) as total_vendas,
            COALESCE(SUM(valor_venda), 0.0) as faturamento,
            COALESCE(SUM(num_pessoas), 0) as total_clientes
        FROM vendas
        WHERE cidade_origem LIKE '%-%'
    """
    params = []

    if ano:
        query += " AND strftime('%Y', data_venda) = ?"
        params.append(str(ano))
    if mes:
        query += " AND CAST(strftime('%m', data_venda) AS INTEGER) = ?"
        params.append(int(mes))

    query += " GROUP BY uf"

    dados = {}
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        for r in rows:
            uf = r["uf"].upper()
            dados[uf] = {
                "vendas": int(r["total_vendas"]),
                "faturamento": float(r["faturamento"]),
                "clientes": int(r["total_clientes"]),
            }

    return dados


def get_ranking_cidades(uf: str = None, ano: int = None, mes: int = None, limit: int = 15) -> list[dict]:
    """Retorna o ranking de cidades com base no volume de vendas.

    Se 'uf' for informado, filtra apenas cidades daquele estado específico.
    Filtra opcionalmente por ano e mês.
    """
    query = """
        SELECT
            cidade_origem,
            COUNT(*) as total_vendas,
            COALESCE(SUM(valor_venda), 0.0) as faturamento,
            COALESCE(SUM(num_pessoas), 0) as total_clientes
        FROM vendas
        WHERE cidade_origem LIKE '%-%'
    """
    params = []

    if uf:
        query += " AND cidade_origem LIKE ?"
        params.append(f"%-{uf.upper()}")
    if ano:
        query += " AND strftime('%Y', data_venda) = ?"
        params.append(str(ano))
    if mes:
        query += " AND CAST(strftime('%m', data_venda) AS INTEGER) = ?"
        params.append(int(mes))

    query += " GROUP BY cidade_origem ORDER BY total_vendas DESC, faturamento DESC"

    if limit:
        query += " LIMIT ?"
        params.append(limit)

    cidades = []
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        for r in rows:
            cidades.append({
                "cidade_origem": r["cidade_origem"],
                "vendas": int(r["total_vendas"]),
                "faturamento": float(r["faturamento"]),
                "clientes": int(r["total_clientes"]),
            })

    return cidades
