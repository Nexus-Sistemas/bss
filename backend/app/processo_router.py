"""
/processos — benefícios.

GET  /processos                        → lista com filtros
GET  /processos/{id}/detalhe|documentos|pagamentos|mensagens
POST /processos/{id}/mensagens         → escreve no canal (empresa ↔ analista)
GET  /processos/aguardando-resposta/contagem → número do sino
"""

from typing import Annotated

import json

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form,
                     HTTPException, UploadFile)
from pydantic import BaseModel, field_validator

from .auth import UsuarioInfo, usuario_logado
from . import notificacao, processo_repo, storage, tipo_beneficio_repo, trabalhador_repo


router = APIRouter(prefix="/processos", tags=["processos"])


@router.get("")
def listar(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    busca: str | None = None,
    status: str | None = None,
    status_categoria: str | None = None,
    tipo: str | None = None,
    id_empresa: int | None = None,
    id_sindicato: int | None = None,
    aguardando_resposta: bool = False,   # sino do analista
    so_nao_lidas: bool = False,          # sino do cliente
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "criado_em",
    desc: bool = True,
):
    # ESCOPO ≠ FILTRO.
    #
    # O escopo é o conjunto que o usuário PODE ver (vem do JWT). O filtro é o
    # que ele ESCOLHEU ver (vem da tela). Antes o router confundia os dois:
    # sem filtro, usava `usuario.empresas[0]` como se fosse escopo — e um
    # gestor de 11 CNPJs via os benefícios de um só, escolhido pelo banco.
    #
    # O portal legado não tem "empresa atual": lista tudo que o usuário
    # administra, com a empresa como coluna. É o comportamento correto.
    ids_empresa: list[int] | None = None
    ids_sindicato: list[int] | None = None
    if usuario.perfil == "empresa":
        if not usuario.empresas:
            return {"linhas": [], "total": 0, "pagina": 1,
                    "por_pagina": por_pagina, "paginas": 0}
        if id_empresa is not None and id_empresa not in usuario.empresas:
            raise HTTPException(403, "Empresa fora do escopo")
        # Escopo sempre aplicado, mesmo com filtro: o filtro estreita, nunca alarga.
        ids_empresa = usuario.empresas
    elif usuario.perfil == "sindicato":
        if not usuario.sindicatos:
            return {"linhas": [], "total": 0, "pagina": 1,
                    "por_pagina": por_pagina, "paginas": 0}
        # Escopo = todos os sindicatos do usuário; id_sindicato (seletor) estreita.
        if id_sindicato is not None and id_sindicato not in usuario.sindicatos:
            raise HTTPException(403, "Sindicato fora do escopo")
        ids_sindicato = usuario.sindicatos
    elif usuario.perfil == "funeraria":
        # A funerária opera SÓ Acionamento Funeral, mas de forma GLOBAL (qualquer
        # empresa/sindicato) — ela é a operadora do benefício. Força o tipo e não
        # aplica escopo de empresa/sindicato.
        tipo = "acionamento_funeral"
    elif usuario.perfil not in processo_repo.PERFIS_INTERNOS:
        # Outro perfil externo sem escopo nesta lista: default-deny.
        return {"linhas": [], "total": 0, "pagina": 1,
                "por_pagina": por_pagina, "paginas": 0}

    # Marca d'água de leitura só interessa a quem não é da equipe: o sino do
    # analista é derivado de quem falou por último (ver contar_nao_lidas).
    eh_interno = usuario.perfil in processo_repo.PERFIS_INTERNOS
    uid_leitura = None if eh_interno else usuario.id

    return processo_repo.listar(
        busca=busca, status=status, status_categoria=status_categoria, tipo=tipo,
        id_empresa=id_empresa, ids_empresa=ids_empresa,
        id_sindicato=id_sindicato, ids_sindicato=ids_sindicato,
        aguardando_resposta=aguardando_resposta,
        id_usuario_leitura=uid_leitura, so_nao_lidas=so_nao_lidas,
        pagina=pagina, por_pagina=por_pagina, ordem=ordem, desc=desc,
    )


