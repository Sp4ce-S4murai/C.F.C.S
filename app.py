import os
import re
import csv
import io
import secrets
from datetime import date, timedelta, datetime
import calendar
from urllib.parse import quote
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, Response
from database import (
    get_connection, init_db, seed_defaults, backup_db,
    get_whatsapp_numero, set_whatsapp_numero,
    get_pagamentos_da_venda, get_venda_by_id,
)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Secret key — persistent & unique per installation, never hardcoded
# ---------------------------------------------------------------------------
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SECRET_FILE = os.path.join(_BASE_DIR, ".secret_key")
if not os.path.exists(_SECRET_FILE):
    with open(_SECRET_FILE, "w") as _f:
        _f.write(secrets.token_hex(32))
with open(_SECRET_FILE) as _f:
    app.secret_key = _f.read().strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_money(value: str) -> float:
    """Convert masked monetary string like 'R$ 1.234,56' to float."""
    if not value:
        return 0.0
    cleaned = re.sub(r"[R$\s.]", "", value).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def fmt_brl(value: float) -> str:
    """Format float as Brazilian currency string (R$ 1.234,56)."""
    s = f"{value:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def get_config(tipo: str) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT valor FROM configuracoes WHERE tipo = ? ORDER BY valor",
            (tipo,),
        ).fetchall()
    return [r["valor"] for r in rows]


