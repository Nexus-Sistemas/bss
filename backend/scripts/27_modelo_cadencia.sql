-- ============================================================================
-- 27_modelo_cadencia.sql — cadência de disparo dos modelos + log de envios
-- ============================================================================
--
-- Cada modelo de e-mail pode ter uma CADÊNCIA (quando disparar automaticamente):
--   'manual'      → só pelo botão "disparar agora"
--   'diaria_util' → todo dia útil (ex.: Boletos Vencidos)
--   'dias_do_mes' → em dias fixos (ex.: {14,28}); se postergar_fds e o dia cair
--                   no fim de semana, dispara na próxima segunda-feira
--
-- O PÚBLICO é fixo por modelo (calculado do dado real na hora — ver
-- app/modelo_publico.py); a cadência só diz QUANDO.
--
-- Aplicar:
--     venv/bin/python -m scripts.aplicar_sql scripts/27_modelo_cadencia.sql
-- ============================================================================

ALTER TABLE bss.modelo_email
    ADD COLUMN IF NOT EXISTS cadencia_tipo VARCHAR(20) NOT NULL DEFAULT 'manual'
        CHECK (cadencia_tipo IN ('manual', 'diaria_util', 'dias_do_mes')),
    ADD COLUMN IF NOT EXISTS cadencia_dias INT[],
    ADD COLUMN IF NOT EXISTS cadencia_postergar_fds BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN bss.modelo_email.cadencia_dias IS
    'Dias do mês pra cadencia_tipo=dias_do_mes (ex.: {14,28}).';


-- Log de cada e-mail disparado. Serve pra: (1) auditoria (o que foi enviado a
-- quem, quando); (2) NÃO reenviar o mesmo modelo ao mesmo e-mail no mesmo dia
-- (evita duplicata se o job rodar 2x ou manual + agendado no mesmo dia).
CREATE TABLE IF NOT EXISTS bss.modelo_email_envio (
    id              BIGSERIAL PRIMARY KEY,
    id_modelo       BIGINT NOT NULL REFERENCES bss.modelo_email(id) ON DELETE CASCADE,
    id_usuario_destino INT,          -- contato (perfil empresa) — se destinatario='contato'
    id_empresa      BIGINT,          -- se destinatario='empresa'
    email           VARCHAR(150) NOT NULL,
    assunto         TEXT,
    status          VARCHAR(12) NOT NULL,   -- 'enviado' | 'falha'
    erro            TEXT,
    origem          VARCHAR(12) NOT NULL DEFAULT 'manual',  -- 'manual' | 'agendado'
    -- redirecionado: TRUE quando a trava de teste desviou pra outro endereço
    redirecionado   BOOLEAN NOT NULL DEFAULT FALSE,
    enviado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_envio_modelo_data
    ON bss.modelo_email_envio (id_modelo, enviado_em);
-- Consulta "já enviei este modelo pra este e-mail hoje?"
CREATE INDEX IF NOT EXISTS idx_envio_dedup
    ON bss.modelo_email_envio (id_modelo, email, enviado_em);
