# BSS — Especificação de Infraestrutura para Produção (AWS)


## 1. Lista de recursos (resumo para o time AWS)

| # | Recurso | Serviço AWS | Tamanho sugerido | Observação |
|---|---|---|---|---|
| 1 | Servidor de aplicação | EC2 (2×, em AZs diferentes) | **c6i.xlarge** (4 vCPU / 8 GB) | 2 unidades atrás do Load Balancer (HA). Núcleos dimensionados p/ o PICO: nos dias 13-15 **todos os clientes** sobem planilha (parse de XLS = CPU) e geram boleto ao mesmo tempo. Ver §3.8 sobre escala elástica no pico |
| 2 | Load Balancer | Application Load Balancer (ALB) | — | TLS termina aqui (certificado ACM) |
| 3 | Banco de dados (primário) | **RDS PostgreSQL 16**, Multi-AZ | **db.r6i.2xlarge** (8 vCPU / 64 GB) | Dimensionado PARA O PICO: o legado (t3.2xlarge, 8 vCPU) satura a **100% de CPU** nos dias 10-15. Igualamos os núcleos, mas com **performance fixa** (família r, não burstable) + índices corretos → o pico deixa de travar. Multi-AZ = standby automático |
| 4 | Réplica de leitura do banco | RDS Read Replica | **db.r6i.large** (2 vCPU / 16 GB) | Relatórios/BI (Metabase) e telas pesadas |
| 5 | Storage de documentos | **S3** (buckets privados) | — | Certidões, comprovantes (permanente, LGPD). Boletos NÃO ocupam storage — são gerados sob demanda (ver §3.5) |
| 6 | Segredos (senhas, chaves) | Secrets Manager ou SSM Parameter Store | — | Nunca em arquivo texto no servidor |
| 7 | Certificado TLS | ACM (AWS Certificate Manager) | — | Gratuito, renovação automática |
| 8 | Rede | VPC + subnets pública/privada, NAT | — | Banco isolado da internet |
| 9 | Monitoramento | CloudWatch (logs, métricas, alarmes) | — | Alertas de CPU, disco, conexões |
| 10 | Acesso administrativo | SSM Session Manager (sem SSH aberto) | — | Ou bastion host em subnet pública |

incluir na listagem os servidores de **Homologação**
incluir informações de rede/portas

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

## 7. Resumo executivo (uma linha por item pedido)

- **Servidor de aplicação:** 2× EC2 c6i.xlarge atrás de um Load Balancer (alta
  disponibilidade, deploy sem downtime), com escala agendada nos dias 13-15.
- **Servidor de banco:** RDS PostgreSQL 16, db.r6i.2xlarge, **Multi-AZ**
  (standby automático). Dimensionado para o pico que hoje trava o legado a 100%.
- **Réplica do banco:** RDS Read Replica db.r6i.large (relatórios e BI).
- **Storage:** S3 (buckets privados criptografados para documentos e backups).
  Boletos são gerados sob demanda e não ocupam storage; os milhões de boletos
  do legado não migram.
- **Além disso, recomendado:** ALB + ACM (TLS), SES (e-mail), Secrets Manager,
  Route 53, CloudWatch, VPC com banco em subnet privada, e um ambiente de
  homologação espelhado menor.
