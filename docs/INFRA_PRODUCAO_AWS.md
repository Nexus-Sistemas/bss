# BSS — Especificação de Infraestrutura para Produção (AWS)

**Sistema:** BSS — Benefício Social Sindical
**Objetivo:** ambiente de produção na AWS do cliente, para instalação da solução.
**Base do dimensionamento:** medições reais do ambiente de homologação (volume
de dados, teste de carga) — não estimativas às cegas.

> **Perfil de uso conhecido:** o sistema fica ocioso até ~dia 10 de cada mês e
> tem **pico nos dias 10 a 15** (importação de planilhas de até 5.000 linhas,
> ~350 mil trabalhadores, e geração de boletos). O dimensionamento contempla o
> pico; fora dele, sobra folga.

> **Calibrado contra o ambiente atual (produção legada, AWS).** O monitoramento
> revela um perfil **muito desigual**, e o dimensionamento abaixo responde aos
> DOIS extremos:
>
> - **Fora do pico:** carga leve — banco legado `db.t3.2xlarge` (8 vCPU/32 GB) a
>   **13% de CPU**, ~1.122 requisições **por dia**, app num `m1.small` a 2%.
> - **No pico (dias 10-15):** o mesmo banco vai a **99,8% de CPU (pico 100%),
>   status CRÍTICO** — é a lentidão que o cliente sente na virada do mês.
>
> Duas causas técnicas, ambas resolvidas na proposta nova: (1) o banco legado é
> **burstable** (família T), que estrangula num pico sustentado de vários dias —
> trocado por **família r (performance fixa)**; (2) a ação recomendada pela
> própria AWS é *"criar índices"* — o schema do BSS já nasce indexado. Os
> tamanhos abaixo são de hardware **moderno**, dimensionados para o pico
> **sem** repetir nem o excesso ocioso nem o gargalo de pico do ambiente atual.

---

## 1. Estratégia: começar MÍNIMO, medir, redimensionar

A solução nova deve ser **muito mais rápida que o legado** — índices corretos
(a AWS recomenda "criar índices" no legado; o BSS já nasce indexado) e estrutura
enxuta. Somado a isso, a concorrência real é baixa: **~80 contatos** têm
planilhas grandes; a maioria sobe listas pequenas, inofensivas.

Por isso a estratégia é: **montar a arquitetura completa, mas com máquinas
mínimas**, subir na AWS, rodar o **teste de carga** (script já pronto:
`scripts/teste_carga.py`) e **redimensionar só onde a medição pedir**. Evita
repetir o superdimensionamento do legado (que roda a 13% de CPU o mês todo).

### Lista de recursos — tier MÍNIMO

| # | Recurso | Serviço AWS | Tamanho mínimo (agora) | Alvo se o teste pedir |
|---|---|---|---|---|
| 1 | Servidor de aplicação | EC2 (2×, AZs diferentes) | **t3.medium** (2 vCPU / 4 GB) | c6i.xlarge (4 vCPU) |
| 2 | Load Balancer | Application Load Balancer (ALB) | — (obrigatório p/ TLS + HA) | — |
| 3 | Banco de dados | **RDS PostgreSQL 18**, single-AZ | **db.t4g.large** (2 vCPU / 8 GB) | db.r6i.xlarge + Multi-AZ |
| 4 | Réplica de leitura | RDS Read Replica | *(adicionar após 1º teste, se precisar)* | db.r6i.large |
| 5 | Storage de documentos | **S3** (buckets privados) | — (cresce sob demanda) | — |
| 6 | Segredos | Secrets Manager ou SSM Parameter Store | — | — |
| 7 | DNS | Route 53 | *(migrar quando for a virada)* | — |
| 8 | Certificado TLS | ACM | — (gratuito) | — |
| 9 | Rede | VPC + subnets pública/privada, NAT | — | — |
| 10 | Monitoramento | CloudWatch | — | — |
| 11 | Acesso administrativo | SSM Session Manager | — | — |

