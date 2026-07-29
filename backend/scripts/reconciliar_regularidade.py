"""
Recalcula bss.empresa.regularidade a partir dos boletos gerados.

Uso (na OCI):
    venv/bin/python -m scripts.reconciliar_regularidade
    venv/bin/python -m scripts.reconciliar_regularidade --dry-run

QUANDO RODAR
------------
- Depois de gerar boletos (o pico mensal preenche meses e pode "regularizar"
  uma empresa, ou a virada do mês pode criar um novo buraco).
- Idealmente num job mensal, após a janela de geração (dia ~16).

REGRA (definição BSS, ver migração 24):
  Irregular = existe algum mês, desde o 1º boleto, sem boleto gerado.
  Cancelado conta como mês gerado. É sobre GERAÇÃO, não pagamento.

Este script é a fonte da verdade da regularidade — a sync NÃO copia mais o
campo do legado (evita o cabo-de-guerra). Idempotente; só grava quem mudou.
"""

from __future__ import annotations

import argparse

from app.database import get_pg_connection


SQL_RECALCULAR = """
    UPDATE bss.empresa e
       SET regularidade = novo.valor, atualizado_em = NOW()
      FROM (
          SELECT e2.id,
                 CASE WHEN EXISTS (SELECT 1 FROM bss.empresa_meses_faltantes f
                                    WHERE f.id_empresa = e2.id)
                      THEN 'irregular' ELSE 'regular' END AS valor
            FROM bss.empresa e2
      ) novo
     WHERE novo.id = e.id
       AND e.regularidade IS DISTINCT FROM novo.valor
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="só mostra quantas mudariam, sem gravar")
    args = ap.parse_args()

    with get_pg_connection() as conn, conn.cursor() as cur:
        # Foto atual
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE regularidade = 'regular')   AS regulares,
                COUNT(*) FILTER (WHERE regularidade = 'irregular') AS irregulares,
                COUNT(*) FILTER (WHERE regularidade IS NULL)       AS sem_valor
              FROM bss.empresa
            """
        )
        antes = cur.fetchone()
        print(f"Antes: {antes['regulares']} regulares · "
              f"{antes['irregulares']} irregulares · {antes['sem_valor']} sem valor")

        if args.dry_run:
            cur.execute(
                """
                SELECT COUNT(*) AS mudariam
                  FROM bss.empresa e
                  JOIN LATERAL (
                      SELECT CASE WHEN EXISTS (SELECT 1 FROM bss.empresa_meses_faltantes f
                                                WHERE f.id_empresa = e.id)
                                  THEN 'irregular' ELSE 'regular' END AS valor
                  ) novo ON TRUE
                 WHERE e.regularidade IS DISTINCT FROM novo.valor
                """
            )
            print(f"  [dry-run] {cur.fetchone()['mudariam']} empresa(s) mudariam. Nada gravado.")
            return

        cur.execute(SQL_RECALCULAR)
        n = cur.rowcount
        conn.commit()
        print(f"  {n} empresa(s) atualizada(s).")

        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE regularidade = 'regular')   AS regulares,
                COUNT(*) FILTER (WHERE regularidade = 'irregular') AS irregulares
              FROM bss.empresa
            """
        )
        d = cur.fetchone()
        print(f"Depois: {d['regulares']} regulares · {d['irregulares']} irregulares")


if __name__ == "__main__":
    main()
