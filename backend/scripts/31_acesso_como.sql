-- ============================================================================
-- 31_acesso_como.sql — trilha de auditoria do "Acessar como"
-- ============================================================================
--
-- Um interno (analista) pode acessar o portal COMO um cliente, pra simular e
-- operar pelas empresas. Toda sessão dessas é registrada aqui: quem acessou
-- (interno), como quem (alvo), e cada ação mutante que fez enquanto estava
-- "vestindo" o cliente. É o que garante que, mesmo a transação saindo pela
-- conta do cliente, o log deixe claro que foi FULANO (interno) quem fez.
--
--   evento = 'inicio' → abriu a sessão de acesso-como
--   evento = 'acao'   → executou um POST/PUT/PATCH/DELETE durante a sessão
--
-- Aplicar:
--     venv/bin/python -m scripts.aplicar_sql scripts/31_acesso_como.sql
-- ============================================================================

CREATE TABLE IF NOT EXISTS bss.acesso_como (
    id            BIGSERIAL PRIMARY KEY,
    id_interno    INT NOT NULL,               -- quem acessou (bss_users.id)
    nome_interno  VARCHAR(120),
    email_interno VARCHAR(120),
    id_alvo       INT NOT NULL,               -- acessado como (bss_users.id)
    nome_alvo     VARCHAR(120),
    email_alvo    VARCHAR(120),
    evento        VARCHAR(10) NOT NULL,       -- 'inicio' | 'acao'
    metodo        VARCHAR(8),                 -- POST/PUT/PATCH/DELETE (evento='acao')
    caminho       VARCHAR(300),               -- rota chamada (evento='acao')
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_acesso_como_interno ON bss.acesso_como (id_interno, criado_em DESC);
CREATE INDEX IF NOT EXISTS idx_acesso_como_alvo    ON bss.acesso_como (id_alvo, criado_em DESC);

COMMENT ON TABLE bss.acesso_como IS
    'Auditoria do "Acessar como": interno operando pelo portal do cliente.';