**Decisões desta rodada:**

- **PostgreSQL 18** (a versão mais moderna) desde o início.
- **Sem servidor de e-mail (SES):** usar o **SMTP atual**, já configurado no
  sistema. SES fica como evolução, se/quando o disparo em massa exigir escala.
- **Multi-AZ e réplica de leitura: ligados no go-live de produção**, não agora.
  Para o ambiente de teste/carga, single-AZ e sem réplica bastam e barateiam.
- **Mesma conta e região AWS** (us-east-1 — mesma do legado, sync intra-região).
- **Domínio migrado no DNS só na virada.** Durante o teste, acesso por um
  domínio temporário ou pelo nome do balanceador.

> Mesmo "mínimo", a **arquitetura é a completa** (ALB, subnet privada pro banco,
> S3, segredos gerenciados). Não é um atalho — é a mesma planta, com motores
> menores, prontos pra crescer com um resize de instância (poucos minutos de
> janela), sem redesenhar nada.

---

## 2. Arquitetura

```
                    Internet
                       │
                 [ Route 53 (DNS) ]
                       │
              [ ALB + TLS (ACM) ]        ← porta 443, público
                   │        │
        (AZ-a) [ App EC2 ] [ App EC2 ] (AZ-b)   ← subnet PRIVADA, stateless
                   │        │
        ┌──────────┴────────┴───────────┐
        │                               │
 [ RDS PostgreSQL 16 ]  ──replica──►  [ RDS Read Replica ]
   primário (Multi-AZ)                  (leitura/BI)
   subnet PRIVADA                       subnet PRIVADA
        │
   [ standby automático em outra AZ ]

   [ S3 ]  documentos + boletos + backups     ← acesso por IAM role
   [ SES ] envio de e-mail
```

**Princípios:**

- **Banco nunca exposto à internet** — vive em subnet privada, só aceita
  conexão do servidor de aplicação (security group dedicado).
- **Aplicação é stateless** (autenticação por token, sem sessão em memória) —
  por isso roda em 2 ou mais instâncias atrás do balanceador, e escala só
  adicionando instâncias.
- **Tudo criptografado** — em repouso (RDS, S3, discos EBS) e em trânsito (TLS).

---

## 3. Detalhamento por componente

### 3.1 Servidor de aplicação (EC2)

- **Instância:** c6i.xlarge (4 vCPU / 8 GB), **2 unidades** em AZs distintas.
- **Por que família "c" (compute):** a aplicação é limitada por CPU (Python/GIL
  serializa por núcleo → um worker por núcleo) e usa pouca RAM. Teste de carga:
  4 núcleos → ~80 requisições/s, folgado para dezenas de usuários simultâneos.
- **Alta disponibilidade:** com 2 instâncias atrás do ALB, a queda de uma não
  derruba o sistema, e dá para fazer deploy sem downtime (uma de cada vez).
- **Pico dias 10-15:** se o volume simultâneo crescer muito, subir para
  c6i.2xlarge (8 vCPU) ou acrescentar instâncias via Auto Scaling. Como o pico
  é previsível pelo calendário, um **redimensionamento agendado** resolve sem
  autoscaling reativo.
- **Disco:** 30-50 GB gp3 (só sistema operacional + aplicação; dados vão pro RDS
  e S3).
- **Software:** Ubuntu Server 24.04 LTS, Python 3.12, nginx (proxy reverso),
  a aplicação como serviço systemd (4 workers uvicorn por instância).

### 3.2 Load Balancer (ALB)

- **Application Load Balancer**, público, TLS terminando com certificado **ACM**
  (gratuito, renova sozinho — substitui o certbot da homologação).
- Health check nas instâncias; tira de rotação automaticamente a que falhar.
- **WAF (opcional, recomendado):** o endpoint de **autocadastro é público** —
  um WAF na frente protege contra abuso/bots. Sem ele, é obrigatório rate limit
  na aplicação antes de produção.

