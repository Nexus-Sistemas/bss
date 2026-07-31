"""
GET /dashboard-funeraria/serie-mensal — série de solicitados/finalizados por mês
(sempre Acionamento Funeral). Acesso: funerária + equipe interna.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from .auth import UsuarioInfo, usuario_logado
from . import dashboard_funeraria_repo


router = APIRouter(prefix="/dashboard-funeraria", tags=["dashboard-funeraria"])


@router.get("/serie-mensal")
def serie_mensal(usuario: Annotated[UsuarioInfo, Depends(usuario_logado)]):
    if usuario.perfil not in ("funeraria", "admin", "interno", "analista"):
        raise HTTPException(403, "Acesso restrito")
    return {"meses": dashboard_funeraria_repo.serie_mensal()}
