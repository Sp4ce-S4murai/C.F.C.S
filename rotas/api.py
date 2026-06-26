"""
rotas/api.py — Blueprint dos endpoints JSON (API interna).

Endpoints usados pelo frontend para autocomplete, edição modal
e validação de municípios.
"""

from flask import Blueprint, request, jsonify

from servicos.config import get_config, autosave_config
from servicos.municipios import (
    get_ufs, get_municipios_por_uf, validar_cidade_input,
)
from database import get_venda_by_id

bp = Blueprint("api", __name__)


# ---------------------------------------------------------------------------
# Configurações (autocomplete do frontend)
# ---------------------------------------------------------------------------

@bp.route("/api/config/<tipo>")
def api_config(tipo):
    """Retorna lista de valores de configuração como JSON."""
    permitidos = ("canal", "cidade", "equipe")
    if tipo not in permitidos:
        return jsonify([]), 400
    return jsonify(get_config(tipo))


@bp.route("/api/config/add", methods=["POST"])
def api_config_add():
    """Auto-salva um novo valor de configuração (chamado por eventos blur)."""
    data = request.get_json(silent=True) or {}
    tipo  = data.get("tipo", "").strip()
    valor = data.get("valor", "").strip()

    permitidos = ("canal", "cidade", "equipe")
    if tipo not in permitidos:
        return jsonify({"ok": False, "error": "Tipo inválido"}), 400
    if not valor:
        return jsonify({"ok": False, "error": "Valor vazio"}), 400

    # Validar cidade contra base IBGE
    if tipo == "cidade":
        valido, resultado = validar_cidade_input(valor)
        if not valido:
            return jsonify({"ok": False, "error": resultado}), 422

    autosave_config(tipo, valor)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Vendas (modal de edição)
# ---------------------------------------------------------------------------

@bp.route("/api/venda/<int:venda_id>")
def api_venda(venda_id):
    """Retorna dados de uma venda como JSON (usado pelo modal de edição)."""
    v = get_venda_by_id(venda_id)
    if not v:
        return jsonify({"error": "not found"}), 404
    return jsonify(v)


# ---------------------------------------------------------------------------
# Municípios (autocomplete e validação para futuro mapa de calor)
# ---------------------------------------------------------------------------

@bp.route("/api/municipios/ufs")
def api_ufs():
    """Retorna lista de todas as UFs do Brasil."""
    return jsonify(get_ufs())


@bp.route("/api/municipios/<uf>")
def api_municipios(uf):
    """Retorna lista de municípios de uma UF."""
    municipios = get_municipios_por_uf(uf.upper())
    if not municipios:
        return jsonify([]), 404
    return jsonify(municipios)


@bp.route("/api/municipios/validar", methods=["POST"])
def api_validar_municipio():
    """Valida uma string 'Cidade-UF' contra a base IBGE.

    Retorna JSON com 'valido' e 'normalizado' ou 'erro'.
    """
    data = request.get_json(silent=True) or {}
    valor = data.get("valor", "").strip()

    if not valor:
        return jsonify({"valido": True, "normalizado": ""})

    valido, resultado = validar_cidade_input(valor)
    if valido:
        return jsonify({"valido": True, "normalizado": resultado})
    else:
        return jsonify({"valido": False, "erro": resultado}), 422
