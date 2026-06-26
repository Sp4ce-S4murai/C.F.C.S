"""
helpers.py — Funções utilitárias puras do C.F.C.S

Funções de formatação, parsing e validação que não dependem
de Flask nem do banco de dados. Podem ser importadas de qualquer lugar.
"""

import re
from datetime import datetime


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Formas de pagamento aceitas pelo sistema
FORMAS_VALIDAS = {"DIN", "CRE", "DEB", "PIX", "VCH"}

# Mapeamento sigla → nome legível para exibição
FORMA_NOME = {
    "DIN": "Dinheiro",
    "PIX": "PIX",
    "CRE": "Crédito",
    "DEB": "Débito",
    "VCH": "Voucher",
}

# Dias da semana em português
DIAS_SEMANA = [
    "Segunda-feira", "Terça-feira", "Quarta-feira",
    "Quinta-feira", "Sexta-feira", "Sábado", "Domingo",
]


# ---------------------------------------------------------------------------
# Parsing e formatação monetária
# ---------------------------------------------------------------------------

def parse_money(valor: str) -> float:
    """Converte string monetária mascarada (ex: 'R$ 1.234,56') para float.

    Retorna 0.0 se o valor for vazio ou inválido.
    """
    if not valor:
        return 0.0
    limpo = re.sub(r"[R$\s.]", "", valor).replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return 0.0


def fmt_brl(valor: float) -> str:
    """Formata float como moeda brasileira (R$ 1.234,56)."""
    s = f"{valor:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


# ---------------------------------------------------------------------------
# Validação de data
# ---------------------------------------------------------------------------

def validar_data(data_str: str) -> bool:
    """Retorna True se a string for uma data válida no formato YYYY-MM-DD."""
    try:
        datetime.strptime(data_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Mensagem WhatsApp
# ---------------------------------------------------------------------------

def build_whatsapp_message(data_str: str, caixa: dict,
                           vendas: list[dict], subtotais: dict) -> str:
    """Monta mensagem de relatório diário para WhatsApp.

    Texto puro formatado com negrito (*) do WhatsApp.
    """
    d = datetime.strptime(data_str, "%Y-%m-%d")
    dia_semana = DIAS_SEMANA[d.weekday()]
    data_fmt = d.strftime("%d/%m/%Y")

    total = sum(v["valor_venda"] for v in vendas)
    total_pessoas = sum(v["num_pessoas"] for v in vendas)
    num_vendas = len(vendas)
    ticket = total / num_vendas if num_vendas else 0.0

    # Formas de pagamento ativas (só exibe as que tiveram valor)
    formas_txt = ""
    for f in ["DIN", "PIX", "CRE", "DEB", "VCH"]:
        val = subtotais.get(f, 0.0)
        if val > 0:
            pct = int(val / total * 100) if total > 0 else 0
            formas_txt += f"  {FORMA_NOME[f]}: *{fmt_brl(val)}* ({pct}%)\n"

    msg = f"""*RELATÓRIO DIÁRIO*
*Estúdio Rua Coberta*

*{dia_semana}*, {data_fmt}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*CAIXA FÍSICO (DINHEIRO)*
  Abertura: *{fmt_brl(caixa['abertura_caixa'])}*
  Entradas DIN: *{fmt_brl(subtotais.get('DIN', 0.0))}*
  Fechamento: *{fmt_brl(caixa['fechamento_caixa'])}*

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*RESULTADO DO DIA*
  Faturamento Total: *{fmt_brl(total)}*
  Vendas realizadas: *{num_vendas}*
  Pessoas atendidas: *{total_pessoas}*
  Ticket médio: *{fmt_brl(ticket)}*

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*FORMAS DE PAGAMENTO*
{formas_txt}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_Relatório gerado automaticamente_
_C.F.C.S · by OCTO_"""

    return msg
