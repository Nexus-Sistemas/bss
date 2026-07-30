"""
Agregações do painel do SINDICATO — tudo escopado aos sindicatos do usuário.

Uma função só (`resumo`) roda as consultas e devolve o JSON que o
dashboard-sindicato.html desenha. Escopo = ids_sindicato (conjunto do usuário);
o router resolve isso a partir do JWT e do seletor.
"""

from __future__ import annotations

from typing import Any

from .database import get_pg_connection


def resumo(ids_sindicato: list[int]) -> dict[str, Any]:
    if not ids_sindicato:
        return {"trab_ativos": 0, "empresas": 0, "trab_por_sindicato": [],
                "trab_por_empresa": [], "boletos_mes": [], "beneficios_categoria": []}

    ids = list(ids_sindicato)
    with get_pg_connection() as conn, conn.cursor() as cur:
        # Trabalhadores ativos (número grande)
        cur.execute(
            "SELECT COUNT(*) AS n FROM bss.v_trabalhador "
            "WHERE situacao='ativo' AND id_sindicato_atual = ANY(%s)", (ids,))
        trab_ativos = cur.fetchone()["n"]

        # Empresas contribuintes (com trabalhador ativo nos sindicatos)
        cur.execute(
            "SELECT COUNT(DISTINCT id_empresa) AS n FROM bss.empresa_sindicato_ativo "
            "WHERE id_sindicato = ANY(%s)", (ids,))
        empresas = cur.fetchone()["n"]

        # Trabalhador × Sindicato
        cur.execute(
            "SELECT sindicato, COUNT(*) AS ativos FROM bss.v_trabalhador "
            "WHERE situacao='ativo' AND id_sindicato_atual = ANY(%s) "
            "GROUP BY sindicato ORDER BY ativos DESC", (ids,))
        trab_por_sindicato = [dict(r) for r in cur.fetchall()]

        # Trabalhadores por Empresa (top 15)
        cur.execute(
            "SELECT empresa, COUNT(*) AS ativos FROM bss.v_trabalhador "
            "WHERE situacao='ativo' AND id_sindicato_atual = ANY(%s) "
            "GROUP BY empresa ORDER BY ativos DESC LIMIT 15", (ids,))
        trab_por_empresa = [dict(r) for r in cur.fetchall()]

        # Boletos do mês corrente por status (rosca)
        cur.execute(
            "SELECT status, COUNT(*) AS qtd, COALESCE(SUM(valor_total),0) AS valor "
            "FROM bss.v_boleto "
            "WHERE id_sindicato = ANY(%s) "
            "  AND mes_referencia = date_trunc('month', CURRENT_DATE)::date "
            "GROUP BY status ORDER BY valor DESC", (ids,))
        boletos_mes = [dict(r) for r in cur.fetchall()]

        # Benefícios por categoria de status (pendências)
        cur.execute(
            "SELECT COALESCE(status_categoria,'—') AS categoria, COUNT(*) AS qtd "
            "FROM bss.v_processo WHERE id_sindicato = ANY(%s) "
            "GROUP BY status_categoria ORDER BY qtd DESC", (ids,))
        beneficios_categoria = [dict(r) for r in cur.fetchall()]

    return {
        "trab_ativos": trab_ativos,
        "empresas": empresas,
        "trab_por_sindicato": trab_por_sindicato,
        "trab_por_empresa": trab_por_empresa,
        "boletos_mes": boletos_mes,
        "beneficios_categoria": beneficios_categoria,
    }
