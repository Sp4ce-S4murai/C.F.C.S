#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
#  C.F.C.S – Iniciador do Sistema (macOS)
# ──────────────────────────────────────────────────────────────

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"

echo ""
echo "  ============================================================"
echo "    C.F.C.S // CASH FLOW CONTROL SYSTEM"
echo "    BY OCTO"
echo "  ============================================================"
echo ""

# Create venv if it doesn't exist
if [ ! -d "$VENV" ]; then
  echo "  [-] Criando ambiente virtual Python..."
  python3 -m venv "$VENV"
fi

# Install/update dependencies
echo "  [-] Verificando dependencias..."
"$VENV/bin/pip" install -q -r "$DIR/requirements.txt"

echo "  [-] Iniciando servidor web..."
echo "  [-] O seu navegador sera aberto automaticamente em instantes."
echo ""
"$VENV/bin/python" "$DIR/app.py"