def get_or_create_caixa(data_str: str) -> dict:
    """Return caixa_diario row for given date; auto-create if missing."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM caixa_diario WHERE data = ?", (data_str,)
        ).fetchone()
        if row:
            return dict(row)

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


def recalc_fechamento(data_str: str):
    """Recalculate fechamento = abertura + total vendas DIN (via venda_pagamentos) - retiradas."""
    with get_connection() as conn:
        caixa = conn.execute(
            "SELECT abertura_caixa FROM caixa_diario WHERE data = ?", (data_str,)
        ).fetchone()
        abertura = caixa["abertura_caixa"] if caixa else 0.0

        total_dinheiro = conn.execute(
            """SELECT COALESCE(SUM(vp.valor), 0) as total
               FROM venda_pagamentos vp
               JOIN vendas v ON v.id = vp.venda_id
               WHERE v.data_venda = ? AND vp.forma_pagamento = 'DIN'""",
            (data_str,),
        ).fetchone()["total"]

        total_retiradas = conn.execute(
            "SELECT COALESCE(SUM(valor),0) as total FROM retiradas_caixa WHERE data = ?",
            (data_str,),
        ).fetchone()["total"]

        fechamento = abertura + total_dinheiro - total_retiradas
        conn.execute(
            "UPDATE caixa_diario SET fechamento_caixa = ? WHERE data = ?",
            (fechamento, data_str),
        )


def get_retiradas_do_dia(data_str: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM retiradas_caixa WHERE data = ? ORDER BY id",
            (data_str,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_subtotais(data_str: str) -> dict:
    """Sum sales per payment form using venda_pagamentos for accuracy (handles MIX)."""
    formas = ["DIN", "CRE", "DEB", "PIX", "VCH"]
    result = {f: 0.0 for f in formas}
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
        if r["forma_pagamento"] in result:
            result[r["forma_pagamento"]] += r["subtotal"]
    return result


def get_vendas_do_dia(data_str: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM vendas WHERE data_venda = ? ORDER BY id",
            (data_str,),
        ).fetchall()
    vendas = [dict(r) for r in rows]
    for v in vendas:
        v["pagamentos"] = get_pagamentos_da_venda(v["id"])
    return vendas


def build_whatsapp_message(data_str: str, caixa: dict, vendas: list, subtotais: dict, retiradas: list) -> str:
    """Build a formatted WhatsApp message with the daily sales report."""
    d = datetime.strptime(data_str, "%Y-%m-%d")
    data_fmt = d.strftime("%d/%m/%Y")
    total = sum(v["valor_venda"] for v in vendas)

    forma_labels = {
        "DIN": "💵 Dinheiro",
        "PIX": "📱 PIX",
        "CRE": "💳 Crédito",
        "DEB": "🏧 Débito",
        "VCH": "🎫 Voucher",
    }

    lines = [
        "*╔══════════════════════════╗*",
        "*║   RELATÓRIO DE CAIXA    ║*",
        "*╚══════════════════════════╝*",
        "",
        f"📅 *DATA:* {data_fmt}",
        f"🏢 *Estudio Rua Coberta*",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "*💰 RESUMO DO CAIXA (FÍSICO)*",
        f"  • Abertura (DIN):    *{fmt_brl(caixa['abertura_caixa'])}*",
        f"  • Vendas (DIN):      *{fmt_brl(subtotais.get('DIN', 0.0))}*",
    ]

    if retiradas:
        total_retiradas = sum(r["valor"] for r in retiradas)
        lines.append(f"  • Retiradas:         *-{fmt_brl(total_retiradas)}*")

    lines.append(f"  • Saldo (Fechamento):*{fmt_brl(caixa['fechamento_caixa'])}*")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("*📊 RESULTADO TOTAL DO DIA*")
    lines.append(f"  • Faturamento Total: *{fmt_brl(total)}*")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("*💳 FORMAS DE PAGAMENTO*")

    for forma in ["DIN", "PIX", "CRE", "DEB", "VCH"]:
        val = subtotais.get(forma, 0.0)
        if val > 0:
            label = forma_labels.get(forma, forma)
            lines.append(f"  {label}: *{fmt_brl(val)}*")

    if not any(subtotais.get(f, 0) > 0 for f in subtotais):
        lines.append("  _Nenhum pagamento registrado_")

    if vendas:
        lines += [
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"*🛒 VENDAS — {len(vendas)} lançamento{'s' if len(vendas) != 1 else ''}*",
        ]
        for i, v in enumerate(vendas, 1):
            lines.append("")
            pagamentos = v.get("pagamentos", [])
            if len(pagamentos) > 1:
                pag_str = " + ".join(
                    f"{p['forma_pagamento']} {fmt_brl(p['valor'])}" for p in pagamentos
                )
            elif pagamentos:
                pag_str = f"{pagamentos[0]['forma_pagamento']}"
            else:
                pag_str = v['forma_pagamento']
            hora = v.get("hora_venda", "") or ""
            hora_str = f" · {hora}" if hora else ""
            lines.append(
                f"*#{i}* — {fmt_brl(v['valor_venda'])} | "
                f"{pag_str} | {v['num_pessoas']} pess.{hora_str}"
            )
            parts = []
            if v.get("cidade_origem"):
                parts.append(f"📍 {v['cidade_origem']}")
            if v.get("canal_venda"):
                parts.append(f"📢 {v['canal_venda']}")
            if v.get("fotografo"):
                parts.append(f"📷 {v['fotografo']}")
            if v.get("vendedor"):
                parts.append(f"🤝 {v['vendedor']}")
            if parts:
                lines.append("   " + " · ".join(parts))
    else:
        lines += [
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "_Nenhuma venda registrada neste dia._",
        ]

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "_C.F.C.S · by OCTO_",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Routes – Diário
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    today = date.today().isoformat()
    return redirect(url_for("diario", data=today))


@app.route("/dia/<data>", methods=["GET"])
def diario(data):
    try:
        datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        return redirect(url_for("index"))

    caixa = get_or_create_caixa(data)
    vendas = get_vendas_do_dia(data)
    retiradas = get_retiradas_do_dia(data)
    subtotais = get_subtotais(data)
    total_dia = sum(v["valor_venda"] for v in vendas)
    recalc_fechamento(data)
    caixa = get_or_create_caixa(data)

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


CIDADE_RE = re.compile(r'^[A-ZÀ-ÖØ-Ý][A-Za-zÀ-öØ-ÿ\s]+-[A-Z]{2}$')
FORMAS_VALIDAS = {"DIN", "CRE", "DEB", "PIX", "VCH"}


def _parse_pagamentos_from_form() -> list[dict]:
    """Parse payment slices from the submitted form. Returns list of {forma, valor} dicts."""
    pagamentos = []
    i = 1
    while True:
        forma_key = f"forma_pagamento_{i}"
        valor_key = f"valor_pagamento_{i}"
        if forma_key not in request.form:
            break
        forma = request.form.get(forma_key, "DIN").strip().upper()
        valor = parse_money(request.form.get(valor_key, "0").strip())
        if forma in FORMAS_VALIDAS and valor > 0:
            pagamentos.append({"forma": forma, "valor": valor})
        i += 1

    # Fallback: single legacy field (JS disabled)
    if not pagamentos:
        forma_pagamento = request.form.get("forma_pagamento", "DIN").strip().upper()
        valor_raw = request.form.get("valor_venda", "0").strip()
        valor_venda = parse_money(valor_raw)
        if valor_venda > 0:
            pagamentos.append({"forma": forma_pagamento, "valor": valor_venda})

    return pagamentos


@app.route("/dia/<data>/venda/nova", methods=["POST"])
def nova_venda(data):
    try:
        datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        flash("Data inválida.", "error")
        return redirect(url_for("diario", data=date.today().isoformat()))

    num_pessoas  = int(request.form.get("num_pessoas", 1) or 1)
    canal_venda  = request.form.get("canal_venda", "").strip()
    cidade_origem = request.form.get("cidade_origem", "").strip()
    fotografo    = request.form.get("fotografo", "").strip()
    vendedor     = request.form.get("vendedor", "").strip()
    hora_venda   = request.form.get("hora_venda", "").strip()

    pagamentos = _parse_pagamentos_from_form()

    if not pagamentos:
        flash("Valor da venda deve ser maior que zero.", "error")
        return redirect(url_for("diario", data=data))

    if cidade_origem and not CIDADE_RE.match(cidade_origem):
        flash("Cidade inválida. Use o formato: Municipio-ES (ex: Vitória-ES).", "error")
        return redirect(url_for("diario", data=data))

    valor_venda_total = sum(p["valor"] for p in pagamentos)
    forma_pagamento_principal = pagamentos[0]["forma"] if len(pagamentos) == 1 else "MIX"

    get_or_create_caixa(data)

    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO vendas
               (data_venda, hora_venda, num_pessoas, canal_venda, cidade_origem, fotografo, vendedor, valor_venda, forma_pagamento)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (data, hora_venda, num_pessoas, canal_venda, cidade_origem,
             fotografo, vendedor, valor_venda_total, forma_pagamento_principal),
        )
        venda_id = cursor.lastrowid
        conn.executemany(
            "INSERT INTO venda_pagamentos (venda_id, forma_pagamento, valor) VALUES (?, ?, ?)",
            [(venda_id, p["forma"], p["valor"]) for p in pagamentos],
        )

    _autosave_config("equipe", fotografo)
    _autosave_config("equipe", vendedor)
    if cidade_origem:
        _autosave_config("cidade", cidade_origem)

    recalc_fechamento(data)
    flash("Venda registrada com sucesso!", "success")
    return redirect(url_for("diario", data=data))


def _autosave_config(tipo: str, valor: str):
    """Silently save a new config value if it doesn't already exist."""
    if not valor:
        return
    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO configuracoes (tipo, valor) VALUES (?, ?)",
                (tipo, valor),
            )
        except Exception:
            pass


