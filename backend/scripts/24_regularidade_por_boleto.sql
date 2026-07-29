-- ============================================================================
-- 24_regularidade_por_boleto.sql — regularidade calculada sobre BOLETO
-- ============================================================================
--
-- DEFINIÇÃO (confirmada pela BSS, 23/07/2026):
--   Empresa é IRREGULAR se, em algum mês depois do 1º boleto, DEIXOU DE GERAR
--   boleto. É sobre GERAÇÃO, não pagamento.
--     - Irregular ≠ inadimplente. Inadimplente = gerou e não pagou (outro eixo).
--     - Uma empresa pode estar irregular SEM nenhum boleto vencido: o buraco
--       foi no passado, ela só não gerou num mês.
--     - Boleto CANCELADO conta como "mês gerado" (foi emitido, depois cancelado
--       e reemitido — o mês foi coberto).
--
-- POR QUE MUDAR: a view antiga calculava sobre bss.lista_mensal (planilha
-- entregue), fonte que está VAZIA no nosso banco (0 empresas só com planilha).
-- Medição (scripts/verificar_regularidade.py): a fórmula por boleto reproduz o
-- legado em 90,7%, contra 81,2% da planilha. Os ~9% restantes são o próprio
-- cache do legado desatualizado (campo derivado não-confiável — mesma classe do
-- qtd_trabalhadores).
--
-- TENTATIVA DESCARTADA: "só conta o mês se a empresa tinha trabalhador" piorou
-- (80%), porque não temos histórico de trabalhador mês a mês e o proxy usado
-- ("ativo hoje") apagava irregularidades reais. Fica como refinamento futuro,
-- quando o BSS acumular as cargas mensais. Ver verificar_regularidade.py.
--
-- Aplicar:
--     venv/bin/python -m scripts.aplicar_sql scripts/24_regularidade_por_boleto.sql
-- ============================================================================

-- 1) View de meses faltantes, agora sobre BOLETO. Mesmas colunas da anterior
--    (id_empresa, mes_faltante) — quem consome não muda.
CREATE OR REPLACE VIEW bss.empresa_meses_faltantes AS
WITH primeiro AS (
    -- Janela começa no 1º boleto de cada empresa. Qualquer status conta como
    -- "mês gerado" (inclusive cancelado).
    SELECT id_empresa, MIN(mes_referencia) AS desde
      FROM bss.boleto
     WHERE mes_referencia IS NOT NULL
     GROUP BY id_empresa
),
meses_esperados AS (
    SELECT p.id_empresa, gs::DATE AS mes_esperado
      FROM primeiro p
      CROSS JOIN LATERAL generate_series(
          p.desde,
          -- Até o mês ANTERIOR ao atual: o mês corrente ainda está em curso
          -- (os clientes geram por volta do dia 13-15), não é falha ainda.
          (DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month')::DATE,
          INTERVAL '1 month'
      ) AS gs
),
meses_gerados AS (
    SELECT DISTINCT id_empresa, mes_referencia
      FROM bss.boleto
     WHERE mes_referencia IS NOT NULL
)
SELECT me.id_empresa,
       me.mes_esperado AS mes_faltante
  FROM meses_esperados me
  LEFT JOIN meses_gerados g
         ON g.id_empresa = me.id_empresa
        AND g.mes_referencia = me.mes_esperado
 WHERE g.mes_referencia IS NULL;

COMMENT ON VIEW bss.empresa_meses_faltantes IS
    'Meses em que a empresa NÃO gerou boleto, desde o 1º. Base da regularidade (ver migração 24).';


-- 2) Recomputa regularidade de TODAS as empresas a partir da view.
--    A partir de agora o campo é NOSSO (calculado), não copiado do legado.
UPDATE bss.empresa e
   SET regularidade = CASE
           WHEN EXISTS (SELECT 1 FROM bss.empresa_meses_faltantes f
                         WHERE f.id_empresa = e.id)
           THEN 'irregular' ELSE 'regular' END,
       atualizado_em = NOW();


-- 3) Ajusta a mensagem da função de bloqueio: agora é "sem boleto gerado",
--    não "sem planilha". A LÓGICA não muda (conta os meses faltantes da view).
CREATE OR REPLACE FUNCTION bss.motivo_bloqueio_processo(p_id_trabalhador BIGINT)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_id_empresa  BIGINT;
    v_inadimp     RECORD;
    v_meses_emp   INT;
    v_meses_trab  INT;
BEGIN
    SELECT t.id_empresa_atual INTO v_id_empresa
    FROM bss.trabalhador t WHERE t.id = p_id_trabalhador;

    IF v_id_empresa IS NULL THEN
        RETURN 'Trabalhador sem vínculo ativo com empresa';
    END IF;

    -- (1) Empresa inadimplente (gerou e não pagou)
    SELECT * INTO v_inadimp FROM bss.empresa_inadimplencia
    WHERE id_empresa = v_id_empresa;
    IF FOUND THEN
        RETURN format(
            'Empresa inadimplente: %s boleto(s) vencido(s) (R$ %s) desde %s',
            v_inadimp.qtd_boletos_vencidos,
            v_inadimp.valor_em_atraso,
            v_inadimp.vencido_desde
        );
    END IF;

    -- (2) Empresa irregular (deixou de gerar boleto em algum mês)
    SELECT COUNT(*) INTO v_meses_emp FROM bss.empresa_meses_faltantes
    WHERE id_empresa = v_id_empresa;
    IF v_meses_emp > 0 THEN
        RETURN format('Empresa irregular: %s mês(es) sem boleto gerado', v_meses_emp);
    END IF;

    -- (3) Trabalhador com lacuna de contribuição
    SELECT COUNT(*) INTO v_meses_trab FROM bss.trabalhador_lacunas
    WHERE id_trabalhador = p_id_trabalhador;
    IF v_meses_trab > 0 THEN
        RETURN format('Trabalhador com %s mês(es) sem contribuição', v_meses_trab);
    END IF;

    RETURN '';  -- sem bloqueio
END;
$$;
