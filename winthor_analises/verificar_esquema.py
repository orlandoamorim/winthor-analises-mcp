"""Confere no Oracle se as tabelas e colunas do config.toml existem.

Uso:  python -m winthor_analises.verificar_esquema
      python -m winthor_analises.verificar_esquema --descobrir VERBA
O primeiro confere o config; o segundo lista tabelas cujo nome ou coluna
contém a palavra (para achar onde o WinThor guarda algo). Só lê o dicionário
de dados (ALL_TAB_COLUMNS) e faz um SELECT de teste com 0 linhas em cada
tabela. Usa as mesmas variáveis WINTHOR_DB_* do servidor (ou o .env).
"""

from __future__ import annotations

import re
import sys

from .config import carregar
from .fonte_oracle import FonteOracle
from .seguranca import ConsultaRecusada

PALAVRAS_SQL = {"NVL", "COALESCE", "NULL", "AND", "OR", "NOT", "IS", "IN", "LIKE", "ROUND", "TRUNC", "ABS"}


def colunas_citadas(texto: str) -> set[str]:
    sem_literais = re.sub(r"'[^']*'", "", texto)
    return {p.upper() for p in re.findall(r"[A-Za-z_][A-Za-z0-9_$#]*", sem_literais)} - PALAVRAS_SQL


def descobrir(fonte: FonteOracle, cfg, palavra: str) -> int:
    """Lista tabelas e colunas cujo nome contém a palavra (ex.: VERBA, BONIF)."""
    palavra = re.sub(r"[^A-Za-z0-9_]", "", palavra).upper()
    sql = ("SELECT OWNER AS dono, TABLE_NAME AS tabela, COLUMN_NAME AS coluna, DATA_TYPE AS tipo "
           "FROM ALL_TAB_COLUMNS WHERE (TABLE_NAME LIKE :p OR COLUMN_NAME LIKE :p)")
    binds = {"p": f"%{palavra}%"}
    if cfg.esquema:
        sql += " AND OWNER = :o"
        binds["o"] = cfg.esquema.upper()
    sql += " ORDER BY TABLE_NAME, COLUMN_ID"
    atual = None
    for r in fonte._consultar(sql, binds):
        if r["tabela"] != atual:
            atual = r["tabela"]
            print(f"\n{r['dono']}.{atual}")
        print(f"   {r['coluna']:<30} {r['tipo']}")
    return 0


def main() -> int:
    cfg = carregar()
    fonte = FonteOracle(cfg)
    if len(sys.argv) == 3 and sys.argv[1] == "--descobrir":
        return descobrir(fonte, cfg, sys.argv[2])
    try:
        print(f"Conectando (config: {cfg.origem})...")
        fonte._conexao()
        print("OK: usuário somente leitura.\n" if cfg.exigir_usuario_somente_leitura else "")
    except ConsultaRecusada as e:
        print(f"PARE: {e}")
        return 2

    dono = cfg.esquema.upper() if cfg.esquema else None
    erros = 0
    for nome, t in cfg.tabelas.items():
        tabela = t["tabela"].upper()
        sql = "SELECT COLUMN_NAME AS c FROM ALL_TAB_COLUMNS WHERE TABLE_NAME = :t"
        binds = {"t": tabela}
        if dono:
            sql += " AND OWNER = :o"
            binds["o"] = dono
        existentes = {r["c"] for r in fonte._consultar(sql, binds)}
        if not existentes:
            print(f"[{nome}] {tabela}: TABELA NÃO ENCONTRADA (ou sem permissão de leitura)")
            erros += 1
            continue
        faltando = set()
        for campo, valor in t.items():
            if campo != "tabela" and valor:
                faltando |= colunas_citadas(valor) - existentes
        if faltando:
            erros += 1
            print(f"[{nome}] {tabela}: colunas não encontradas: {', '.join(sorted(faltando))}")
        else:
            try:
                fonte._consultar(f"SELECT COUNT(*) AS n FROM {cfg.tabela(nome)} WHERE 1 = 0")
                print(f"[{nome}] {tabela}: ok")
            except Exception as e:  # noqa: BLE001
                erros += 1
                print(f"[{nome}] {tabela}: erro ao ler: {e}")
    print("\nTudo certo." if not erros else f"\n{erros} problema(s). Ajuste o config.toml.")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