### 3.3 Banco de dados — RDS PostgreSQL (primário)

- **Serviço:** Amazon RDS for PostgreSQL **16** (a homologação roda 13; subir a
  versão na produção nova sai de graça e traz anos de suporte + performance).
- **Instância:** db.r6i.xlarge (4 vCPU / 32 GB) — família "r" (memory), para
  manter o dataset (~350k trabalhadores, 6,1M itens de boleto) e os índices em
  cache, evitando ir ao disco.
- **Multi-AZ:** liga um **standby automático em outra zona**. Se a máquina do
  banco cair, a AWS promove o standby sozinha, sem perda de dados. Para um
  sistema com dado pessoal sensível, isto não é luxo — é o mínimo.
- **Armazenamento:** 100 GB gp3 SSD, com **autoscaling de storage** ligado
  (cresce sozinho conforme o histórico aumenta). Provisionar IOPS se o pico de
  importação/sync exigir.
- **Backup:** automático, com **point-in-time recovery** (voltar o banco para
  qualquer minuto dos últimos 7-30 dias). Retenção sugerida: 14 dias.
- **Por que RDS e não Postgres num EC2:** backup, patch, failover e recuperação
  gerenciados pela AWS. Fazer isso à mão num EC2 é trabalho contínuo e risco.

### 3.4 Réplica de leitura (RDS Read Replica)

- **Instância:** db.r6i.large (2 vCPU / 16 GB).
- **Para quê:** desafogar o primário tirando dele as leituras pesadas —
  relatórios, BI (Metabase), e as telas com muitos `COUNT` (dashboard). O
  primário fica dedicado às escritas (importação, geração de boleto, sync).
- É uma réplica **assíncrona** — ótima para leitura/relatório; escrita continua
  só no primário.

### 3.5 Storage — S3

Dois buckets privados (nenhum público):

- **`bss-documentos`** — certidões, comprovantes, RG/CPF dos beneficiários.
  Dado pessoal sensível (LGPD): criptografia SSE, **versionamento** ligado,
  bloqueio de acesso público, e acesso só por **URL pré-assinada** (o sistema
  gera um link temporário quando o usuário autorizado pede o arquivo — o bucket
  nunca fica aberto). **Este é o único storage que cresce de verdade.**
- **`bss-backups`** — exportações e dumps.

Acesso pela aplicação via **IAM role** anexada à EC2 (sem chave de acesso
gravada em lugar nenhum). Regra de ciclo de vida (lifecycle) para mover arquivo
antigo para camada mais barata (S3-IA / Glacier) quando fizer sentido.

#### Boletos NÃO precisam de storage

Regra de negócio: **o boleto é efêmero**. Vence por volta do dia 15, e depois
disso não pode ser pago nem tem utilidade — o usuário gera um **novo** (a
reemissão já existe no sistema). Consequências:

- **O PDF do boleto é gerado sob demanda**, a partir do registro estruturado em
  `bss.boleto` (nosso número, linha digitável, valor, vencimento — tudo no
  banco). Não há por que persistir milhões de arquivos: o dado que importa é o
  registro, não o render.
- Se um cache de PDF do mês corrente for usado, uma regra de lifecycle o **apaga
  após o vencimento** — some sozinho.
- **Os milhões de boletos históricos do legado NÃO migram para o S3.** Só o
  registro (que a sincronização já traz para o banco, e é leve). Isso mantém o
  storage enxuto e evita trazer lixo permanente de um sistema que se descarta a
  cada mês.

> **Volume de storage real:** vem dos **documentos** (certidões, comprovantes),
> não dos boletos. Os binários dos documentos ainda estão no servidor do
> SuiteCRM legado e serão migrados no Big Bang; o dimensionamento exato do S3
> depende desse volume. S3 cresce sob demanda — nada a provisionar antecipado.

