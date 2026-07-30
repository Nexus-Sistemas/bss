"""GET /boletos — listagem + emissão (épico #21)."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from .auth import UsuarioInfo, usuario_logado
from . import boleto_repo, boleto_emissao, boleto_pdf


router = APIRouter(prefix="/boletos", tags=["boletos"])


# =============================================================================
# Listagem (já existia)
# =============================================================================

@router.get("")
def listar(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    busca: str | None = None,
    status: str | None = None,
    mes_referencia: str | None = None,
    id_empresa: int | None = None,
    id_sindicato: int | None = None,
    incluir_cancelados: bool = False,
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "mes_referencia",
    desc: bool = True,
):
    # ESCOPO ≠ FILTRO — ver o comentário no processo_router. `ids_empresa` é o
    # que o usuário pode ver; `id_empresa` é o que ele escolheu ver.
    ids_empresa: list[int] | None = None
    if usuario.perfil == "empresa":
        if not usuario.empresas:
            return {"linhas": [], "total": 0, "pagina": 1,
                    "por_pagina": por_pagina, "paginas": 0}
        if id_empresa is not None and id_empresa not in usuario.empresas:
            raise HTTPException(403, "Empresa fora do escopo")
        ids_empresa = usuario.empresas
        # Empresa NUNCA vê cancelados (regra do épico #21):
        incluir_cancelados = False
    elif usuario.perfil == "sindicato":
        if not usuario.sindicatos:
            return {"linhas": [], "total": 0, "pagina": 1,
                    "por_pagina": por_pagina, "paginas": 0}
        if id_sindicato is None:
            id_sindicato = usuario.sindicatos[0]
        elif id_sindicato not in usuario.sindicatos:
            raise HTTPException(403, "Sindicato fora do escopo")

    return boleto_repo.listar(
        busca=busca, status=status, mes_referencia=mes_referencia,
        id_empresa=id_empresa, ids_empresa=ids_empresa, id_sindicato=id_sindicato,
        incluir_cancelados=incluir_cancelados,
        pagina=pagina, por_pagina=por_pagina, ordem=ordem, desc=desc,
    )


@router.get("/{id_boleto}")
def detalhe(
    id_boleto: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    row = boleto_repo.buscar_por_id(id_boleto)
    if not row:
        raise HTTPException(404, "Boleto não encontrado")
    if usuario.perfil == "empresa" and row.get("id_empresa") not in usuario.empresas:
        raise HTTPException(403, "Boleto fora do escopo")
    if usuario.perfil == "sindicato" and row.get("id_sindicato") not in usuario.sindicatos:
        raise HTTPException(403, "Boleto fora do escopo")
    return row


@router.get("/{id_boleto}/detalhe")
def detalhe_completo(
    id_boleto: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Detalhe completo do boleto + trabalhadores (boleto_item) pra tela de detalhe."""
    row = boleto_repo.buscar_detalhe(id_boleto)
    if not row:
        raise HTTPException(404, "Boleto não encontrado")
    # Empresa nunca vê cancelado:
    if usuario.perfil == "empresa":
        if row.get("status") == "cancelado":
            raise HTTPException(404, "Boleto não disponível")
        if row.get("id_empresa") not in usuario.empresas:
            raise HTTPException(403, "Boleto fora do escopo")
    elif usuario.perfil == "sindicato":
        if row.get("id_sindicato") not in usuario.sindicatos:
            raise HTTPException(403, "Boleto fora do escopo")
    return row


# =============================================================================
# Emissão (épico #21)
# =============================================================================

def _mes_corrente_inicio() -> date:
    h = date.today()
    return h.replace(day=1)


@router.get("/emissao/preview")
def preview_emissao(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    id_empresa: int | None = None,
):
    """
    Preview da emissão pra mês de amparo CORRENTE (regra: mês fixo).

    Por perfil:
      - empresa: lista TODAS as empresas vinculadas ao usuário
      - admin/interno: REQUER id_empresa na query string
                       (sem isso, retorna vazio com aviso)
    """
    return boleto_emissao.preview_emissao(usuario, _mes_corrente_inicio(), id_empresa)


