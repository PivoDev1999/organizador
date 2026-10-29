# Organizador

[![CI](https://github.com/PivoDev1999/organizador/actions/workflows/ci.yml/badge.svg)](https://github.com/PivoDev1999/organizador/actions/workflows/ci.yml)

Sistema pessoal de organização da casa: afazeres, rotina, mercado, despensa, pets, finanças e arquivos.

Roda num computador de casa (o "servidor") e é acessado pelos outros aparelhos da mesma rede Wi-Fi.
Não há deploy em nuvem e nada fica exposto para a internet. Funciona sem internet.

## Stack

| Camada | Tecnologia |
|---|---|
| API | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 |
| Banco | PostgreSQL 16 |
| Arquivos | [Garage](https://garagehq.deuxfleurs.fr/) (armazenamento compatível com S3) |
| Frontend | React, TypeScript, Vite, Tailwind |
| Infra | Docker Compose, Nginx (proxy reverso), GitHub Actions |

## Por que Garage e não MinIO?

O plano original usava o MinIO. Em 2025 a MinIO descontinuou a edição Community como produto
distribuído: as imagens oficiais (`minio/minio` no Docker Hub e `quay.io/minio/minio`) deixaram de
ser publicadas e hoje não estão mais disponíveis para download. As alternativas seriam compilar o
MinIO a partir do código-fonte ou depender de imagens de terceiros, o que aumenta a manutenção e o
risco de supply chain.

O [Garage](https://garagehq.deuxfleurs.fr/) é um armazenamento de objetos compatível com S3, feito
para self-hosting em hardware modesto. Ele tem imagem oficial mantida (`dxflrs/garage`) e é leve
(um binário só). Como a API conversa com o storage pelo protocolo S3 (boto3), a troca é transparente
para o código: a API usa só a interface `Storage` (`backend/app/core/storage.py`).

Diferenças práticas:
- O Garage não tem console web. Use a CLI (`docker compose exec garage /garage ...`) ou qualquer
  cliente S3.
- O layout do cluster, a chave de acesso e os buckets precisam ser configurados uma vez. O serviço
  `garage-init` do `docker-compose.yml` faz isso automaticamente pela Admin API, e é idempotente. Ele
  cria o bucket do app (`S3_BUCKET`) e o dos testes de integração (`S3_TEST_BUCKET`, padrão
  `organizador-test`), com a mesma chave, sem permissão de dono.

### Como os arquivos são servidos

- O Garage continua preso em `127.0.0.1`. Upload e download passam pela API: no download ela lê o
  objeto e repassa em blocos (streaming), sem carregar o arquivo inteiro na memória e sem URL
  pré-assinada.
- Limite por arquivo: `MAX_UPLOAD_MB` (padrão 20). Um middleware recusa com 413, antes de gravar o
  multipart em disco, o corpo acima do limite + 1 MB de envelope (pelo `Content-Length` ou contando os
  bytes, se vier chunked). Depois a API conta os bytes do arquivo enquanto envia ao Garage e aborta
  acima do limite (413), apagando o objeto parcial. Arquivo vazio é recusado (422).
- Qualquer tipo é aceito, mas o download sai como anexo (`application/octet-stream`). `?inline=true`
  só vale para JPEG, PNG, GIF, WebP e PDF **confirmados pelos primeiros bytes** (nunca pelo tipo que o
  cliente informou); SVG e HTML nunca saem inline. Toda resposta leva `X-Content-Type-Options: nosniff`
  e `Content-Security-Policy: default-src 'none'; sandbox`, inclusive as de erro (401, 404, 413, 503).
  Regras em `backend/app/core/file_types.py`.
- A chave do objeto é `{user_id}/{entity_type}/{uuid}`: o nome original fica só no banco (saneado).
- Apagar um registro (tarefa, pet, evento, transação etc.) apaga os anexos: as linhas na mesma
  transação e os objetos depois do commit. Se o Garage falhar nessa hora, sobra um objeto órfão,
  registrado no log.
- Apagar um usuário (o `ON DELETE CASCADE` leva as linhas de `files`) ou recriar o demo com
  `python -m scripts.seed` também deixa os objetos dele órfãos no Garage. Para limpar:

```bash
cd backend
python -m scripts.cleanup_orphans --dry-run   # só mostra o que seria apagado
python -m scripts.cleanup_orphans             # apaga órfãos com mais de 24 horas
```

## Pré-requisitos

- Docker com Docker Compose v2
- Python 3.12 com `venv` (no Ubuntu/Debian: `sudo apt install python3.12-venv`)
- Node.js 22.22+ ou 24 e npm 11 (frontend)
- `openssl` (para gerar os segredos)

## Requisito do PostgreSQL: ICU

As listagens ordenadas por nome usam a collation `pt-BR-x-icu` ("agua, Água, banho, Faxina"), porque na
imagem Alpine o locale padrão ordena por bytes. A imagem oficial `postgres` do `docker-compose.yml` já
vem com ICU; um Postgres instalado de outra forma precisa ter suporte a ICU (o teste
`tests/test_database_requirements.py` acusa se faltar).

## Instalação no servidor (produção)

Tudo roda em containers com um único `docker compose up -d --build`: Postgres, Garage, a API (FastAPI) e o
`web` (Nginx servindo o frontend e repassando `/api` para a API). Só o `web` fica aberto na rede local, na
porta `HTTP_PORT` (padrão 80); Postgres, Garage e Adminer continuam presos em `127.0.0.1`. Sem HTTPS: o
acesso é só pela rede de casa.

```bash
# 1. Código e configuração
git clone https://github.com/PivoDev1999/organizador.git && cd organizador
cp .env.example .env
#    Troque todos os "change-me": os comandos para gerar cada segredo estão nos comentários do .env.
#    Se a porta 80 já estiver em uso no servidor, defina outra em HTTP_PORT (ex.: 8088).

# 2. Build das imagens e subida de tudo
docker compose up -d --build
docker compose ps                   # api e web "healthy"; garage-init "exited (0)"

# 3. Primeiro usuário (a senha é pedida no terminal, nunca vai na linha de comando)
docker compose exec api python -m scripts.create_user --email voce@casa.local --name "Seu nome"
```

Depois, em qualquer aparelho da rede, acesse `http://<IP-do-servidor>` (ou `http://<IP>:<HTTP_PORT>`).
Descubra o IP com `hostname -I` no servidor.

- **Outras contas:** rode o `create_user` de novo para cada pessoa. Na stack Docker o cadastro público
  fica sempre fechado: o `docker-compose.yml` fixa `ALLOW_REGISTRATION=false` e `ENVIRONMENT=production`
  no `api`, independentemente do `.env` (que vale para o desenvolvimento com `uvicorn`).
- **Abrir o cadastro temporariamente (se precisar):** crie um `docker-compose.override.yml` (o Compose lê
  esse arquivo sozinho; ele está no `.gitignore`), recrie a API, cadastre e depois desfaça:

  ```yaml
  # docker-compose.override.yml (temporário)
  services:
    api:
      environment:
        ALLOW_REGISTRATION: "true"
  ```

  ```bash
  docker compose up -d api            # cadastro aberto (POST /api/auth/register, também em /api/docs)
  rm docker-compose.override.yml
  docker compose up -d api            # cadastro fechado de novo
  ```
- **Dados de exemplo (opcional):** `docker compose exec api python -m scripts.seed` (usuário
  `demo@organizador.local`, senha `SEED_USER_PASSWORD`).
- **Atualizar:** `git pull && docker compose up -d --build`. As migrations rodam sozinhas quando a API sobe.
- **Logs:** `docker compose logs -f api web` (ou de um serviço só). Os logs de todos os serviços têm
  rotação (3 arquivos de 10 MB cada).
- **Parar:** `docker compose stop` (os dados ficam nos volumes). Com `restart: unless-stopped`, tudo volta
  sozinho quando o computador reinicia, exceto o que foi parado com `stop`.

O que cada imagem faz:

| Serviço | Imagem | Detalhes |
|---|---|---|
| `api` | `backend/Dockerfile` (`python:3.12.15-slim-trixie`) | Ao subir: espera o Postgres, roda `alembic upgrade head` uma vez e inicia o `uvicorn` com 2 workers (`API_WORKERS`). Usuário sem privilégios (uid 10001), sistema de arquivos só leitura, sem porta publicada. O `/tmp` (onde os uploads ficam enquanto vão para o Garage) é um disco em RAM limitado a `API_TMP_SIZE` (padrão `256m`, uns 12 uploads simultâneos de 20 MB); se encher, só o upload em andamento falha. |
| `web` | `frontend/Dockerfile` (build com `node:24.22.0-alpine3.24`, roda `nginx:1.30.6-alpine3.24`) | Serve o build do React e faz proxy de `/api/` para `http://api:8000`. Configuração em `frontend/nginx/`. O processo mestre do Nginx roda como root dentro do container (para abrir a porta 80 e trocar os workers para o usuário `nginx`), mas com as capacidades reduzidas ao mínimo (`cap_drop: ALL` + `CHOWN`, `SETGID`, `SETUID`, `NET_BIND_SERVICE`) e `no-new-privileges`. |

Proteções no Nginx:

- **Tentativas de login:** 5 `POST /api/auth/login` por minuto por IP (com rajada de 5); a 6ª no mesmo
  minuto recebe 429 e a tela de login mostra "Muitas tentativas. Aguarde um minuto e tente de novo.".
- **Tamanho do corpo:** `/api/files` aceita até `MAX_UPLOAD_MB` + 2 MB (413 acima disso; a API confere o
  limite exato do arquivo). O resto de `/api` aceita até 1 MB.
- **Downloads em streaming:** `/api/files` sem buffer no proxy, e os cabeçalhos da API (`nosniff`, CSP
  `sandbox`, `no-store`) passam intactos.
- **Cabeçalhos de segurança** no app: CSP estrita (`default-src 'self'`, sem `unsafe-inline`; `blob:` só
  para imagens e para o visualizador de PDF dos anexos), `X-Content-Type-Options`, `X-Frame-Options: DENY`,
  `Referrer-Policy` e `Permissions-Policy`. Assets com hash no nome têm cache de 1 ano (`immutable`);
  o `index.html`, `no-cache`.
- **API fora do ar** (parada, reiniciando ou migrando): `/api` responde 502/503/504 em JSON
  (`{"detail": "API indisponível. Tente de novo em instantes."}`), e o app continua carregando.
- **Swagger sem internet:** `/api/docs` carrega o Swagger UI do pacote npm `swagger-ui-dist` (copiado na
  imagem do Nginx, em `/api/docs-assets/`), nunca de CDN.

## Desenvolvimento

API e frontend rodam fora do Docker, com recarga automática; só a infraestrutura sobe em containers.

```bash
# 1. Configuração: copie e troque todos os valores "change-me"
cp .env.example .env
#    As instruções para gerar cada segredo estão em comentários no próprio .env.example.

# 2. Infraestrutura: Postgres, Garage (+ init) e Adminer (sem a API e o web do Docker)
docker compose up -d postgres garage garage-init adminer
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

O `.env` de desenvolvimento usa `POSTGRES_HOST=localhost` e `S3_ENDPOINT_URL=http://localhost:3900`;
dentro do Docker o `docker-compose.yml` troca só esses endereços (`postgres` e `http://garage:3900`).
Se o `api`/`web` do Docker estiverem no ar, pare-os com `docker compose stop api web` (o `web` ocupa a
porta 80).

O `/api/docs` também funciona sem internet em desenvolvimento: a própria API serve os arquivos do Swagger
UI a partir de `frontend/node_modules/swagger-ui-dist` (basta ter rodado `npm ci` no `frontend`; outro
caminho pode ser indicado em `SWAGGER_UI_DIR`).

## Serviços e portas

| Serviço | Endereço | Acesso |
|---|---|---|
| App + API (produção) | `http://<IP-do-servidor>:${HTTP_PORT}` (docs em `/api/docs`) | rede local |
| API (dev) | `http://localhost:8000/api` (docs em `/api/docs`) | servidor |
| Frontend (dev) | `http://localhost:5173` (proxy de `/api` para a API) | servidor |
| PostgreSQL | `127.0.0.1:5432` | só o servidor |
| Garage (S3) | `127.0.0.1:3900` | só o servidor |
| Adminer | `http://127.0.0.1:8080` (servidor `postgres`) | só o servidor |

As portas vêm do `.env`. Postgres, Garage e Adminer ficam presos em `127.0.0.1` de propósito, e só o
Nginx (`web`) fica exposto na rede local. A API não publica porta: só o `web` fala com ela, por uma rede
interna do Docker (`proxy`, sub-rede `PROXY_SUBNET`).

O painel do dia sai em `GET /api/dashboard?within=7&limit=5`: tarefas atrasadas e de hoje, rotinas,
alertas da despensa, mercado, lembretes dos pets, contas a pagar, totais do mês e orçamentos em alerta
(`warning` com gasto de 80% a 100% do orçamento, `exceeded` acima dele, comparando os valores exatos),
com as mesmas regras dos endpoints de cada módulo, lidos todos no mesmo instante (uma transação só de
leitura, REPEATABLE READ).

## Frontend

React + TypeScript + Vite + Tailwind, em `frontend/`. Funciona sem internet: nada de CDN nem fontes
externas (usa as fontes do sistema). O app chama a API sempre por `/api`; em desenvolvimento, o Vite faz
proxy de `/api` para `http://127.0.0.1:${API_PORT}`, com `API_PORT` lido do `.env` da raiz (padrão 8000).

```bash
cd frontend
npm ci                 # instala exatamente o que está no package-lock.json
npm run dev            # http://localhost:5173 (com a API rodando na porta API_PORT)
```

Entre com `demo@organizador.local` e a senha `SEED_USER_PASSWORD` do `.env` (depois de rodar o seed).
Para abrir no celular durante o desenvolvimento, use `npm run dev -- --host` e acesse pelo IP do servidor.

| Comando | O que faz |
|---|---|
| `npm run api:types` | Gera `src/api/schema.d.ts` a partir de `http://127.0.0.1:${API_PORT}/api/openapi.json`. Sem a API no ar, usa o snapshot `openapi/openapi.json`. Os dois arquivos são versionados, então o build não depende da API. Rode sempre que mudar um schema do backend. |
| `npm test` | Testes (Vitest + Testing Library, jsdom) |
| `npm run lint` | ESLint (regras recomendadas de TypeScript e React Hooks) |
| `npm run build` | Checagem de tipos (`tsc -b`) e build de produção em `frontend/dist/` |
| `npm run preview` | Serve o build localmente |

As dependências ficam com versões exatas (`.npmrc` com `save-exact=true`) e o `package-lock.json` é
versionado. Só entram versões publicadas há pelo menos 2 semanas.

Organização:

```
frontend/src/
  api/          cliente HTTP (apiFetch tipado pelo schema.d.ts, ApiError, erros 422 por campo) e endpoints
  auth/         token (único acesso ao localStorage), AuthProvider/useAuth, rota protegida
  components/   componentes base, layout (menu lateral / barra inferior), toasts, anexos
  lib/          formatadores (dinheiro e quantidades sem float, datas sem fuso)
  pages/        uma página por rota
```

- **Sessão:** o token fica no `localStorage`. Qualquer 401 encerra a sessão e leva para
  `/login?next=<página>`; depois do login, o usuário volta para onde estava.
- **Erros:** a API responde `{"detail": "..."}` ou, no 422 (validação e regras de negócio),
  `{"detail": [{"type", "loc", "msg"}]}`. `getFieldErrors` agrupa por campo (último item de `loc`);
  regras de negócio chegam como `body`.
- **Anexos:** `<Attachments entityType="task" entityId={id} />` lista, envia, pré-visualiza (imagens e PDF),
  baixa e exclui. O download usa `fetch` com o token e abre o conteúdo como blob, então a CSP `sandbox`
  da resposta não se aplica ao visualizador de PDF do navegador.

## Testes

> O backend lê o `.env` da raiz do repositório. Para usar outro arquivo, defina a variável de ambiente
> `ENV_FILE` (ex.: `ENV_FILE=/caminho/.env.local pytest`).

```bash
cd backend
pytest                       # usa o banco POSTGRES_TEST_DB (criado na 1ª subida do Postgres)
                             # e o bucket S3_TEST_BUCKET do Garage (testes de integração do storage,
                             # pulados se o Garage estiver fora do ar; os demais usam um storage em memória)
ruff check . && ruff format --check .
```

Os testes que precisam do Garage real têm o marcador `integration` (hoje,
`tests/test_files_storage_integration.py`). O `pytest` sozinho roda tudo; para escolher:

```bash
pytest -m integration          # só os de integração (precisa do Garage: docker compose up -d garage garage-init)
pytest -m "not integration"    # todos menos os de integração (o que o CI roda)
```

## Integração contínua

O GitHub Actions (`.github/workflows/ci.yml`) roda em todo pull request e em todo push para `main`, com
três jobs em paralelo:

| Job | O que faz |
|---|---|
| `backend` | Postgres `16.10-alpine` como serviço, `ruff check`, `ruff format --check` e `pytest -m "not integration"` (sem Garage no CI) |
| `frontend` | Node 24: `npm ci`, `npm run lint`, `npm test` e `npm run build` |
| `docker` | Valida o `docker-compose.yml` (`docker compose config -q`) e faz o build das imagens `api` e `web` (sem push) |

- No CI não existe `.env`: as variáveis vêm do próprio workflow, com valores falsos que só servem ao CI.
- As actions são fixadas pelo SHA completo do commit (com a tag em comentário) e só entram versões
  publicadas há pelo menos 2 semanas.
- O Dependabot (`.github/dependabot.yml`) propõe atualizações semanais de pip, npm, GitHub Actions e
  imagens Docker (do `docker-compose.yml` e dos Dockerfiles), com `cooldown` de 14 dias: uma versão só é
  sugerida 2 semanas depois de publicada.
- No build da imagem da API, o `pip` só considera pacotes publicados há pelo menos 14 dias
  (`--uploaded-prior-to=P14D`), o que vale também para as dependências transitivas.

Para reproduzir o job `backend` localmente sem o `.env` interferir, use `ENV_FILE=/dev/null` e passe as
mesmas variáveis do workflow (com a senha do Postgres local).

## Estrutura

```
backend/
  app/{api/routers, services, repositories, models, schemas, core}
  alembic/          migrations
  scripts/          seed, create_user, wait_for_db e utilitários
  tests/
  Dockerfile        imagem da API (+ docker-entrypoint.sh)
infra/
  postgres/init/    scripts da 1ª inicialização (cria o banco de teste)
  garage/           garage.toml e init.py (layout, chave e bucket)
frontend/           React + Vite (ver seção Frontend)
  Dockerfile        imagem web: build do React + Nginx
  nginx/            nginx.conf, template do site e snippets (proxy, cabeçalhos)
docs/ROADMAP.md
.github/          workflow do CI e dependabot.yml
docker-compose.yml
.env.example
```

## Modelo de dados

Todas as tabelas têm `id uuid` (PK), `created_at` e `updated_at` (`timestamptz`, este mantido por trigger
no banco). Tabelas de dados têm `user_id` (FK para `users`, `ON DELETE CASCADE`). Valores monetários usam
`numeric(12,2)` e "enums" são `varchar` com `CHECK`.

As FKs entre módulos são compostas com o dono: por exemplo, `pet_events (pet_id, user_id)` referencia
`pets (id, user_id)`. Assim o banco garante que um registro filho pertence ao mesmo usuário do pai. Nas
FKs opcionais, `ON DELETE SET NULL (pet_id)` (PostgreSQL 15+) limpa só o vínculo e mantém o `user_id`.

Rotinas mensais com `day_of_month` maior que o último dia do mês (29 a 31) caem no último dia: a do dia 31
vale em 30/04 e em 28/02 (29/02 em ano bissexto).

Um evento de pet com `next_due_on` é lembrete até existir um evento mais recente (por `occurred_on`,
`created_at` e `id`) do mesmo pet, com o mesmo `type` e a mesma descrição normalizada (espaços nas pontas
removidos e minúsculas Unicode, via `lower(... COLLATE "pt-BR-x-icu")`; sem descrição conta como uma série):
registrar "v10 " resolve o lembrete da "V10", mas "Antirrábica" não.

```mermaid
erDiagram
    users ||--o{ tasks : ""
    users ||--o{ routines : ""
    users ||--o{ pantry_items : ""
    users ||--o{ shopping_items : ""
    users ||--o{ pets : ""
    users ||--o{ transactions : ""
    users ||--o{ budgets : ""
    users ||--o{ files : ""
    routines ||--o{ routine_logs : "CASCADE"
    pets ||--o{ pet_events : "CASCADE"
    pets |o--o{ transactions : "SET NULL (pet_id)"
    pantry_items |o--o{ shopping_items : "SET NULL (pantry_item_id)"

    users {
        uuid id PK
        varchar email UK "único em lower(email)"
        varchar name
        varchar password_hash
        boolean is_active
    }
    tasks {
        uuid id PK
        uuid user_id FK
        varchar title
        text description
        varchar status "todo | doing | done; done exige completed_at"
        varchar priority "low | medium | high"
        date due_date
        timestamptz completed_at
    }
    routines {
        uuid id PK
        uuid user_id FK "UK (id, user_id)"
        varchar name
        text description
        varchar frequency "daily | weekly | monthly"
        smallint[] days_of_week "0-6, 1 dimensão, só weekly"
        smallint day_of_month "1-31, só monthly"
        time time_of_day
        boolean is_active
    }
    routine_logs {
        uuid id PK
        uuid routine_id FK "FK (routine_id, user_id); UK (routine_id, done_on)"
        uuid user_id FK
        date done_on
        text note
    }
    pantry_items {
        uuid id PK
        uuid user_id FK "UK (id, user_id)"
        varchar name
        varchar category
        numeric quantity "10,3"
        varchar unit
        numeric min_quantity "10,3"
        date expires_on
        varchar location
    }
    shopping_items {
        uuid id PK
        uuid user_id FK
        uuid pantry_item_id FK "FK (pantry_item_id, user_id)"
        varchar name
        numeric quantity "10,3"
        varchar unit
        varchar category
        numeric estimated_price "12,2"
        boolean is_purchased "true exige purchased_at"
        timestamptz purchased_at
    }
    pets {
        uuid id PK
        uuid user_id FK "UK (id, user_id)"
        varchar name
        varchar species
        varchar breed
        date birth_date
        numeric weight_kg "5,2"
        text notes
    }
    pet_events {
        uuid id PK
        uuid pet_id FK "FK (pet_id, user_id)"
        uuid user_id FK
        varchar type "vaccine | vet | medication | grooming | other"
        date occurred_on
        date next_due_on ">= occurred_on"
        text description
    }
    transactions {
        uuid id PK
        uuid user_id FK
        uuid pet_id FK "FK (pet_id, user_id)"
        varchar type "income | expense"
        numeric amount "12,2, > 0"
        varchar category
        varchar description
        date due_date
        timestamptz paid_at
    }
    budgets {
        uuid id PK
        uuid user_id FK "UK (user_id, category, month)"
        varchar category
        date month "sempre dia 1"
        numeric amount "12,2, >= 0"
    }
    files {
        uuid id PK
        uuid user_id FK
        varchar entity_type "task | routine | pantry_item | ..."
        uuid entity_id "sem FK"
        varchar bucket "UK (bucket, object_key)"
        varchar object_key UK
        varchar original_name
        varchar content_type
        bigint size_bytes
    }
```

`files` é polimórfica: `entity_type` + `entity_id` apontam para um registro de qualquer módulo, por isso
`entity_id` não tem FK, e apagar os arquivos de uma entidade removida é responsabilidade da API.