@app.route("/dia/<data>/venda/<int:venda_id>/editar", methods=["POST"])
def editar_venda(data, venda_id):
    """Update an existing sale in-place."""
    try:
        datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        flash("Data inválida.", "error")
        return redirect(url_for("index"))

    num_pessoas   = int(request.form.get("num_pessoas", 1) or 1)
    canal_venda   = request.form.get("canal_venda", "").strip()
    cidade_origem = request.form.get("cidade_origem", "").strip()
    fotografo     = request.form.get("fotografo", "").strip()
    vendedor      = request.form.get("vendedor", "").strip()
    hora_venda    = request.form.get("hora_venda", "").strip()

    pagamentos = _parse_pagamentos_from_form()

    if not pagamentos:
        flash("Valor da venda deve ser maior que zero.", "error")
        return redirect(url_for("diario", data=data))

    if cidade_origem and not CIDADE_RE.match(cidade_origem):
        flash("Cidade inválida. Use o formato: Municipio-ES (ex: Vitória-ES).", "error")
        return redirect(url_for("diario", data=data))

    valor_venda_total = sum(p["valor"] for p in pagamentos)
    forma_pagamento_principal = pagamentos[0]["forma"] if len(pagamentos) == 1 else "MIX"

    with get_connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM vendas WHERE id = ? AND data_venda = ?", (venda_id, data)
        ).fetchone()
        if not exists:
            flash("Venda não encontrada.", "error")
            return redirect(url_for("diario", data=data))

        conn.execute(
            """UPDATE vendas SET
               hora_venda=?, num_pessoas=?, canal_venda=?, cidade_origem=?,
               fotografo=?, vendedor=?, valor_venda=?, forma_pagamento=?
               WHERE id=?""",
            (hora_venda, num_pessoas, canal_venda, cidade_origem,
             fotografo, vendedor, valor_venda_total, forma_pagamento_principal, venda_id),
        )
        conn.execute("DELETE FROM venda_pagamentos WHERE venda_id = ?", (venda_id,))
        conn.executemany(
            "INSERT INTO venda_pagamentos (venda_id, forma_pagamento, valor) VALUES (?, ?, ?)",
            [(venda_id, p["forma"], p["valor"]) for p in pagamentos],
        )

    _autosave_config("equipe", fotografo)
    _autosave_config("equipe", vendedor)
    if cidade_origem:
        _autosave_config("cidade", cidade_origem)

    recalc_fechamento(data)
    flash("Venda atualizada com sucesso!", "success")
    return redirect(url_for("diario", data=data))


