# Organizador

Sistema pessoal de organização da casa: afazeres, rotina, mercado, despensa, pets, finanças e arquivos.

Roda num computador de casa (o "servidor") e é acessado pelos outros aparelhos da mesma rede Wi-Fi.
Não há deploy em nuvem e nada fica exposto para a internet. Funciona sem internet.

## Stack

| Camada | Tecnologia |
|---|---|
| API | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 |
| Banco | PostgreSQL 16 |
| Arquivos | [Garage](https://garagehq.deuxfleurs.fr/) (armazenamento compatível com S3) |
| Frontend | React, TypeScript, Vite, Tailwind *(Fase 4)* |
| Infra | Docker Compose, Nginx/Caddy *(Fase 5)*, GitHub Actions |

## Por que Garage e não MinIO?

O plano original usava o MinIO. Em 2025 a MinIO descontinuou a edição Community como produto
distribuído: as imagens oficiais (`minio/minio` no Docker Hub e `quay.io/minio/minio`) deixaram de
ser publicadas e hoje não estão mais disponíveis para download. As alternativas seriam compilar o
MinIO a partir do código-fonte ou depender de imagens de terceiros, o que aumenta a manutenção e o
risco de supply chain.

O [Garage](https://garagehq.deuxfleurs.fr/) é um armazenamento de objetos compatível com S3, feito
para self-hosting em hardware modesto. Ele tem imagem oficial mantida (`dxflrs/garage`) e é leve
(um binário só). Como a API conversa com o storage pelo protocolo S3 (boto3), a troca é transparente
para o código: a tabela `files`, os uploads e as URLs temporárias funcionam igual.

Diferenças práticas:
- O Garage não tem console web. Use a CLI (`docker compose exec garage /garage ...`) ou qualquer
  cliente S3.
- O layout do cluster, a chave de acesso e o bucket precisam ser configurados uma vez. O serviço
  `garage-init` do `docker-compose.yml` faz isso automaticamente pela Admin API, e é idempotente.

## Pré-requisitos

- Docker com Docker Compose v2
- Python 3.12 com `venv` (no Ubuntu/Debian: `sudo apt install python3.12-venv`)
- `openssl` (para gerar os segredos)

## Como subir

```bash
# 1. Configuração: copie e troque todos os valores "change-me"
cp .env.example .env
#    As instruções para gerar cada segredo estão em comentários no próprio .env.example.

# 2. Infraestrutura: Postgres, Garage (+ init) e Adminer
docker compose up -d
docker compose logs garage-init     # deve terminar com "garage-init: done"

# 3. Backend
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m scripts.seed               # dados de exemplo (usuário demo@organizador.local)

# 4. API
uvicorn app.main:app --reload --port 8000
```

## Serviços e portas

| Serviço | Endereço | Acesso |
|---|---|---|
| API (dev) | `http://localhost:8000/api` (docs em `/api/docs`) | servidor |
| PostgreSQL | `127.0.0.1:5432` | só o servidor |
| Garage (S3) | `127.0.0.1:3900` | só o servidor |
| Adminer | `http://127.0.0.1:8080` (servidor `postgres`) | só o servidor |

As portas vêm do `.env`. Postgres, Garage e Adminer ficam presos em `127.0.0.1` de propósito, e só o
proxy reverso (Fase 5) vai ficar exposto na rede local.

## Testes

```bash
cd backend
pytest                       # usa o banco POSTGRES_TEST_DB (criado na 1ª subida do Postgres)
ruff check . && ruff format --check .
```

## Estrutura

```
backend/
  app/{api/routers, services, repositories, models, schemas, core}
  alembic/          migrations
  scripts/          seed e utilitários
  tests/
infra/
  postgres/init/    scripts da 1ª inicialização (cria o banco de teste)
  garage/           garage.toml e init.py (layout, chave e bucket)
docs/ROADMAP.md
docker-compose.yml
.env.example
```

## Modelo de dados

*(diagrama adicionado na Fase 1)*
