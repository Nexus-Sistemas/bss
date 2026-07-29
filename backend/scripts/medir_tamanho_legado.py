"""
Mede o tamanho do banco MySQL legado — por tabela e total.

Uso (na OCI):
    venv/bin/python -m scripts.medir_tamanho_legado

POR QUE
-------
Para dimensionar a migração pra AWS, precisamos saber o tamanho do legado. O
BANCO nós medimos aqui (temos conexão de leitura). Os DOCUMENTOS (arquivos no
filesystem do servidor SuiteCRM) precisam do admin — ver docs/INFRA_PRODUCAO_AWS.md §8.

Este script responde: quão grande é o banco, quais tabelas dominam, e destaca
as de documentos (metadados dos anexos — o binário não está aqui, está no disco
do app server).

SOMENTE LEITURA.
"""

from app.database import get_mysql_connection


def main() -> None:
    with get_mysql_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT DATABASE() AS db")
        db = cur.fetchone()["db"]
        print(f"\nBanco legado: {db}\n")

        # Tamanho total (dados + índices)
        cur.execute(
            """
            SELECT
                ROUND(SUM(data_length + index_length) / 1024 / 1024 / 1024, 2) AS gb_total,
                ROUND(SUM(data_length) / 1024 / 1024 / 1024, 2)                AS gb_dados,
                ROUND(SUM(index_length) / 1024 / 1024 / 1024, 2)              AS gb_indices,
                COUNT(*)                                                       AS tabelas
              FROM information_schema.TABLES
             WHERE table_schema = DATABASE()
            """
        )
        t = cur.fetchone()
        print(f"TOTAL: {t['gb_total']} GB  "
              f"(dados {t['gb_dados']} GB + índices {t['gb_indices']} GB)  "
              f"em {t['tabelas']} tabelas")

        # As 25 maiores tabelas
        cur.execute(
            """
            SELECT table_name AS nome,
                   ROUND((data_length + index_length) / 1024 / 1024, 1) AS mb,
                   table_rows AS linhas
              FROM information_schema.TABLES
             WHERE table_schema = DATABASE()
             ORDER BY (data_length + index_length) DESC
             LIMIT 25
            """
        )
        print("\n=== 25 MAIORES TABELAS ===")
        print(f"{'MB':>10}  {'linhas~':>12}  tabela")
        for r in cur.fetchall():
            print(f"{r['mb']:>10}  {r['linhas'] or 0:>12,}  {r['nome']}")

        # Foco: tabelas de documentos (metadados; o binário está no filesystem)
        cur.execute(
            """
            SELECT table_name AS nome,
                   ROUND((data_length + index_length) / 1024 / 1024, 1) AS mb,
                   table_rows AS linhas
              FROM information_schema.TABLES
             WHERE table_schema = DATABASE()
               AND (table_name LIKE '%%document%%' OR table_name LIKE '%%upload%%'
                    OR table_name LIKE '%%note%%' OR table_name LIKE '%%file%%')
             ORDER BY (data_length + index_length) DESC
            """
        )
        docs = cur.fetchall()
        if docs:
            print("\n=== TABELAS DE DOCUMENTOS (metadados — binário fica no disco do app) ===")
            for r in docs:
                print(f"{r['mb']:>10} MB  {r['linhas'] or 0:>10,} linhas  {r['nome']}")
            print("\n  → O número de LINHAS em documents/document_revisions indica")
            print("    quantos ARQUIVOS existem no filesystem do SuiteCRM. O admin")
            print("    mede o TAMANHO desses arquivos (du -sh da pasta upload).")

    print()


if __name__ == "__main__":
    main()
