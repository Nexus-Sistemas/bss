"""
/tarefas — checklist de demandas da implantação. RESTRITO à equipe interna.

GET  /tarefas                → lista (filtros)
GET  /tarefas/modulos        → módulos já usados (datalist)
POST /tarefas                → criar
PUT  /tarefas/{id}           → editar (campos + status)
POST /tarefas/{id}/anexo     → subir o print (imagem)
GET  /tarefas/{id}/anexo     → ver o print
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from .auth import UsuarioInfo, exigir_interno
from . import storage, tarefa_repo


router = APIRouter(prefix="/tarefas", tags=["tarefas"])

_STATUS = {"aberta", "em_dev", "aguardando", "resolvida", "cancelada"}
_MAX_ANEXO = 10 * 1024 * 1024   # 10 MB por print


@router.get("")
def listar(
    usuario: Annotated[UsuarioInfo, Depends(exigir_interno)],
    status: str | None = None,
    modulo: str | None = None,
    prioridade: int | None = None,
    busca: str | None = None,
    incluir_encerradas: bool = False,
):
    return tarefa_repo.listar(status, modulo, prioridade, busca, incluir_encerradas)


@router.get("/modulos")
def modulos(usuario: Annotated[UsuarioInfo, Depends(exigir_interno)]):
    return tarefa_repo.modulos_usados()


class TarefaIn(BaseModel):
    prioridade: int = 2
    modulo: str | None = None
    assunto: str
    descricao: str | None = None
    status: str = "aberta"


def _valida(dados: TarefaIn) -> None:
    if not (dados.assunto or "").strip():
        raise HTTPException(400, "Assunto é obrigatório")
    if dados.status not in _STATUS:
        raise HTTPException(400, "Status inválido")
    if dados.prioridade not in (1, 2, 3):
        raise HTTPException(400, "Prioridade deve ser 1, 2 ou 3")


@router.post("", status_code=201)
def criar(
    dados: TarefaIn,
    usuario: Annotated[UsuarioInfo, Depends(exigir_interno)],
):
    _valida(dados)
    return tarefa_repo.criar(dados.prioridade, (dados.modulo or "").strip() or None,
                             dados.assunto.strip(), dados.descricao, dados.status,
                             usuario.id)


@router.put("/{id_tarefa}")
def atualizar(
    id_tarefa: int,
    dados: TarefaIn,
    usuario: Annotated[UsuarioInfo, Depends(exigir_interno)],
):
    _valida(dados)
    t = tarefa_repo.atualizar(id_tarefa, dados.prioridade,
                              (dados.modulo or "").strip() or None,
                              dados.assunto.strip(), dados.descricao, dados.status)
    if not t:
        raise HTTPException(404, "Tarefa não encontrada")
    return t


@router.post("/{id_tarefa}/anexo")
async def anexar(
    id_tarefa: int,
    usuario: Annotated[UsuarioInfo, Depends(exigir_interno)],
    arquivo: Annotated[UploadFile, File()],
):
    if not tarefa_repo.buscar(id_tarefa):
        raise HTTPException(404, "Tarefa não encontrada")
    conteudo = await arquivo.read()
    if len(conteudo) > _MAX_ANEXO:
        raise HTTPException(413, "Print excede 10 MB")
    ref = storage.salvar(conteudo, arquivo.filename or "print.png")
    tarefa_repo.salvar_anexo(id_tarefa, ref, arquivo.filename or "print.png")
    return {"ok": True}


@router.get("/{id_tarefa}/anexo")
def ver_anexo(
    id_tarefa: int,
    usuario: Annotated[UsuarioInfo, Depends(exigir_interno)],
):
    t = tarefa_repo.buscar(id_tarefa)
    if not t or not t["anexo_url"]:
        raise HTTPException(404, "Sem anexo")
    try:
        conteudo = storage.ler(t["anexo_url"])
    except Exception:
        raise HTTPException(404, "Anexo não encontrado no storage")
    nome = (t["anexo_nome"] or "print").replace('"', "")
    # mime pela extensão simples (imagens são o caso comum)
    ext = nome.lower().rsplit(".", 1)[-1] if "." in nome else ""
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf"
            }.get(ext, "application/octet-stream")
    return Response(content=conteudo, media_type=mime,
                    headers={"Content-Disposition": f'inline; filename="{nome}"'})
