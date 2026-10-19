# Organizador — instruções do projeto

Sistema pessoal de organização da casa: tarefas, rotina, compras, despensa, pets, finanças e arquivos.
Projeto de portfólio: deve seguir práticas de mercado (código limpo, testes, Docker, CI).

## Idioma
- Converse comigo em português.
- Código, nomes de tabelas, variáveis e commits em **inglês**. Textos da interface em português.

## Ambiente: somente rede local
- O sistema roda em um computador de casa (o "servidor") e é acessado pelos outros aparelhos da mesma rede Wi-Fi (PC, celular, tablet), pelo IP do servidor (ex.: `http://192.168.0.10`).
- **Não há deploy em nuvem** e nada fica exposto para a internet: sem port forwarding no roteador.
- Tudo sobe com um único `docker compose up -d`: banco, storage, API e frontend.
- Serviços escutam em `0.0.0.0` para serem acessíveis na rede. Postgres, Garage e Adminer ficam fechados para a rede, acessíveis só pelo próprio servidor (bind em `127.0.0.1`) ou pela rede interna do Docker.
- Endereços e portas vêm do `.env`, nunca fixos no código. O frontend chama a API por caminho relativo (`/api`) via proxy reverso (Nginx ou Caddy) na porta 80.
- O sistema deve funcionar **sem internet**: nenhuma dependência de CDN, fonte externa ou API externa obrigatória.
- Backup automático diário do Postgres e do Garage em uma pasta local (`backups/`).

## Stack
- Backend: Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2
- Banco: PostgreSQL 16 (via Docker)
- Arquivos: Garage (compatível com S3; substituiu o MinIO, cuja edição Community foi descontinuada), acessado via API S3 (boto3), metadados na tabela `files`. O layout, a chave e o bucket são criados pelo serviço `garage-init` do compose.
- Frontend: React + TypeScript + Vite + Tailwind
- Testes: pytest (backend), Vitest (frontend)
- Infra: Docker Compose na rede local, Nginx/Caddy como proxy reverso, GitHub Actions para CI (o código vai pro GitHub, o sistema não)

## Módulos
1. Painel — resumo do dia (agrega dados dos outros módulos)
2. Afazeres (`tasks`)
3. Rotina (`routines`, `routine_logs`)
4. Mercado (`shopping_items`)
5. Despensa (`pantry_items`)
6. Pets (`pets`, `pet_events`; gastos ficam em `transactions` com `pet_id`)
7. Finanças (`transactions`, `budgets`)
8. Arquivos (`files`, polimórfica: `entity_type` + `entity_id`)

## Estrutura de pastas
```
backend/app/{api/routers, services, repositories, models, schemas, core}
backend/alembic/   backend/tests/   backend/scripts/
infra/{postgres, garage}   (config e scripts de init dos serviços)
frontend/src/{pages, components, api}
docker-compose.yml   .env.example   docs/
```

## Regras de banco
- Toda mudança de schema é uma migration do Alembic. Nunca alterar o banco "na mão".
- Chaves primárias UUID; colunas `created_at` e `updated_at` em todas as tabelas.
- Dinheiro em `NUMERIC(12,2)`, nunca float.
- Toda tabela de dados do usuário tem `user_id` com FK e índice.

## Regras de código
- Camadas: router → service → repository. Regra de negócio só no service.
- Nada de senha ou chave no código: tudo em `.env` (só `.env.example` vai pro Git).
- Mensagens de validação e de erro nunca incluem o valor recebido (nada de `f"... {value!r}"`): elas vão direto para o cliente e podem expor senhas ou dados pessoais.
- Todo endpoint novo ganha teste. Rodar `pytest` antes de dizer que terminou.

## Comandos
- Subir infra: `docker compose up -d`
- Ambiente Python: `cd backend && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"` (ative com `source .venv/bin/activate`)
- Migrations: `cd backend && alembic upgrade head`
- Nova migration: `alembic revision --autogenerate -m "descricao"`
- Seed: `cd backend && python -m scripts.seed`
- Testes: `cd backend && pytest` (usa o banco `POSTGRES_TEST_DB`)
- Lint: `cd backend && ruff check . && ruff format --check .`
- API local: `cd backend && uvicorn app.main:app --reload --port $API_PORT` (docs em `http://localhost:$API_PORT/api/docs`)

## Fluxo de trabalho
- Uma branch por funcionalidade (`feat/tasks-crud`), commits pequenos no padrão Conventional Commits.
- Antes de implementar algo grande, apresente um plano e espere minha aprovação.
- Roteiro completo em `docs/ROADMAP.md`. Marque o que for concluído.
