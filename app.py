import re
from datetime import date, timedelta, datetime
import calendar
from urllib.parse import quote
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from database import get_connection, init_db, seed_defaults, get_whatsapp_numero, set_whatsapp_numero

app = Flask(__name__)
app.secret_key = "cfcs-octo-secret-2024"


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
    """Recalculate fechamento = abertura + total vendas (DIN) - retiradas and persist."""
    with get_connection() as conn:
        caixa = conn.execute(
            "SELECT abertura_caixa FROM caixa_diario WHERE data = ?", (data_str,)
        ).fetchone()
        abertura = caixa["abertura_caixa"] if caixa else 0.0

        total_dinheiro = conn.execute(
            "SELECT COALESCE(SUM(valor_venda),0) as total FROM vendas WHERE data_venda = ? AND forma_pagamento = 'DIN'",
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
    formas = ["DIN", "CRE", "DEB", "PIX", "VCH"]
    result = {f: 0.0 for f in formas}
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT forma_pagamento, COALESCE(SUM(valor_venda),0) as subtotal
               FROM vendas WHERE data_venda = ? GROUP BY forma_pagamento""",
            (data_str,),
        ).fetchall()
    for r in rows:
        if r["forma_pagamento"] in result:
            result[r["forma_pagamento"]] = r["subtotal"]
    return result


def get_vendas_do_dia(data_str: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM vendas WHERE data_venda = ? ORDER BY id",
            (data_str,),
        ).fetchall()
    return [dict(r) for r in rows]


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
            lines.append(
                f"*#{i}* — {fmt_brl(v['valor_venda'])} | "
                f"{v['forma_pagamento']} | {v['num_pessoas']} pess."
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


@app.route("/dia/<data>/venda/nova", methods=["POST"])
def nova_venda(data):
    try:
        datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        flash("Data inválida.", "error")
        return redirect(url_for("diario", data=date.today().isoformat()))

    num_pessoas = int(request.form.get("num_pessoas", 1) or 1)
    canal_venda = request.form.get("canal_venda", "").strip()
    cidade_origem = request.form.get("cidade_origem", "").strip()
    fotografo = request.form.get("fotografo", "").strip()
    vendedor = request.form.get("vendedor", "").strip()
    valor_raw = request.form.get("valor_venda", "0").strip()
    valor_venda = parse_money(valor_raw)
    forma_pagamento = request.form.get("forma_pagamento", "DIN").strip()

    if valor_venda <= 0:
        flash("Valor da venda deve ser maior que zero.", "error")
        return redirect(url_for("diario", data=data))

    get_or_create_caixa(data)

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO vendas
               (data_venda, num_pessoas, canal_venda, cidade_origem, fotografo, vendedor, valor_venda, forma_pagamento)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (data, num_pessoas, canal_venda, cidade_origem, fotografo, vendedor, valor_venda, forma_pagamento),
        )

    recalc_fechamento(data)
    flash("Venda registrada com sucesso!", "success")
    return redirect(url_for("diario", data=data))


@app.route("/dia/<data>/venda/<int:venda_id>/excluir", methods=["POST"])
def excluir_venda(data, venda_id):
    with get_connection() as conn:
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

    motivo = request.form.get("motivo", "").strip()
    valor_raw = request.form.get("valor", "0").strip()
    valor = parse_money(valor_raw)

    if valor <= 0:
        flash("Valor da retirada deve ser maior que zero.", "error")
        return redirect(url_for("diario", data=data))

    get_or_create_caixa(data)

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO retiradas_caixa (data, valor, motivo) VALUES (?, ?, ?)""",
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

    caixa = get_or_create_caixa(data)
    vendas = get_vendas_do_dia(data)
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
    last_day = date(ano, mes, calendar.monthrange(ano, mes)[1]).isoformat()

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
    tipo = request.form.get("tipo", "").strip()
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
    tipo = request.form.get("tipo", "").strip()
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    seed_defaults()
    print("\n" + "=" * 60)
    print("  C.F.C.S  //  CASH FLOW CONTROL SYSTEM")
    print("  BY OCTO")
    print("=" * 60)
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
