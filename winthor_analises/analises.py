"""Lógica das três análises. Não sabe de onde vêm os dados: recebe uma fonte
(Oracle ou exemplo) com os métodos totais(), estoque() e verbas()."""

from __future__ import annotations

import unicodedata
from datetime import date, datetime, timedelta

from .datas import data_comemorativa, ler_data, mesmo_periodo, nome_data
from .seguranca import exigir_fora_do_horario

INDICADORES = ("vendas", "compras", "faturamento")


def _r(x) -> float:
    return round(float(x or 0), 2)


def _var(atual, anterior):
    """Variação percentual do atual sobre o anterior (None se não há base)."""
    if not anterior:
        return None
    return round((atual / anterior - 1) * 100, 1)


def _como_data(x):
    if isinstance(x, datetime):
        return x.date()
    return x


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


# ---------------------------------------------------------------------------
def comparar_periodo(fonte, cfg, inicio: str, fim: str, anos_anteriores: int = 1,
                     indicadores: list[str] | None = None, agrupar_por: str = "total",
                     limite: int = 20, hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    ini, fi = ler_data(inicio), ler_data(fim)
    if fi < ini:
        raise ValueError("a data final é anterior à inicial")
    if not 1 <= anos_anteriores <= 5:
        raise ValueError("anos_anteriores deve ser de 1 a 5")
    if agrupar_por not in ("total", "produto", "fornecedor"):
        raise ValueError("agrupar_por deve ser total, produto ou fornecedor")
    indicadores = indicadores or list(INDICADORES)
    for ind in indicadores:
        if ind not in INDICADORES:
            raise ValueError(f"indicador desconhecido: {ind}. Use {', '.join(INDICADORES)}")
    limite = max(1, min(limite, cfg.limite_linhas))

    obs = []
    if ini > hoje:
        raise ValueError("o período começa no futuro")
    if fi > hoje:
        fi = hoje
        obs.append(f"O período ainda não terminou: todos os anos foram comparados só até "
                   f"{hoje:%d/%m} para a comparação ser justa.")

    periodos = []
    for k in range(anos_anteriores + 1):
        a, b = mesmo_periodo(ini, fi, k)
        rot = str(a.year) if a.year == b.year else f"{a.year}/{b.year}"
        periodos.append({"rotulo": rot, "inicio": a, "fim": b})
    dias = sum((p["fim"] - p["inicio"]).days + 1 for p in periodos) * len(indicadores)
    exigir_fora_do_horario(cfg, dias)

    resultado = {
        "periodos": [{"rotulo": p["rotulo"], "inicio": p["inicio"].isoformat(), "fim": p["fim"].isoformat()}
                     for p in periodos],
        "agrupado_por": agrupar_por,
        "indicadores": {},
    }
    for ind in indicadores:
        agrupar = agrupar_por
        if ind == "faturamento" and agrupar_por != "total":
            agrupar = "total"
            obs.append("Faturamento (notas fiscais) aparece só no total, sem quebra por produto ou fornecedor.")

        if agrupar == "total":
            linhas = []
            for p in periodos:
                t = fonte.totais(ind, p["inicio"], p["fim"], "total").get("total", {})
                linhas.append({"periodo": p["rotulo"], "valor": _r(t.get("valor")),
                               "quantidade": _r(t.get("quantidade"))})
            atual = linhas[0]["valor"]
            for i, l in enumerate(linhas):
                if ind == "faturamento":
                    l.pop("quantidade")
                # variação deste período sobre o mesmo período do ano anterior a ele
                l["variacao_vs_ano_anterior_pct"] = (
                    _var(l["valor"], linhas[i + 1]["valor"]) if i + 1 < len(linhas) else None)
                if i:
                    l["periodo_atual_vs_este_pct"] = _var(atual, l["valor"])
            resultado["indicadores"][ind] = {"total": linhas}
            continue

        # ranking pelo período atual; se vazio, pelo ano anterior
        base = fonte.totais(ind, periodos[0]["inicio"], periodos[0]["fim"], agrupar, limite=limite)
        ref = 0
        if not base:
            base = fonte.totais(ind, periodos[1]["inicio"], periodos[1]["fim"], agrupar, limite=limite)
            ref = 1
        chaves = list(base)
        por_periodo = [base if i == ref else fonte.totais(ind, p["inicio"], p["fim"], agrupar, chaves=chaves)
                       for i, p in enumerate(periodos)]
        itens = []
        for k in chaves:
            valores = {p["rotulo"]: {"valor": _r(d.get(k, {}).get("valor")),
                                     "quantidade": _r(d.get(k, {}).get("quantidade"))}
                       for p, d in zip(periodos, por_periodo)}
            v0 = valores[periodos[0]["rotulo"]]["valor"]
            v1 = valores[periodos[1]["rotulo"]]["valor"]
            itens.append({"codigo": k, "nome": base[k]["nome"], "por_periodo": valores,
                          "variacao_vs_ano_anterior_pct": _var(v0, v1)})
        resultado["indicadores"][ind] = {
            "itens": itens,
            "nota": f"Os {len(itens)} maiores em valor no período {periodos[ref]['rotulo']}.",
        }
    resultado["observacoes"] = list(dict.fromkeys(obs))
    return resultado


# ---------------------------------------------------------------------------
def sazonalidade(fonte, cfg, data_comemorativa_: str, anos: int = 3, dias_antes: int = 15,
                 limite: int = 20, fornecedor: int | None = None, hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    if not 1 <= anos <= 5:
        raise ValueError("anos deve ser de 1 a 5")
    if not 1 <= dias_antes <= 60:
        raise ValueError("dias_antes deve ser de 1 a 60")
    limite = max(1, min(limite, cfg.limite_linhas))

    proxima = data_comemorativa(data_comemorativa_, hoje.year)
    if proxima < hoje:
        proxima = data_comemorativa(data_comemorativa_, hoje.year + 1)
    exigir_fora_do_horario(cfg, (dias_antes + 1) * anos)

    janelas = []
    for k in range(1, anos + 1):
        d = data_comemorativa(data_comemorativa_, proxima.year - k)
        janelas.append({"ano": d.year, "inicio": d - timedelta(days=dias_antes), "fim": d})

    # produtos mais vendidos na janela do ano mais recente, depois os mesmos nos outros anos
    ultimo = janelas[0]
    top = fonte.totais("vendas", ultimo["inicio"], ultimo["fim"], "produto",
                       limite=limite, fornecedor=fornecedor)
    chaves = list(top)
    vendas = {ultimo["ano"]: top}
    for j in janelas[1:]:
        vendas[j["ano"]] = fonte.totais("vendas", j["inicio"], j["fim"], "produto",
                                        chaves=chaves, fornecedor=fornecedor)
    est = fonte.estoque(chaves) if chaves else {}

    itens = []
    for k in chaves:
        por_ano = {j["ano"]: _r(vendas[j["ano"]].get(k, {}).get("quantidade")) for j in janelas}
        media = sum(por_ano.values()) / len(por_ano)
        tendencia = _var(por_ano[janelas[0]["ano"]], por_ano[janelas[1]["ano"]]) if len(janelas) > 1 else None
        # previsão simples: ano passado ajustado pela tendência (limitada a ±30%)
        ajuste = 1 + max(-0.3, min(0.3, (tendencia or 0) / 100))
        previsao = por_ano[janelas[0]["ano"]] * ajuste
        estoque = _r(est.get(k, {}).get("quantidade"))
        cobertura = round(estoque / previsao * 100) if previsao else None
        if previsao and estoque < 0.5 * previsao:
            situacao = "risco de ruptura"
        elif previsao and estoque < previsao:
            situacao = "atenção"
        else:
            situacao = "ok"
        itens.append({
            "codigo": k, "produto": top[k]["nome"],
            "fornecedor": est.get(k, {}).get("nome_fornecedor"),
            "vendido_na_janela_por_ano": por_ano,
            "media_vendida": _r(media),
            "tendencia_pct": tendencia,
            "previsao_para_a_data": _r(previsao),
            "estoque_atual": estoque,
            "cobertura_pct": cobertura,
            "falta_comprar_aprox": _r(max(0.0, previsao - estoque)),
            "situacao": situacao,
        })
    ordem = {"risco de ruptura": 0, "atenção": 1, "ok": 2}
    itens.sort(key=lambda i: (ordem[i["situacao"]], -(i["previsao_para_a_data"])))
    return {
        "data": nome_data(data_comemorativa_),
        "proxima_ocorrencia": proxima.isoformat(),
        "dias_ate_la": (proxima - hoje).days,
        "janela_analisada": f"{dias_antes} dias antes da data até o dia, em cada ano",
        "anos": [j["ano"] for j in janelas],
        "itens": itens,
        "resumo": {s: sum(1 for i in itens if i["situacao"] == s) for s in ordem},
        "observacoes": [
            "Quantidades em unidades de venda. A previsão é o ano passado ajustado pela "
            "tendência entre os dois últimos anos (limitada a ±30%).",
            "O estoque é o de hoje: não conta pedidos de compra ainda não recebidos.",
        ],
    }


# ---------------------------------------------------------------------------
# Verbas, no modelo da TOTVS (rotina 1809): a verba é um débito do fornecedor,
# baixado por créditos. Cada forma de recebimento tem a sua rotina de baixa.
ROTINAS_BAIXA = {
    "1301": "mercadoria (entrada bonificada tipo 5)",
    "1803": "dinheiro",
    "1804": "desconto financeiro",
    "1806": "rebaixa de custo",
}
COMO_RECEBER = {
    "mercadoria": "Pedir em mercadoria: pedido bonificado (209) e entrada tipo 5 (1301).",
    "dinheiro": "Cobrar o pagamento do fornecedor; baixa na 1803 (ou 1804 se veio de devolução).",
    "desconto financeiro": "Abater numa duplicata a pagar ao fornecedor (1804).",
    "rebaixa de custo": "Aplicar na rotina 1806 para baixar o custo do produto.",
}


def _forma(cfg, bruto) -> str:
    """Traduz o código da forma de recebimento para um rótulo legível."""
    if bruto in (None, ""):
        return "não informada"
    texto = str(bruto).strip().upper()
    if texto in cfg.formas_verba:
        return cfg.formas_verba[texto]
    t = _sem_acento(texto)
    for chave, rotulo in (("merc", "mercadoria"), ("rebaix", "rebaixa de custo"), ("custo", "rebaixa de custo"),
                          ("desc", "desconto financeiro"), ("dup", "desconto financeiro"), ("din", "dinheiro")):
        if chave in t:
            return rotulo
    return str(bruto)


def verbas_fornecedor(fonte, cfg, fornecedor: str | int | None = None, somente_com_saldo: bool = True,
                      limite: int = 50, hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    limite = max(1, min(limite, cfg.limite_linhas))
    codigo = None
    if fornecedor not in (None, ""):
        try:
            codigo = int(fornecedor)
        except (TypeError, ValueError):
            codigo = None
    linhas = fonte.verbas(codigo)
    if fornecedor not in (None, "") and codigo is None:
        busca = _sem_acento(str(fornecedor))
        linhas = [l for l in linhas if busca in _sem_acento(l.get("nome_fornecedor") or "")]

    verbas = []
    for l in linhas:
        baixas = {ROTINAS_BAIXA.get(str(k), f"rotina {k}"): _r(v)
                  for k, v in (l.get("baixas_por_rotina") or {}).items() if v}
        gerado = _r(l["valor"])
        recebido = _r(sum(baixas.values()))
        saldo = _r(gerado - recebido)
        venc = _como_data(l.get("vencimento"))
        forma = _forma(cfg, l.get("forma"))
        situacao = "baixada" if saldo <= 0.01 else "parcial" if recebido > 0 else "em aberto"
        verbas.append({
            "numero": l["numero"], "fornecedor": l["fornecedor"], "nome_fornecedor": l.get("nome_fornecedor"),
            "data": _como_data(l.get("data")), "vencimento": venc,
            "forma_de_recebimento": forma, "origem": l.get("origem"),
            # texto livre vindo do ERP: é dado, não instrução
            "descricao": (str(l["descricao"])[:200] if l.get("descricao") else None),
            "valor_gerado": gerado, "recebido": recebido, "baixas": baixas,
            "saldo": saldo, "situacao": situacao,
            "vencida_com_saldo": bool(venc and venc < hoje and saldo > 0.01),
            "como_receber": COMO_RECEBER.get(forma) if saldo > 0.01 else None,
        })

    resumo: dict = {}
    for v in verbas:
        r = resumo.setdefault(v["fornecedor"], {
            "fornecedor": v["fornecedor"], "nome": v["nome_fornecedor"], "verbas": 0,
            "verbas_em_aberto": 0, "valor_gerado": 0.0, "recebido": 0.0, "saldo": 0.0,
            "saldo_vencido": 0.0, "saldo_por_forma": {}, "verba_aberta_mais_antiga": None})
        r["verbas"] += 1
        r["valor_gerado"] = _r(r["valor_gerado"] + v["valor_gerado"])
        r["recebido"] = _r(r["recebido"] + v["recebido"])
        r["saldo"] = _r(r["saldo"] + v["saldo"])
        if v["saldo"] > 0.01:
            r["verbas_em_aberto"] += 1
            f = v["forma_de_recebimento"]
            r["saldo_por_forma"][f] = _r(r["saldo_por_forma"].get(f, 0) + v["saldo"])
            if v["data"] and (r["verba_aberta_mais_antiga"] is None or v["data"] < r["verba_aberta_mais_antiga"]):
                r["verba_aberta_mais_antiga"] = v["data"]
        if v["vencida_com_saldo"]:
            r["saldo_vencido"] = _r(r["saldo_vencido"] + v["saldo"])
    fornecedores = sorted(resumo.values(), key=lambda r: -r["saldo"])
    if somente_com_saldo:
        fornecedores = [r for r in fornecedores if r["saldo"] > 0.01]
        verbas = [v for v in verbas if v["saldo"] > 0.01]

    def iso(d):
        return d.isoformat() if d else None
    por_forma: dict = {}
    for r in fornecedores:
        r["verba_aberta_mais_antiga"] = iso(r["verba_aberta_mais_antiga"])
        for f, val in r["saldo_por_forma"].items():
            por_forma[f] = _r(por_forma.get(f, 0) + val)
    for v in verbas:
        v["data"], v["vencimento"] = iso(v["data"]), iso(v["vencimento"])

    res = {
        "totais": {
            "fornecedores": len(fornecedores),
            "saldo": _r(sum(r["saldo"] for r in fornecedores)),
            "saldo_vencido": _r(sum(r["saldo_vencido"] for r in fornecedores)),
            "saldo_por_forma": por_forma,
        },
        "fornecedores": fornecedores[:limite],
        "como_receber": {f: COMO_RECEBER[f] for f in por_forma if f in COMO_RECEBER},
        "observacoes": [
            "Mesmo critério da rotina 1809: saldo = valor gerado (débito) menos o que já foi "
            "baixado (crédito) em mercadoria (1301), dinheiro (1803), desconto financeiro (1804) "
            "ou rebaixa de custo (1806).",
            "Verbas geradas por devolução ao fornecedor (1302) não têm valor a aplicar em "
            "rebaixa de custo: são recebidas em dinheiro ou desconto.",
            "Confira os números com a 1809 antes de usá-los para cobrar o fornecedor.",
        ],
    }
    if fornecedor not in (None, ""):
        verbas.sort(key=lambda v: (v["vencimento"] or ""))
        res["verbas"] = verbas[:limite]
    return res


# ---------------------------------------------------------------------------
# Avaria parada. A dona aplica verba só em parte do estoque movendo o resto para
# a avaria e depois esquece de devolver; quando devolve, leva junto a avaria real.
# Aqui cada ida para a avaria vira um "lote", e o lote é ligado à verba quando
# aconteceu perto de uma rebaixa de custo (1806) do mesmo fornecedor.
def avaria_parada(fonte, cfg, dias_parado: int = 15, janela_verba_dias: int = 7,
                  historico_dias: int = 180, fornecedor: int | None = None,
                  limite: int = 50, hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    if not 30 <= historico_dias <= 730:
        raise ValueError("historico_dias deve ser de 30 a 730")
    limite = max(1, min(limite, cfg.limite_linhas))
    exigir_fora_do_horario(cfg, historico_dias)
    desde = hoje - timedelta(days=historico_dias)

    estoque = fonte.estoque_avaria()
    if fornecedor is not None:
        estoque = {k: v for k, v in estoque.items() if v.get("fornecedor") == fornecedor}
    movs = fonte.movimentos_avaria(desde, list(estoque))
    aplicacoes = fonte.aplicacoes_rebaixa(desde - timedelta(days=janela_verba_dias))
    obs = []
    if aplicacoes is None:
        aplicacoes = []
        obs.append("Sem data/rotina das baixas de verba configuradas: não dá para separar o que foi "
                   "para a avaria por causa de verba. Configure [tabelas.movimentos_verba] data e rotina.")

    por_forn: dict = {}
    for a in aplicacoes:
        por_forn.setdefault(a["fornecedor"], []).append((_como_data(a["data"]), a["numero"]))
    por_prod: dict = {}
    for m in movs:
        por_prod.setdefault(m["produto"], []).append((_como_data(m["data"]), m["tipo"], m["quantidade"]))

    itens = []
    for cod, e in estoque.items():
        verbas_forn = por_forn.get(e.get("fornecedor"), [])
        lotes = []  # [data, quantidade, numeros_de_verba]
        for data, tipo, qt in sorted(por_prod.get(cod, []), key=lambda x: (x[0], x[1])):
            if tipo == "E":
                ligadas = sorted({n for d, n in verbas_forn if abs((d - data).days) <= janela_verba_dias})
                lotes.append([data, qt, ligadas])
            else:
                # quem volta primeiro é a mercadoria da verba (era só para "esconder" do cálculo)
                for lote in sorted(lotes, key=lambda l: (not l[2], l[0])):
                    usar = min(qt, lote[1])
                    lote[1] -= usar
                    qt -= usar
                    if qt <= 0:
                        break
        lotes = [l for l in lotes if l[1] > 0]
        diferenca = e["avaria"] - sum(l[1] for l in lotes)
        if diferenca > 0:
            lotes.append([None, diferenca, []])  # já estava lá antes do histórico
        elif diferenca < 0:
            # saiu da avaria por outro caminho (descarte, indenização): tira primeiro da avaria real
            falta = -diferenca
            for lote in sorted(lotes, key=lambda l: (bool(l[2]), l[0] or date.min)):
                usar = min(falta, lote[1])
                lote[1] -= usar
                falta -= usar
            lotes = [l for l in lotes if l[1] > 0]

        def dias(l):
            return (hoje - l[0]).days if l[0] else None
        da_verba = [l for l in lotes if l[2]]
        real = [l for l in lotes if not l[2] and l[0]]
        sem_hist = [l for l in lotes if not l[0]]
        devolver = sum(l[1] for l in da_verba)
        dias_verba = max((dias(l) for l in da_verba), default=None)
        dias_max = max([dias(l) for l in lotes if l[0]] or [0])

        if da_verba and dias_verba >= dias_parado:
            situacao = "esquecido na avaria"
        elif da_verba:
            situacao = "devolver em breve"
        elif sem_hist or dias_max >= dias_parado:
            situacao = "avaria antiga"
        else:
            situacao = "avaria recente"

        partes = []
        if devolver:
            nums = sorted({n for l in da_verba for n in l[2]})
            partes.append(f"Devolver {devolver:g} un. ao estoque disponível (foram para a avaria junto com "
                          f"a verba {', '.join(map(str, nums))}, há {dias_verba} dias).")
        manter = sum(l[1] for l in real) + sum(l[1] for l in sem_hist)
        if manter and devolver:
            partes.append(f"Manter {manter:g} un. na avaria: não têm ligação com verba e parecem avaria real. "
                          f"Devolva só a quantidade acima, não a avaria inteira.")
        elif sem_hist and not devolver:
            partes.append(f"{sum(l[1] for l in sem_hist):g} un. estão na avaria desde antes de "
                          f"{desde:%d/%m/%Y}: conferir se é avaria real ou mercadoria esquecida.")
        elif real and dias_max >= dias_parado:
            partes.append(f"Avaria real há {dias_max} dias: decidir troca, indenização ou descarte.")

        custo = e.get("custo")
        itens.append({
            "codigo": cod, "produto": e.get("descricao"), "fornecedor": e.get("nome_fornecedor"),
            "avaria_hoje": _r(e["avaria"]), "disponivel_hoje": _r(e.get("disponivel")),
            "devolver_ao_estoque": _r(devolver),
            "avaria_real_provavel": _r(sum(l[1] for l in real)),
            "origem_desconhecida": _r(sum(l[1] for l in sem_hist)),
            "dias_parado": dias_verba if da_verba else (dias_max or None),
            "valor_parado": _r(devolver * custo) if custo is not None and devolver else None,
            "valor_na_avaria": _r(e["avaria"] * custo) if custo is not None else None,
            "lotes": [{"desde": l[0].isoformat() if l[0] else "antes do histórico", "quantidade": _r(l[1]),
                       "motivo_provavel": f"verba {', '.join(map(str, l[2]))}" if l[2] else
                       ("avaria real" if l[0] else "desconhecido")} for l in lotes],
            "situacao": situacao,
            "recomendacao": " ".join(partes) or "Nada a fazer por enquanto.",
        })

    ordem = {"esquecido na avaria": 0, "devolver em breve": 1, "avaria antiga": 2, "avaria recente": 3}
    itens.sort(key=lambda i: (ordem[i["situacao"]], -(i["valor_parado"] or 0), -(i["dias_parado"] or 0)))
    devolver_itens = [i for i in itens if i["devolver_ao_estoque"]]
    return {
        "resumo": {
            "produtos_na_avaria": len(itens),
            "produtos_para_devolver": len(devolver_itens),
            "unidades_para_devolver": _r(sum(i["devolver_ao_estoque"] for i in devolver_itens)),
            "valor_parado_para_devolver": _r(sum(i["valor_parado"] or 0 for i in devolver_itens)),
            "por_situacao": {s: sum(1 for i in itens if i["situacao"] == s) for s in ordem},
        },
        "itens": itens[:limite],
        "observacoes": obs + [
            f"Uma ida para a avaria é ligada à verba quando aconteceu até {janela_verba_dias} dias de uma "
            "rebaixa de custo (1806) do mesmo fornecedor. É uma inferência: confira antes de mover.",
            "Este MCP só aponta. A transferência de volta para o disponível é feita no WinThor.",
        ],
    }
