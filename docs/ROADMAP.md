# Roteiro do Organizador

Marque `[x]` ao concluir. Use `/proxima-fase` no Claude Code para saber onde parou.

## Fase 0 — Fundação
- [ ] Repositório Git + GitHub, README inicial *(Git e README ok; falta criar o repositório no GitHub)*
- [x] `docker-compose.yml` com PostgreSQL 16, Garage (+ serviço `garage-init`: layout, chave e bucket) e Adminer
- [x] `.env.example` e `.gitignore`
- [x] Projeto FastAPI com config via `.env`, conexão com o banco e rota `/health`
- [x] Alembic configurado

## Fase 1 — Banco de dados completo
- [ ] Tabela `users`
- [ ] `tasks`
- [ ] `routines` e `routine_logs`
- [ ] `pantry_items` e `shopping_items`
- [ ] `pets` e `pet_events`
- [ ] `transactions` e `budgets`
- [ ] `files` (polimórfica)
- [ ] Script de dados de exemplo (seed)
- [ ] Diagrama do banco no README (Mermaid)

## Fase 2 — Autenticação + Afazeres (módulo modelo)
- [ ] Cadastro, login e JWT
- [ ] CRUD de tarefas com filtros (status, prazo, prioridade)
- [ ] Testes

## Fase 3 — Módulos (`/novo-modulo <nome>`)
- [ ] Rotina
- [ ] Despensa
- [ ] Mercado (com "gerar lista a partir da despensa")
- [ ] Pets
- [ ] Finanças (orçamento por categoria, contas a pagar)
- [ ] Arquivos (upload/download com URL temporária no Garage, via API S3)
- [ ] Painel (endpoint que agrega o resumo do dia)

## Fase 4 — Frontend
- [ ] Projeto React + TS + Vite + Tailwind, login
- [ ] Uma tela por módulo
- [ ] Painel com gráficos

## Fase 5 — Qualidade e instalação na rede local
- [ ] GitHub Actions (lint + testes + build em todo PR)
- [ ] Dockerfiles de produção (API e frontend) e proxy reverso (Nginx/Caddy) na porta 80
- [ ] `docker-compose.yml` sobe tudo; serviços com `restart: unless-stopped` (voltam sozinhos após reiniciar o PC)
- [ ] IP fixo para o servidor (reserva de DHCP no roteador) e teste de acesso pelo celular
- [ ] Backup diário automático (pg_dump + cópia do bucket do Garage via S3) com rotação dos arquivos antigos
- [ ] Script de restauração de backup testado
- [ ] Logs centralizados e página `/health` mostrando o status dos serviços
- [ ] Instalar como app no celular (PWA)

## Fase 6 — IA (diferencial de portfólio)
- [ ] Modelo local com Ollama (funciona sem internet), API externa como opcional
- [ ] Leitura de cupom fiscal por foto → despensa + despesa
- [ ] Assistente com RAG sobre os seus dados (pgvector)
- [ ] Sugestão de lista de compras pelo histórico
