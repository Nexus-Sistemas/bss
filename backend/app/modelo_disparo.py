"""
Motor de disparo dos modelos de e-mail em massa.

  preview(id_modelo)          → quem receberia + amostra do conteúdo, SEM enviar
  disparar(id_modelo, origem) → resolve público, renderiza, envia, registra

TRAVA DE SEGURANÇA (config.EMAIL_REDIRECIONAR_PARA)
---------------------------------------------------
Disparo em massa manda e-mail pra empresas REAIS. Em homologação isso seria
desastre. Se EMAIL_REDIRECIONAR_PARA estiver setado, TODO e-mail vai pra esse
endereço (com o destinatário real anotado no topo do corpo). Em produção,
deixa vazio → vai pro real.

IDEMPOTÊNCIA: não reenvia o mesmo modelo pro mesmo e-mail no MESMO dia (consulta
bss.modelo_email_envio). Assim manual + agendado, ou o job rodando 2x, não
duplicam. "Reenviar enquanto persistir" acontece de um DIA pro outro.
"""

from __future__ import annotations

from typing import Any

from .config import settings
from .database import get_pg_connection
from . import modelo_publico, modelo_variaveis, notificacao


def _alvos_com_email(id_modelo: int, codigo: str, destinatario: str) -> list[dict]:
    """
    Resolve os alvos e traz o e-mail de cada um. Para 'contato', o e-mail é do
    bss_users; para 'empresa', o email_cobranca (fallback email) da empresa.
    Já exclui e-mail vazio.
    """
    ids = modelo_publico.resolver_alvos(codigo, destinatario)
    if not ids:
        return []
    with get_pg_connection() as conn, conn.cursor() as cur:
        if destinatario == "contato":
            cur.execute(
                "SELECT id AS id_contato, NULL::bigint AS id_empresa, nome, email "
                "FROM bss_users WHERE id = ANY(%s) AND email IS NOT NULL AND email <> ''",
                (ids,),
            )
        else:
            cur.execute(
                "SELECT NULL::int AS id_contato, id AS id_empresa, razao_social AS nome, "
                "COALESCE(NULLIF(email_cobranca,''), email) AS email "
                "FROM bss.empresa WHERE id = ANY(%s) "
                "AND COALESCE(NULLIF(email_cobranca,''), email) IS NOT NULL",
                (ids,),
            )
        return [r for r in cur.fetchall() if r["email"]]


def _ja_enviou_hoje(cur, id_modelo: int, email: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM bss.modelo_email_envio
         WHERE id_modelo = %s AND lower(email) = lower(%s)
           AND enviado_em::date = CURRENT_DATE AND status = 'enviado'
         LIMIT 1
        """,
        (id_modelo, email),
    )
    return cur.fetchone() is not None


def _render(modelo: dict, alvo: dict) -> dict:
    """Renderiza assunto+corpo pra um alvo, usando modelo_variaveis."""
    return modelo_variaveis.renderizar(
        assunto=modelo["assunto"], corpo=modelo["corpo"],
        destinatario=modelo["destinatario"],
        id_contato=alvo["id_contato"], id_empresa=alvo["id_empresa"],
    )


def preview(modelo: dict) -> dict:
    """
    Dry-run: quantos e quem receberia, + o conteúdo renderizado pro 1º alvo.
    NÃO envia nada. É a ferramenta de teste segura.
    """
    if not modelo_publico.tem_publico_automatico(modelo["codigo"]):
        return {"total": 0, "sem_publico_automatico": True, "alvos": [], "amostra": None}

    alvos = _alvos_com_email(modelo["id"], modelo["codigo"], modelo["destinatario"])
    amostra = None
    if alvos:
        r = _render(modelo, alvos[0])
        amostra = {"para": alvos[0]["email"], "nome": alvos[0]["nome"],
                   "assunto": r["assunto"], "corpo": r["corpo"], "orfas": r["orfas"]}
    return {
        "total": len(alvos),
        "sem_publico_automatico": False,
        # amostra dos primeiros 20 destinatários (só nome+email, sem render em massa)
        "alvos": [{"nome": a["nome"], "email": a["email"]} for a in alvos[:20]],
        "amostra": amostra,
        "redirecionado_para": settings.EMAIL_REDIRECIONAR_PARA or None,
    }


def disparar(modelo: dict, origem: str = "manual") -> dict:
    """
    Envia pra todos os alvos. Respeita a trava de redirecionamento e a
    idempotência do dia. Grava tudo no log. Retorna resumo.
    """
    if not modelo.get("ativo"):
        return {"erro": "Modelo inativo — ative antes de disparar."}
    if not modelo_publico.tem_publico_automatico(modelo["codigo"]):
        return {"erro": "Modelo sem público automático."}

    alvos = _alvos_com_email(modelo["id"], modelo["codigo"], modelo["destinatario"])
    redirecionar = settings.EMAIL_REDIRECIONAR_PARA.strip()

    enviados = pulados = falhas = 0
    with get_pg_connection() as conn:
        for a in alvos:
            with conn.cursor() as cur:
                if _ja_enviou_hoje(cur, modelo["id"], a["email"]):
                    pulados += 1
                    continue

            r = _render(modelo, a)
            corpo = r["corpo"]
            destino = a["email"]
            if redirecionar:
                corpo = (f"[TESTE — destinatário real: {a['nome']} <{a['email']}>]\n\n"
                         + corpo)
                destino = redirecionar

            ok = notificacao.enviar_simples(destino, r["assunto"], corpo)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO bss.modelo_email_envio
                        (id_modelo, id_usuario_destino, id_empresa, email, assunto,
                         status, origem, redirecionado)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (modelo["id"], a["id_contato"], a["id_empresa"], a["email"],
                     r["assunto"], "enviado" if ok else "falha", origem,
                     bool(redirecionar)),
                )
            conn.commit()
            if ok:
                enviados += 1
            else:
                falhas += 1

    return {"total": len(alvos), "enviados": enviados,
            "pulados_ja_enviado_hoje": pulados, "falhas": falhas,
            "redirecionado_para": redirecionar or None}
