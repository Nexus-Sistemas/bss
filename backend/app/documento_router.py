"""
/documentos/{id}/download — serve o binário de um documento, AUTENTICADO.

Os arquivos não ficam num diretório público (LGPD — dado pessoal). O acesso
passa por aqui: confere se o usuário pode ver o processo dono do documento e
então entrega o conteúdo (lido do storage: disco local hoje, S3 em produção).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from .auth import UsuarioInfo, usuario_logado
from . import storage
from .database import get_pg_connection


router = APIRouter(prefix="/documentos", tags=["documentos"])


@router.get("/{id_documento}/download")
def download(
    id_documento: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.arquivo_url, d.mime_type, d.nome_original,
                   d.entidade_tipo, d.entidade_id,
                   p.id_empresa, p.id_sindicato
              FROM bss.documento d
              LEFT JOIN bss.processo_beneficio p
                     ON d.entidade_tipo = 'processo' AND p.id = d.entidade_id
             WHERE d.id = %s
            """,
            (id_documento,),
        )
        doc = cur.fetchone()

    if not doc:
        raise HTTPException(404, "Documento não encontrado")

    # RLS: por ora só documentos de processo. Empresa/sindicato só veem os do
    # seu escopo. 404 (não 403) pra não confirmar existência fora do escopo.
    if doc["entidade_tipo"] == "processo":
        if usuario.perfil == "empresa" and doc["id_empresa"] not in usuario.empresas:
            raise HTTPException(404, "Documento não encontrado")
        if usuario.perfil == "sindicato" and doc["id_sindicato"] not in usuario.sindicatos:
            raise HTTPException(404, "Documento não encontrado")

    ref = doc["arquivo_url"] or ""
    # Documentos migrados do legado são ponteiros — o binário ainda está no
    # servidor do SuiteCRM (será trazido no Big Bang). Não dá pra servir agora.
    if ref.startswith("legado://"):
        raise HTTPException(
            409, "Arquivo ainda no sistema legado — será migrado no Big Bang")

    try:
        conteudo = storage.ler(ref)
    except FileNotFoundError:
        raise HTTPException(404, "Arquivo não encontrado no storage")
    except Exception:
        raise HTTPException(500, "Falha ao ler o arquivo")

    # inline: abre no navegador (PDF/imagem). O nome preserva o original.
    nome = (doc["nome_original"] or "documento").replace('"', "")
    return Response(
        content=conteudo,
        media_type=doc["mime_type"] or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{nome}"'},
    )
