"""
Prepara um usuário SINDICATO de teste — pra validar o escopo do portal do
sindicato antes da tela de gestão contato↔sindicato ficar pronta.

Uso (backend/, na OCI):

  # 1) ver os sindicatos com mais trabalhadores (pra escolher os ids):
  venv/bin/python -m scripts.vincular_sindicato_teste --listar

  # 2) transformar um contato em sindicato e vincular sindicatos:
  venv/bin/python -m scripts.vincular_sindicato_teste \
      --email fulano@empresa.com --sindicatos 12,45

O usuário passa a perfil='sindicato', ativo=TRUE, e ganha as linhas em
bss.usuario_sindicato. Idempotente. LEMBRE: o JWT é cache — a pessoa precisa
FAZER LOGIN DE NOVO pra o escopo novo valer.
"""

from __future__ import annotations

import argparse

from app.database import get_pg_connection


def listar_sindicatos() -> None:
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, razao_social, qtd_trabalhadores_ativos
              FROM bss.sindicato
             WHERE ativo
             ORDER BY qtd_trabalhadores_ativos DESC NULLS LAST
             LIMIT 40
            """
        )
        print(f"{'id':>6}  {'ativos':>8}  razão social")
        print("-" * 70)
        for r in cur.fetchall():
            print(f"{r['id']:>6}  {(r['qtd_trabalhadores_ativos'] or 0):>8}  {r['razao_social']}")


def vincular(email: str, ids: list[int]) -> None:
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, nome, perfil, ativo FROM bss_users WHERE LOWER(email)=LOWER(%s)", (email,))
        u = cur.fetchone()
        if not u:
            print(f"! usuário não encontrado: {email}")
            return

        cur.execute("UPDATE bss_users SET perfil='sindicato', ativo=TRUE WHERE id=%s", (u["id"],))
        for sid in ids:
            cur.execute(
                "INSERT INTO bss.usuario_sindicato (id_usuario, id_sindicato, ativo) "
                "VALUES (%s, %s, TRUE) ON CONFLICT (id_usuario, id_sindicato) "
                "DO UPDATE SET ativo=TRUE",
                (u["id"], sid),
            )
        conn.commit()
        print(f"✓ {u['nome']} <{email}> agora é perfil='sindicato' (ativo) "
              f"com sindicatos {ids}.")
        print("  ATENÇÃO: precisa fazer LOGIN DE NOVO pro escopo valer (JWT é cache).")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listar", action="store_true", help="lista sindicatos (id, ativos)")
    ap.add_argument("--email", help="e-mail do contato a virar sindicato")
    ap.add_argument("--sindicatos", help="ids separados por vírgula, ex.: 12,45")
    args = ap.parse_args()

    if args.listar:
        listar_sindicatos()
        return
    if args.email and args.sindicatos:
        ids = [int(x) for x in args.sindicatos.split(",") if x.strip()]
        vincular(args.email, ids)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
