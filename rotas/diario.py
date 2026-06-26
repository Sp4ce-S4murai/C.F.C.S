"""
rotas/diario.py — Blueprint de rotas do controle diário.

Inclui: página principal, CRUD de vendas, retiradas de caixa,
abertura do caixa e envio de relatório via WhatsApp.
"""

from datetime import date, timedelta, datetime

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash

from helpers import parse_money, fmt_brl, validar_data, build_whatsapp_message
from servicos.caixa import (
    get_or_create_caixa, recalc_fechamento, set_abertura,
    get_retiradas_do_dia, criar_retirada, excluir_retirada,
)
from servicos.vendas import (
    get_vendas_do_dia, get_subtotais, parse_pagamentos_do_form,
    criar_venda, editar_venda, excluir_venda,
)
from servicos.config import get_config, autosave_config
from servicos.municipios import validar_cidade_input
from database import get_whatsapp_numero

bp = Blueprint("diario", __name__)


# ---------------------------------------------------------------------------
# Página principal — redireciona para o dia atual
# ---------------------------------------------------------------------------

@bp.route("/", methods=["GET"])
def index():
    """Redireciona para o diário do dia atual."""
    return redirect(url_for("diario.pagina_diario", data=date.today().isoformat()))


# ---------------------------------------------------------------------------
# Diário — visualização do dia
# ---------------------------------------------------------------------------

@bp.route("/dia/<data>", methods=["GET"])
def pagina_diario(data):
    """Exibe a página completa do diário para a data informada."""
    if not validar_data(data):
        return redirect(url_for("diario.index"))

    caixa = get_or_create_caixa(data)
    vendas = get_vendas_do_dia(data)
    retiradas = get_retiradas_do_dia(data)
    subtotais = get_subtotais(data)
    total_dia = sum(v["valor_venda"] for v in vendas)
    recalc_fechamento(data)
    caixa = get_or_create_caixa(data)  # Recarregar após recálculo

    canais = get_config("canal")
    cidades = get_config("cidade")
    equipe = get_config("equipe")
    whatsapp_numero = get_whatsapp_numero()

    d = datetime.strptime(data, "%Y-%m-%d").date()
    prev_day = (d - timedelta(days=1)).isoformat()
    next_day = (d + timedelta(days=1)).isoformat()
    today = date.today().isoformat()

    return render_template(
        "diario.html",
        data=data,
        data_fmt=d.strftime("%d/%m/%Y"),
        caixa=caixa,
        vendas=vendas,
        retiradas=retiradas,
        subtotais=subtotais,
        total_dia=total_dia,
        canais=canais,
        cidades=cidades,
        equipe=equipe,
        prev_day=prev_day,
        next_day=next_day,
        today=today,
        formas=["DIN", "CRE", "DEB", "PIX", "VCH"],
        whatsapp_numero=whatsapp_numero,
    )


# ---------------------------------------------------------------------------
# Vendas — CRUD
# ---------------------------------------------------------------------------

@bp.route("/dia/<data>/venda/nova", methods=["POST"])
def nova_venda(data):
    """Registra uma nova venda no dia."""
    if not validar_data(data):
        flash("Data inválida.", "error")
        return redirect(url_for("diario.index"))

    num_pessoas   = int(request.form.get("num_pessoas", 1) or 1)
    canal_venda   = request.form.get("canal_venda", "").strip()
    cidade_origem = request.form.get("cidade_origem", "").strip()
    fotografo     = request.form.get("fotografo", "").strip()
    vendedor      = request.form.get("vendedor", "").strip()

    pagamentos = parse_pagamentos_do_form()

    if not pagamentos:
        flash("Valor da venda deve ser maior que zero.", "error")
        return redirect(url_for("diario.pagina_diario", data=data))

    # Validar cidade contra base IBGE
    if cidade_origem:
        valido, resultado = validar_cidade_input(cidade_origem)
        if not valido:
            flash(resultado, "error")
            return redirect(url_for("diario.pagina_diario", data=data))
        cidade_origem = resultado  # Usar nome normalizado

    criar_venda(data, num_pessoas, canal_venda, cidade_origem,
                fotografo, vendedor, pagamentos)

    # Auto-salvar novos valores de configuração
    autosave_config("equipe", fotografo)
    autosave_config("equipe", vendedor)
    if cidade_origem:
        autosave_config("cidade", cidade_origem)

    flash("Venda registrada com sucesso!", "success")
    return redirect(url_for("diario.pagina_diario", data=data))


