"""
Storage de documentos — abstração com costura pra trocar de backend.

Hoje: disco local (dev/homolog na OCI). Amanhã: S3 (produção). O código que
CHAMA (upload de benefício, download de documento) usa só estas funções e não
sabe onde o arquivo mora — trocar `STORAGE_BACKEND` no .env muda tudo, sem
mexer em quem chama.

O REF guardado em bss.documento.arquivo_url identifica o backend pelo prefixo:
    local://2026/07/<uuid>_<nome>.pdf     → disco (este módulo)
    s3://<bucket>/2026/07/<uuid>_<nome>   → S3 (produção, futuro)
    legado://document_revision/<id>       → dados migrados (só leitura; nunca
                                             gerados aqui)

SEGURANÇA: os arquivos NÃO ficam num diretório servido estaticamente. O
download passa por endpoint autenticado, que checa se o usuário pode ver aquele
documento e então entrega o conteúdo (ou, em S3, uma URL pré-assinada temporária).
Dado de benefício é pessoal (LGPD) — nunca um bucket/pasta aberta.
"""

from __future__ import annotations

import os
import re
import unicodedata
import uuid
from datetime import date

from .config import settings


# --- helpers de nome -------------------------------------------------------

def _nome_seguro(nome: str) -> str:
    """
    Sanitiza o nome original pra virar parte de um caminho: sem acento, sem
    espaço, sem `..` ou barra (evita path traversal). O nome ORIGINAL de
    verdade fica em bss.documento.nome_original; aqui é só pra legibilidade.
    """
    n = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode()
    n = re.sub(r"[^A-Za-z0-9._-]+", "_", n).strip("_.")
    return (n or "arquivo")[:80]


def _subpasta_mes() -> str:
    """Organiza por ano/mês — evita milhares de arquivos num diretório só."""
    hoje = date.today()
    return f"{hoje.year:04d}/{hoje.month:02d}"


# --- API pública (igual pros dois backends) --------------------------------

def salvar(conteudo: bytes, nome_original: str) -> str:
    """
    Grava o conteúdo e retorna o REF (a string que vai em arquivo_url).
    """
    if settings.STORAGE_BACKEND == "s3":
        return _salvar_s3(conteudo, nome_original)
    return _salvar_local(conteudo, nome_original)


def ler(ref: str) -> bytes:
    """Lê o conteúdo de volta a partir do REF. Usado pelo download autenticado."""
    if ref.startswith("local://"):
        caminho = _caminho_local(ref)
        with open(caminho, "rb") as f:
            return f.read()
    if ref.startswith("s3://"):
        return _ler_s3(ref)
    raise ValueError(f"REF de storage não suportado para leitura: {ref!r}")


def existe(ref: str) -> bool:
    if ref.startswith("local://"):
        return os.path.isfile(_caminho_local(ref))
    if ref.startswith("s3://"):
        return _existe_s3(ref)
    return False


# --- backend LOCAL ---------------------------------------------------------

def _caminho_local(ref: str) -> str:
    """
    Converte 'local://a/b/c.pdf' no caminho físico dentro de STORAGE_LOCAL_DIR.
    Blinda contra path traversal: o caminho final TEM que estar dentro da raiz.
    """
    rel = ref[len("local://"):].lstrip("/")
    base = os.path.realpath(settings.STORAGE_LOCAL_DIR)
    caminho = os.path.realpath(os.path.join(base, rel))
    if caminho != base and not caminho.startswith(base + os.sep):
        raise ValueError(f"caminho fora da raiz do storage: {ref!r}")
    return caminho


def _salvar_local(conteudo: bytes, nome_original: str) -> str:
    rel = f"{_subpasta_mes()}/{uuid.uuid4().hex}_{_nome_seguro(nome_original)}"
    ref = f"local://{rel}"
    caminho = _caminho_local(ref)
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "wb") as f:
        f.write(conteudo)
    return ref


# --- backend S3 (produção — implementar quando ligar) ----------------------
# Deixado explícito pra a costura ficar óbvia. Usa boto3 (adicionar ao
# requirements quando STORAGE_BACKEND='s3'), com credenciais via IAM Role da
# EC2 (sem chave em arquivo).

def _salvar_s3(conteudo: bytes, nome_original: str) -> str:
    import boto3  # noqa: import tardio — só carrega em produção
    key = f"{_subpasta_mes()}/{uuid.uuid4().hex}_{_nome_seguro(nome_original)}"
    boto3.client("s3", region_name=settings.STORAGE_S3_REGIAO).put_object(
        Bucket=settings.STORAGE_S3_BUCKET, Key=key, Body=conteudo,
        ServerSideEncryption="AES256",
    )
    return f"s3://{settings.STORAGE_S3_BUCKET}/{key}"


def _ler_s3(ref: str) -> bytes:
    import boto3
    bucket, key = ref[len("s3://"):].split("/", 1)
    obj = boto3.client("s3", region_name=settings.STORAGE_S3_REGIAO).get_object(
        Bucket=bucket, Key=key)
    return obj["Body"].read()


def _existe_s3(ref: str) -> bool:
    import boto3
    from botocore.exceptions import ClientError
    bucket, key = ref[len("s3://"):].split("/", 1)
    try:
        boto3.client("s3", region_name=settings.STORAGE_S3_REGIAO).head_object(
            Bucket=bucket, Key=key)
        return True
    except ClientError:
        return False
