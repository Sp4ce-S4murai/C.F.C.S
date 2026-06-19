# C.F.C.S — Cash Flow Control Solution
**Um oferecimento OCTO**

Sistema de controle de fluxo de caixa para a equipe de vendas de estúdio fotográfico.

---

## Estrutura do Projeto

```
C.F.C.S/
├── app.py              # Servidor Flask — Rotas e regras de negócio
├── database.py         # Conexão SQLite e inicialização das tabelas
├── requirements.txt    # Dependências Python
├── iniciar.sh          # Script de início rápido (Linux/macOS)
├── database.db         # Gerado automaticamente na 1ª execução
└── templates/
    ├── base.html       # Layout base com navegação
    ├── diario.html     # Tela de Vendas do Dia
    ├── mes.html        # Calendário do Mês
    └── admin.html      # Painel Administrativo
```

---

## Como Executar (Execução Local)

### Opção 1 — Script automático (recomendado)

```bash
cd /home/recordarfotos/Documentos/Projetos/C.F.C.S
chmod +x iniciar.sh
./iniciar.sh
```

### Opção 2 — Manual

```bash
cd /home/recordarfotos/Documentos/Projetos/C.F.C.S

# 1. Criar ambiente virtual (apenas na primeira vez)
python3 -m venv .venv

# 2. Ativar o ambiente
source .venv/bin/activate

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Iniciar o servidor
python app.py
```

Depois abra o navegador em: **http://127.0.0.1:5000**

Para encerrar: `CTRL+C`

---

## Rotas da Aplicação

| Rota | Descrição |
|------|-----------|
| `/` | Redireciona para vendas do dia atual |
| `/dia/<YYYY-MM-DD>` | Vendas de uma data específica |
| `/mes` | Calendário do mês atual |
| `/mes/<ano>/<mes>` | Calendário de mês específico |
| `/admin` | Painel de gerenciamento de listas |

---

## Banco de Dados

O arquivo `database.db` é criado automaticamente na primeira execução no mesmo diretório do `app.py`.  
**Não requer instalação de servidor de banco de dados.**

### Tabelas

- `vendas` — Registros de vendas
- `caixa_diario` — Abertura e fechamento de caixa por data
- `configuracoes` — Listas de canais, cidades e equipe

---

## Regras de Negócio

- **Persistência de Caixa**: A `abertura_caixa` do dia D é automaticamente preenchida com o `fechamento_caixa` do dia D-1.
- **Fechamento Automático**: Recalculado a cada operação como `abertura + soma das vendas do dia`.
- **Lançamentos Retroativos**: Qualquer data pode ser editada via calendário ou link direto.