@bp.route("/dia/<data>/venda/<int:venda_id>/editar", methods=["POST"])
def rota_editar_venda(data, venda_id):
    """Atualiza uma venda existente."""
    if not validar_data(data):
        flash("Data inválida.", "error")
        return redirect(url_for("diario.index"))

    num_pessoas   = int(request.form.get("num_pessoas", 1) or 1)
    canal_venda   = request.form.get("canal_venda", "").strip()
    cidade_origem = request.form.get("cidade_origem", "").strip()
    fotografo     = request.form.get("fotografo", "").strip()
    vendedor      = request.form.get("vendedor", "").strip()

    pagamentos = parse_pagamentos_do_form()

    if not pagamentos:
        flash("Valor da venda deve ser maior que zero.", "error")
        return redirect(url_for("diario.pagina_diario", data=data))

    # Validar cidade contra base IBGE
    if cidade_origem:
        valido, resultado = validar_cidade_input(cidade_origem)
        if not valido:
            flash(resultado, "error")
            return redirect(url_for("diario.pagina_diario", data=data))
        cidade_origem = resultado

    encontrada = editar_venda(data, venda_id, num_pessoas, canal_venda,
                              cidade_origem, fotografo, vendedor, pagamentos)

    if not encontrada:
        flash("Venda não encontrada.", "error")
        return redirect(url_for("diario.pagina_diario", data=data))

    autosave_config("equipe", fotografo)
    autosave_config("equipe", vendedor)
    if cidade_origem:
        autosave_config("cidade", cidade_origem)

    flash("Venda atualizada com sucesso!", "success")
    return redirect(url_for("diario.pagina_diario", data=data))


@bp.route("/dia/<data>/venda/<int:venda_id>/excluir", methods=["POST"])
def rota_excluir_venda(data, venda_id):
    """Exclui uma venda e seus pagamentos."""
    excluir_venda(data, venda_id)
    flash("Venda excluída.", "success")
    return redirect(url_for("diario.pagina_diario", data=data))


# ---------------------------------------------------------------------------
# Abertura do caixa
# ---------------------------------------------------------------------------

@bp.route("/dia/<data>/abertura", methods=["POST"])
def rota_set_abertura(data):
    """Define manualmente a abertura do caixa do dia."""
    valor_raw = request.form.get("abertura_caixa", "0").strip()
    abertura = parse_money(valor_raw)

    set_abertura(data, abertura)
    recalc_fechamento(data)
    flash("Abertura de caixa atualizada.", "success")
    return redirect(url_for("diario.pagina_diario", data=data))


# ---------------------------------------------------------------------------
# Retiradas de caixa
# ---------------------------------------------------------------------------

@bp.route("/dia/<data>/retirada/nova", methods=["POST"])
def nova_retirada(data):
    """Registra uma nova retirada de caixa."""
    if not validar_data(data):
        flash("Data inválida.", "error")
        return redirect(url_for("diario.index"))

    motivo    = request.form.get("motivo", "").strip()
    valor_raw = request.form.get("valor", "0").strip()
    valor     = parse_money(valor_raw)

    if valor <= 0:
        flash("Valor da retirada deve ser maior que zero.", "error")
        return redirect(url_for("diario.pagina_diario", data=data))

    criar_retirada(data, valor, motivo)
    flash("Retirada registrada com sucesso!", "success")
    return redirect(url_for("diario.pagina_diario", data=data))


@bp.route("/dia/<data>/retirada/<int:retirada_id>/excluir", methods=["POST"])
def rota_excluir_retirada(data, retirada_id):
    """Exclui uma retirada de caixa."""
    excluir_retirada(data, retirada_id)
    flash("Retirada excluída.", "success")
    return redirect(url_for("diario.pagina_diario", data=data))


# ---------------------------------------------------------------------------
# WhatsApp — envio de relatório
# ---------------------------------------------------------------------------

@bp.route("/dia/<data>/whatsapp")
def whatsapp_enviar(data):
    """Retorna texto do relatório diário + número do WhatsApp como JSON."""
    if not validar_data(data):
        return jsonify({"error": "Data inválida."}), 400

    numero = get_whatsapp_numero()
    if not numero:
        return jsonify({"error": "Configure o número do WhatsApp no Admin."}), 400

    caixa     = get_or_create_caixa(data)
    vendas    = get_vendas_do_dia(data)
    subtotais = get_subtotais(data)

    msg = build_whatsapp_message(data, caixa, vendas, subtotais)
    numero_limpo = "".join(filter(str.isdigit, numero))

    return jsonify({"text": msg, "numero": numero_limpo})
