"""
Carga inicial da equipe interna da BSS — todos INATIVOS.

Idempotente: se o e-mail já existir, pula (não duplica, não sobrescreve).
Cada usuário nasce com uma senha aleatória inutilizável — como estão inativos,
não logam; quando forem ativados, definem a senha pelo "Esqueci minha senha".

Rodar (do diretório backend/, na OCI):
    venv/bin/python -m scripts.inserir_usuarios_iniciais

Conflitos de e-mail resolvidos com o Mauro (30/07/2026):
  - Milena Guerra Galhardo → milena@ (a lista trazia larissa@, duplicado).
  - Hanna Luar e Nicolly Gomes → FORA por ora (ambos com offline@, sem e-mail
    próprio). Inserir quando tiverem e-mail individual.
"""

import secrets

from app import usuario_repo
from app.auth import hash_senha


# (nome, departamento, cargo, email)
USUARIOS = [
    ("Allan Renan Di Nardi Almeida",     "Administrativo", "Assistente Administrativo", "allan@bssindical.com.br"),
    ("Camilly Santos Pinto",             "Administrativo", "Analista Administrativo",   "camilly@bssindical.com.br"),
    ("Fernanda Rocha Souza",             "Administrativo", "Assistente Administrativo", "fernanda@bssindical.com.br"),
    ("Gabriel Fontana de Matos",         "Financeiro",     "Analista Financeiro",       "gabriel@bssindical.com.br"),
    ("João Victor Diniz Nery Oliveira",  "Administrativo", "Analista Administrativo",   "joao@bssindical.com.br"),
    ("Larissa Santos",                   "Administrativo", "Líder Administrativo",      "larissa@bssindical.com.br"),
    ("Milena Guerra Galhardo",           "Administrativo", "Analista Administrativo",   "milena@bssindical.com.br"),
    ("Moisés de Moura Greco",            "Administrativo", "Gerente",                   "moises@bssindical.com.br"),
    ("Thayná de Oliveira Costa",         "Financeiro",     "Assistente Financeiro",     "thayna241205@bssindical.com.br"),
    ("Wanessa Freitas Silva Aragão",     "Financeiro",     "Supervisor Financeiro",     "wanessa@bssindical.com.br"),
]


def main() -> None:
    criados, pulados = 0, 0
    for nome, depto, cargo, email in USUARIOS:
        if usuario_repo.email_em_uso(email):
            print(f"  = já existe, pulando: {email}")
            pulados += 1
            continue
        usuario_repo.criar(
            nome=nome, email=email,
            senha_hash=hash_senha(secrets.token_urlsafe(24)),
            departamento=depto, cargo=cargo,
            perfil="interno", ativo=False,
        )
        print(f"  + criado (inativo): {nome} <{email}>")
        criados += 1
    print(f"\nFeito. {criados} criado(s), {pulados} já existiam.")


if __name__ == "__main__":
    main()
