"""GET /empresas — listagem com filtros."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .auth import UsuarioInfo, usuario_logado
from . import empresa_repo


router = APIRouter(prefix="/empresas", tags=["empresas"])


_PERFIS_INTERNOS = ("admin", "interno", "analista")


def _exigir_empresa_no_escopo(usuario: UsuarioInfo, id_empresa: int) -> None:
    """RLS de detalhe: empresa vê as suas; sindicato vê as que têm trabalhador
    ativo nos seus sindicatos; internos veem tudo; outros perfis (ex.: funerária)
    são barrados por padrão."""
    if usuario.perfil in _PERFIS_INTERNOS:
        return
    if usuario.perfil == "empresa":
        if id_empresa not in usuario.empresas:
            raise HTTPException(403, "Empresa fora do escopo")
    elif usuario.perfil == "sindicato":
        if not empresa_repo.empresa_no_escopo_sindicato(id_empresa, usuario.sindicatos):
            raise HTTPException(403, "Empresa fora do escopo")
    else:
        raise HTTPException(403, "Acesso restrito")


@router.get("")
def listar(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    busca: str | None = None,
    status: str | None = None,
    adimplencia: str | None = None,
    regularidade: str | None = None,
    uf: str | None = Query(None, max_length=2),
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "razao_social",
    desc: bool = False,
):
    # Escopo: perfil 'empresa' só enxerga as empresas vinculadas a ele
    # (bss.usuario_empresa, carregado no JWT). O filtro vai pro SQL via
    # `ids` — NÃO filtrar o resultado depois de paginar (ver docstring do
    # empresa_repo.listar: era assim, e escondia 10 das 11 empresas do
    # usuário atrás de 105 páginas).
    ids: list[int] | None = None
    ids_sindicato: list[int] | None = None
    if usuario.perfil == "empresa":
        if not usuario.empresas:
            # Sem vínculo não há o que mostrar. Devolve vazio coerente em vez
            # de ids=[] (que geraria SQL válido mas semanticamente confuso).
            return {"linhas": [], "total": 0, "pagina": 1,
                    "por_pagina": por_pagina, "paginas": 0}
        ids = usuario.empresas
    elif usuario.perfil == "sindicato":
        # Sindicato só vê empresas com trabalhador ativo nos seus sindicatos.
        if not usuario.sindicatos:
            return {"linhas": [], "total": 0, "pagina": 1,
                    "por_pagina": por_pagina, "paginas": 0}
        ids_sindicato = usuario.sindicatos
    elif usuario.perfil not in ("admin", "interno", "analista"):
        # Perfil externo sem escopo nesta lista (ex.: funeraria): default-deny.
        return {"linhas": [], "total": 0, "pagina": 1,
                "por_pagina": por_pagina, "paginas": 0}

    return empresa_repo.listar(
        busca=busca, status=status, adimplencia=adimplencia,
        regularidade=regularidade, uf=uf, ids=ids, ids_sindicato=ids_sindicato,
        pagina=pagina, por_pagina=por_pagina, ordem=ordem, desc=desc,
    )


@router.get("/{id_empresa}/detalhe")
def detalhe_completo(
    id_empresa: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Detalhe completo da empresa (endereço + caches + datas)."""
    _exigir_empresa_no_escopo(usuario, id_empresa)
    row = empresa_repo.buscar_detalhe(id_empresa)
    if not row:
        raise HTTPException(404, "Empresa não encontrada")
    return row


class EmpresaEditar(BaseModel):
    razao_social: str
    nome_fantasia: str | None = None
    cnpj: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None
    cep: str | None = None
    telefone: str | None = None
    status: str | None = None


@router.put("/{id_empresa}")
def editar(
    id_empresa: int,
    dados: EmpresaEditar,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Edita o cadastro da empresa. Interno ou sindicato no escopo."""
    if usuario.perfil in _PERFIS_INTERNOS:
        pass
    elif usuario.perfil == "sindicato":
        if not empresa_repo.empresa_no_escopo_sindicato(id_empresa, usuario.sindicatos):
            raise HTTPException(403, "Empresa fora do escopo")
    else:
        raise HTTPException(403, "Sem permissão para editar empresa")

    if not (dados.razao_social or "").strip():
        raise HTTPException(400, "Razão social é obrigatória")
    if not empresa_repo.buscar_por_id(id_empresa):
        raise HTTPException(404, "Empresa não encontrada")

    campos = dados.model_dump()
    campos["razao_social"] = dados.razao_social.strip()
    if campos.get("cnpj"):
        campos["cnpj"] = "".join(c for c in campos["cnpj"] if c.isdigit())
    if campos.get("uf"):
        campos["uf"] = campos["uf"].strip().upper()[:2]
    row = empresa_repo.atualizar(id_empresa, campos)
    row["aviso"] = "Campos enviados pela sync podem ser sobrescritos no próximo ciclo."
    return row


@router.get("/{id_empresa}/usuarios")
def usuarios(
    id_empresa: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Usuários com acesso à empresa (aba de relacionamento)."""
    _exigir_empresa_no_escopo(usuario, id_empresa)
    return empresa_repo.listar_usuarios(id_empresa)


@router.get("/{id_empresa}")
def detalhe(
    id_empresa: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    row = empresa_repo.buscar_por_id(id_empresa)
    if not row:
        raise HTTPException(404, "Empresa não encontrada")
    _exigir_empresa_no_escopo(usuario, id_empresa)
    return row
