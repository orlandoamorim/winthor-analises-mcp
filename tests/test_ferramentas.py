from datetime import date

import pytest

from winthor_analises import analises
from winthor_analises.config import carregar
from winthor_analises.fonte_exemplo import FonteExemplo

HOJE = date(2026, 11, 24)
cfg = carregar()
fonte = FonteExemplo(cfg, hoje=HOJE)


def test_comparar_total_corta_periodo_em_aberto():
    r = analises.comparar_periodo(fonte, cfg, "2026-11-01", "2026-11-30", 3, hoje=HOJE)
    assert [p["fim"] for p in r["periodos"]] == ["2026-11-24", "2025-11-24", "2024-11-24", "2023-11-24"]
    vendas = r["indicadores"]["vendas"]["total"]
    assert len(vendas) == 4 and all(l["valor"] > 0 for l in vendas)
    assert vendas[0]["variacao_vs_ano_anterior_pct"] == round((vendas[0]["valor"] / vendas[1]["valor"] - 1) * 100, 1)
    assert "quantidade" not in r["indicadores"]["faturamento"]["total"][0]
    assert r["observacoes"]


def test_comparar_por_produto():
    r = analises.comparar_periodo(fonte, cfg, "01/10/2026", "31/10/2026", 2, ["vendas", "compras"],
                                  "produto", 5, hoje=HOJE)
    itens = r["indicadores"]["vendas"]["itens"]
    assert len(itens) == 5
    assert set(itens[0]["por_periodo"]) == {"2026", "2025", "2024"}


def test_comparar_valida_entrada():
    with pytest.raises(ValueError):
        analises.comparar_periodo(fonte, cfg, "2026-01-01", "2026-01-31", 9, hoje=HOJE)


def test_sazonalidade_natal():
    r = analises.sazonalidade(fonte, cfg, "natal", 3, 15, 10, hoje=HOJE)
    assert r["proxima_ocorrencia"] == "2026-12-25" and r["dias_ate_la"] == 31
    assert r["anos"] == [2025, 2024, 2023]
    nomes = [i["produto"] for i in r["itens"]]
    assert "PANETONE 500G" in nomes
    situacoes = [i["situacao"] for i in r["itens"]]
    assert situacoes == sorted(situacoes, key=["risco de ruptura", "atenção", "ok"].index)


def test_sazonalidade_por_fornecedor():
    r = analises.sazonalidade(fonte, cfg, "pascoa", 2, 15, 10, fornecedor=104, hoje=HOJE)
    assert r["itens"] and all(i["fornecedor"].startswith("Doces") for i in r["itens"])


def test_verbas():
    r = analises.verbas_fornecedor(fonte, cfg, hoje=HOJE)
    assert r["totais"]["saldo"] == round(sum(f["saldo"] for f in r["fornecedores"]), 2)
    assert round(sum(r["totais"]["saldo_por_forma"].values()), 2) == r["totais"]["saldo"]
    assert all(f["saldo"] > 0 for f in r["fornecedores"])
    assert set(r["como_receber"]) <= {"mercadoria", "dinheiro", "desconto financeiro", "rebaixa de custo"}
    r2 = analises.verbas_fornecedor(fonte, cfg, "doces alegria", hoje=HOJE)
    assert r2["verbas"] and all(v["nome_fornecedor"].startswith("Doces") for v in r2["verbas"])
    r3 = analises.verbas_fornecedor(fonte, cfg, "104", somente_com_saldo=False, hoje=HOJE)
    assert {v["fornecedor"] for v in r3["verbas"]} == {104}
    for v in r3["verbas"]:
        assert v["saldo"] == round(v["valor_gerado"] - v["recebido"], 2)
        assert v["situacao"] in ("baixada", "parcial", "em aberto")


def test_forma_traduzida():
    assert analises._forma(cfg, "m") == "mercadoria"
    assert analises._forma(cfg, "Rebaixa Custo") == "rebaixa de custo"
    assert analises._forma(cfg, None) == "não informada"


def test_avaria_separa_verba_da_avaria_real():
    r = analises.avaria_parada(fonte, cfg, hoje=HOJE)
    itens = {i["codigo"]: i for i in r["itens"]}
    misto = itens[4002]  # 8 de avaria real + 52 movidos por causa da verba
    assert (misto["devolver_ao_estoque"], misto["avaria_real_provavel"]) == (52, 8)
    assert misto["situacao"] == "esquecido na avaria" and "Manter 8" in misto["recomendacao"]
    assert itens[2002]["devolver_ao_estoque"] == 90       # a volta parcial saiu do lote da verba
    assert itens[3004]["origem_desconhecida"] == 36
    assert itens[5001]["situacao"] == "avaria recente"
    assert r["itens"][0]["situacao"] == "esquecido na avaria"
    assert r["resumo"]["unidades_para_devolver"] == 342


def test_avaria_sem_datas_de_verba_avisa():
    class SemDatas(FonteExemplo):
        def aplicacoes_rebaixa(self, desde):
            return None
    r = analises.avaria_parada(SemDatas(cfg, hoje=HOJE), cfg, hoje=HOJE)
    assert r["resumo"]["produtos_para_devolver"] == 0 and "Configure" in r["observacoes"][0]