@app.route("/dia/<data>/venda/<int:venda_id>/excluir", methods=["POST"])
def excluir_venda(data, venda_id):
    with get_connection() as conn:
        # venda_pagamentos will cascade-delete via FK
        conn.execute("DELETE FROM vendas WHERE id = ? AND data_venda = ?", (venda_id, data))
    recalc_fechamento(data)
    flash("Venda excluída.", "success")
    return redirect(url_for("diario", data=data))


@app.route("/dia/<data>/abertura", methods=["POST"])
def set_abertura(data):
    """Manually set abertura_caixa for a given day."""
    valor_raw = request.form.get("abertura_caixa", "0").strip()
    abertura = parse_money(valor_raw)

    with get_connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM caixa_diario WHERE data = ?", (data,)
        ).fetchone()
        if exists:
            conn.execute(
                "UPDATE caixa_diario SET abertura_caixa = ? WHERE data = ?",
                (abertura, data),
            )
        else:
            conn.execute(
                "INSERT INTO caixa_diario (data, abertura_caixa, fechamento_caixa) VALUES (?, ?, ?)",
                (data, abertura, abertura),
            )

    recalc_fechamento(data)
    flash("Abertura de caixa atualizada.", "success")
    return redirect(url_for("diario", data=data))


@app.route("/dia/<data>/retirada/nova", methods=["POST"])
def nova_retirada(data):
    try:
        datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        flash("Data inválida.", "error")
        return redirect(url_for("diario", data=date.today().isoformat()))

    motivo    = request.form.get("motivo", "").strip()
    valor_raw = request.form.get("valor", "0").strip()
    valor     = parse_money(valor_raw)

    if valor <= 0:
        flash("Valor da retirada deve ser maior que zero.", "error")
        return redirect(url_for("diario", data=data))

    get_or_create_caixa(data)

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO retiradas_caixa (data, valor, motivo) VALUES (?, ?, ?)",
            (data, valor, motivo),
        )

    recalc_fechamento(data)
    flash("Retirada registrada com sucesso!", "success")
    return redirect(url_for("diario", data=data))


