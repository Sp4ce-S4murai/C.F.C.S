#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
#  C.F.C.S – Cash Flow Control Solution | Iniciador
#  Um oferecimento OCTO
# ──────────────────────────────────────────────────────────────

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   C.F.C.S – Cash Flow Control Solution  ║"
echo "  ║          Um oferecimento OCTO            ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# Create venv if it doesn't exist
if [ ! -d "$VENV" ]; then
  echo "  → Criando ambiente virtual Python..."
  python3 -m venv "$VENV"
fi

# Install/update dependencies
echo "  → Verificando dependências..."
"$VENV/bin/pip" install -q -r "$DIR/requirements.txt"

echo "  → Iniciando servidor na porta 5000..."
echo "  → Acesse: http://127.0.0.1:5000"
echo ""
"$VENV/bin/python" "$DIR/app.py"
