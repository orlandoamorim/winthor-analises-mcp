"""Fonte de dados de exemplo: números fictícios, gerados de forma determinística.

Serve para testar as ferramentas sem conexão com o banco. Os produtos e
fornecedores são inventados; os padrões (crescimento anual, picos em datas
comemorativas, fins de semana mais fortes, alguns itens em ruptura) imitam
um atacarejo para que as análises tenham algo a mostrar.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from functools import lru_cache

from .datas import data_comemorativa

FORNECEDORES = {
    101: "Distribuidora Boa Safra (exemplo)",
    102: "Laticínios Vale Verde (exemplo)",
    103: "Bebidas Norte Sul (exemplo)",
    104: "Doces Alegria (exemplo)",
    105: "Higiene Lar & Cia (exemplo)",
    106: "Carvoaria Brasa Forte (exemplo)",
    107: "Massas Dona Nena (exemplo)",
    108: "Frios Campo Bom (exemplo)",
}

# código, descrição, fornecedor, preço de venda (2020), unidades/dia, picos {data: multiplicador}
PRODUTOS = [
    (1001, "ARROZ TIPO 1 5KG", 101, 22.9, 40, {"natal": 1.3}),
    (1002, "FEIJAO CARIOCA 1KG", 101, 7.5, 55, {}),
    (1003, "ACUCAR CRISTAL 5KG", 101, 18.0, 30, {"sao_joao": 1.4, "natal": 1.3}),
    (1004, "OLEO DE SOJA 900ML", 101, 6.9, 45, {}),
    (1005, "FLOCAO DE MILHO 500G", 101, 2.6, 35, {"sao_joao": 2.5}),
    (1006, "MILHO DE PIPOCA 500G", 101, 4.2, 12, {"sao_joao": 3.0, "criancas": 1.5}),
    (2001, "LEITE UHT INTEGRAL 1L", 102, 4.6, 90, {}),
    (2002, "LEITE CONDENSADO 395G", 102, 5.8, 25, {"pascoa": 1.8, "sao_joao": 2.0, "natal": 2.0}),
    (2003, "CREME DE LEITE 200G", 102, 3.2, 22, {"natal": 2.2, "maes": 1.5}),
    (2004, "MANTEIGA 200G", 102, 9.9, 15, {"natal": 1.5}),
    (3001, "CERVEJA LATA 350ML", 103, 3.4, 150, {"carnaval": 2.5, "pais": 1.8, "sao_joao": 2.0, "ano_novo": 2.2}),
    (3002, "REFRIGERANTE COLA 2L", 103, 8.5, 60, {"natal": 1.8, "ano_novo": 1.8, "criancas": 1.6}),
    (3003, "ESPUMANTE 750ML", 103, 32.0, 2, {"natal": 6.0, "ano_novo": 8.0, "maes": 2.0, "namorados": 3.0}),
    (3004, "VINHO TINTO SUAVE 750ML", 103, 19.9, 6, {"natal": 3.5, "namorados": 2.5, "pais": 2.0}),
    (3005, "AGUA MINERAL 500ML", 103, 1.5, 80, {"carnaval": 2.0}),
    (4001, "OVO DE PASCOA 200G", 104, 39.9, 0.3, {"pascoa": 120.0}),
    (4002, "CAIXA DE BOMBONS 250G", 104, 12.9, 8, {"pascoa": 3.0, "maes": 3.5, "namorados": 3.0, "natal": 2.5}),
    (4003, "PANETONE 500G", 104, 19.9, 0.5, {"natal": 60.0}),
    (4004, "PIRULITO PACOTE 50UN", 104, 9.5, 5, {"criancas": 5.0}),
    (4005, "CHOCOLATE BARRA 90G", 104, 6.5, 30, {"pascoa": 2.0, "namorados": 1.8, "criancas": 2.0}),
    (5001, "SABAO EM PO 1KG", 105, 13.5, 25, {}),
    (5002, "PAPEL HIGIENICO 12 ROLOS", 105, 17.9, 30, {}),
    (5003, "KIT PERFUME PRESENTE", 105, 49.9, 0.5, {"maes": 15.0, "pais": 10.0, "natal": 12.0, "namorados": 8.0}),
    (6001, "CARVAO VEGETAL 4KG", 106, 16.0, 10, {"pais": 3.0, "sao_joao": 2.5, "ano_novo": 2.0}),
    (6002, "FOGOS ESTRELINHA PACOTE", 106, 5.0, 0.5, {"sao_joao": 40.0, "ano_novo": 20.0}),
    (7001, "MACARRAO ESPAGUETE 500G", 107, 4.3, 50, {}),
    (7002, "MOLHO DE TOMATE 340G", 107, 2.9, 45, {}),
    (7003, "FARINHA DE TRIGO 1KG", 107, 5.2, 28, {"natal": 1.6, "pascoa": 1.4}),
    (8001, "LINGUICA TOSCANA KG", 108, 21.0, 18, {"pais": 2.5, "sao_joao": 2.0, "ano_novo": 1.8}),
    (8002, "CHESTER KG", 108, 34.0, 0.3, {"natal": 50.0, "ano_novo": 15.0}),
]
PROD = {p[0]: p for p in PRODUTOS}
ANO_BASE = 2020
DIAS_PICO = 15  # o pico sobe nos 15 dias antes da data


def _ruido(*partes) -> float:
    """Número entre 0 e 1, sempre o mesmo para as mesmas entradas."""
    h = hashlib.blake2b(repr(partes).encode(), digest_size=4).digest()
    return int.from_bytes(h, "big") / 0xFFFFFFFF


@lru_cache(maxsize=None)
def _datas_do_ano(ano: int) -> dict[str, date]:
    chaves = {k for p in PRODUTOS for k in p[5]}
    return {k: data_comemorativa(k, ano) for k in chaves}


def _fator_pico(cod: int, dia: date) -> float:
    picos = PROD[cod][5]
    if not picos:
        return 1.0
    datas = _datas_do_ano(dia.year)
    fator = 1.0
    for chave, mult in picos.items():
        dist = (datas[chave] - dia).days
        if 0 <= dist < DIAS_PICO:
            fator = max(fator, 1 + (mult - 1) * (1 - dist / DIAS_PICO) * 1.6)
    return fator


def _vendas_dia(cod: int, dia: date) -> tuple[float, float]:
    _, _, _, preco, base, _ = PROD[cod]
    anos = dia.year - ANO_BASE + dia.timetuple().tm_yday / 366
    semana = (0.8, 0.85, 0.9, 0.95, 1.2, 1.5, 0.7)[dia.weekday()]
    qt = base * (1.06 ** anos) * semana * _fator_pico(cod, dia) * (0.8 + 0.4 * _ruido(cod, dia))
    qt = round(qt)
    return qt, qt * preco * (1.055 ** anos)


def _compras_dia(cod: int, dia: date) -> tuple[float, float]:
    """Entrega semanal no dia do fornecedor, cobrindo a semana seguinte."""
    if dia.weekday() != PROD[cod][2] % 5:
        return 0, 0.0
    qt = sum(_vendas_dia(cod, dia + timedelta(days=d))[0] for d in range(1, 8)) * (0.95 + 0.15 * _ruido("c", cod, dia))
    preco = PROD[cod][3] * 0.72 * (1.055 ** (dia.year - ANO_BASE))
    return round(qt), round(qt) * preco


class FonteExemplo:
    def __init__(self, cfg=None, hoje: date | None = None):
        self.cfg = cfg
        self.hoje = hoje or date.today()

    def _dias(self, inicio: date, fim: date):
        fim = min(fim, self.hoje)
        d = inicio
        while d <= fim:
            yield d
            d += timedelta(days=1)

    def totais(self, fato, inicio, fim, agrupar="total", chaves=None, limite=None, fornecedor=None) -> dict:
        if fato not in ("vendas", "compras", "faturamento"):
            raise ValueError(f"fato desconhecido: {fato}")
        if fato == "faturamento" and agrupar != "total":
            raise ValueError("faturamento só pode ser somado no total")
        calc = _compras_dia if fato == "compras" else _vendas_dia
        res: dict = {}
        for cod, _, forn, *_ in PRODUTOS:
            if fornecedor is not None and forn != fornecedor:
                continue
            if agrupar == "produto":
                chave, nome = cod, PROD[cod][1]
            elif agrupar == "fornecedor":
                chave, nome = forn, FORNECEDORES[forn]
            else:
                chave, nome = "total", "Total"
            if chaves is not None and chave not in chaves:
                continue
            item = res.setdefault(chave, {"nome": nome, "quantidade": 0.0, "valor": 0.0})
            for dia in self._dias(inicio, fim):
                qt, valor = calc(cod, dia)
                item["quantidade"] += qt
                item["valor"] += valor
        if fato == "faturamento":
            for item in res.values():
                item["quantidade"] = 0.0
        if limite:
            res = dict(sorted(res.items(), key=lambda kv: -kv[1]["valor"])[:limite])
        return res

    def estoque(self, produtos=None) -> dict:
        res = {}
        for cod, desc, forn, _, base, _ in PRODUTOS:
            if produtos is not None and cod not in produtos:
                continue
            r = _ruido("estoque", cod)
            # ~20% dos itens com estoque muito baixo, para aparecer risco de ruptura
            dias_cobertura = r * 3 if r < 0.2 else 5 + r * 45
            res[cod] = {"produto": cod, "descricao": desc, "fornecedor": forn,
                        "nome_fornecedor": FORNECEDORES[forn],
                        "quantidade": float(round(max(base, 2) * dias_cobertura))}
        return res

    def verbas(self, fornecedor=None) -> list[dict]:
        """Verbas fictícias seguindo o ciclo descrito pela TOTVS: gera um débito e
        vai baixando por créditos na rotina da forma de recebimento."""
        rotina_da_forma = {"M": "1301", "D": "1803", "F": "1804", "R": "1806"}
        linhas = []
        numero = 5000
        for forn in FORNECEDORES:
            for i in range(2 + int(_ruido("qv", forn) * 4)):
                numero += 1
                if fornecedor is not None and forn != fornecedor:
                    continue
                emissao = self.hoje - timedelta(days=int(20 + _ruido("dv", forn, i) * 700))
                valor = round(500 + _ruido("vv", forn, i) * 7500, 2)
                devolucao = _ruido("or", forn, i) < 0.25
                forma = ("D" if _ruido("fd", forn, i) < 0.5 else "F") if devolucao else "MRDR"[int(_ruido("fm", forn, i) * 4)]
                r = _ruido("av", forn, i)
                recebido = valor if r > 0.55 else round(valor * r, 2) if r > 0.25 else 0.0
                linhas.append({
                    "numero": numero, "fornecedor": forn, "nome_fornecedor": FORNECEDORES[forn],
                    "data": emissao, "vencimento": emissao + timedelta(days=90), "valor": valor,
                    "forma": forma,
                    "origem": "devolução ao fornecedor (1302)" if devolucao else
                              ("pedido bonificado (209)" if forma == "M" else "acordo comercial"),
                    "descricao": "Verba de exemplo",
                    "baixas_por_rotina": {rotina_da_forma[forma]: recebido} if recebido else {},
                })
        return linhas

    # ------------------------------------------------------------------ avaria
    # Cenários fictícios que imitam o problema real: mercadoria mandada para a
    # avaria só para aplicar verba em parte do estoque, e que ninguém devolveu.
    def _cenarios_avaria(self):
        h = self.hoje
        d = lambda n: h - timedelta(days=n)  # noqa: E731
        # produto: (movimentos [(data, tipo, qt)], aplicações 1806 [(data, numero_verba)])
        return {
            4002: ([(d(70), "E", 8), (d(40), "E", 52)], [(d(40), 5012)]),   # 8 avaria real + 52 da verba
            2002: ([(d(95), "E", 120), (d(80), "R", 30)], [(d(94), 5003)]),  # verba, devolveu só uma parte
            5001: ([(d(10), "E", 5)], []),                                    # avaria real recente
            3004: ([], []),                                                   # está lá desde antes do histórico
            7003: ([(d(18), "E", 200)], [(d(18), 5031)]),                     # verba recente, ainda não voltou
        }

    def estoque_avaria(self) -> dict:
        res = {}
        for cod, (movs, _) in self._cenarios_avaria().items():
            _, desc, forn, preco, base, _ = PROD[cod]
            saldo = sum(q if t == "E" else -q for _, t, q in movs) or 36
            res[cod] = {"produto": cod, "descricao": desc, "fornecedor": forn,
                        "nome_fornecedor": FORNECEDORES[forn], "avaria": float(saldo),
                        "disponivel": float(round(max(base, 2) * 12)), "custo": round(preco * 0.72, 2)}
        return res

    def movimentos_avaria(self, desde, produtos) -> list[dict]:
        return [{"produto": cod, "data": data, "quantidade": float(q), "tipo": t}
                for cod, (movs, _) in self._cenarios_avaria().items() if cod in produtos
                for data, t, q in movs if data >= desde]

    def aplicacoes_rebaixa(self, desde) -> list[dict]:
        return [{"fornecedor": PROD[cod][2], "data": data, "numero": num, "valor": 1500.0}
                for cod, (_, apls) in self._cenarios_avaria().items() for data, num in apls if data >= desde]
