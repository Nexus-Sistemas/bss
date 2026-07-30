"""
Autenticação por JWT — login + dependência usuario_logado.

Usa a tabela `bss_users` (criada por scripts/criar_tabela_usuarios.py).
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

from .config import settings
from .database import get_pg_connection


router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# === Hash / verificação de senha ===========================================

def hash_senha(senha_plana: str) -> str:
    return bcrypt.hashpw(senha_plana.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha_plana: str, hash_armazenado: str) -> bool:
    try:
        return bcrypt.checkpw(senha_plana.encode("utf-8"), hash_armazenado.encode("utf-8"))
    except Exception:
        return False


# === JWT ====================================================================

def criar_token(dados: dict) -> str:
    expira = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    dados = {**dados, "exp": expira}
    return jwt.encode(dados, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decodificar_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token inválido")


# === Schemas ================================================================

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UsuarioInfo(BaseModel):
    id: int
    email: str
    nome: str
    perfil: str                       # admin/interno/analista/empresa/sindicato/contabilidade
    # Vínculos N:N (vazios se perfil interno/admin/analista/contabilidade):
    empresas: list[int] = []          # IDs de bss.empresa que o usuário opera (perfil=empresa)
    sindicatos: list[int] = []        # IDs de bss.sindicato que o usuário vê (perfil=sindicato)
    # "Acessar como": quando um interno está operando pelo portal de um cliente,
    # o token carrega a identidade do CLIENTE (id/perfil acima), mas guarda aqui
    # QUEM de verdade está por trás. É o que permite auditar a transação no nome
    # do interno, mesmo ela saindo pela conta do cliente.
    imp_por: int | None = None
    imp_por_nome: str | None = None
    imp_por_email: str | None = None


# === Helpers de vínculo =====================================================

def _carregar_vinculos(conn, user_id: int, perfil: str) -> tuple[list[int], list[int]]:
    """Carrega empresas/sindicatos do usuário conforme o perfil.
    Internos/admin/analista/contabilidade não têm filtro (listas vazias).

    O ORDER BY não é estética. Vários routers usam `usuario.empresas[0]` como
    escopo padrão quando a requisição não manda id_empresa. Sem ORDER BY, o
    Postgres devolve a ordem que quiser — e essa ordem pode MUDAR sozinha
    (VACUUM, reescrita de página). Ou seja, "a primeira empresa do usuário"
    era, na prática, uma empresa aleatória e instável.

    Isso não é hipotético: um usuário com 11 vínculos abriu Trabalhadores e
    viu a tela vazia, porque o [0] caiu numa empresa sem trabalhador ativo.
    Com ORDER BY o padrão passa a ser sempre o mesmo — reproduzível, e o
    dropdown de troca (js/empresa-atual.js) cobre o resto.
    """
    empresas: list[int] = []
    sindicatos: list[int] = []
    with conn.cursor() as cur:
        if perfil == "empresa":
            cur.execute(
                "SELECT id_empresa FROM bss.usuario_empresa "
                "WHERE id_usuario = %s AND ativo "
                "ORDER BY id_empresa",
                (user_id,),
            )
            empresas = [r["id_empresa"] for r in cur.fetchall()]
        elif perfil == "sindicato":
            cur.execute(
                "SELECT id_sindicato FROM bss.usuario_sindicato "
                "WHERE id_usuario = %s AND ativo "
                "ORDER BY id_sindicato",
                (user_id,),
            )
            sindicatos = [r["id_sindicato"] for r in cur.fetchall()]
    return empresas, sindicatos


# === Endpoints ==============================================================

@router.post("/login", response_model=TokenResponse)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """Recebe form-data com 'username' (email) e 'password'."""
    sql = """
        SELECT id, email, nome, senha_hash, ativo, perfil
        FROM bss_users
        WHERE email = %s
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (form.username.strip().lower(),))
            user = cur.fetchone()

        erro = HTTPException(status_code=401, detail="Email ou senha inválidos")
        if not user:
            raise erro
        if not user["ativo"]:
            raise HTTPException(status_code=401, detail="Usuário desativado")
        if not verificar_senha(form.password, user["senha_hash"]):
            raise erro

        empresas, sindicatos = _carregar_vinculos(conn, user["id"], user["perfil"])

        # Atualiza ultimo_login (não falha login se der erro)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE bss_users SET ultimo_login = NOW() WHERE id = %s",
                    (user["id"],),
                )
            conn.commit()
        except Exception:
            conn.rollback()

    token = criar_token({
        "sub":        str(user["id"]),
        "email":      user["email"],
        "nome":       user["nome"],
        "perfil":     user["perfil"],
        "empresas":   empresas,
        "sindicatos": sindicatos,
    })
    return TokenResponse(access_token=token)


def usuario_logado(token: Annotated[str, Depends(oauth2_scheme)]) -> UsuarioInfo:
    """Dependência: use Depends(usuario_logado) em endpoints protegidos."""
    p = decodificar_token(token)
    return UsuarioInfo(
        id=int(p["sub"]),
        email=p["email"],
        nome=p["nome"],
        perfil=p.get("perfil", ""),
        empresas=p.get("empresas") or [],
        sindicatos=p.get("sindicatos") or [],
        imp_por=p.get("imp_por"),
        imp_por_nome=p.get("imp_por_nome"),
        imp_por_email=p.get("imp_por_email"),
    )


