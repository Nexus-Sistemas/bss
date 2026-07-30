"""
Acesso a bss.tarefa — o checklist de demandas da implantação.
"""

from __future__ import annotations

from typing import Any

from .database import get_pg_connection


_COLS = """
    t.id, t.prioridade, t.modulo, t.assunto, t.descricao, t.status,
    t.anexo_url, t.anexo_nome, t.criado_por_id, u.nome AS criado_por,
    t.criado_em, t.atualizado_em, t.resolvido_em
"""


def listar(status: str | None = None, modulo: str | None = None,
           prioridade: int | None = None, busca: str | None = None,
           incluir_encerradas: bool = False) -> list[dict[str, Any]]:
    where = ["1=1"]
    params: dict[str, Any] = {}
    if status:
        where.append("t.status = %(status)s")
        params["status"] = status
    elif not incluir_encerradas:
        # Por padrão esconde resolvidas/canceladas — foco no que está aberto.
        where.append("t.status NOT IN ('resolvida','cancelada')")
    if modulo:
        where.append("t.modulo = %(modulo)s")
        params["modulo"] = modulo
    if prioridade:
        where.append("t.prioridade = %(prio)s")
        params["prio"] = prioridade
    if busca:
        where.append("(t.assunto ILIKE %(b)s OR t.descricao ILIKE %(b)s)")
        params["b"] = f"%{busca}%"

    sql = f"""
        SELECT {_COLS}
          FROM bss.tarefa t
          LEFT JOIN bss_users u ON u.id = t.criado_por_id
         WHERE {" AND ".join(where)}
         ORDER BY
           CASE t.status WHEN 'aguardando' THEN 0 WHEN 'em_dev' THEN 1
                         WHEN 'aberta' THEN 2 ELSE 3 END,
           t.prioridade, t.id DESC
    """
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def modulos_usados() -> list[str]:
    """Módulos já cadastrados — pro datalist do formulário."""
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT DISTINCT modulo FROM bss.tarefa "
                    "WHERE modulo IS NOT NULL AND modulo <> '' ORDER BY modulo")
        return [r["modulo"] for r in cur.fetchall()]


def buscar(id_tarefa: int) -> dict[str, Any] | None:
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLS} FROM bss.tarefa t "
            "LEFT JOIN bss_users u ON u.id = t.criado_por_id WHERE t.id = %s",
            (id_tarefa,),
        )
        return cur.fetchone()


def criar(prioridade: int, modulo: str | None, assunto: str,
          descricao: str | None, status: str, criado_por_id: int) -> dict:
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bss.tarefa (prioridade, modulo, assunto, descricao, status, criado_por_id)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (prioridade, modulo, assunto, descricao, status, criado_por_id),
        )
        novo = cur.fetchone()["id"]
        conn.commit()
    return buscar(novo)


def atualizar(id_tarefa: int, prioridade: int, modulo: str | None,
              assunto: str, descricao: str | None, status: str) -> dict | None:
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE bss.tarefa SET
                prioridade = %s, modulo = %s, assunto = %s, descricao = %s,
                status = %s, atualizado_em = NOW(),
                -- carimba resolvido_em ao virar 'resolvida'; limpa se reabrir
                resolvido_em = CASE WHEN %s = 'resolvida' AND resolvido_em IS NULL
                                    THEN NOW()
                                    WHEN %s <> 'resolvida' THEN NULL
                                    ELSE resolvido_em END
             WHERE id = %s
            """,
            (prioridade, modulo, assunto, descricao, status, status, status, id_tarefa),
        )
        conn.commit()
    return buscar(id_tarefa)


def salvar_anexo(id_tarefa: int, anexo_url: str, anexo_nome: str) -> None:
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE bss.tarefa SET anexo_url = %s, anexo_nome = %s, atualizado_em = NOW() "
            "WHERE id = %s",
            (anexo_url, anexo_nome, id_tarefa),
        )
        conn.commit()
