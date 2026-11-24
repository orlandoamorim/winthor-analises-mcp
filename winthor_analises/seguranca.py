"""Garantias de somente leitura.

Camadas (da mais forte para a mais fraca):
1. Usuário do Oracle só com SELECT (pedido à TI) – conferido ao conectar.
2. Cada consulta roda dentro de `SET TRANSACTION READ ONLY` e termina em
   ROLLBACK; o Oracle recusa qualquer escrita nessa transação.
3. Todo SQL passa por `exigir_select` antes de ir ao banco.
4. Não existe ferramenta de "SQL livre": as consultas são montadas aqui.
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

PROIBIDAS = {
    "INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT", "DROP", "ALTER", "CREATE",
    "TRUNCATE", "GRANT", "REVOKE", "EXECUTE", "EXEC", "BEGIN", "DECLARE", "CALL",
    "LOCK", "COMMIT", "ROLLBACK", "SAVEPOINT", "RENAME", "COMMENT", "PURGE",
    "FLASHBACK", "AUDIT", "NOAUDIT", "ANALYZE", "SHUTDOWN", "INTO",
}
PREFIXOS_PROIBIDOS = ("DBMS_", "UTL_", "SYS.")


class ConsultaRecusada(PermissionError):
    pass


def _sem_literais(sql: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def exigir_select(sql: str) -> str:
    """Devolve o SQL se for uma única consulta de leitura; senão levanta erro."""
    limpo = _sem_literais(sql)
    if ";" in limpo or "--" in limpo or "/*" in limpo:
        raise ConsultaRecusada("SQL com ';' ou comentários não é aceito")
    palavras = re.findall(r"[A-Za-z_][A-Za-z0-9_$#.]*", limpo)
    if not palavras or palavras[0].upper() not in ("SELECT", "WITH"):
        raise ConsultaRecusada("só consultas SELECT são permitidas")
    for p in palavras:
        up = p.upper()
        if up in PROIBIDAS or up.startswith(PREFIXOS_PROIBIDOS):
            raise ConsultaRecusada(f"palavra não permitida em consulta de leitura: {p}")
    if re.search(r"\bFOR\s+UPDATE\b", limpo, re.IGNORECASE):
        raise ConsultaRecusada("SELECT ... FOR UPDATE não é permitido")
    return sql


def horario_comercial(cfg, agora: datetime | None = None) -> bool:
    agora = agora or datetime.now(ZoneInfo(cfg.fuso))
    if agora.weekday() >= 5:  # sábado e domingo: liberado
        return False
    return cfg.hora_inicio_comercial <= agora.hour < cfg.hora_fim_comercial


def exigir_fora_do_horario(cfg, dias: int, agora: datetime | None = None) -> None:
    """Bloqueia consultas pesadas no horário comercial (só no modo oracle).

    `dias` é o total de dias de movimento que a consulta vai varrer.
    """
    if cfg.modo != "oracle" or dias <= cfg.dias_max_horario_comercial:
        return
    if cfg.banco == "replica" and not cfg.horario_vale_na_replica:
        return
    if horario_comercial(cfg, agora):
        raise ConsultaRecusada(
            f"Essa consulta varre {dias} dias de movimento e é pesada para o banco. "
            f"Pela regra da empresa, consultas pesadas só depois das {cfg.hora_fim_comercial}h "
            f"(ou no fim de semana). Agora dá para pedir até {cfg.dias_max_horario_comercial} "
            f"dias no total, por exemplo menos anos ou um período menor."
        )
