"""
rotas/mapa.py — Blueprint da página do Mapa de Calor e API de dados espaciais.

Gerencia a renderização do dashboard do mapa e fornece os endpoints JSON
consumidos de forma assíncrona pelo JavaScript da interface.
"""

from datetime import date
from flask import Blueprint, render_template, request, jsonify

from servicos.relatorios import get_anos_disponiveis
from servicos.mapa import get_dados_mapa, get_ranking_cidades

bp = Blueprint("mapa", __name__)


@bp.route("/mapa")
def pagina_mapa():
    """Exibe o painel do mapa de calor do Brasil."""
    hoje = date.today()
    ano_padrao = hoje.year
    mes_padrao = hoje.month

    # Obter anos que possuem dados registrados
    anos_disponiveis = get_anos_disponiveis()
    if ano_padrao not in anos_disponiveis:
        anos_disponiveis.insert(0, ano_padrao)

    return render_template(
        "mapa.html",
        ano_atual=ano_padrao,
        mes_atual=mes_padrao,
        anos_disponiveis=anos_disponiveis,
    )


@bp.route("/api/mapa/dados")
def api_mapa_dados():
    """Retorna os dados consolidados do mapa e rankings em formato JSON.

    Aceita os parâmetros opcionais via query string:
    - ano: ano das vendas (ex: 2026, ou vazio para Geral)
    - mes: mês das vendas (ex: 6, ou vazio para Geral)
    - uf: sigla do estado para detalhar cidades (ex: RS)
    """
    ano_str = request.args.get("ano", "").strip()
    mes_str = request.args.get("mes", "").strip()
    uf_str = request.args.get("uf", "").strip()

    # Tratar valores vazios ou "todos" como None
    ano = int(ano_str) if (ano_str and ano_str.isdigit()) else None
    mes = int(mes_str) if (mes_str and mes_str.isdigit()) else None
    uf = uf_str.upper() if (uf_str and len(uf_str) == 2) else None

    # Obter os dados consolidados
    dados_estados = get_dados_mapa(ano=ano, mes=mes)
    ranking_cidades = get_ranking_cidades(uf=uf, ano=ano, mes=mes, limit=15)

    return jsonify({
        "estados": dados_estados,
        "cidades": ranking_cidades,
    })
