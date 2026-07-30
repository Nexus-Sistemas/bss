"""
/usuarios — gestão básica da equipe interna da BSS. RESTRITO a internos.

Por ora todos os internos têm as mesmas funções, então esta tela NÃO edita
perfil: cuida de nome/departamento/cargo/e-mail/ativo. Novos usuários nascem
com perfil 'interno' e uma senha inicial (que a pessoa troca no login).

Senha é assunto do login ("esqueci minha senha" self-service, em auth). Aqui
só há senha na CRIAÇÃO — depois disso, ninguém "vê" nem redefine por esta tela.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import UsuarioInfo, exigir_interno, hash_senha
from . import usuario_repo


router = APIRouter(prefix="/usuarios", tags=["usuarios"])

_SENHA_MIN = 6


@router.get("")
def listar(
    usuario: Annotated[UsuarioInfo, Depends(exigir_interno)],
    busca: str | None = None,
):
    return usuario_repo.listar_internos(busca)


class UsuarioCriar(BaseModel):
    nome: str
    email: str
    departamento: str | None = None
    cargo: str | None = None
    senha: str
    ativo: bool = True


class UsuarioEditar(BaseModel):
    nome: str
    email: str
    departamento: str | None = None
    cargo: str | None = None
    ativo: bool = True


def _valida_comum(nome: str, email: str) -> None:
    if not (nome or "").strip():
        raise HTTPException(400, "Nome é obrigatório")
    if "@" not in (email or "") or "." not in email.split("@")[-1]:
        raise HTTPException(400, "E-mail inválido")


@router.post("", status_code=201)
def criar(
    dados: UsuarioCriar,
    usuario: Annotated[UsuarioInfo, Depends(exigir_interno)],
):
    _valida_comum(dados.nome, dados.email)
    if len(dados.senha or "") < _SENHA_MIN:
        raise HTTPException(400, f"Senha deve ter ao menos {_SENHA_MIN} caracteres")
    if usuario_repo.email_em_uso(dados.email):
        raise HTTPException(409, "Já existe um usuário com esse e-mail")
    return usuario_repo.criar(
        dados.nome.strip(), dados.email.strip(), hash_senha(dados.senha),
        (dados.departamento or "").strip() or None,
        (dados.cargo or "").strip() or None,
        perfil="interno", ativo=dados.ativo,
    )


@router.put("/{id_usuario}")
def editar(
    id_usuario: int,
    dados: UsuarioEditar,
    usuario: Annotated[UsuarioInfo, Depends(exigir_interno)],
):
    _valida_comum(dados.nome, dados.email)
    alvo = usuario_repo.buscar(id_usuario)
    if not alvo or alvo["perfil"] not in usuario_repo.PERFIS_INTERNOS:
        raise HTTPException(404, "Usuário interno não encontrado")
    if usuario_repo.email_em_uso(dados.email, excluir_id=id_usuario):
        raise HTTPException(409, "Já existe um usuário com esse e-mail")
    # Guarda-chuva: não deixa o usuário se auto-desativar e se trancar pra fora.
    if id_usuario == usuario.id and not dados.ativo:
        raise HTTPException(400, "Você não pode desativar a própria conta")
    return usuario_repo.atualizar(
        id_usuario, dados.nome.strip(), dados.email.strip(),
        (dados.departamento or "").strip() or None,
        (dados.cargo or "").strip() or None, dados.ativo,
    )
