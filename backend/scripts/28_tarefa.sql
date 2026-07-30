-- ============================================================================
-- 28_tarefa.sql — checklist de demandas (testes e ajustes da implantação)
-- ============================================================================
--
-- Substitui a planilha do OneDrive que a Nexus e a BSS usavam pra controlar
-- demandas. Simples de propósito: as colunas que eles já usavam (prioridade,
-- módulo, assunto, descrição, status, print) + auditoria mínima.
--
-- Uso interno (equipe Nexus + admin BSS). Não é do portal do cliente.
--
-- Aplicar:
--     venv/bin/python -m scripts.aplicar_sql scripts/28_tarefa.sql
-- ============================================================================

CREATE TABLE IF NOT EXISTS bss.tarefa (
    id            BIGSERIAL PRIMARY KEY,          -- o "seq" da planilha
    prioridade    SMALLINT NOT NULL DEFAULT 2,    -- 1=alta, 2=média, 3=baixa
    modulo        VARCHAR(40),                    -- Portal, Benefícios, Boletos...
    assunto       VARCHAR(200) NOT NULL,
    descricao     TEXT,
    status        VARCHAR(20) NOT NULL DEFAULT 'aberta'
                  CHECK (status IN ('aberta','em_dev','aguardando','resolvida','cancelada')),
    -- Print (screenshot) via storage — opcional, um por tarefa (ver app.storage)
    anexo_url     VARCHAR(500),
    anexo_nome    VARCHAR(255),
    criado_por_id INT,                            -- bss_users.id
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolvido_em  TIMESTAMPTZ                      -- preenchido quando vira 'resolvida'
);
CREATE INDEX IF NOT EXISTS idx_tarefa_status ON bss.tarefa (status);
CREATE INDEX IF NOT EXISTS idx_tarefa_prio   ON bss.tarefa (prioridade, status);

COMMENT ON TABLE bss.tarefa IS
    'Checklist de demandas da implantação (Nexus + BSS). Substitui a planilha do OneDrive.';
