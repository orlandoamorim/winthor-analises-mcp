"""Datas comemorativas do varejo e utilitários de período."""

from __future__ import annotations

from datetime import date, timedelta


def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


def _n_esimo_dia_semana(ano: int, mes: int, dia_semana: int, n: int) -> date:
    """n-ésimo dia da semana do mês (segunda=0 ... domingo=6)."""
    d = date(ano, mes, 1)
    d += timedelta(days=(dia_semana - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


DATAS: dict[str, tuple[str, callable]] = {
    "carnaval": ("Carnaval (terça)", lambda a: pascoa(a) - timedelta(days=47)),
    "pascoa": ("Páscoa", pascoa),
    "maes": ("Dia das Mães", lambda a: _n_esimo_dia_semana(a, 5, 6, 2)),
    "namorados": ("Dia dos Namorados", lambda a: date(a, 6, 12)),
    "sao_joao": ("São João", lambda a: date(a, 6, 24)),
    "pais": ("Dia dos Pais", lambda a: _n_esimo_dia_semana(a, 8, 6, 2)),
    "criancas": ("Dia das Crianças", lambda a: date(a, 10, 12)),
    "black_friday": ("Black Friday", lambda a: _n_esimo_dia_semana(a, 11, 3, 4) + timedelta(days=1)),
    "natal": ("Natal", lambda a: date(a, 12, 25)),
    "ano_novo": ("Réveillon", lambda a: date(a, 12, 31)),
}


def data_comemorativa(chave: str, ano: int) -> date:
    """Data da comemoração no ano. Aceita as chaves de DATAS ou 'MM-DD'."""
    chave = chave.strip().lower()
    if chave in DATAS:
        return DATAS[chave][1](ano)
    try:
        mes, dia = (int(x) for x in chave.split("-"))
        return date(ano, mes, dia)
    except ValueError:
        opcoes = ", ".join(DATAS)
        raise ValueError(f"Data comemorativa desconhecida: {chave!r}. Use uma de: {opcoes}, ou 'MM-DD'.")


def nome_data(chave: str) -> str:
    return DATAS.get(chave.lower(), (f"Data {chave}",))[0]


def mesmo_periodo(inicio: date, fim: date, anos_atras: int) -> tuple[date, date]:
    """Mesmo período N anos antes (29/02 vira 28/02)."""
    def recua(d: date) -> date:
        try:
            return d.replace(year=d.year - anos_atras)
        except ValueError:
            return d.replace(year=d.year - anos_atras, day=28)
    return recua(inicio), recua(fim)


def ler_data(texto: str) -> date:
    """Aceita AAAA-MM-DD ou DD/MM/AAAA."""
    texto = texto.strip()
    if "/" in texto:
        d, m, a = (int(x) for x in texto.split("/"))
        return date(a, m, d)
    return date.fromisoformat(texto)
