"""
Endpoints de contato — os usuários externos que administram empresas.

GET /contatos                    → listagem com filtros
GET /contatos/pendentes/contagem → o sininho (fila de aprovação)
GET /contatos/pendentes          → a fila que o analista aprova
GET /contatos/{id}/detalhe       → cabeçalho do contato
GET /contatos/{id}/empresas      → os CNPJs que ele administra (o N:N)
GET /contatos/{id}/solicitacoes  → histórico de pedidos de acesso

Ver docs/AUTOCADASTRO.md.

PERMISSÃO: só staff interno. Contato é dado de gestão de acesso — cliente não
vê a lista de quem administra o quê.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .auth import UsuarioInfo, usuario_logado
from . import contato_repo


router = APIRouter(prefix="/contatos", tags=["contatos"])

PERFIS_INTERNOS = {"admin", "interno", "analista"}


def _exigir_interno(usuario: UsuarioInfo) -> None:
    if usuario.perfil not in PERFIS_INTERNOS:
        raise HTTPException(403, "Acesso restrito à equipe interna")


@router.get("")
def listar(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    busca: str | None = Query(None, description="Nome, e-mail ou CNPJ administrado"),
    ativo: bool | None = None,
    tipo_cadastro: str | None = Query(None, description="auto | interno"),
    id_empresa: int | None = None,
    perfil: str | None = Query(None, description="empresa | sindicato"),
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "nome",
    desc: bool = False,
):
    _exigir_interno(usuario)
    return contato_repo.listar(
        busca=busca, ativo=ativo, tipo_cadastro=tipo_cadastro,
        id_empresa=id_empresa, perfil=perfil, pagina=pagina, por_pagina=por_pagina,
        ordem=ordem, desc=desc,
    )


@router.get("/pendentes/contagem")
def contagem_pendentes(usuario: Annotated[UsuarioInfo, Depends(usuario_logado)]):
    """O sininho. Chamado a cada carga de página — por isso é só um COUNT."""
    _exigir_interno(usuario)
    return {"pendentes": contato_repo.contar_pendentes()}


@router.get("/pendentes")
def pendentes(usuario: Annotated[UsuarioInfo, Depends(usuario_logado)]):
    """
    A fila de aprovação. A view já traz o contexto pro analista decidir:
    quantos gestores o CNPJ já tem, e há quantos dias o pedido espera.
    """
    _exigir_interno(usuario)
    return contato_repo.listar_pendentes()


@router.get("/{id_contato}/detalhe")
def detalhe(
    id_contato: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    _exigir_interno(usuario)
    row = contato_repo.buscar_detalhe(id_contato)
    if not row:
        raise HTTPException(404, "Contato não encontrado")
    return row


class ContatoEditar(BaseModel):
    nome: str
    email: str
    telefone: str | None = None
    perfil: str                       # 'empresa' | 'sindicato'
    ativo: bool = True
    preferencias: dict | None = None  # {financeiro, beneficio, atualizacao, boleto}


@router.put("/{id_contato}")
def editar(
    id_contato: int,
    dados: ContatoEditar,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Edita o contato externo — inclusive o perfil (empresa↔sindicato)."""
    _exigir_interno(usuario)
    if not (dados.nome or "").strip():
        raise HTTPException(400, "Nome é obrigatório")
    if "@" not in (dados.email or "") or "." not in dados.email.split("@")[-1]:
        raise HTTPException(400, "E-mail inválido")
    if dados.perfil not in contato_repo.PERFIS_EXTERNOS:
        raise HTTPException(400, "Perfil deve ser empresa, sindicato ou funerária")
    if contato_repo.email_em_uso(dados.email.strip(), id_contato):
        raise HTTPException(409, "Já existe um usuário com esse e-mail")
    row = contato_repo.atualizar(
        id_contato, dados.nome.strip(), dados.email.strip(),
        (dados.telefone or "").strip() or None, dados.perfil, dados.ativo,
        dados.preferencias,
    )
    if not row:
        raise HTTPException(404, "Contato externo não encontrado")
    row["aviso"] = "Mudanças de perfil/vínculo só valem no próximo login do usuário."
    return row


@router.get("/{id_contato}/empresas")
def empresas(
    id_contato: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Os CNPJs que o contato administra — o N:N que o legado não mostra."""
    _exigir_interno(usuario)
    return contato_repo.listar_empresas(id_contato)


@router.get("/{id_contato}/solicitacoes")
def solicitacoes(
    id_contato: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    _exigir_interno(usuario)
    return contato_repo.listar_solicitacoes(id_contato)


# === Contato ↔ Sindicato (perfil sindicato) ================================

@router.get("/{id_contato}/sindicatos")
def sindicatos(
    id_contato: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Sindicatos que o contato administra (aba de relacionamento)."""
    _exigir_interno(usuario)
    return contato_repo.listar_sindicatos(id_contato)


class PerfilIn(BaseModel):
    perfil: str   # 'empresa' | 'sindicato'


@router.put("/{id_contato}/perfil")
def definir_perfil(
    id_contato: int,
    dados: PerfilIn,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Alterna o contato entre empresa e sindicato. (Não mexe em perfil interno.)"""
    _exigir_interno(usuario)
    if dados.perfil not in ("empresa", "sindicato"):
        raise HTTPException(400, "Perfil deve ser 'empresa' ou 'sindicato'")
    if not contato_repo.definir_perfil(id_contato, dados.perfil):
        raise HTTPException(404, "Contato externo não encontrado")
    return {"ok": True, "perfil": dados.perfil,
            "aviso": "O usuário precisa fazer login de novo para o novo perfil valer."}


class SindicatoIn(BaseModel):
    id_sindicato: int


@router.post("/{id_contato}/sindicatos")
def vincular_sindicato(
    id_contato: int,
    dados: SindicatoIn,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    _exigir_interno(usuario)
    contato_repo.vincular_sindicato(id_contato, dados.id_sindicato)
    return {"ok": True}


@router.delete("/{id_contato}/sindicatos/{id_sindicato}")
def desvincular_sindicato(
    id_contato: int,
    id_sindicato: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    _exigir_interno(usuario)
    contato_repo.desvincular_sindicato(id_contato, id_sindicato)
    return {"ok": True}