@app.route("/dia/<data>/retirada/<int:retirada_id>/excluir", methods=["POST"])
def excluir_retirada(data, retirada_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM retiradas_caixa WHERE id = ? AND data = ?", (retirada_id, data))
    recalc_fechamento(data)
    flash("Retirada excluída.", "success")
    return redirect(url_for("diario", data=data))


@app.route("/dia/<data>/whatsapp")
def whatsapp_enviar(data):
    """Generate WhatsApp message with daily report and redirect to wa.me."""
    try:
        datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        flash("Data inválida.", "error")
        return redirect(url_for("index"))

    numero = get_whatsapp_numero()
    if not numero:
        flash("Configure o número do WhatsApp no Painel Administrativo → aba SISTEMA.", "error")
        return redirect(url_for("diario", data=data))

    caixa     = get_or_create_caixa(data)
    vendas    = get_vendas_do_dia(data)
    retiradas = get_retiradas_do_dia(data)
    subtotais = get_subtotais(data)

    message = build_whatsapp_message(data, caixa, vendas, subtotais, retiradas)
    encoded = quote(message)
    numero_clean = "".join(filter(str.isdigit, numero))
    wa_url = f"https://wa.me/{numero_clean}?text={encoded}"

    return redirect(wa_url)


# ---------------------------------------------------------------------------
# Routes – Calendário Mensal
# ---------------------------------------------------------------------------

@app.route("/mes", methods=["GET"])
@app.route("/mes/<int:ano>/<int:mes>", methods=["GET"])
def mes(ano=None, mes=None):
    today = date.today()
    if ano is None:
        ano = today.year
    if mes is None:
        mes = today.month

    mes = max(1, min(12, mes))

    cal = calendar.monthcalendar(ano, mes)
    month_name = calendar.month_name[mes]

    first_day = date(ano, mes, 1).isoformat()
    last_day  = date(ano, mes, calendar.monthrange(ano, mes)[1]).isoformat()

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
            (first_day, last_day),
        ).fetchall()

    dia_map = {r["data"]: dict(r) for r in rows}

    with get_connection() as conn:
        vrows = conn.execute(
            """SELECT data_venda as data, COALESCE(SUM(valor_venda),0) as total_vendas, COUNT(*) as num_vendas
               FROM vendas WHERE data_venda >= ? AND data_venda <= ?
               GROUP BY data_venda""",
            (first_day, last_day),
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
        cal=cal,
        ano=ano,
        mes=mes,
        month_name=month_name,
        dia_map=dia_map,
        today=today.isoformat(),
        prev_ano=prev_ano,
        prev_mes=prev_mes,
        next_ano=next_ano,
        next_mes=next_mes,
        weekdays=["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"],
    )


