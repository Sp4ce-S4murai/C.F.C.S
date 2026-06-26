"""
rotas/calendario.py — Blueprint do calendário mensal.

Inclui: visualização mensal e exportação CSV.
"""

import calendar
from datetime import date

from flask import Blueprint, render_template, Response

from servicos.relatorios import get_dados_mensais, gerar_csv_mensal

bp = Blueprint("calendario", __name__)


# ---------------------------------------------------------------------------
# Calendário mensal
# ---------------------------------------------------------------------------

@bp.route("/mes", methods=["GET"])
@bp.route("/mes/<int:ano>/<int:mes>", methods=["GET"])
def pagina_mes(ano=None, mes=None):
    """Exibe o calendário mensal com resumo de vendas por dia."""
    today = date.today()
    if ano is None:
        ano = today.year
    if mes is None:
        mes = today.month

    mes = max(1, min(12, mes))
    dados = get_dados_mensais(ano, mes)

    # Navegação entre meses
    if mes == 1:
        prev_ano, prev_mes = ano - 1, 12
    else:
        prev_ano, prev_mes = ano, mes - 1

    if mes == 12:
        next_ano, next_mes = ano + 1, 1
    else:
        next_ano, next_mes = ano, mes + 1

    return render_template(
        "mes.html",
        cal=dados["cal"],
        ano=ano,
        mes=mes,
        month_name=dados["month_name"],
        dia_map=dados["dia_map"],
        today=today.isoformat(),
        prev_ano=prev_ano,
        prev_mes=prev_mes,
        next_ano=next_ano,
        next_mes=next_mes,
        weekdays=["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"],
    )


# ---------------------------------------------------------------------------
# Exportação CSV
# ---------------------------------------------------------------------------

@bp.route("/mes/<int:ano>/<int:mes>/csv")
def exportar_csv(ano, mes):
    """Exporta as vendas do mês como CSV (ponto-e-vírgula, UTF-8 BOM)."""
    conteudo, filename = gerar_csv_mensal(ano, mes)

    return Response(
        conteudo,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
