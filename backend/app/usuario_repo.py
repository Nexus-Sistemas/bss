"""
Gestão de usuários INTERNOS (equipe da BSS) + tokens de redefinição de senha.

Escopo de propósito enxuto: por ora todos os internos têm as mesmas funções,
então a tela cuida de nome/departamento/cargo/e-mail/ativo — sem granular
perfil. Usuários externos (empresa/sindicato/contabilidade) NÃO aparecem aqui;
esses são geridos em Contatos.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from .database import get_pg_connection

# Espelha auth.PERFIS_INTERNOS — os que esta tela administra.
PERFIS_INTERNOS = ("admin", "interno", "analista")

_COLS = """
    id, nome, email, departamento, cargo, perfil, ativo,
    ultimo_login, criado_em
"""


# === Usuários ===============================================================

def listar_internos(busca: str | None = None,
                    incluir_inativos: bool = True) -> list[dict[str, Any]]:
    where = ["perfil = ANY(%(perfis)s)"]
    params: dict[str, Any] = {"perfis": list(PERFIS_INTERNOS)}
    if busca:
        where.append("(nome ILIKE %(b)s OR email ILIKE %(b)s "
                     "OR departamento ILIKE %(b)s OR cargo ILIKE %(b)s)")
        params["b"] = f"%{busca}%"
    if not incluir_inativos:
        where.append("ativo")
    sql = f"SELECT {_COLS} FROM bss_users WHERE {' AND '.join(where)} " \
          f"ORDER BY ativo DESC, nome"
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def buscar(id_usuario: int) -> dict[str, Any] | None:
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {_COLS} FROM bss_users WHERE id = %s", (id_usuario,))
        return cur.fetchone()


def email_em_uso(email: str, excluir_id: int | None = None) -> bool:
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM bss_users WHERE LOWER(email) = LOWER(%s) "
            "AND (%s::int IS NULL OR id <> %s::int)",
            (email, excluir_id, excluir_id),
        )
        return cur.fetchone() is not None


def criar(nome: str, email: str, senha_hash: str, departamento: str | None,
          cargo: str | None, perfil: str = "interno", ativo: bool = True) -> dict:
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bss_users (nome, email, senha_hash, departamento, cargo, perfil, ativo)
            VALUES (%s, LOWER(%s), %s, %s, %s, %s, %s) RETURNING id
            """,
            (nome, email, senha_hash, departamento, cargo, perfil, ativo),
        )
        novo = cur.fetchone()["id"]
        conn.commit()
    return buscar(novo)


def atualizar(id_usuario: int, nome: str, email: str, departamento: str | None,
              cargo: str | None, ativo: bool) -> dict | None:
    """Edita os dados básicos. NÃO mexe em perfil nem senha de propósito."""
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE bss_users SET
                nome = %s, email = LOWER(%s), departamento = %s, cargo = %s, ativo = %s
             WHERE id = %s AND perfil = ANY(%s)
            """,
            (nome, email, departamento, cargo, ativo, id_usuario, list(PERFIS_INTERNOS)),
        )
        conn.commit()
    return buscar(id_usuario)


def definir_senha(id_usuario: int, senha_hash: str) -> None:
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE bss_users SET senha_hash = %s WHERE id = %s",
                    (senha_hash, id_usuario))
        conn.commit()


# === Reset de senha (self-service) =========================================

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def buscar_usuario_ativo_por_email(email: str) -> dict[str, Any] | None:
    """Qualquer usuário ativo (interno OU externo) — o login é geral."""
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, nome, email FROM bss_users "
            "WHERE LOWER(email) = LOWER(%s) AND ativo",
            (email,),
        )
        return cur.fetchone()


def criar_token_reset(id_usuario: int, validade_horas: int = 1) -> str:
    """
    Gera um token, guarda só o hash e devolve o token em CLARO (vai no e-mail).
    Invalida tokens anteriores não usados do mesmo usuário (um link por vez).
    """
    token = secrets.token_urlsafe(32)
    expira = datetime.now(timezone.utc) + timedelta(hours=validade_horas)
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE bss.reset_senha SET usado_em = NOW() "
            "WHERE id_usuario = %s AND usado_em IS NULL",
            (id_usuario,),
        )
        cur.execute(
            "INSERT INTO bss.reset_senha (id_usuario, token_hash, expira_em) "
            "VALUES (%s, %s, %s)",
            (id_usuario, _hash_token(token), expira),
        )
        conn.commit()
    return token


def consumir_token_reset(token: str) -> int | None:
    """
    Valida o token (existe, não usado, não expirado) e o MARCA como usado.
    Retorna o id_usuario, ou None se inválido. Uso único e atômico.
    """
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE bss.reset_senha
               SET usado_em = NOW()
             WHERE token_hash = %s
               AND usado_em IS NULL
               AND expira_em > NOW()
            RETURNING id_usuario
            """,
            (_hash_token(token),),
        )
        row = cur.fetchone()
        conn.commit()
    return row["id_usuario"] if row else None
