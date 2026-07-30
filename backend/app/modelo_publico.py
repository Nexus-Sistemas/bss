"""
Resolvedor de PÚBLICO por modelo de e-mail.

Público é fixo por modelo (decisão BSS): cada codigo sabe quem recebe, e a lista
é calculada do dado REAL na hora do disparo (empresas inadimplentes agora, etc.)
— reenvia enquanto o problema persistir, sem manter lista.

Cada resolvedor devolve os ALVOS: para modelo destinatario='contato', ids de
bss_users (o gestor); para 'empresa', ids de bss.empresa. O motor de disparo
(modelo_disparo.py) pega esses ids, renderiza o e-mail com modelo_variaveis e
envia.

Modelos SEM público automático (benef_*, atualiza_base, novo_contato) não
aparecem aqui — só podem ser disparados manualmente com público a definir, ou
ficam pra uma fase futura. `tem_publico_automatico(codigo)` diz quais.
"""

from __future__ import annotations

from typing import Any

from .database import get_pg_connection


# Contatos (gestores ativos, com e-mail válido) das empresas que casam a condição.
# Reaproveita a mesma exclusão de e-mail sintético do notificacao.py.
_SQL_CONTATOS_DE_EMPRESAS = """
    SELECT DISTINCT u.id
      FROM bss.empresa e
      JOIN bss.usuario_empresa ue ON ue.id_empresa = e.id AND ue.ativo
      JOIN bss_users u            ON u.id = ue.id_usuario
     WHERE u.ativo AND u.perfil = 'empresa'
       AND u.email NOT LIKE '%%@contato.invalid'
       AND ({cond})
"""

_SQL_EMPRESAS = """
    SELECT e.id
      FROM bss.empresa e
     WHERE ({cond})
"""

# Condição SQL por "situação" que os modelos usam. Uma fonte só.
_COND = {
    "inadimplente": "e.adimplencia = 'inadimplente'",
    "irregular":    "e.regularidade = 'irregular'",
    # tem pelo menos um boleto vencido em aberto:
    "boleto_vencido": """EXISTS (SELECT 1 FROM bss.boleto b
                                  WHERE b.id_empresa = e.id AND b.status = 'vencido')""",
    # não gerou boleto no mês passado (competência mais recente fechada):
    "nao_gerou_boletos": """EXISTS (SELECT 1 FROM bss.empresa_meses_faltantes f
                                     WHERE f.id_empresa = e.id)""",
}

# codigo do modelo → (situação, destinatário implícito). O destinatário real vem
# de modelo_email.destinatario; aqui só ligamos o codigo à condição de público.
_PUBLICO_POR_CODIGO = {
    "inadimplente_contato":       "inadimplente",
    "inadimplente_empresa":       "inadimplente",
    "inadimplente_contato_ant":   "inadimplente",
    "inadimplente_empresa_ant":   "inadimplente",
    "irregular_contato":          "irregular",
    "irregular_empresa":          "irregular",
    "boleto_vencido":             "boleto_vencido",
    "nao_gerou_boletos_contato":  "nao_gerou_boletos",
    "nao_gerou_boletos_empresa":  "nao_gerou_boletos",
    # benef_*, atualiza_base_*, novo_contato_autocadastro: sem público automático.
}


def tem_publico_automatico(codigo: str) -> bool:
    return codigo in _PUBLICO_POR_CODIGO


def resolver_alvos(codigo: str, destinatario: str) -> list[int]:
    """
    IDs dos alvos (contatos OU empresas) que devem receber o modelo AGORA.
    Retorna [] se o modelo não tem público automático.
    """
    situacao = _PUBLICO_POR_CODIGO.get(codigo)
    if not situacao:
        return []
    cond = _COND[situacao]
    sql = (_SQL_CONTATOS_DE_EMPRESAS if destinatario == "contato"
           else _SQL_EMPRESAS).format(cond=cond)
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(sql)
        return [r["id"] for r in cur.fetchall()]