### 3.6 E-mail — SMTP atual (SES fica como evolução)

- Nesta fase, o sistema usa o **SMTP já configurado** (o mesmo da homologação).
  Nada a provisionar na AWS.
- **Evolução futura:** quando o disparo em massa (inadimplência, irregularidade)
  precisar escalar para milhares de e-mails com boa entregabilidade, migrar para
  **Amazon SES** (SPF/DKIM no domínio, barato, escalável). Não é necessário agora.

### 3.8 Escala elástica no pico mensal (dias 13-15)

O pico é **concentrado e previsível**: nos dias 13-15, praticamente toda a base
de empresas sobe planilha e gera boleto ao mesmo tempo. Fora dessa janela, o
sistema fica quase ocioso (como o legado, a 2-13% de CPU). Isso pede **escala
sob calendário**, não autoscaling reativo:

- **Opção A — Auto Scaling Group agendado (recomendada):** mantém 2 instâncias
  de app o mês todo e **acrescenta instâncias automaticamente nos dias 12-16**
  (scheduled scaling), removendo-as depois. Paga hardware extra só na janela do
  pico (~5 dias/mês), sem intervenção manual.
- **Opção B — tamanho fixo generoso:** manter 2× c6i.xlarge o tempo todo. Mais
  simples de operar; como a verba não é o gargalo, é aceitável.

**Aliviando o pico no software (evita ter de crescer tanto o hardware):**

- A importação de planilha já foi **otimizada para lote** (5.000 linhas gravam
  em ~2 s; testado com 12.000 em ~2 s). O gargalo do parse é CPU, endereçado
  pelo tier de app.
- **Evolução recomendada quando o pico crescer:** processar as importações e a
  geração de boletos em **fila de fundo** (Amazon SQS + workers). O upload é
  aceito na hora e processado por trás; a interface não trava mesmo com a base
  inteira submetendo junto, e os workers de processamento escalam separados do
  tier web. É a arquitetura que absorve a "manada" sem depender de hardware
  grande parado o mês todo.

### 3.9 Segredos, rede e acesso

- **Segredos** (senha do banco, chave JWT, credenciais SES): **Secrets Manager**
  ou **SSM Parameter Store** — nunca em arquivo `.env` no disco.
- **Rede (VPC):** subnets públicas (ALB, NAT) e privadas (app, banco); Internet
  Gateway + NAT Gateway. Security groups com regra mínima: ALB→app (443),
  app→banco (5432), admin→app via SSM.
- **Acesso administrativo:** **SSM Session Manager** (acesso ao servidor pelo
  console AWS, sem abrir porta SSH para a internet) ou um bastion host mínimo.
- **Monitoramento:** CloudWatch com alarmes de CPU, conexões do banco, espaço em
  disco e saúde das instâncias → notificação por e-mail (SNS).

---

## 4. A ponte com o legado (durante a coexistência)

Enquanto o SuiteCRM antigo estiver no ar, o BSS **sincroniza a partir dele**. O
legado é um **RDS MySQL na AWS, região us-east-1**.

- **Recomendação forte: manter a produção do BSS em `us-east-1`** (mesma região
  do legado). Assim a sincronização é intra-região, rápida e barata. Se a
  produção ficar em outra região/nuvem, cada sincronização atravessa a internet.
- O acesso ao MySQL legado é **somente leitura** e já está blindado no código.
- Um job agendado (EventBridge + o script de sync, ou cron no app server) roda a
  sincronização (hoje: noturna).

---

## 5. Backup, recuperação e continuidade

| Item | Estratégia |
|---|---|
| Banco | RDS backup automático + PITR (14 dias) + snapshots manuais antes de releases grandes |
| Banco (falha de zona) | Multi-AZ → failover automático |
| Documentos (S3) | Versionamento + (opcional) replicação cross-region para DR |
| Aplicação | Stateless — recriável a partir do repositório git + script de provisionamento |
| Segredos | Secrets Manager (versionado, com rotação possível) |