# Perfis da equipe da BSS. 'contabilidade' NÃO está aqui de propósito: os
# contadores estão entre os "gestores" das empresas clientes, ou seja, são
# externos — não podem ver dado consolidado da BSS. Mesmo conjunto usado pelo
# contato_router.
PERFIS_INTERNOS = {"admin", "interno", "analista"}


def exigir_interno(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
) -> UsuarioInfo:
    """
    Dependência pra endpoint que só a equipe da BSS pode ver.

    Use em qualquer endpoint cujo SQL seja global (sem WHERE por empresa ou
    sindicato). É a diferença entre "esqueci de filtrar" e "não filtra porque
    não deve filtrar" — e evita repetir o vazamento do dashboard, cujos 4
    endpoints recebiam o `usuario` e nunca o liam, entregando o faturamento
    da BSS pra qualquer um que logasse.
    """
    if usuario.perfil not in PERFIS_INTERNOS:
        raise HTTPException(403, "Acesso restrito à equipe interna")
    return usuario


@router.get("/me", response_model=UsuarioInfo)
def me(usuario: Annotated[UsuarioInfo, Depends(usuario_logado)]):
    return usuario


# === Esqueci / redefinir senha (self-service) ==============================

class EsqueciSenhaIn(BaseModel):
    email: str


class RedefinirSenhaIn(BaseModel):
    token: str
    nova_senha: str


_SENHA_MIN = 6


@router.post("/esqueci-senha")
def esqueci_senha(dados: EsqueciSenhaIn):
    """
    Dispara o e-mail com o link de redefinição.

    RESPOSTA NEUTRA de propósito: retorna sempre ok, exista ou não o e-mail.
    Assim a tela não vira um oráculo de "quem tem conta aqui" (enumeração de
    usuários). O envio roda inline — se o SMTP estiver fora, o e-mail não sai,
    mas a resposta é a mesma.
    """
    # Import tardio evita ciclo (usuario_repo → nada de auth, mas fica seguro).
    from . import usuario_repo, notificacao

    email = (dados.email or "").strip().lower()
    if email:
        user = usuario_repo.buscar_usuario_ativo_por_email(email)
        if user:
            token = usuario_repo.criar_token_reset(user["id"])
            link = (f"{settings.APP_BASE_URL.rstrip('/')}"
                    f"/app/redefinir-senha.html?token={token}")
            notificacao.enviar_reset_senha(user["email"], user["nome"], link)

    return {"ok": True,
            "mensagem": "Se o e-mail estiver cadastrado, enviamos um link de redefinição."}


@router.post("/redefinir-senha")
def redefinir_senha(dados: RedefinirSenhaIn):
    from . import usuario_repo

    if len((dados.nova_senha or "")) < _SENHA_MIN:
        raise HTTPException(400, f"A senha deve ter ao menos {_SENHA_MIN} caracteres")

    id_usuario = usuario_repo.consumir_token_reset((dados.token or "").strip())
    if not id_usuario:
        raise HTTPException(400, "Link inválido ou expirado. Solicite um novo.")

    usuario_repo.definir_senha(id_usuario, hash_senha(dados.nova_senha))
    return {"ok": True}


# === Acessar como (impersonação auditada) ==================================

@router.post("/acessar-como/{id_alvo}", response_model=TokenResponse)
def acessar_como(
    id_alvo: int,
    interno: Annotated[UsuarioInfo, Depends(exigir_interno)],
):
    """
    Emite um token que faz o interno operar o portal COMO o cliente `id_alvo`.

    Só a equipe interna aciona (exigir_interno). O alvo tem que ser um usuário
    EXTERNO (empresa/sindicato/contabilidade), ativo e com login de verdade —
    não dá pra "acessar como" outro interno nem como ficha sem e-mail.

    O token resultante carrega a identidade do CLIENTE (pra ver e fazer
    exatamente o que ele faria) MAIS as claims imp_por*, que amarram tudo ao
    interno. O início fica auditado em bss.acesso_como; as ações seguintes são
    auditadas pelo middleware.
    """
    from . import acesso_como

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, nome, perfil, ativo FROM bss_users WHERE id = %s",
                (id_alvo,),
            )
            alvo = cur.fetchone()

        if not alvo:
            raise HTTPException(404, "Usuário não encontrado")
        if alvo["perfil"] in PERFIS_INTERNOS:
            raise HTTPException(400, "Não é possível acessar como outro usuário interno")
        if not alvo["ativo"]:
            raise HTTPException(400, "Este usuário está inativo")
        if (alvo["email"] or "").endswith("@contato.invalid"):
            raise HTTPException(400, "Este contato não tem login no portal")

        empresas, sindicatos = _carregar_vinculos(conn, alvo["id"], alvo["perfil"])

    acesso_como.registrar(
        "inicio", interno.id, interno.nome, interno.email,
        alvo["id"], alvo["nome"], alvo["email"],
    )

    token = criar_token({
        "sub":           str(alvo["id"]),
        "email":         alvo["email"],
        "nome":          alvo["nome"],
        "perfil":        alvo["perfil"],
        "empresas":      empresas,
        "sindicatos":    sindicatos,
        "imp_por":       interno.id,
        "imp_por_nome":  interno.nome,
        "imp_por_email": interno.email,
    })
    return TokenResponse(access_token=token)
