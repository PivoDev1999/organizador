# Roteiro do Organizador

Marque `[x]` ao concluir. Use `/proxima-fase` no Claude Code para saber onde parou.

## Fase 0 — Fundação
- [x] Repositório Git + GitHub, README inicial
- [x] `docker-compose.yml` com PostgreSQL 16, Garage (+ serviço `garage-init`: layout, chave e bucket) e Adminer
- [x] `.env.example` e `.gitignore`
- [x] Projeto FastAPI com config via `.env`, conexão com o banco e rota `/health`
- [x] Alembic configurado

## Fase 1 — Banco de dados completo
- [x] Tabela `users`
- [x] `tasks`
- [x] `routines` e `routine_logs`
- [x] `pantry_items` e `shopping_items`
- [x] `pets` e `pet_events`
- [x] `transactions` e `budgets`
- [x] `files` (polimórfica)
- [x] Script de dados de exemplo (seed)
- [x] Diagrama do banco no README (Mermaid)

## Fase 2 — Autenticação + Afazeres (módulo modelo)
- [x] Cadastro, login e JWT
- [x] CRUD de tarefas com filtros (status, prazo, prioridade, atraso, busca, ordenação e paginação)
- [x] Testes

## Fase 3 — Módulos (`/novo-modulo <nome>`)
> Pendências herdadas da revisão da Fase 1:
> - O `user_id` de registros filhos (`pet_events`, `routine_logs`, gastos de pet, itens de mercado ligados à despensa) vem sempre do usuário autenticado; o banco rejeita vínculo entre usuários (FK composta).
> - Download de arquivos: decidido o download pela própria API, em streaming (`GET /api/files/{id}/download`). O Garage continua só em `127.0.0.1`, sem URL pré-assinada nem rota `/s3` no proxy.
- [x] Rotina
- [x] Despensa
- [x] Mercado (com "gerar lista a partir da despensa")
- [x] Pets (eventos e lembretes de próximas datas)
- [x] Finanças (orçamento por categoria, contas a pagar)
  - Ao gravar ou alterar `transactions.pet_id`, chamar `pet_repo.exists_for_user` (KEY SHARE no pet) **antes** de travar a transação, para seguir a ordem pet → transação do DELETE do pet (que faz SET NULL nas transações); senão há deadlock
  - Regime de competência: o mês de uma transação é o do `due_date`, paga ou não (resumo mensal e `spent` do orçamento)
  - Categoria de orçamento é única por mês sem diferenciar maiúsculas; hoje garantido por `pg_advisory_xact_lock` por (usuário, mês). Melhoria estrutural futura (exige migration): índice único em `(user_id, lower(category COLLATE "pt-BR-x-icu"), month)`, e um índice funcional equivalente em `transactions` para o filtro por categoria
- [x] Arquivos (upload e download em streaming pela API, Garage via API S3; limpeza de órfãos com `python -m scripts.cleanup_orphans`)
  - [x] Ao apagar uma entidade (tarefa, pet etc.), apagar também os anexos em `files` e no Garage (a relação polimórfica não tem FK)
  - Melhoria futura: cota de armazenamento por usuário (soma de `files.size_bytes`), checada no upload
- [x] Painel (endpoint que agrega o resumo do dia: `GET /api/dashboard`)
  - Alerta de orçamento, decidido com os valores exatos (sem o arredondamento do `percent_used` exibido): `warning` com gasto de 80% a 100% do orçamento (inclusive), `exceeded` com gasto maior que o orçamento; orçamento 0 com gasto conta como `exceeded`, sem gasto não alerta (`app/core/finance.py`)

## Fase 4 — Frontend
- [x] Projeto React + TS + Vite + Tailwind, login
  - Pendência: a partir de 29/10/2026, subir `undici` para 7.30.1 (via `overrides`) — vulnerabilidade alta só no ambiente de testes (jsdom), fora do bundle
  - Dependências novas: instalar com `npm install --before=<data de hoje − 14 dias>` para manter a regra das 2 semanas também nas indiretas
- [x] Uma tela por módulo
  - PDF inline com CSP sandbox: resolvido no frontend. O componente de anexos baixa com `fetch` + token e exibe um blob (`URL.createObjectURL`); o blob não carrega os headers da resposta (CSP `sandbox`), então o visualizador de PDF do Chrome não é bloqueado e a API mantém `default-src 'none'; sandbox`. A pré-visualização só aceita os tipos confirmados pela API com `?inline=true` (JPEG, PNG, GIF, WebP, PDF); o resto é baixado
- [x] Painel com gráficos (cards por módulo, ação rápida de rotina com atualização otimista, gráficos de despesas por categoria e uso dos orçamentos com Recharts carregados sob demanda; nível do orçamento com a mesma regra exata do backend em `src/lib/decimal.ts`)

## Fase 5 — Qualidade e instalação na rede local
- [x] GitHub Actions (lint + testes + build em todo PR, incluindo o build das imagens Docker)
- [x] Dockerfiles de produção (API e frontend) e proxy reverso (Nginx) na porta 80
  - [x] Limite no proxy do corpo do `POST /api/files` (`MAX_UPLOAD_MB` + 2 MB), como segunda barreira ao limite que a API já aplica; 1 MB no resto de `/api`
- [x] Servir os assets do Swagger (`/api/docs`) localmente (pacote `swagger-ui-dist`, sem CDN)
- [x] Limite de tentativas no `POST /api/auth/login` no proxy (`limit_req` do Nginx: 5 por minuto por IP, 429)
- [x] `docker-compose.yml` sobe tudo; serviços com `restart: unless-stopped` (voltam sozinhos após reiniciar o PC)
- [ ] IP fixo para o servidor (reserva de DHCP no roteador) e teste de acesso pelo celular
- [ ] Backup diário automático (pg_dump + cópia do bucket do Garage via S3) com rotação dos arquivos antigos
- [ ] Script de restauração de backup testado
- [ ] Logs centralizados e página `/health` mostrando o status dos serviços

## Fase 6 — IA (diferencial de portfólio)
- [ ] Modelo local com Ollama (funciona sem internet), API externa como opcional
- [ ] Leitura de cupom fiscal por foto → despensa + despesa
- [ ] Assistente com RAG sobre os seus dados (pgvector)
- [ ] Sugestão de lista de compras pelo histórico
