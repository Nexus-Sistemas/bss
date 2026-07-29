"""
Conexões de banco do BSS.

- get_pg_connection(): PostgreSQL (banco novo, fonte da verdade) — via POOL
- get_mysql_connection(): MySQL do SuiteCRM (somente leitura, opcional)

POR QUE UM POOL (23/07/2026)
----------------------------
Antes, cada request abria uma conexão nova no Postgres e fechava no fim. Com
1 usuário é imperceptível; sob carga vira gargalo — pagar o setup de conexão a
cada request, e risco de estourar max_connections.

O teste de carga (scripts/teste_carga.py) mostrou a vazão travando em ~22 req/s
com a latência crescendo linear com a concorrência. A cura são duas coisas
JUNTAS: mais workers no uvicorn (paralelismo real, driblando o GIL) e este pool
(reusar conexões + limitar quantas existem).

DIMENSIONAMENTO: max_connections do Postgres = 100. Com 4 workers × max_size 15
= 60 conexões no pior caso, sobra folga pra o sync noturno e psql manual. Se
mudar o nº de workers, revisar POOL_MAX pra manter (workers × POOL_MAX) < ~80.
"""

import atexit
import threading
from contextlib import contextmanager
from typing import Generator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings


# Teto de conexões POR WORKER. Ver dimensionamento no docstring do módulo.
POOL_MIN = 2
POOL_MAX = 15

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def _obter_pool() -> ConnectionPool:
    """
    Cria o pool na primeira chamada (lazy) e reusa depois.

    Lazy de propósito: os scripts de sync/inspeção importam este módulo mas
    muitos só falam com o MySQL — não faz sentido abrir conexões Postgres à toa
    só por importar. Com uvicorn --workers, cada worker é um processo separado
    e cria o seu próprio pool na primeira request.
    """
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                conninfo = (
                    f"host={settings.PG_HOST} port={settings.PG_PORT} "
                    f"dbname={settings.PG_DB} user={settings.PG_USER} "
                    f"password={settings.PG_PASSWORD}"
                )
                p = ConnectionPool(
                    conninfo=conninfo,
                    min_size=POOL_MIN,
                    max_size=POOL_MAX,
                    # Se o pool esgotar, a request espera no máx 10s por uma
                    # conexão e então falha — melhor erro rápido do que request
                    # pendurado indefinidamente.
                    timeout=10.0,
                    kwargs={"row_factory": dict_row},
                    open=True,
                )
                atexit.register(p.close)
                _pool = p
    return _pool


@contextmanager
def get_pg_connection() -> Generator[psycopg.Connection, None, None]:
    """
    Pega uma conexão do POOL (interface inalterada — os call sites não mudam).

    Uso:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()

    A conexão volta pro pool ao sair do `with`, não é fechada. O pool faz commit
    ou rollback automático conforme a transação terminou com/sem exceção.
    """
    with _obter_pool().connection() as conn:
        yield conn


def get_mysql_connection():
    """
    Abre conexão com o MySQL do SuiteCRM legado em modo READ-ONLY.

    SEGURANÇA: este banco é a base de produção da GNB. Todas as queries
    feitas por este projeto são SELECT — mas pra blindar contra erros,
    a sessão MySQL é configurada como READ ONLY assim que conecta:
      SET SESSION TRANSACTION READ ONLY;
    Qualquer INSERT/UPDATE/DELETE/DDL aciona erro 1792.

    Importa pymysql só quando chamado, pra evitar dependência se não usado.
    """
    if not settings.MYSQL_HOST:
        raise RuntimeError(
            "MySQL legado não configurado. Defina MYSQL_HOST/MYSQL_DB/... no .env"
        )
    import pymysql
    import pymysql.cursors
    conn = pymysql.connect(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        database=settings.MYSQL_DB,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    # Blindagem: força a sessão a ser READ ONLY no servidor.
    # Qualquer escrita aciona ERROR 1792: "Cannot execute statement in a READ ONLY transaction."
    try:
        with conn.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
    except Exception:
        # Se o servidor MySQL não suportar (versão antiga), não bloqueia o uso —
        # nosso código segue só rodando SELECT mesmo.
        pass
    return conn