# Teto por arquivo (o nginx de produção aceita 25M; alinhar com ele).
_MAX_ARQUIVO = 25 * 1024 * 1024


@router.post("", status_code=201)
async def criar(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    # Campos estruturados vão num JSON string (multipart não carrega objeto):
    dados: Annotated[str, Form()],
    # Arquivos + a categoria (código do tipo de documento) de cada um, em
    # arrays paralelos — arquivos[i] pertence a categorias[i].
    arquivos: Annotated[list[UploadFile], File()] = [],
    categorias: Annotated[list[str], Form()] = [],
):
    """
    Abre um benefício: cria o processo, grava os documentos e atualiza os
    complementares do trabalhador — tudo atômico. Não salva sem os documentos
    obrigatórios do tipo.

    `dados` (JSON): { cpf, tipo (codigo), data_evento, qtd_bebes,
        trabalhador: {data_nascimento, data_admissao, genero, nome_mae, rg},
        quem_recebe: 'proprio'|'outra',
        beneficiario: {nome, cpf, telefone, data_nasc, grau_parentesco,
                       nome_mae, cep, logradouro, numero, complemento,
                       bairro, cidade, uf}  # só se quem_recebe='outra'
    }
    """
    try:
        d = json.loads(dados)
    except json.JSONDecodeError:
        raise HTTPException(400, "dados inválidos (JSON malformado)")

    # 1) Trabalhador + ESCOPO (empresa só abre pra trabalhador das suas empresas)
    trab = trabalhador_repo.buscar_por_cpf(d.get("cpf", ""))
    if not trab:
        raise HTTPException(404, "Trabalhador não encontrado")
    if usuario.perfil == "empresa" and trab["id_empresa_atual"] not in usuario.empresas:
        raise HTTPException(403, "Trabalhador fora da sua cobertura")
    if usuario.perfil == "sindicato" and trab["id_sindicato_atual"] not in usuario.sindicatos:
        raise HTTPException(403, "Trabalhador fora do seu escopo")

    # 2) Cobertura (pode abrir benefício?)
    motivo = trabalhador_repo.motivo_bloqueio(trab["id"])
    if motivo:
        raise HTTPException(422, f"Não é possível abrir benefício: {motivo}")

    # 3) Tipo + o que ele exige
    #    Funerária só abre "Acionamento Funeral" (defesa no servidor, além do
    #    seletor travado no form).
    if usuario.perfil == "funeraria" and d.get("tipo") != "acionamento_funeral":
        raise HTTPException(403, "Funerária só pode abrir Acionamento Funeral")
    tipo = tipo_beneficio_repo.form_do_tipo(d.get("tipo", ""))
    if not tipo:
        raise HTTPException(400, "Tipo de benefício inválido")

    # 4) Validação dos documentos obrigatórios ANTES de salvar arquivo (não
    #    gravar lixo no storage se vai recusar).
    if len(arquivos) != len(categorias):
        raise HTTPException(400, "arquivos e categorias não batem")
    enviados = {c for c, a in zip(categorias, arquivos) if a and a.filename}
    doc_por_codigo = {doc["codigo"]: doc for doc in tipo["documentos"]}
    obrigatorios = {doc["codigo"] for doc in tipo["documentos"] if doc["obrigatorio"]}
    faltando = obrigatorios - enviados
    if faltando:
        nomes = [doc_por_codigo[c]["nome"] for c in faltando]
        raise HTTPException(422, "Documentos obrigatórios faltando: " + ", ".join(nomes))

    # 5) Salva os arquivos no storage (fora da transação — I/O). Se algum tipo
    #    de documento não pertence ao tipo de benefício, recusa.
    documentos = []
    for arq, cat in zip(arquivos, categorias):
        if not arq or not arq.filename:
            continue
        if cat not in doc_por_codigo:
            raise HTTPException(400, f"Documento '{cat}' não pertence a este tipo")
        conteudo = await arq.read()
        if len(conteudo) > _MAX_ARQUIVO:
            raise HTTPException(413, f"Arquivo '{arq.filename}' excede 25 MB")
        ref = storage.salvar(conteudo, arq.filename)
        documentos.append({
            "id_tipo_documento": None,   # resolvido logo abaixo
            "codigo": cat, "nome": arq.filename, "ref": ref,
            "mime": arq.content_type, "tamanho": len(conteudo),
        })

    # id_tipo_documento: o form_do_tipo devolve codigo/nome/obrigatorio/ordem,
    # mas não o id. Buscamos o id de cada tipo de documento deste benefício.
    ids_tipo_doc = tipo_beneficio_repo.ids_tipo_documento(tipo["id"])
    for doc in documentos:
        doc["id_tipo_documento"] = ids_tipo_doc.get(doc["codigo"])

    # 6) Beneficiário só se 'outra pessoa'
    beneficiario = d.get("beneficiario") if d.get("quem_recebe") == "outra" else None

    # 6b) Dados bancários só se o tipo pede. O titular_tipo vem da config do
    #     tipo ('beneficiario' ou 'empresa'), não da tela — a tela só coleta a
    #     conta; quem decide de quem ela é, é o tipo de benefício.
    dados_bancarios = None
    tipo_conta_dono = tipo["campos"].get("dados_bancarios")
    if tipo_conta_dono:
        db = d.get("dados_bancarios") or {}
        db["titular_tipo"] = tipo_conta_dono
        dados_bancarios = db

    # 7) Grava tudo, atômico
    trab_c = d.get("trabalhador", {})
    resultado = processo_repo.criar_beneficio(
        id_trabalhador=trab["id"],
        id_empresa=trab["id_empresa_atual"],
        id_sindicato=trab["id_sindicato_atual"],
        id_tipo_beneficio=tipo["id"],
        data_evento=d.get("data_evento"),
        qtd_bebes=d.get("qtd_bebes"),
        id_usuario=usuario.id,
        trab_complementos={
            "nome_completo": trab_c.get("nome_completo") or None,
            "data_nascimento": trab_c.get("data_nascimento") or None,
            "data_admissao": trab_c.get("data_admissao") or None,
            "genero": trab_c.get("genero") or None,
            "nome_mae": trab_c.get("nome_mae") or None,
            "rg": trab_c.get("rg") or None,
        },
        beneficiario=beneficiario,
        dados_bancarios=dados_bancarios,
        documentos=documentos,
    )
    return resultado


