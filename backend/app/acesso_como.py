"""
Auditoria do "Acessar como" — grava em bss.acesso_como.

Nunca derruba a operação: se o registro falhar, loga e segue. Auditoria é
obrigatória pro rastro, mas não pode ser o motivo de uma ação do usuário
quebrar. (O rastro também vai pro log da aplicação, via logger.)
"""

from __future__ import annotations

import logging

from .database import get_pg_connection

log = logging.getLogger("bss.acesso_como")


def registrar(evento: str, id_interno: int, nome_interno: str | None,
              email_interno: str | None, id_alvo: int, nome_alvo: str | None,
              email_alvo: str | None, metodo: str | None = None,
              caminho: str | None = None) -> None:
    # Log da aplicação primeiro — sempre sai, mesmo se o banco recusar.
    if evento == "inicio":
        log.warning("ACESSAR-COMO início: interno #%s (%s) acessando como #%s (%s)",
                    id_interno, email_interno, id_alvo, email_alvo)
    else:
        log.warning("ACESSAR-COMO ação: interno #%s (%s) executou %s %s como #%s (%s)",
                    id_interno, email_interno, metodo, caminho, id_alvo, email_alvo)
    try:
        with get_pg_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bss.acesso_como
                    (evento, id_interno, nome_interno, email_interno,
                     id_alvo, nome_alvo, email_alvo, metodo, caminho)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (evento, id_interno, nome_interno, email_interno,
                 id_alvo, nome_alvo, email_alvo, metodo, caminho),
            )
            conn.commit()
    except Exception as e:
        log.warning("falha ao gravar auditoria acessar-como: %s", e)