@app.route("/mes/<int:ano>/<int:mes>/csv")
def exportar_csv(ano, mes):
    """Export monthly sales as a semicolon-delimited CSV (UTF-8 BOM, Excel-ready)."""
    mes = max(1, min(12, mes))
    first_day = date(ano, mes, 1).isoformat()
    last_day  = date(ano, mes, calendar.monthrange(ano, mes)[1]).isoformat()

    with get_connection() as conn:
        rows = conn.execute(
            """SELECT v.data_venda, v.hora_venda, v.num_pessoas, v.canal_venda,
                      v.cidade_origem, v.fotografo, v.vendedor,
                      v.valor_venda, v.forma_pagamento
               FROM vendas v
               WHERE v.data_venda >= ? AND v.data_venda <= ?
               ORDER BY v.data_venda, v.id""",
            (first_day, last_day),
        ).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Data", "Hora", "Pessoas", "Canal", "Cidade", "Fotógrafo", "Vendedor", "Valor (R$)", "Pagamento"])
    for r in rows:
        writer.writerow([
            r["data_venda"],
            r["hora_venda"] or "",
            r["num_pessoas"],
            r["canal_venda"],
            r["cidade_origem"],
            r["fotografo"],
            r["vendedor"],
            f"{r['valor_venda']:.2f}".replace(".", ","),
            r["forma_pagamento"],
        ])

    month_abbr = calendar.month_abbr[mes].upper()
    filename   = f"CFCS_{ano}_{mes:02d}_{month_abbr}.csv"

    return Response(
        "\ufeff" + buf.getvalue(),   # UTF-8 BOM for Excel compatibility
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Routes – Relatórios Anuais
# ---------------------------------------------------------------------------

@app.route("/relatorios")
@app.route("/relatorios/<int:ano>")
def relatorios(ano=None):
    today = date.today()
    if ano is None:
        ano = today.year

    # Years that have data
    with get_connection() as conn:
        yr = conn.execute(
            "SELECT DISTINCT strftime('%Y', data_venda) as a FROM vendas WHERE a IS NOT NULL ORDER BY a DESC"
        ).fetchall()
    anos_disponiveis = [int(r["a"]) for r in yr if r["a"]]
    if ano not in anos_disponiveis:
        anos_disponiveis.insert(0, ano)

    ano_str = str(ano)

    # Monthly totals
    with get_connection() as conn:
        monthly_rows = conn.execute(
            """SELECT CAST(strftime('%m', data_venda) AS INTEGER) as mes,
                      COALESCE(SUM(valor_venda), 0) as total,
                      COUNT(*) as num_vendas
               FROM vendas
               WHERE strftime('%Y', data_venda) = ?
               GROUP BY mes ORDER BY mes""",
            (ano_str,),
        ).fetchall()

    monthly_map  = {r["mes"]: dict(r) for r in monthly_rows}
    monthly_data = []
    for m in range(1, 13):
        info = monthly_map.get(m, {"total": 0.0, "num_vendas": 0})
        monthly_data.append({
            "mes":       m,
            "nome":      calendar.month_abbr[m].upper(),
            "total":     float(info["total"]),
            "num_vendas": int(info["num_vendas"]),
        })

    total_ano        = sum(m["total"] for m in monthly_data)
    total_vendas_ano = sum(m["num_vendas"] for m in monthly_data)
    ticket_medio     = total_ano / total_vendas_ano if total_vendas_ano else 0.0
    melhor_mes       = max(monthly_data, key=lambda x: x["total"]) if any(m["total"] for m in monthly_data) else None

    # Canal breakdown
    with get_connection() as conn:
        canais_rows = conn.execute(
            """SELECT canal_venda, COUNT(*) as num, COALESCE(SUM(valor_venda), 0) as total
               FROM vendas
               WHERE strftime('%Y', data_venda) = ? AND canal_venda != ''
               GROUP BY canal_venda ORDER BY total DESC LIMIT 10""",
            (ano_str,),
        ).fetchall()
    canais_data = [dict(r) for r in canais_rows]

    # City top 10
    with get_connection() as conn:
        cidades_rows = conn.execute(
            """SELECT cidade_origem, COUNT(*) as num, COALESCE(SUM(valor_venda), 0) as total
               FROM vendas
               WHERE strftime('%Y', data_venda) = ? AND cidade_origem != ''
               GROUP BY cidade_origem ORDER BY total DESC LIMIT 10""",
            (ano_str,),
        ).fetchall()
    cidades_data = [dict(r) for r in cidades_rows]

    # Payment form breakdown
    with get_connection() as conn:
        formas_rows = conn.execute(
            """SELECT vp.forma_pagamento, COALESCE(SUM(vp.valor), 0) as total
               FROM venda_pagamentos vp
               JOIN vendas v ON v.id = vp.venda_id
               WHERE strftime('%Y', v.data_venda) = ?
               GROUP BY vp.forma_pagamento ORDER BY total DESC""",
            (ano_str,),
        ).fetchall()
    formas_data = [dict(r) for r in formas_rows]

    # Equipe (fotografo) breakdown
    with get_connection() as conn:
        equipe_rows = conn.execute(
            """SELECT fotografo, COUNT(*) as num, COALESCE(SUM(valor_venda), 0) as total
               FROM vendas
               WHERE strftime('%Y', data_venda) = ? AND fotografo != ''
               GROUP BY fotografo ORDER BY total DESC LIMIT 10""",
            (ano_str,),
        ).fetchall()
    equipe_data = [dict(r) for r in equipe_rows]

    return render_template(
        "relatorios.html",
        ano=ano,
        anos_disponiveis=anos_disponiveis,
        monthly_data=monthly_data,
        total_ano=total_ano,
        total_vendas_ano=total_vendas_ano,
        ticket_medio=ticket_medio,
        melhor_mes=melhor_mes,
        canais_data=canais_data,
        cidades_data=cidades_data,
        formas_data=formas_data,
        equipe_data=equipe_data,
        fmt_brl=fmt_brl,
    )


# ---------------------------------------------------------------------------
# Routes – Admin
# ---------------------------------------------------------------------------

@app.route("/admin", methods=["GET"])
def admin():
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


@app.route("/admin/add", methods=["POST"])
def admin_add():
    tipo  = request.form.get("tipo", "").strip()
    valor = request.form.get("valor", "").strip()

    if tipo not in ("canal", "cidade", "equipe"):
        flash("Tipo inválido.", "error")
        return redirect(url_for("admin"))

    if not valor:
        flash("O campo valor não pode ser vazio.", "error")
        return redirect(url_for("admin"))

    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO configuracoes (tipo, valor) VALUES (?, ?)", (tipo, valor)
            )
            flash(f'"{valor}" adicionado com sucesso.', "success")
        except Exception:
            flash(f'"{valor}" já existe nesta lista.', "error")

    return redirect(url_for("admin"))


