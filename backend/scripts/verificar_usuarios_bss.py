"""
Diagnóstico: mostra o estado atual dos usuários @bssindical.com.br.

Por que existe: a carga inicial (inserir_usuarios_iniciais) pulou vários e-mails
com "já existe", e eles não aparecem na tela de Usuários. Suspeita: já estavam
no banco com perfil != interno (autocadastro nasce perfil='empresa', inativo).
Este script confirma qual é o perfil/ativo de cada um.

Rodar (backend/, na OCI):
    venv/bin/python -m scripts.verificar_usuarios_bss
"""

from app.database import get_pg_connection


def main() -> None:
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, nome, email, perfil, ativo, departamento, cargo
              FROM bss_users
             WHERE email ILIKE '%@bssindical.com.br'
             ORDER BY perfil, email
            """
        )
        linhas = cur.fetchall()

    print(f"{len(linhas)} usuário(s) @bssindical.com.br:\n")
    print(f"{'id':>4}  {'perfil':<14} {'ativo':<6} {'email':<38} nome")
    print("-" * 100)
    for r in linhas:
        print(f"{r['id']:>4}  {r['perfil']:<14} {str(r['ativo']):<6} "
              f"{r['email']:<38} {r['nome']}")


if __name__ == "__main__":
    main()
