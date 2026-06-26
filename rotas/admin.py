"""
rotas/admin.py — Blueprint da área administrativa.

Gerencia configurações: canais de venda, cidades, equipe e WhatsApp.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash

from servicos.config import get_config, adicionar_config, remover_config
from database import get_whatsapp_numero, set_whatsapp_numero

bp = Blueprint("admin", __name__)


# ---------------------------------------------------------------------------
# Página principal do admin
# ---------------------------------------------------------------------------

@bp.route("/admin", methods=["GET"])
def pagina_admin():
    """Exibe a página de configurações administrativas."""
    canais = get_config("canal")
    cidades = get_config("cidade")
    equipe = get_config("equipe")
    whatsapp_numero = get_whatsapp_numero() or ""
    return render_template(
        "admin.html",
        canais=canais,
        cidades=cidades,
        equipe=equipe,
        whatsapp_numero=whatsapp_numero,
    )


# ---------------------------------------------------------------------------
# CRUD de configurações
# ---------------------------------------------------------------------------

@bp.route("/admin/add", methods=["POST"])
def admin_add():
    """Adiciona um novo valor de configuração."""
    tipo  = request.form.get("tipo", "").strip()
    valor = request.form.get("valor", "").strip()

    if tipo not in ("canal", "cidade", "equipe"):
        flash("Tipo inválido.", "error")
        return redirect(url_for("admin.pagina_admin"))

    if not valor:
        flash("O campo valor não pode ser vazio.", "error")
        return redirect(url_for("admin.pagina_admin"))

    sucesso, mensagem = adicionar_config(tipo, valor)
    flash(mensagem, "success" if sucesso else "error")
    return redirect(url_for("admin.pagina_admin"))


@bp.route("/admin/delete", methods=["POST"])
def admin_delete():
    """Remove um valor de configuração."""
    tipo  = request.form.get("tipo", "").strip()
    valor = request.form.get("valor", "").strip()

    remover_config(tipo, valor)
    flash(f'"{valor}" removido.', "success")
    return redirect(url_for("admin.pagina_admin"))


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------

@bp.route("/admin/whatsapp", methods=["POST"])
def admin_whatsapp():
    """Salva ou limpa o número do WhatsApp."""
    numero = request.form.get("whatsapp_numero", "").strip()
    set_whatsapp_numero(numero)
    if numero:
        flash(f"Número do WhatsApp salvo: {numero}", "success")
    else:
        flash("Número do WhatsApp removido.", "success")
    return redirect(url_for("admin.pagina_admin"))
