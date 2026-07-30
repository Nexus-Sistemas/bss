"""
GET /dashboard-sindicato/resumo — agregações do painel do sindicato.

Escopo pelo JWT: usa usuario.sindicatos. Aceita id_sindicato (do seletor) pra
estreitar num sindicato. Internos podem passar id_sindicato pra inspecionar um
sindicato específico; sem ele, internos NÃO recebem tudo (evita consulta pesada
sem escopo) — a tela é do sindicato.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from .auth import UsuarioInfo, usuario_logado
from . import dashboard_sindicato_repo


router = APIRouter(prefix="/dashboard-sindicato", tags=["dashboard-sindicato"])


@router.get("/resumo")
def resumo(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    id_sindicato: int | None = None,
):
    if usuario.perfil == "sindicato":
        if not usuario.sindicatos:
            return dashboard_sindicato_repo.resumo([])
        if id_sindicato is not None:
            if id_sindicato not in usuario.sindicatos:
                raise HTTPException(403, "Sindicato fora do escopo")
            ids = [id_sindicato]
        else:
            ids = usuario.sindicatos
    elif usuario.perfil in ("admin", "interno", "analista"):
        # Interno inspecionando: precisa escolher um sindicato (não devolve tudo).
        if id_sindicato is None:
            raise HTTPException(400, "Informe id_sindicato para inspecionar")
        ids = [id_sindicato]
    else:
        raise HTTPException(403, "Acesso restrito")

    return dashboard_sindicato_repo.resumo(ids)