---

## 6. Itens em aberto (a alinhar com o cliente antes de provisionar)

1. **Conta e região AWS** — confirmar que será `us-east-1` (mesma do legado). Se
   o cliente exigir outra região, ajustar a estratégia de sync.
2. **Domínio** — qual domínio o portal usará em produção (para Route 53 + ACM).
3. **Volume de simultaneidade no pico** — se forem dezenas de usuários, o
   dimensionamento acima está folgado; se forem centenas, já partir de app
   c6i.2xlarge e considerar Auto Scaling.
4. **Volume dos documentos no legado** — para estimar o storage inicial do S3.
5. **VPC/conta do legado** — se o RDS MySQL antigo está em outra conta/VPC,
   pode ser preciso VPC peering ou regra de security group para o sync alcançá-lo.
6. **Janela do Big Bang** — a virada final (migrar binários dos documentos,
   trocar senhas de todos os usuários, desligar o legado).

---

## 7. O que solicitar ao admin AWS para PROVISIONAR o ambiente

Como é a conta do cliente, o admin não deve entregar poder de criação amplo.
Dois modelos, do mais recomendado ao alternativo:

### Modelo A (recomendado) — admin cria a base, nós instalamos a aplicação

O admin provisiona os recursos conforme esta especificação (VPC, RDS, EC2, S3,
ALB) e nos concede acesso **apenas ao necessário para instalar e operar o app**:

1. **Acesso aos servidores de aplicação** via **SSM Session Manager** (não
   precisa abrir SSH; o admin só anexa a role `AmazonSSMManagedInstanceCore` às
   EC2 e nos dá permissão de iniciar sessão). Alternativa: chave SSH + IP nosso
   liberado no security group.
2. **Endpoint e credenciais do RDS** — um usuário PostgreSQL da aplicação (não o
   master), entregue via **Secrets Manager** (nós lemos o segredo, nunca a senha
   em texto).
3. **IAM Role anexada às EC2 de app** com permissão de ler/gravar **apenas** nos
   buckets S3 do BSS (`bss-documentos`, `bss-backups`) — a aplicação usa a role,
   sem chave gravada.
4. **Bucket(s) S3** criados e criptografados, com acesso público bloqueado.

Com isso instalamos e mantemos o BSS sem precisar de permissão de criar/destruir
recursos na conta do cliente.

### Modelo B (alternativo) — nós provisionamos com IAM restrito

Se o cliente preferir que nós montemos tudo, pedir um **usuário IAM** (ou role
via SSO) chamado ex. `bss-deploy`, **restrito à região us-east-1**, com
permissão nos serviços: EC2, RDS, S3, VPC, ELB, ACM, CloudWatch, Secrets
Manager, Auto Scaling e IAM (só para criar as roles da aplicação — idealmente
com *permissions boundary*, que é o ponto que admins mais protegem).

> Recomendação: **Modelo A**. É o de menor privilégio, mantém o admin no
> controle da conta, e é suficiente para nós entregarmos e operarmos o sistema.

---

## 8. O que solicitar ao admin para ANALISAR os servidores do SuiteCRM

O objetivo é descobrir o **tamanho do storage a migrar** (documentos) e ter uma
foto completa dos servidores. A divisão importante:

**O banco (RDS MySQL), NÓS medimos** — temos conexão de leitura ao legado. Não
precisa do admin: rodamos uma query que lista o tamanho de cada tabela e o total.

**Os documentos, PRECISAM do admin** — os arquivos (certidões, comprovantes)
ficam no **filesystem do servidor de aplicação do SuiteCRM** (pasta de upload),
ao qual não temos acesso. Pedir ao admin para rodar, no servidor da aplicação
SuiteCRM, e enviar a saída:

