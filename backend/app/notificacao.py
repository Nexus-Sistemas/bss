"""
Envio de e-mail de notificação.

NOME DO ARQUIVO: `notificacao.py`, NÃO `email.py`. Um módulo chamado `email.py`
dentro do pacote sombrearia o pacote `email` da biblioteca padrão — do qual o
próprio smtplib depende — e o import quebraria de um jeito difícil de
diagnosticar. Não renomear.

PRINCÍPIO
---------
Notificação NUNCA derruba a operação. Se o SMTP estiver fora, mal configurado
ou lento, a mensagem já foi gravada no banco e o usuário já viu a resposta na
tela. O e-mail é um extra que avisa quem não está olhando — não é o canal.

Por isso:
  - sem SMTP_HOST configurado, as funções viram no-op silencioso;
  - toda exceção é capturada e logada, nunca propagada;
  - o envio roda em BackgroundTask (o POST responde antes de o e-mail sair).

CONTEÚDO
--------
Decisão da BSS (22/07/2026): **só aviso + link**, sem o texto da mensagem.
Benefício social lida com falecimento, acidente e incapacitação — conteúdo que
não deve trafegar por e-mail nem parar numa caixa compartilhada do RH. Quem
quiser ler, entra no portal.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

from .config import settings
from .database import get_pg_connection

log = logging.getLogger("bss.notificacao")


def _habilitado() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USER)


def _remetente() -> str:
    return settings.SMTP_FROM or settings.SMTP_USER


def _enviar(destinatarios: list[str], assunto: str, texto: str, html: str) -> bool:
    """
    Envia um e-mail. Retorna True se enviou, False se falhou/desligado.
    Engole a exceção (loga) — notificação nunca derruba a operação.
    """
    if not _habilitado() or not destinatarios:
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = assunto
        msg["From"] = f"{settings.SMTP_FROM_NOME} <{_remetente()}>"
        # BCC e não To: os gestores de uma empresa não precisam ver o e-mail
        # uns dos outros, e num CNPJ com vários contatos isso vazaria a lista.
        msg["To"] = _remetente()
        msg["Bcc"] = ", ".join(destinatarios)
        msg.set_content(texto)
        msg.add_alternative(html, subtype="html")

        ctx = ssl.create_default_context()
        if not settings.SMTP_VERIFICAR_CERT:
            # Ver o comentário de SMTP_VERIFICAR_CERT em config.py. Loga em
            # WARNING toda vez de propósito: configuração insegura não deve
            # virar silêncio confortável.
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            log.warning("SMTP com verificação de certificado DESLIGADA "
                        "(SMTP_VERIFICAR_CERT=false) — não usar em produção")

        if settings.SMTP_SSL:
            # SSL direto (465): já conecta criptografado.
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT,
                                  context=ctx, timeout=20) as s:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.send_message(msg)
        else:
            # STARTTLS (587): conecta em claro e sobe pra TLS.
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as s:
                if settings.SMTP_USE_TLS:
                    s.starttls(context=ctx)
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.send_message(msg)

        log.info("e-mail enviado para %d destinatário(s): %s",
                 len(destinatarios), assunto)
        return True
    except Exception as e:
        log.warning("falha ao enviar e-mail (%s): %s", assunto, e)
        return False


def enviar_simples(destino: str, assunto: str, corpo_texto: str) -> bool:
    """
    Envia um e-mail de texto pra UM destinatário. Retorna True/False.
    Usado pelo disparo em massa (modelo_disparo). O corpo vem como texto (o que
    o cliente escreve nos modelos); geramos um HTML simples preservando quebras.
    """
    if not destino:
        return False
    html = ("<div style=\"font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;"
            "font-size:14px;color:#334155;white-space:pre-wrap\">"
            + _escape_html(corpo_texto) + "</div>")
    return _enviar([destino], assunto, corpo_texto, html)


def _escape_html(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def enviar_reset_senha(destino: str, nome: str, link: str) -> bool:
    """
    Manda o link de redefinição de senha PRA PESSOA (To direto, não Bcc — é um
    e-mail transacional individual). Retorna True/False; nunca levanta.
    """
    if not _habilitado() or not destino:
        return False

    assunto = "Redefinição de senha — BSS"
    texto = f"""Olá {nome or ''},