def _processo_no_escopo(id_processo: int, usuario: UsuarioInfo) -> dict:
    """Busca o processo e aplica RLS por perfil. Levanta 404/403."""
    p = processo_repo.buscar_detalhe(id_processo)
    if not p:
        raise HTTPException(404, "Processo não encontrado")
    if usuario.perfil in processo_repo.PERFIS_INTERNOS:
        return p
    if usuario.perfil == "empresa":
        if p.get("id_empresa") not in usuario.empresas:
            raise HTTPException(403, "Processo fora do escopo")
    elif usuario.perfil == "sindicato":
        if p.get("id_sindicato") not in usuario.sindicatos:
            raise HTTPException(403, "Processo fora do escopo")
    elif usuario.perfil == "funeraria":
        # Funerária só vê Acionamento Funeral (global).
        if p.get("tipo_beneficio_codigo") != "acionamento_funeral":
            raise HTTPException(403, "Processo fora do escopo")
    else:
        raise HTTPException(403, "Processo fora do escopo")
    return p


@router.get("/{id_processo}/detalhe")
def detalhe_completo(
    id_processo: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Cabeçalho do benefício: dados, beneficiário, endereço e dados bancários."""
    return _processo_no_escopo(id_processo, usuario)


@router.get("/{id_processo}/documentos")
def documentos(
    id_processo: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Checklist de documentos: o que o tipo exige x o que foi anexado."""
    p = _processo_no_escopo(id_processo, usuario)
    return processo_repo.listar_documentos(id_processo, p.get("id_tipo_beneficio"))


@router.get("/{id_processo}/pagamentos")
def pagamentos(
    id_processo: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Parcelas de contas a pagar do processo."""
    _processo_no_escopo(id_processo, usuario)
    return processo_repo.listar_pagamentos(id_processo)


@router.get("/{id_processo}/mensagens")
def mensagens(
    id_processo: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """
    Canal de mensagens do processo. Só a equipe da BSS vê as mensagens
    marcadas como internas.

    A checagem é LISTA BRANCA (`in PERFIS_INTERNOS`), não `!= "empresa"`.
    Com a lista negra anterior, qualquer perfil que não fosse exatamente
    'empresa' — sindicato, contabilidade, e qualquer perfil criado no futuro —
    lia as notas internas da equipe. Perfil novo deve nascer sem acesso e
    ganhá-lo de propósito, nunca o contrário.
    """
    _processo_no_escopo(id_processo, usuario)
    incluir_internas = usuario.perfil in processo_repo.PERFIS_INTERNOS
    msgs = processo_repo.listar_mensagens(id_processo, incluir_internas=incluir_internas)

    # Abrir a aba = ler. Carimba a marca d'água DEPOIS de montar a resposta,
    # senão o sino apagaria antes de o usuário ver o conteúdo.
    #
    # Só pra quem depende dela (não-internos): pro analista o sino é derivado
    # de quem falou por último e não precisa de marca. Escrever à toa criaria
    # linha por analista por processo, sem uso.
    if usuario.perfil not in processo_repo.PERFIS_INTERNOS:
        try:
            processo_repo.marcar_lido(id_processo, usuario.id)
        except Exception:
            # Falha ao marcar leitura não pode derrubar a leitura em si —
            # no pior caso o sino fica aceso mais um pouco.
            pass

    return msgs


@router.get("/motivos-rejeicao-documento")
def motivos_rejeicao_documento(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Catálogo de motivos de rejeição (dropdown da avaliação de documento)."""
    return processo_repo.listar_motivos_rejeicao()


class DocStatusIn(BaseModel):
    status: str                    # 'pendente' | 'aprovado' | 'rejeitado'
    motivo: str | None = None      # código do motivo (só rejeitado)
    observacao: str | None = None


@router.put("/documento/{id_processo_documento}/status")
def mudar_status_documento(
    id_processo_documento: int,
    dados: DocStatusIn,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Avalia um documento anexado (aceitar/rejeitar/em análise). Só interno."""
    if usuario.perfil not in processo_repo.PERFIS_INTERNOS:
        raise HTTPException(403, "Só a equipe interna avalia documentos")
    if dados.status not in ("pendente", "aprovado", "rejeitado"):
        raise HTTPException(400, "Status inválido")
    ok = processo_repo.mudar_status_documento(
        id_processo_documento, dados.status, usuario.id, dados.motivo, dados.observacao)
    if not ok:
        raise HTTPException(404, "Documento não encontrado")
    return {"ok": True}


@router.get("/{id_processo}/mensagens/contagem")
def mensagens_contagem(
    id_processo: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Contagem pro badge da aba (total + não lidas). NÃO marca leitura."""
    _processo_no_escopo(id_processo, usuario)
    eh_interno = usuario.perfil in processo_repo.PERFIS_INTERNOS
    return processo_repo.contar_mensagens(
        id_processo, incluir_internas=eh_interno, eh_interno=eh_interno)


class MensagemIn(BaseModel):
    corpo: str
    # Nota interna: conversa da equipe, invisível pro cliente. Só internos
    # podem marcar — o router ignora o que vier de externo.
    interno: bool = False
    # Mudança de status junto com a resposta (opcional, só internos).
    # Decisão da BSS: "analista escolhe ao responder".
    status_novo: str | None = None

    @field_validator("corpo")
    @classmethod
    def _valida_corpo(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("mensagem vazia")
        if len(v) > 10_000:
            raise ValueError("mensagem muito longa (máx. 10.000 caracteres)")
        return v


@router.post("/{id_processo}/mensagens", status_code=201)
def criar_mensagem(
    id_processo: int,
    dados: MensagemIn,
    tarefas: BackgroundTasks,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """
    Escreve no canal do processo. Empresa fala, analista responde.

    Regras:
      - qualquer perfil COM acesso ao processo pode escrever (o RLS de
        _processo_no_escopo já barrou quem não pode);
      - só interno marca `interno=True` — se um externo mandar, é ignorado
        silenciosamente, não dá erro. Erro aqui só ensinaria que a flag existe;
      - só interno muda status, e a mudança vai pro audit trail junto.
    """
    _processo_no_escopo(id_processo, usuario)
    eh_interno = usuario.perfil in processo_repo.PERFIS_INTERNOS
    # Externo pedindo nota interna é ignorado em silêncio — erro só ensinaria
    # que a flag existe.
    nota_interna = dados.interno and eh_interno

    msg = processo_repo.criar_mensagem(
        id_processo=id_processo,
        id_usuario=usuario.id,
        corpo=dados.corpo,
        interno=nota_interna,
        autor_eh_externo=not eh_interno,
    )

    if dados.status_novo:
        if not eh_interno:
            raise HTTPException(403, "Só a equipe interna muda o status")
        if not processo_repo.status_existe(dados.status_novo):
            raise HTTPException(400, f"Status inválido: {dados.status_novo}")
        # Comentário do andamento = a própria mensagem. Assim o histórico
        # de auditoria explica POR QUE o status mudou, em vez de registrar
        # uma transição órfã.
        processo_repo.mudar_status(
            id_processo=id_processo,
            status_novo=dados.status_novo,
            id_usuario=usuario.id,
            comentario=dados.corpo[:500],
        )

    # E-mail pro cliente quando a BSS responde. Em BackgroundTask: o POST
    # responde na hora e o SMTP não segura a tela de ninguém. Nota interna
    # NÃO notifica — é conversa da equipe.
    if eh_interno and not nota_interna:
        tarefas.add_task(notificacao.avisar_mensagem_nova, id_processo, usuario.id)

    return msg


@router.get("/status-disponiveis")
def status_disponiveis(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """
    Lista de status (bss.status_processo). Serve pra dois usos: o dropdown
    'mudar status para…' do analista E o filtro de status da tela de Benefícios.
    São só rótulos de workflow (não sensível), então qualquer usuário logado lê —
    a AÇÃO de mudar status é que fica restrita (ver mudar_status).
    """
    return processo_repo.listar_status_disponiveis()


@router.get("/aguardando-resposta/contagem")
def contar_aguardando_resposta(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """
    Número do sino no topo do módulo de Benefícios. A CONTA MUDA POR PERFIL:

    - equipe interna → processos cuja última mensagem veio do CLIENTE
      ("alguém esperando resposta"). Apaga sozinho quando a BSS responde.

    - cliente (empresa) → processos com mensagem que ELE ainda não leu.
      Aqui é preciso marca d'água (bss.processo_mensagem_leitura): o cliente
      muitas vezes lê e não responde, então "a última é da BSS" deixaria o
      sino aceso pra sempre.

    São perguntas diferentes de propósito, não inconsistência.

    ATENÇÃO À ORDEM: esta rota precisa vir antes de qualquer `/{id_processo}`
    que aceite string, senão o FastAPI tenta converter "aguardando-resposta"
    em int. Aqui está safe porque as rotas de id são todas `/{id}/algo`.
    """
    if usuario.perfil in processo_repo.PERFIS_INTERNOS:
        ids_sind = usuario.sindicatos if usuario.perfil == "sindicato" else None
        qtd = processo_repo.contar_aguardando_resposta(None, ids_sind)
        return {"aguardando": qtd, "modo": "aguardando_resposta"}

    ids_empresa = usuario.empresas if usuario.perfil == "empresa" else None
    qtd = processo_repo.contar_nao_lidas(usuario.id, ids_empresa)
    return {"aguardando": qtd, "modo": "nao_lidas"}


@router.get("/{id_processo}")
def detalhe(
    id_processo: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    p = processo_repo.buscar_por_id(id_processo)
    if not p:
        raise HTTPException(404, "Processo não encontrado")
    if usuario.perfil == "empresa" and p.get("id_empresa") not in usuario.empresas:
        raise HTTPException(403, "Processo fora do escopo")
    if usuario.perfil == "sindicato" and p.get("id_sindicato") not in usuario.sindicatos:
        raise HTTPException(403, "Processo fora do escopo")
    return p