class EmitirRequest(BaseModel):
    ids_empresa: list[int] | None = None  # opcional — subset; default = todas do escopo


@router.post("/emissao/emitir")
def emitir(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    # default=None + embed torna o CORPO OPCIONAL: o perfil empresa emite sem
    # corpo nenhum (todas as suas empresas), e o interno manda {ids_empresa:[...]}.
    # Sem o default, FastAPI exigia corpo e devolvia 422 pra empresa (body=null).
    payload: Annotated[EmitirRequest | None, Body()] = None,
):
    """
    Gera boletos pro mês de amparo CORRENTE.
    Idempotente: pares (empresa × sindicato × mês) que já têm boleto vivo
    são pulados (volta no campo 'pulados').
    """
    ids = payload.ids_empresa if payload else None
    return boleto_emissao.emitir_boletos(usuario, _mes_corrente_inicio(), ids)


class CancelarRequest(BaseModel):
    motivo: str


@router.post("/{id_boleto}/cancelar")
def cancelar(
    id_boleto: int,
    payload: Annotated[CancelarRequest, Body()],
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    res = boleto_emissao.cancelar_boleto(usuario, id_boleto, payload.motivo)
    if not res.get("ok"):
        raise HTTPException(400, res.get("erro", "Erro ao cancelar"))
    return res


@router.post("/{id_boleto}/reemitir")
def reemitir(
    id_boleto: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    res = boleto_emissao.reemitir_boleto(usuario, id_boleto)
    if not res.get("ok"):
        raise HTTPException(400, res.get("erro", "Erro ao reemitir"))
    return res


# =============================================================================
# Downloads PDF (boleto + lista de trabalhadores)
# =============================================================================

def _check_acesso_boleto(usuario: UsuarioInfo, row: dict[str, Any]) -> None:
    """Confere se o usuário tem permissão de ver o boleto."""
    if not row:
        raise HTTPException(404, "Boleto não encontrado")
    if usuario.perfil == "empresa":
        if row.get("status") == "cancelado":
            # Empresa NUNCA vê cancelado:
            raise HTTPException(404, "Boleto não disponível")
        if row.get("id_empresa") not in usuario.empresas:
            raise HTTPException(403, "Boleto fora do escopo")
    elif usuario.perfil == "sindicato":
        if row.get("id_sindicato") not in usuario.sindicatos:
            raise HTTPException(403, "Boleto fora do escopo")


def _ids_lote(usuario, busca, status, mes_referencia, id_empresa,
              id_sindicato, incluir_cancelados) -> list[int]:
    """Resolve os ids do lote aplicando o escopo do perfil (igual à listagem)."""
    ids_empresa = None
    if usuario.perfil == "empresa":
        if not usuario.empresas:
            return []
        if id_empresa is not None and id_empresa not in usuario.empresas:
            raise HTTPException(403, "Empresa fora do escopo")
        ids_empresa = usuario.empresas
        incluir_cancelados = False   # empresa nunca vê cancelado
    elif usuario.perfil == "sindicato":
        if not usuario.sindicatos:
            return []
        if id_sindicato is None:
            id_sindicato = usuario.sindicatos[0]
        elif id_sindicato not in usuario.sindicatos:
            raise HTTPException(403, "Sindicato fora do escopo")
    return boleto_repo.ids_por_filtro(
        busca=busca, status=status, mes_referencia=mes_referencia,
        id_empresa=id_empresa, ids_empresa=ids_empresa, id_sindicato=id_sindicato,
        incluir_cancelados=incluir_cancelados,
    )


@router.get("/lote/boletos-pdf")
def download_lote_boletos(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    busca: str | None = None,
    status: str | None = None,
    mes_referencia: str | None = None,
    id_empresa: int | None = None,
    id_sindicato: int | None = None,
    incluir_cancelados: bool = False,
):
    """Todos os boletos do filtro num PDF só (teto de 500 — ver boleto_repo)."""
    ids = _ids_lote(usuario, busca, status, mes_referencia, id_empresa,
                    id_sindicato, incluir_cancelados)
    if not ids:
        raise HTTPException(404, "Nenhum boleto para baixar neste filtro")
    pdf = boleto_pdf.gerar_pdf_boletos_lote(ids)
    if not pdf:
        raise HTTPException(404, "Nenhum boleto gerado")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="boletos_lote_{len(ids)}.pdf"'},
    )


@router.get("/lote/listas-pdf")
def download_lote_listas(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    busca: str | None = None,
    status: str | None = None,
    mes_referencia: str | None = None,
    id_empresa: int | None = None,
    id_sindicato: int | None = None,
    incluir_cancelados: bool = False,
):
    """Todas as listas de trabalhadores do filtro num PDF só."""
    ids = _ids_lote(usuario, busca, status, mes_referencia, id_empresa,
                    id_sindicato, incluir_cancelados)
    if not ids:
        raise HTTPException(404, "Nenhuma lista para baixar neste filtro")
    pdf = boleto_pdf.gerar_pdf_listas_lote(ids)
    if not pdf:
        raise HTTPException(404, "Nenhuma lista gerada")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="listas_lote_{len(ids)}.pdf"'},
    )


