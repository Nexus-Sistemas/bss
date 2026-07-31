"""
Agregações do painel da FUNERÁRIA — sempre Acionamento Funeral, global.

Série mensal (12 meses) de benefícios SOLICITADOS (por criado_em) e FINALIZADOS
(por data_finalizacao). A funerária é a operadora do benefício, então o recorte
é global (todas as empresas/sindicatos), só do tipo 'acionamento_funeral'.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .database import get_pg_connection

_TIPO = "acionamento_funeral"


def _ultimos_12_meses() -> list[str]:
    hoje = date.today()
    meses = []
    ano, mes = hoje.year, hoje.month
    for _ in range(12):
        meses.append(f"{ano:04d}-{mes:02d}")
        mes -= 1
        if mes == 0:
            mes = 12
            ano -= 1
    return list(reversed(meses))


def serie_mensal() -> list[dict[str, Any]]:
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT to_char(date_trunc('month', criado_em), 'YYYY-MM') AS mes,
                   COUNT(*) AS n
              FROM bss.v_processo
             WHERE tipo_beneficio_codigo = %s
               AND criado_em >= date_trunc('month', CURRENT_DATE) - INTERVAL '11 months'
             GROUP BY 1
            """,
            (_TIPO,),
        )
        solicitados = {r["mes"]: r["n"] for r in cur.fetchall()}

        cur.execute(
            """
            SELECT to_char(date_trunc('month', data_finalizacao), 'YYYY-MM') AS mes,
                   COUNT(*) AS n
              FROM bss.v_processo
             WHERE tipo_beneficio_codigo = %s
               AND data_finalizacao IS NOT NULL
               AND data_finalizacao >= date_trunc('month', CURRENT_DATE) - INTERVAL '11 months'
             GROUP BY 1
            """,
            (_TIPO,),
        )
        finalizados = {r["mes"]: r["n"] for r in cur.fetchall()}

    return [
        {"mes": m, "solicitados": solicitados.get(m, 0), "finalizados": finalizados.get(m, 0)}
        for m in _ultimos_12_meses()
    ]
