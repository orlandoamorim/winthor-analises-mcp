"""Testa a fonte Oracle com uma conexão falsa: confere o SQL gerado e que toda
consulta roda dentro de SET TRANSACTION READ ONLY e termina em ROLLBACK."""

from dataclasses import replace
from datetime import date

from winthor_analises.config import carregar
from winthor_analises.fonte_oracle import FonteOracle
from winthor_analises.seguranca import exigir_select


class CursorFalso:
    def __init__(self, log, linhas):
        self.log, self.linhas, self.description = log, linhas, None

    def execute(self, sql, binds=None):
        self.log.append(sql)
        if self.linhas:
            self.description = [(c,) for c in self.linhas[0]]

    def fetchmany(self, n):
        return [tuple(l.values()) for l in self.linhas]

    def close(self):
        pass


class ConexaoFalsa:
    def __init__(self, linhas):
        self.log, self.linhas = [], linhas

    def cursor(self):
        return CursorFalso(self.log, self.linhas)

    def rollback(self):
        self.log.append("ROLLBACK")


def test_transacao_somente_leitura():
    con = ConexaoFalsa([{"CHAVE": "total", "NOME": "Total", "QUANTIDADE": 10, "VALOR": 99.5}])
    f = FonteOracle(replace(carregar(), modo="oracle"), conexao=con)
    r = f.totais("vendas", date(2025, 11, 1), date(2025, 11, 30))
    assert r == {"total": {"nome": "Total", "quantidade": 10.0, "valor": 99.5}}
    assert con.log[0] == "SET TRANSACTION READ ONLY"
    assert con.log[1].startswith("WITH f AS (SELECT CODPROD AS produto")
    assert con.log[-1] == "ROLLBACK"


def test_sql_gerado_passa_na_guarda():
    cfg = replace(carregar(), modo="oracle", filial="1", esquema="WINTHOR")
    f = FonteOracle(cfg, conexao=ConexaoFalsa([]))
    d1, d2 = date(2025, 1, 1), date(2025, 1, 31)
    for fato in ("vendas", "compras"):
        for agr in ("total", "produto", "fornecedor"):
            sql, binds = f.sql_totais(fato, d1, d2, agr, chaves=[1, 2], limite=10, fornecedor=101)
            exigir_select(sql)
            assert "WINTHOR.PCMOV" in sql and binds["filial"] == "1" and binds["forn"] == 101
    sql, _ = f.sql_totais("faturamento", d1, d2, "total")
    exigir_select(sql)
    exigir_select(f.sql_estoque([1, 2])[0])
    exigir_select(f.sql_verbas(101)[0])
    sql, binds = f.sql_movimentos_verba(101)
    exigir_select(sql)
    assert "WINTHOR.PCMOVCRFOR" in sql and binds == {"cred": "C", "forn": 101}


def test_sql_avaria_passa_na_guarda():
    cfg = replace(carregar(), modo="oracle", filial="1", esquema="WINTHOR")
    f = FonteOracle(cfg, conexao=ConexaoFalsa([]))
    sql, _ = f.sql_estoque_avaria()
    exigir_select(sql)
    assert "HAVING SUM(e.avaria) > 0" in sql
    sql, binds = f.sql_movimentos_avaria(date(2026, 1, 1), [1, 2])
    exigir_select(sql)
    assert sql.count("UNION ALL") == 1 and binds["k1"] == 2 and binds["filial"] == "1"
    sql, binds = f.sql_aplicacoes_rebaixa(date(2026, 1, 1))
    exigir_select(sql)
    assert binds["rot"] == 1806


def test_verbas_junta_baixas_por_rotina():
    class ConexaoVerbas(ConexaoFalsa):
        def cursor(self):
            ultima = self.log[-1] if self.log else ""
            linhas = self.respostas.pop(0) if ultima == "ROLLBACK" or not self.log else []
            return CursorFalso(self.log, linhas)

    con = ConexaoVerbas([])
    con.respostas = [
        [{"NUMERO": 7, "FORNECEDOR": 101, "NOME_FORNECEDOR": "X", "DATA": None, "VENCIMENTO": None,
          "VALOR": 100, "FORMA": "M", "ORIGEM": None, "DESCRICAO": None}],
        [{"NUMERO": 7, "ROTINA": 1301, "CREDITOS": 30, "DEBITOS": 0},
         {"NUMERO": 7, "ROTINA": 1806, "CREDITOS": 20, "DEBITOS": 0}],
    ]
    f = FonteOracle(replace(carregar(), modo="oracle"), conexao=con)
    v = f.verbas(101)
    assert v[0]["baixas_por_rotina"] == {"1301": 30.0, "1806": 20.0}
    assert con.log.count("SET TRANSACTION READ ONLY") == 2 and con.log.count("ROLLBACK") == 2
