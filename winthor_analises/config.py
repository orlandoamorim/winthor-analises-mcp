"""Leitura e validação do config.toml.

Os nomes de tabelas e colunas vêm da configuração porque o esquema real
ainda não foi conferido. Tudo é validado aqui para que só identificadores e
expressões simples cheguem ao SQL.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONFIG_EXEMPLO = RAIZ / "config.exemplo.toml"

_IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,127}$")
# Expressões de coluna: identificadores, números, espaço, operadores e parênteses.
_EXPR = re.compile(r"^[A-Za-z0-9_$#.,()*+\-/ ]*$")
# Filtros: o mesmo, mais comparações e literais entre aspas simples.
_FILTRO = re.compile(r"^[A-Za-z0-9_$#.,()*+\-/ =<>!'%]*$")

# Colunas obrigatórias de cada tabela; as demais são opcionais ("" = não existe).
OBRIGATORIAS: dict[str, tuple[str, ...]] = {
    "produtos": ("tabela", "codigo", "descricao", "fornecedor"),
    "fornecedores": ("tabela", "codigo", "nome"),
    "vendas": ("tabela", "data", "produto", "quantidade", "valor"),
    "compras": ("tabela", "data", "produto", "quantidade", "valor"),
    "faturamento": ("tabela", "data", "valor"),
    "estoque": ("tabela", "produto", "quantidade"),
    "movimentos_avaria": ("tabela", "data", "produto", "quantidade", "filtro_entrada", "filtro_retorno"),
    "verbas": ("tabela", "numero", "fornecedor", "valor"),
    "movimentos_verba": ("tabela", "numero_verba", "valor"),
}
OPCIONAIS: dict[str, tuple[str, ...]] = {
    "vendas": ("fornecedor", "filial", "filtro"),
    "compras": ("fornecedor", "filial", "filtro"),
    "faturamento": ("filial", "filtro"),
    "estoque": ("filial", "filtro", "avaria", "custo"),
    "movimentos_avaria": ("filial",),
    "verbas": ("data", "vencimento", "forma", "origem", "descricao", "filtro"),
    "movimentos_verba": ("natureza", "credito", "rotina", "data", "filtro"),
}
# Campos que aceitam expressão em vez de só nome de coluna.
CAMPOS_EXPRESSAO = {"quantidade", "valor"}
# Campos que são um valor literal (ex.: o código que marca crédito), não coluna.
CAMPOS_LITERAL = {"credito"}


class ErroConfiguracao(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    modo: str = "exemplo"
    filial: str = ""
    fuso: str = "America/Sao_Paulo"
    hora_inicio_comercial: int = 7
    hora_fim_comercial: int = 18
    dias_max_horario_comercial: int = 400
    limite_linhas: int = 200
    esquema: str = ""
    timeout_segundos: int = 120
    exigir_usuario_somente_leitura: bool = True
    banco: str = "replica"
    horario_vale_na_replica: bool = True
    tabelas: dict[str, dict[str, str]] = field(default_factory=dict)
    formas_verba: dict[str, str] = field(default_factory=dict)
    origem: str = ""

    def tabela(self, nome: str) -> str:
        """Nome qualificado da tabela (com esquema, se houver)."""
        t = self.tabelas[nome]["tabela"]
        return f"{self.esquema}.{t}" if self.esquema else t

    def col(self, tabela: str, campo: str) -> str:
        return self.tabelas[tabela].get(campo, "")


def _validar_campo(tabela: str, campo: str, valor: str) -> None:
    if not isinstance(valor, str):
        raise ErroConfiguracao(f"[tabelas.{tabela}] {campo} deve ser texto")
    if valor == "":
        return
    if campo in CAMPOS_LITERAL:
        ok = re.fullmatch(r"[A-Za-z0-9]{1,10}", valor)
    elif campo.startswith("filtro"):
        ok = _FILTRO.match(valor) and valor.count("'") % 2 == 0 and "--" not in valor
    elif campo in CAMPOS_EXPRESSAO:
        ok = _EXPR.match(valor) and "--" not in valor
    else:
        ok = _IDENT.match(valor)
    if not ok:
        raise ErroConfiguracao(f"[tabelas.{tabela}] {campo} = {valor!r} não é permitido")


def _banco(valor: str) -> str:
    if valor not in ("replica", "producao"):
        raise ErroConfiguracao("oracle.banco deve ser 'replica' ou 'producao'")
    return valor


def carregar_env(arquivo: str | os.PathLike = ".env") -> None:
    """Lê um .env simples (CHAVE=valor) sem sobrescrever o que já está definido.

    Mesmo formato do winthor-mcp da VanguardIA, para dar para usar o mesmo arquivo.
    """
    for caminho in (Path(arquivo), RAIZ / ".env"):
        if not caminho.is_file():
            continue
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                chave, valor = linha.split("=", 1)
                os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))
        return


def carregar(caminho: str | os.PathLike | None = None) -> Config:
    """Carrega a configuração.

    Ordem: argumento, variável WINTHOR_MCP_CONFIG, ./config.toml, config.toml
    na raiz do projeto e, por último, config.exemplo.toml.
    """
    candidatos = [caminho, os.environ.get("WINTHOR_MCP_CONFIG"), "config.toml",
                  RAIZ / "config.toml", CONFIG_EXEMPLO]
    arquivo = next(Path(c) for c in candidatos if c and Path(c).is_file())
    with open(arquivo, "rb") as f:
        dados = tomllib.load(f)

    geral = dados.get("geral", {})
    oracle = dados.get("oracle", {})
    tabelas = dados.get("tabelas", {})

    modo = os.environ.get("WINTHOR_MCP_MODO", geral.get("modo", "exemplo"))
    if modo not in ("exemplo", "oracle"):
        raise ErroConfiguracao("geral.modo deve ser 'exemplo' ou 'oracle'")

    esquema = os.environ.get("WINTHOR_DB_SCHEMA") or oracle.get("esquema", "")
    if esquema and not _IDENT.match(esquema):
        raise ErroConfiguracao(f"oracle.esquema = {esquema!r} não é permitido")

    filial = str(geral.get("filial", ""))
    if filial and not re.fullmatch(r"[A-Za-z0-9]{1,10}", filial):
        raise ErroConfiguracao("geral.filial deve ser um código simples")

    limpas: dict[str, dict[str, str]] = {}
    for nome, obrig in OBRIGATORIAS.items():
        t = tabelas.get(nome)
        if t is None:
            raise ErroConfiguracao(f"faltou a seção [tabelas.{nome}]")
        for campo in obrig:
            if not t.get(campo):
                raise ErroConfiguracao(f"[tabelas.{nome}] precisa de '{campo}'")
        permitidos = set(obrig) | set(OPCIONAIS.get(nome, ()))
        desconhecidos = set(t) - permitidos
        if desconhecidos:
            raise ErroConfiguracao(f"[tabelas.{nome}] campos desconhecidos: {sorted(desconhecidos)}")
        for campo, valor in t.items():
            _validar_campo(nome, campo, valor)
        limpas[nome] = {c: t.get(c, "") for c in permitidos}

    return Config(
        modo=modo,
        filial=filial,
        fuso=geral.get("fuso", "America/Sao_Paulo"),
        hora_inicio_comercial=int(geral.get("hora_inicio_comercial", 7)),
        hora_fim_comercial=int(geral.get("hora_fim_comercial", 18)),
        dias_max_horario_comercial=int(geral.get("dias_max_horario_comercial", 400)),
        limite_linhas=int(geral.get("limite_linhas", 200)),
        esquema=esquema,
        timeout_segundos=int(oracle.get("timeout_segundos", 120)),
        exigir_usuario_somente_leitura=bool(oracle.get("exigir_usuario_somente_leitura", True)),
        banco=_banco(oracle.get("banco", "replica")),
        horario_vale_na_replica=bool(oracle.get("horario_vale_na_replica", True)),
        tabelas=limpas,
        formas_verba={str(k).upper(): str(v) for k, v in dados.get("formas_verba", {}).items()},
        origem=str(arquivo),
    )