Recebemos um pedido para redefinir a senha da sua conta no BSS.

Para criar uma nova senha, acesse o link abaixo (válido por 1 hora):
{link}

Se não foi você que pediu, ignore este e-mail — sua senha continua a mesma.

Mensagem automática — não responda a este e-mail.
"""
    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><body style="margin:0;padding:24px;background:#f8fafc;
      font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#334155">
  <div style="max-width:520px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;
              border-radius:12px;padding:28px">
    <h2 style="margin:0 0 4px;font-size:17px;color:#1e293b">Redefinição de senha</h2>
    <p style="margin:0 0 20px;font-size:14px;color:#64748b">
      Olá {_escape_html(nome or '')}, recebemos um pedido para redefinir a senha da sua conta.</p>
    <p style="margin:0 0 20px;font-size:14px">
      Clique no botão abaixo para criar uma nova senha. O link vale por 1 hora.</p>
    <p style="margin:0 0 24px">
      <a href="{link}" style="display:inline-block;background:#4f46e5;color:#fff;
         text-decoration:none;padding:11px 22px;border-radius:8px;font-size:14px;
         font-weight:500">Criar nova senha</a>
    </p>
    <p style="margin:24px 0 0;font-size:12px;color:#94a3b8;border-top:1px solid #f1f5f9;
              padding-top:16px">
      Se não foi você que pediu, ignore este e-mail — sua senha continua a mesma.<br>
      Mensagem automática — não responda.
    </p>
  </div>
</body></html>"""

    try:
        msg = EmailMessage()
        msg["Subject"] = assunto
        msg["From"] = f"{settings.SMTP_FROM_NOME} <{_remetente()}>"
        msg["To"] = destino
        msg.set_content(texto)
        msg.add_alternative(html, subtype="html")

        ctx = ssl.create_default_context()
        if not settings.SMTP_VERIFICAR_CERT:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            log.warning("SMTP com verificação de certificado DESLIGADA")

        if settings.SMTP_SSL:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT,
                                  context=ctx, timeout=20) as s:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as s:
                if settings.SMTP_USE_TLS:
                    s.starttls(context=ctx)
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.send_message(msg)
        log.info("e-mail de reset de senha enviado para %s", destino)
        return True
    except Exception as e:
        log.warning("falha ao enviar reset de senha: %s", e)
        return False


