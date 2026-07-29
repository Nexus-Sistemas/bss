"""
Tipos de benefício + a configuração de formulário de cada um.

Duas fontes:
  - DOCUMENTOS obrigatórios → tabela bss.tipo_beneficio_documento (dado).
  - CAMPOS próprios do tipo (qtd bebês, dados bancários, beneficiário) → o mapa
    CAMPOS abaixo (código). São poucos e estáveis; se um dia variarem por
    sindicato, viram tabela. Por ora, mapa legível > tabela vazia.

Assim o formulário do front se monta sozinho a partir de /tipos-beneficio/{cod}/form,
sem espalhar `if tipo == ...` pelo JS.
"""

from __future__ import annotations

from typing import Any

from .database import get_pg_connection


# Config de formulário por código de tipo. Baseado na análise dos 19k processos
# e das telas do legado (ver docs/PORTAL_EMPRESA.md).
#   qtd_bebes        : mostra o campo "Quantidade de Bebês"
#   dados_bancarios  : None | 'beneficiario' | 'empresa' — de quem é a conta
#   tem_beneficiario : pode haver beneficiário (bloco "outra pessoa")?
#   beneficiario_padrao : 'proprio' | 'outra' — default do "quem recebe"
_PADRAO = {"qtd_bebes": False, "dados_bancarios": None,
           "tem_beneficiario": True, "beneficiario_padrao": "proprio"}

CAMPOS: dict[str, dict[str, Any]] = {
    "natalidade":        {"qtd_bebes": True},
    "falecimento":       {"dados_bancarios": "beneficiario", "beneficiario_padrao": "outra"},
    "acidente":          {},
    "incapacitacao":     {"dados_bancarios": "beneficiario"},
    # Reembolso é pra EMPRESA: conta da empresa, sem beneficiário pessoa.
    "reembolso_rescisao": {"dados_bancarios": "empresa", "tem_beneficiario": False},
    "acionamento_funeral": {},
    "consulta_medica":   {},
    "exame":             {},
    "brinde_sindicato":  {},
    "auxilio_creche":    {},
}


def listar_tipos() -> list[dict[str, Any]]:
    """Tipos ativos, pro dropdown do formulário."""
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, codigo, nome FROM bss.tipo_beneficio "
            "WHERE ativo ORDER BY ordem, nome"
        )
        return list(cur.fetchall())


def ids_tipo_documento(id_tipo_beneficio: int) -> dict[str, int]:
    """{codigo do documento → id em tipo_beneficio_documento} pra o POST ligar
    cada arquivo ao tipo de documento certo."""
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, codigo FROM bss.tipo_beneficio_documento "
            "WHERE id_tipo_beneficio = %s AND ativo",
            (id_tipo_beneficio,),
        )
        return {r["codigo"]: r["id"] for r in cur.fetchall()}


def form_do_tipo(codigo: str) -> dict[str, Any] | None:
    """
    Devolve tudo que o formulário precisa pra montar aquele tipo:
    id/nome, os flags de campos, e a lista de documentos (obrigatórios marcados).
    """
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, codigo, nome FROM bss.tipo_beneficio WHERE codigo = %s AND ativo",
            (codigo,),
        )
        tipo = cur.fetchone()
        if not tipo:
            return None

        cur.execute(
            """
            SELECT codigo, nome, obrigatorio, ordem
              FROM bss.tipo_beneficio_documento
             WHERE id_tipo_beneficio = %s AND ativo
             ORDER BY ordem
            """,
            (tipo["id"],),
        )
        documentos = list(cur.fetchall())

    campos = {**_PADRAO, **CAMPOS.get(codigo, {})}
    return {
        "id": tipo["id"],
        "codigo": tipo["codigo"],
        "nome": tipo["nome"],
        "campos": campos,
        "documentos": documentos,
    }
