-- ============================================================================
-- 30_usuarios_admin.sql — gestão básica de usuários internos + reset de senha
-- ============================================================================
--
-- Por ora todos os internos têm as MESMAS funções (é cedo pra granular perfis).
-- O cadastro fica no básico: nome, departamento, cargo, e-mail, ativo. Senha se
-- resolve no login ("esqueci minha senha" self-service) — ver bss.reset_senha.
--
-- Aplicar:
--     venv/bin/python -m scripts.aplicar_sql scripts/30_usuarios_admin.sql
-- ============================================================================

-- 1) Campos organizacionais no usuário -------------------------------------
ALTER TABLE bss_users
    ADD COLUMN IF NOT EXISTS departamento VARCHAR(60),
    ADD COLUMN IF NOT EXISTS cargo        VARCHAR(60);

-- 2) Tokens de redefinição de senha ----------------------------------------
-- Guardamos só o HASH do token (sha256). Quem tiver acesso de leitura ao banco
-- não consegue forjar um link válido — o token em claro só existe no e-mail.
CREATE TABLE IF NOT EXISTS bss.reset_senha (
    id          BIGSERIAL PRIMARY KEY,
    id_usuario  INT NOT NULL REFERENCES bss_users(id) ON DELETE CASCADE,
    token_hash  CHAR(64) NOT NULL,           -- sha256 hex
    expira_em   TIMESTAMPTZ NOT NULL,        -- normalmente NOW() + 1h
    usado_em    TIMESTAMPTZ,                 -- carimbado ao redefinir (uso único)
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_reset_token ON bss.reset_senha (token_hash);
CREATE INDEX IF NOT EXISTS idx_reset_usuario ON bss.reset_senha (id_usuario);