def _destinatarios_da_empresa(id_empresa: int, excluir_id_usuario: int | None = None
                              ) -> list[dict[str, Any]]:
    """
    Contatos ativos vinculados à empresa que aceitam aviso de benefício.

    Filtros que importam:
      - `@contato.invalid` — a sync gera e-mail sintético pros contatos do
        legado que não tinham e-mail (ver sync/contato.py). Mandar pra lá é
        garantir bounce.
      - `preferencias_notificacao->>'beneficio'` — o contato pode ter desligado.
        Default TRUE quando a chave não existe: contato migrado do legado não
        escolheu nada, e o silêncio não deve ser lido como "não quero saber".
      - `ue.ativo` e `u.ativo` — vínculo ou usuário desativado não recebe.
    """
    sql = """
        SELECT u.id, u.nome, u.email
          FROM bss.usuario_empresa ue
          JOIN bss_users u ON u.id = ue.id_usuario
         WHERE ue.id_empresa = %(id_empresa)s
           AND ue.ativo
           AND u.ativo
           AND u.perfil = 'empresa'
           AND u.email NOT LIKE '%%@contato.invalid'
           AND COALESCE((u.preferencias_notificacao->>'beneficio')::boolean, TRUE)
           AND (%(excluir)s::int IS NULL OR u.id <> %(excluir)s::int)
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"id_empresa": id_empresa, "excluir": excluir_id_usuario})
            return list(cur.fetchall())


def avisar_mensagem_nova(id_processo: int, id_autor: int) -> None:
    """
    Avisa os contatos da empresa que há mensagem nova no benefício.

    Chamada em BackgroundTask pelo POST de mensagens. Só dispara quando quem
    escreveu é da equipe da BSS e a mensagem NÃO é nota interna — o router
    decide isso antes de agendar.
    """
    if not _habilitado():
        return

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.id, p.protocolo, p.id_empresa,
                       e.razao_social AS empresa,
                       tb.nome        AS tipo_beneficio,
                       t.nome_completo AS trabalhador
                  FROM bss.processo_beneficio p
                  LEFT JOIN bss.empresa e        ON e.id  = p.id_empresa
                  LEFT JOIN bss.tipo_beneficio tb ON tb.id = p.id_tipo_beneficio
                  LEFT JOIN bss.trabalhador t     ON t.id  = p.id_trabalhador
                 WHERE p.id = %s
                """,
                (id_processo,),
            )
            proc = cur.fetchone()

    if not proc or not proc["id_empresa"]:
        return

    dest = _destinatarios_da_empresa(proc["id_empresa"], excluir_id_usuario=id_autor)
    if not dest:
        return

    protocolo = proc["protocolo"] or f"#{proc['id']}"
    link = f"{settings.APP_BASE_URL.rstrip('/')}/app/processo-detalhe.html?id={proc['id']}"
    assunto = f"Nova mensagem no benefício {protocolo}"

    # Sem o texto da mensagem, de propósito. Ver o cabeçalho deste módulo.
    texto = f"""Olá,

Há uma nova mensagem da equipe da BSS no benefício abaixo.

  Protocolo:   {protocolo}
  Tipo:        {proc['tipo_beneficio'] or '—'}
  Trabalhador: {proc['trabalhador'] or '—'}
  Empresa:     {proc['empresa'] or '—'}

Para ler e responder, acesse o portal:
{link}

Esta é uma mensagem automática — não responda a este e-mail.
Para deixar de receber estes avisos, ajuste suas preferências no portal.
"""

    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><body style="margin:0;padding:24px;background:#f8fafc;
      font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#334155">
  <div style="max-width:520px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;
              border-radius:12px;padding:28px">
    <h2 style="margin:0 0 4px;font-size:17px;color:#1e293b">Nova mensagem no seu benefício</h2>
    <p style="margin:0 0 20px;font-size:14px;color:#64748b">
      A equipe da BSS respondeu no benefício abaixo.</p>

    <table style="width:100%;font-size:14px;border-collapse:collapse">
      <tr><td style="padding:6px 0;color:#94a3b8;width:110px">Protocolo</td>
          <td style="padding:6px 0;font-family:monospace;color:#1e293b">{protocolo}</td></tr>
      <tr><td style="padding:6px 0;color:#94a3b8">Tipo</td>
          <td style="padding:6px 0">{proc['tipo_beneficio'] or '—'}</td></tr>
      <tr><td style="padding:6px 0;color:#94a3b8">Trabalhador</td>
          <td style="padding:6px 0">{proc['trabalhador'] or '—'}</td></tr>
      <tr><td style="padding:6px 0;color:#94a3b8">Empresa</td>
          <td style="padding:6px 0">{proc['empresa'] or '—'}</td></tr>
    </table>

    <p style="margin:24px 0 0">
      <a href="{link}" style="display:inline-block;background:#4f46e5;color:#fff;
         text-decoration:none;padding:11px 22px;border-radius:8px;font-size:14px;
         font-weight:500">Ler no portal</a>
    </p>

    <p style="margin:24px 0 0;font-size:12px;color:#94a3b8;border-top:1px solid #f1f5f9;
              padding-top:16px">
      Por segurança, o conteúdo da mensagem não é enviado por e-mail.<br>
      Mensagem automática — não responda. Para deixar de receber estes avisos,
      ajuste suas preferências no portal.
    </p>
  </div>
</body></html>"""

    _enviar([d["email"] for d in dest], assunto, texto, html)
