-- ============================================================================
-- 29_tarefa_tipo_responsavel.sql — dois campos novos no checklist
-- ============================================================================
--
--   tipo        → classifica a demanda: Ajuste, Bug ou Melhoria
--   responsavel → quem toca a tarefa (hoje Larissa / Figueiredo). Texto livre
--                 de propósito: entra gente nova sem precisar de migração.
--
-- Aplicar:
--     venv/bin/python -m scripts.aplicar_sql scripts/29_tarefa_tipo_responsavel.sql
-- ============================================================================

ALTER TABLE bss.tarefa
    ADD COLUMN IF NOT EXISTS tipo        VARCHAR(20)
        CHECK (tipo IS NULL OR tipo IN ('ajuste','bug','melhoria')),
    ADD COLUMN IF NOT EXISTS responsavel VARCHAR(40);

CREATE INDEX IF NOT EXISTS idx_tarefa_responsavel ON bss.tarefa (responsavel, status);