@app.route("/admin/delete", methods=["POST"])
def admin_delete():
    tipo  = request.form.get("tipo", "").strip()
    valor = request.form.get("valor", "").strip()

    with get_connection() as conn:
        conn.execute(
            "DELETE FROM configuracoes WHERE tipo = ? AND valor = ?", (tipo, valor)
        )

    flash(f'"{valor}" removido.', "success")
    return redirect(url_for("admin"))


@app.route("/admin/whatsapp", methods=["POST"])
def admin_whatsapp():
    """Save or clear the WhatsApp phone number."""
    numero = request.form.get("whatsapp_numero", "").strip()
    set_whatsapp_numero(numero)
    if numero:
        flash(f"Número do WhatsApp salvo: {numero}", "success")
    else:
        flash("Número do WhatsApp removido.", "success")
    return redirect(url_for("admin"))


# ---------------------------------------------------------------------------
# API – autocomplete JSON endpoints
# ---------------------------------------------------------------------------

@app.route("/api/config/<tipo>")
def api_config(tipo):
    allowed = ("canal", "cidade", "equipe")
    if tipo not in allowed:
        return jsonify([]), 400
    return jsonify(get_config(tipo))


@app.route("/api/config/add", methods=["POST"])
def api_config_add():
    """Auto-save a new config value from the frontend (blur events)."""
    data = request.get_json(silent=True) or {}
    tipo  = data.get("tipo", "").strip()
    valor = data.get("valor", "").strip()

    allowed = ("canal", "cidade", "equipe")
    if tipo not in allowed:
        return jsonify({"ok": False, "error": "Tipo inválido"}), 400
    if not valor:
        return jsonify({"ok": False, "error": "Valor vazio"}), 400

    if tipo == "cidade" and not CIDADE_RE.match(valor):
        return jsonify({
            "ok": False,
            "error": "Formato inválido. Use: Municipio-ES (ex: Vitória-ES)"
        }), 422

    _autosave_config(tipo, valor)
    return jsonify({"ok": True})


@app.route("/api/venda/<int:venda_id>")
def api_venda(venda_id):
    """Return a venda as JSON — used by the edit modal."""
    v = get_venda_by_id(venda_id)
    if not v:
        return jsonify({"error": "not found"}), 404
    return jsonify(v)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    seed_defaults()
    bk = backup_db()

    print("\n" + "=" * 60)
    print("  C.F.C.S  //  CASH FLOW CONTROL SYSTEM")
    print("  BY OCTO")
    print("=" * 60)
    if bk:
        print(f"  BACKUP   >>  backups/{os.path.basename(bk)}")
    print("  SYSTEM ONLINE  >>  http://127.0.0.1:5000")
    print("  CTRL+C TO TERMINATE")
    print("=" * 60 + "\n")

    import threading
    import webbrowser
    import time

    def open_browser():
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:5000")

    threading.Thread(target=open_browser, daemon=True).start()

    app.run(debug=False, host="127.0.0.1", port=5000)
