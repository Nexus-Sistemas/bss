-- ============================================================================
-- 26_seq_protocolo_avancar.sql — corrige a colisão de numero_processo
-- ============================================================================
--
-- SINTOMA: ao abrir um benefício novo, 500 com
--   UniqueViolation: duplicate key ... "processo_beneficio_numero_processo_key"
--   DETAIL: Key (numero_processo)=(21179) already exists.
--
-- CAUSA: gerar_protocolo() usa nextval('bss.seq_protocolo') como numero_processo,
-- mas a sequence estava atrás do MAIOR numero_processo já migrado do legado.
-- Então o "próximo" valor colidia com um que já existe. numero_processo tem
-- UNIQUE (processo_beneficio_numero_processo_key).
--
-- CORREÇÃO: avançar a sequence pra logo depois do maior numero_processo em uso.
-- setval com o MAX garante que o próximo nextval seja MAX+1, sem colisão.
--
-- Idempotente: pode rodar de novo; sempre reposiciona pro MAX atual.
--
-- Aplicar:
--     venv/bin/python -m scripts.aplicar_sql scripts/26_seq_protocolo_avancar.sql
-- ============================================================================

SELECT setval(
    'bss.seq_protocolo',
    GREATEST(
        (SELECT COALESCE(MAX(numero_processo), 0) FROM bss.processo_beneficio),
        (SELECT last_value FROM bss.seq_protocolo)
    )
);

-- Confere: o próximo valor tem que ser MAIOR que qualquer numero_processo atual.
-- (não altera nada; só mostra pra validação no log do aplicador)
SELECT
    (SELECT MAX(numero_processo) FROM bss.processo_beneficio) AS maior_atual,
    (SELECT last_value FROM bss.seq_protocolo)                AS seq_agora;
