from datetime import date

from winthor_analises.datas import data_comemorativa, mesmo_periodo, pascoa


def test_datas_moveis():
    assert pascoa(2025) == date(2025, 4, 20)
    assert pascoa(2026) == date(2026, 4, 5)
    assert data_comemorativa("maes", 2025) == date(2025, 5, 11)
    assert data_comemorativa("pais", 2025) == date(2025, 8, 10)
    assert data_comemorativa("black_friday", 2025) == date(2025, 11, 28)
    assert data_comemorativa("carnaval", 2026) == date(2026, 2, 17)
    assert data_comemorativa("09-07", 2026) == date(2026, 9, 7)


def test_ano_bissexto():
    assert mesmo_periodo(date(2024, 2, 1), date(2024, 2, 29), 1) == (date(2023, 2, 1), date(2023, 2, 28))
