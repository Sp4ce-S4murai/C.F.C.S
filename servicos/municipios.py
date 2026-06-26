"""
servicos/municipios.py — Validação de municípios brasileiros (IBGE).

Carrega a lista oficial de municípios do Brasil a partir de um JSON
gerado com dados do IBGE. Usado para validar inputs de cidade/estado
e futuramente alimentar o mapa de calor por UF.
"""

import json
import os

# Caminho do JSON com municípios agrupados por UF
_DADOS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dados")
_JSON_PATH = os.path.join(_DADOS_DIR, "municipios_br.json")

# Cache em memória (carregado uma única vez)
_municipios_por_uf: dict[str, list[str]] | None = None


def _carregar():
    """Carrega o JSON de municípios em memória (lazy loading)."""
    global _municipios_por_uf
    if _municipios_por_uf is not None:
        return

    with open(_JSON_PATH, "r", encoding="utf-8") as f:
        _municipios_por_uf = json.load(f)


def get_ufs() -> list[str]:
    """Retorna lista de todas as siglas de UF disponíveis, ordenada."""
    _carregar()
    return sorted(_municipios_por_uf.keys())


def get_municipios_por_uf(uf: str) -> list[str]:
    """Retorna a lista de municípios de uma UF (já ordenada).

    Retorna lista vazia se a UF não existir.
    """
    _carregar()
    return _municipios_por_uf.get(uf.upper(), [])


def get_todos_municipios() -> dict[str, list[str]]:
    """Retorna o dicionário completo {UF: [municípios]}."""
    _carregar()
    return _municipios_por_uf


def validar_municipio(cidade: str, uf: str) -> bool:
    """Verifica se o município existe na UF informada.

    A comparação é case-insensitive para robustez.
    """
    _carregar()
    uf = uf.upper()
    if uf not in _municipios_por_uf:
        return False
    # Comparar sem case para tolerar variações de digitação
    nomes_lower = [m.lower() for m in _municipios_por_uf[uf]]
    return cidade.lower() in nomes_lower


def normalizar_nome_municipio(cidade: str, uf: str) -> str | None:
    """Retorna o nome oficial do município (com acentos corretos).

    Útil para padronizar o que o usuário digitou.
    Retorna None se não encontrar.
    """
    _carregar()
    uf = uf.upper()
    if uf not in _municipios_por_uf:
        return None
    for nome_oficial in _municipios_por_uf[uf]:
        if nome_oficial.lower() == cidade.lower():
            return nome_oficial
    return None


def parse_cidade_uf(valor: str) -> tuple[str, str] | None:
    """Extrai cidade e UF de uma string no formato 'Cidade-UF'.

    Retorna (cidade, uf) ou None se o formato for inválido.
    """
    if not valor or "-" not in valor:
        return None
    # Separar pelo último hífen (cidades podem ter hífen no nome)
    partes = valor.rsplit("-", 1)
    if len(partes) != 2:
        return None
    cidade = partes[0].strip()
    uf = partes[1].strip().upper()
    if len(uf) != 2 or not cidade:
        return None
    return cidade, uf


def validar_cidade_input(valor: str) -> tuple[bool, str]:
    """Valida e normaliza um input de cidade no formato 'Cidade-UF'.

    Retorna (valido, valor_normalizado_ou_mensagem_erro).
    Se válido, retorna o nome oficial: 'NomeOficial-UF'.
    Se inválido, retorna mensagem de erro.
    """
    if not valor:
        return True, ""  # Campo vazio é permitido (opcional)

    parsed = parse_cidade_uf(valor)
    if not parsed:
        return False, "Formato inválido. Use: Cidade-UF (ex: Gramado-RS)"

    cidade, uf = parsed

    # Verificar se a UF existe
    _carregar()
    if uf not in _municipios_por_uf:
        return False, f"Estado '{uf}' não encontrado. Use a sigla de 2 letras (ex: RS, SP, MG)."

    # Verificar se o município existe na UF
    nome_oficial = normalizar_nome_municipio(cidade, uf)
    if not nome_oficial:
        return False, f"Município '{cidade}' não encontrado em {uf}. Verifique a ortografia."

    return True, f"{nome_oficial}-{uf}"
