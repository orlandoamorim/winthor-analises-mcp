from dataclasses import replace
from datetime import datetime

import pytest

from winthor_analises.config import ErroConfiguracao, carregar
from winthor_analises.seguranca import ConsultaRecusada, exigir_fora_do_horario, exigir_select


@pytest.mark.parametrize("sql", [
    "SELECT * FROM PCMOV",
    "WITH f AS (SELECT 1 AS x FROM DUAL) SELECT x FROM f",
    "SELECT * FROM PCMOV WHERE CODOPER = 'S' AND OBS = 'DELETE; DROP'",
])
def test_aceita_leitura(sql):
    assert exigir_select(sql) == sql


@pytest.mark.parametrize("sql", [
    "UPDATE PCMOV SET QT = 0",
    "DELETE FROM PCVERBA",
    "SELECT 1 FROM DUAL; DROP TABLE PCMOV",
    "SELECT * FROM PCMOV FOR UPDATE",
    "SELECT * FROM PCMOV -- comentario",
    "SELECT DBMS_RANDOM.VALUE FROM DUAL",
    "BEGIN NULL; END",
    "INSERT INTO PCMOV SELECT * FROM PCMOV",
    "MERGE INTO PCEST USING DUAL ON (1=1)",
])
def test_recusa_escrita(sql):
    with pytest.raises(ConsultaRecusada):
        exigir_select(sql)


def test_config_recusa_injecao(tmp_path):
    base = open(carregar().origem, encoding="utf-8").read()
    ruim = base.replace('tabela = "PCMOV"', 'tabela = "PCMOV; DROP TABLE X"', 1)
    arq = tmp_path / "c.toml"
    arq.write_text(ruim, encoding="utf-8")
    with pytest.raises(ErroConfiguracao):
        carregar(arq)


def test_credenciais_no_padrao_winthor_analises(monkeypatch):
    from winthor_analises.fonte_oracle import dados_conexao
    for k in ("WINTHOR_DB_DSN",):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("WINTHOR_DB_HOST", "h")
    monkeypatch.setenv("WINTHOR_DB_SERVICE", "WINT")
    monkeypatch.setenv("WINTHOR_DB_USER", "u")
    monkeypatch.setenv("WINTHOR_DB_PASSWORD", "p")
    assert dados_conexao() == ("u", "p", "h:1521/WINT")


def test_horario_pesado():
    cfg = replace(carregar(), modo="oracle")
    terca_10h = datetime(2026, 11, 24, 10, 0)
    terca_19h = datetime(2026, 11, 24, 19, 0)
    exigir_fora_do_horario(cfg, 100, terca_10h)          # leve: passa
    exigir_fora_do_horario(cfg, 2000, terca_19h)         # pesada à noite: passa
    with pytest.raises(ConsultaRecusada):
        exigir_fora_do_horario(cfg, 2000, terca_10h)     # pesada no expediente: bloqueia
    exigir_fora_do_horario(replace(cfg, modo="exemplo"), 2000, terca_10h)
    # réplica liberada pelo TI: a regra deixa de valer
    exigir_fora_do_horario(replace(cfg, banco="replica", horario_vale_na_replica=False), 2000, terca_10h)
    with pytest.raises(ConsultaRecusada):  # produção continua com a regra
        exigir_fora_do_horario(replace(cfg, banco="producao", horario_vale_na_replica=False), 2000, terca_10h)
