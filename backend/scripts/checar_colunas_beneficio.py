"""
Confere se as colunas da migração 25 (campos de benefício) existem.

Uso (na OCI):
    venv/bin/python -m scripts.checar_colunas_beneficio

Diagnóstico do 500 ao gravar benefício: se as colunas não existem, a migração
25 não foi aplicada (o deploy dela falhou antes por causa do psycopg_pool).
"""

from app.database import get_pg_connection

ESPERADAS = {
    "trabalhador": ["genero", "nome_mae", "rg"],
    "processo_beneficio": ["beneficiario_nome_mae"],
}


def main() -> None:
    with get_pg_connection() as c, c.cursor() as k:
        tudo_ok = True
        for tabela, cols in ESPERADAS.items():
            k.execute(
                """
                SELECT column_name FROM information_schema.columns
                 WHERE table_schema = 'bss' AND table_name = %s
                   AND column_name = ANY(%s)
                """,
                (tabela, cols),
            )
            achadas = {r["column_name"] for r in k.fetchall()}
            for col in cols:
                ok = col in achadas
                tudo_ok = tudo_ok and ok
                print(f"  {'OK ' if ok else 'FALTA'}  bss.{tabela}.{col}")
        print()
        if tudo_ok:
            print("✓ Todas as colunas existem — migração 25 aplicada. O 500 é outra causa.")
        else:
            print("✗ Faltam colunas — aplicar: "
                  "venv/bin/python -m scripts.aplicar_sql scripts/25_beneficio_campos.sql")


if __name__ == "__main__":
    main()
