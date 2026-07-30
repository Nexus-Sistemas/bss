"""
Converte para INTERNO (inativos) os 7 e-mails da equipe BSS que estavam como
perfil 'empresa' (autocadastro de teste). Corrige nome/departamento/cargo e
DESLIGA os vínculos de empresa (interno não opera por empresa; enxerga tudo).

Decidido com o Mauro (30/07/2026): converter, inativos, sem vínculo de empresa.
A pessoa é ativada depois pela tela de Usuários e define a senha pelo
"Esqueci minha senha".

Idempotente: são UPDATEs por e-mail; rodar de novo não causa dano.

Rodar (backend/, na OCI):
    venv/bin/python -m scripts.converter_usuarios_internos
"""

from app.database import get_pg_connection


# email → (nome, departamento, cargo)
ALVOS = {
    "allan@bssindical.com.br":    ("Allan Renan Di Nardi Almeida", "Administrativo", "Assistente Administrativo"),
    "camilly@bssindical.com.br":  ("Camilly Santos Pinto",         "Administrativo", "Analista Administrativo"),
    "fernanda@bssindical.com.br": ("Fernanda Rocha Souza",         "Administrativo", "Assistente Administrativo"),
    "gabriel@bssindical.com.br":  ("Gabriel Fontana de Matos",     "Financeiro",     "Analista Financeiro"),
    "joao@bssindical.com.br":     ("João Victor Diniz Nery Oliveira", "Administrativo", "Analista Administrativo"),
    "larissa@bssindical.com.br":  ("Larissa Santos",               "Administrativo", "Líder Administrativo"),
    "wanessa@bssindical.com.br":  ("Wanessa Freitas Silva Aragão", "Financeiro",     "Supervisor Financeiro"),
}


def main() -> None:
    with get_pg_connection() as conn, conn.cursor() as cur:
        for email, (nome, depto, cargo) in ALVOS.items():
            cur.execute(
                "SELECT id, perfil, ativo FROM bss_users WHERE LOWER(email) = LOWER(%s)",
                (email,),
            )
            u = cur.fetchone()
            if not u:
                print(f"  ! não encontrado: {email}")
                continue

            # Desliga vínculos de empresa (deixa histórico, só marca inativo).
            cur.execute(
                "UPDATE bss.usuario_empresa SET ativo = FALSE "
                "WHERE id_usuario = %s AND ativo",
                (u["id"],),
            )
            vinc = cur.rowcount

            cur.execute(
                """
                UPDATE bss_users
                   SET perfil = 'interno', ativo = FALSE,
                       nome = %s, departamento = %s, cargo = %s
                 WHERE id = %s
                """,
                (nome, depto, cargo, u["id"]),
            )
            print(f"  ✓ {email:<32} id={u['id']} "
                  f"(era perfil={u['perfil']}/ativo={u['ativo']}) "
                  f"→ interno/inativo, {vinc} vínculo(s) de empresa desligado(s)")
        conn.commit()
    print("\nFeito.")


if __name__ == "__main__":
    main()
