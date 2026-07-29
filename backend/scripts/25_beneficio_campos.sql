-- ============================================================================
-- 25_beneficio_campos.sql — campos que só a abertura de benefício preenche
-- ============================================================================
--
-- Regra (PORTAL_EMPRESA.md): a carga mensal por planilha sobe o MÍNIMO (CPF,
-- nome, sindicato). Alguns dados só viram obrigatórios na hora do benefício —
-- e, uma vez informados, GRAVAM no trabalhador e são reaproveitados no próximo
-- benefício. São estes:
--
--   bss.trabalhador.genero    — gênero
--   bss.trabalhador.nome_mae  — nome da mãe do trabalhador
--   bss.trabalhador.rg        — RG
--
-- E o bloco Beneficiário (quando OUTRA pessoa recebe) precisa do nome da mãe
-- dela — o resto do bloco (nome, cpf, telefone, nascimento, grau, endereço) já
-- existe em processo_beneficio:
--
--   bss.processo_beneficio.beneficiario_nome_mae
--
-- Idempotente (ADD COLUMN IF NOT EXISTS): rodar de novo não quebra.
--
-- Aplicar:
--     venv/bin/python -m scripts.aplicar_sql scripts/25_beneficio_campos.sql
-- ============================================================================

ALTER TABLE bss.trabalhador
    ADD COLUMN IF NOT EXISTS genero   VARCHAR(20),
    ADD COLUMN IF NOT EXISTS nome_mae VARCHAR(200),
    ADD COLUMN IF NOT EXISTS rg       VARCHAR(30);

COMMENT ON COLUMN bss.trabalhador.genero   IS 'Preenchido na abertura de benefício; reaproveitado depois.';
COMMENT ON COLUMN bss.trabalhador.nome_mae IS 'Preenchido na abertura de benefício; reaproveitado depois.';
COMMENT ON COLUMN bss.trabalhador.rg       IS 'Preenchido na abertura de benefício; reaproveitado depois.';

ALTER TABLE bss.processo_beneficio
    ADD COLUMN IF NOT EXISTS beneficiario_nome_mae VARCHAR(200);

COMMENT ON COLUMN bss.processo_beneficio.beneficiario_nome_mae IS
    'Nome da mãe do beneficiário — só quando quem recebe é OUTRA pessoa.';
