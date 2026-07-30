"""
Acesso a bss.modelo_email — os textos dos e-mails em massa.
"""

from __future__ import annotations

from typing import Any

from .database import get_pg_connection


def listar() -> list[dict[str, Any]]:
    """Todos os modelos, pra lista do editor. Ordena por categoria e nome."""
    sql = """
        SELECT id, codigo, nome, destinatario, categoria, ativo,
               (assunto <> '' OR corpo <> '') AS preenchido,
               atualizado_em
          FROM bss.modelo_email
         ORDER BY categoria NULLS LAST, nome
    """
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(sql)
        return list(cur.fetchall())


_COLS = """id, codigo, nome, destinatario, categoria, assunto, corpo, ativo,
           observacao, cadencia_tipo, cadencia_dias, cadencia_postergar_fds,
           atualizado_em"""


def buscar(id_modelo: int) -> dict[str, Any] | None:
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {_COLS} FROM bss.modelo_email WHERE id = %s", (id_modelo,))
        return cur.fetchone()


def listar_ativos_com_cadencia() -> list[dict[str, Any]]:
    """Modelos ATIVOS com cadência automática (pro agendador). Manual fica fora."""
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLS} FROM bss.modelo_email "
            "WHERE ativo AND cadencia_tipo <> 'manual' ORDER BY id"
        )
        return list(cur.fetchall())


def salvar(id_modelo: int, assunto: str, corpo: str, ativo: bool,
           observacao: str | None, atualizado_por_id: int,
           cadencia_tipo: str, cadencia_dias: list[int] | None,
           cadencia_postergar_fds: bool) -> dict[str, Any] | None:
    """
    Grava texto + cadência. NÃO deixa mexer em codigo nem destinatario: o codigo
    é a chave que o disparo procura, e o destinatario define as variáveis —
    mudá-los pela edição quebraria um gatilho ou tornaria variáveis órfãs.
    """
    sql = f"""
        UPDATE bss.modelo_email
           SET assunto = %s, corpo = %s, ativo = %s, observacao = %s,
               cadencia_tipo = %s, cadencia_dias = %s, cadencia_postergar_fds = %s,
               atualizado_por_id = %s, atualizado_em = NOW()
         WHERE id = %s
        RETURNING {_COLS}
    """
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, (assunto, corpo, ativo, observacao,
                          cadencia_tipo, cadencia_dias, cadencia_postergar_fds,
                          atualizado_por_id, id_modelo))
        row = cur.fetchone()
        conn.commit()
        return row
