"""
/tipos-beneficio — o que o formulário de abertura de benefício precisa saber.

GET /tipos-beneficio              → lista pro dropdown
GET /tipos-beneficio/{codigo}/form → campos + documentos daquele tipo

Qualquer usuário logado que possa abrir benefício (empresa e internos) consulta.
Não expõe dado sensível — só a estrutura do formulário.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from .auth import UsuarioInfo, usuario_logado
from . import tipo_beneficio_repo


router = APIRouter(prefix="/tipos-beneficio", tags=["tipos-beneficio"])


@router.get("")
def listar(usuario: Annotated[UsuarioInfo, Depends(usuario_logado)]):
    return tipo_beneficio_repo.listar_tipos()


@router.get("/{codigo}/form")
def form(codigo: str, usuario: Annotated[UsuarioInfo, Depends(usuario_logado)]):
    f = tipo_beneficio_repo.form_do_tipo(codigo)
    if not f:
        raise HTTPException(404, "Tipo de benefício não encontrado")
    return f
