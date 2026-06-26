"""
rotas/relatorios.py — Blueprint dos relatórios anuais.

Exibe métricas anuais: faturamento mensal, canais, cidades,
formas de pagamento e ranking de equipe.
"""

from datetime import date

from flask import Blueprint, render_template, request

from helpers import fmt_brl
from servicos.relatorios import (
    get_anos_disponiveis, get_dados_anuais,
    get_todos_fotografos, get_todos_vendedores,
)

bp = Blueprint("relatorios", __name__)


@bp.route("/relatorios")
@bp.route("/relatorios/<int:ano>")
def pagina_relatorios(ano=None):
    """Exibe o painel de relatórios anuais."""
    today = date.today()
    if ano is None:
        ano = today.year

    # Anos disponíveis para o seletor
    anos_disponiveis = get_anos_disponiveis()
    if ano not in anos_disponiveis:
        anos_disponiveis.insert(0, ano)

    # Capturar os filtros dos parâmetros de URL
    filtro_fotografo = request.args.get("fotografo", "").strip()
    filtro_vendedor = request.args.get("vendedor", "").strip()

    todos_fotografos = get_todos_fotografos()
    todos_vendedores = get_todos_vendedores()

    dados = get_dados_anuais(
        ano,
        fotografo=filtro_fotografo if filtro_fotografo else None,
        vendedor=filtro_vendedor if filtro_vendedor else None,
    )

    return render_template(
        "relatorios.html",
        ano=ano,
        anos_disponiveis=anos_disponiveis,
        fmt_brl=fmt_brl,
        todos_fotografos=todos_fotografos,
        todos_vendedores=todos_vendedores,
        filtro_fotografo=filtro_fotografo,
        filtro_vendedor=filtro_vendedor,
        **dados,
    )