```bash
# 1. Tamanho TOTAL da pasta de uploads do SuiteCRM (o número que vai pro S3).
#    O caminho costuma ser <raiz_do_suitecrm>/upload
du -sh /caminho/do/suitecrm/upload/

# 2. Quantidade de arquivos (impacta o tempo de migração, não só o tamanho)
find /caminho/do/suitecrm/upload/ -type f | wc -l

# 3. Uso de disco geral do servidor
df -h

# 4. Tipo de instância e volumes (ou pelo console EC2):
#    instância, vCPU/RAM, tamanho e uso de cada volume EBS
```

E, do **CloudWatch** (o cliente já tem o painel de Health Check — ótimo):

- Exportar o **CSV** do painel (há o botão "↓ CSV") na janela de **30 dias**,
  cobrindo pelo menos um ciclo de pico (dias 10-15), pra confirmarmos o
  comportamento sob carga real.
- Confirmar os **tipos de instância** de todos os recursos (EC2, RDS,
  ElastiCache se houver) e o **storage alocado** do RDS (não só o livre).

> Com a pasta de upload medida + as tabelas do banco (que medimos), fechamos o
> dimensionamento do S3 e a estimativa de tempo do Big Bang (migração dos
> binários).

### 8.1 Resultado da medição do banco legado (já feita)

Medido via nossa conexão de leitura (`scripts/medir_tamanho_legado.py`):

- **Banco inteiro: 11,28 GB** (5,38 GB dados + 5,90 GB índices, 293 tabelas).
- **Boa parte NÃO migra** (cruft do SuiteCRM): workflow (`aow_processed*` ~2,8 GB),
  e-mails (`emails*` ~1,3 GB), `job_queue` (256 MB), tabelas `_audit`. O dado de
  negócio efetivo é ~7 GB, e o maior item é a junção boleto↔trabalhador
  (4,2 GB / 7 M linhas — já sincronizada).
- **Conclusão de sizing do banco:** 11 GB é pequeno. Um `db.t4g.large`
  (2 vCPU / 8 GB) com 50-100 GB de disco gp3 atende com folga enorme.

**Documentos (o que dimensiona o S3):**

- `documents`: **~85.000** arquivos no total.
- `documents_cases`: **~22.000** ligados a processos (os documentos de benefício
  — o subconjunto que de fato interessa ao BSS).
- **Falta só o tamanho em bytes** (o `du -sh` do admin). Estimativa preliminar,
  a ~500 KB/arquivo: **~10 a 40 GB** no S3. Cresce sob demanda; nada a
  provisionar antecipado.

> Ou seja: o legado é **pequeno**. Isso reforça a estratégia de tier mínimo — a
> nova estrutura, indexada e enxuta, roda sobrando nesse porte de dados.

---

## 9. Resumo executivo (uma linha por item pedido)

**Tier mínimo (agora, para subir e testar carga):**

- **Servidor de aplicação:** 2× EC2 **t3.medium** atrás de um Load Balancer.
- **Servidor de banco:** RDS **PostgreSQL 18**, **db.t4g.large**, single-AZ.
- **Réplica / Multi-AZ:** adicionados no go-live de produção, não agora.
- **Storage:** S3 (buckets privados) só para **documentos** — boletos são
  gerados sob demanda; os milhões de boletos do legado não migram.
- **E-mail:** SMTP atual (sem SES nesta fase).
- **Arquitetura completa** mesmo no mínimo: ALB + ACM (TLS), Secrets Manager,
  VPC com banco em subnet privada, CloudWatch, acesso via SSM.

**Redimensionar sob evidência:** rodar `scripts/teste_carga.py` contra o
ambiente e subir instância só onde a medição pedir (resize de poucos minutos,
sem redesenho). Alvos prováveis se necessário: app → c6i.xlarge, banco →
db.r6i.xlarge + Multi-AZ + réplica de leitura.