class LoteIdsRequest(BaseModel):
    ids: list[int]


def _ids_acessiveis(usuario: UsuarioInfo, ids: list[int]) -> list[int]:
    """Filtra os ids que o usuário PODE ver (escopo). Preserva a ordem pedida."""
    ok = []
    for i in ids[:boleto_repo.LIMITE_LOTE]:
        row = boleto_repo.buscar_por_id(i)
        if not row:
            continue
        try:
            _check_acesso_boleto(usuario, row)
            ok.append(i)
        except HTTPException:
            continue   # fora do escopo: ignora em silêncio (não vaza)
    return ok


@router.post("/lote/por-ids/boletos-pdf")
def download_lote_boletos_ids(
    payload: LoteIdsRequest,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Boletos de ids explícitos num PDF só — usado pelo resultado da emissão
    ('baixar tudo que acabou de gerar'). ids vão no corpo (podem ser centenas)."""
    ids = _ids_acessiveis(usuario, payload.ids)
    pdf = boleto_pdf.gerar_pdf_boletos_lote(ids) if ids else None
    if not pdf:
        raise HTTPException(404, "Nenhum boleto acessível para baixar")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="boletos_gerados_{len(ids)}.pdf"'})


@router.post("/lote/por-ids/listas-pdf")
def download_lote_listas_ids(
    payload: LoteIdsRequest,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    ids = _ids_acessiveis(usuario, payload.ids)
    pdf = boleto_pdf.gerar_pdf_listas_lote(ids) if ids else None
    if not pdf:
        raise HTTPException(404, "Nenhuma lista acessível para baixar")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="listas_geradas_{len(ids)}.pdf"'})


@router.get("/{id_boleto}/pdf")
def download_pdf_boleto(
    id_boleto: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    row = boleto_repo.buscar_por_id(id_boleto)
    _check_acesso_boleto(usuario, row)
    pdf = boleto_pdf.gerar_pdf_boleto(id_boleto)
    if not pdf:
        raise HTTPException(404, "Boleto não encontrado")
    nome = f"boleto_{row.get('nosso_numero') or id_boleto}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nome}"'},
    )


@router.get("/{id_boleto}/lista-pdf")
def download_pdf_lista(
    id_boleto: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    row = boleto_repo.buscar_por_id(id_boleto)
    _check_acesso_boleto(usuario, row)
    pdf = boleto_pdf.gerar_pdf_lista(id_boleto)
    if not pdf:
        raise HTTPException(404, "Boleto não encontrado")
    nome = f"lista_trabalhadores_{row.get('nosso_numero') or id_boleto}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nome}"'},
    )
