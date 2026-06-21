#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
#  C.F.C.S – Iniciador do Sistema (macOS)
#  Duplo clique neste arquivo para iniciar.
#  (Na primeira vez: clique direito → Abrir, para liberar o Gatekeeper)
# ──────────────────────────────────────────────────────────────

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"

# ── Criar venv se não existir ──────────────────────────────────
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi

# ── Instalar / atualizar dependências ─────────────────────────
"$VENV/bin/pip" install -q -r "$DIR/requirements.txt"

# ── Iniciar servidor (o próprio app.py abrirá o navegador) ────
"$VENV/bin/python" "$DIR/app.py"
