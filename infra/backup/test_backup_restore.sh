#!/usr/bin/env bash
# End-to-end test of backup + restore on the local stack (needs Postgres, Garage, api and web; NOT in CI).
#
#   infra/backup/test_backup_restore.sh --yes
#
# DESTRUCTIVE for the local data: it reruns the seed, deletes the demo tasks, drops a table and restores
# from the backup it makes. Run it on the development machine, never on the server with real data.
#
#  1. seed, api + web up, 2 attachments (PNG and PDF) uploaded through the API
#  2. backup-now; checks the directory, the manifest and every SHA-256 (also with sha256sum on the host)
#  3. destroys: deletes the attachments and the demo tasks through the API, DROP TABLE shopping_items,
#     plus a stray object in the bucket
#  4. infra/backup/restore.sh <backup> --yes
#  5. row counts back to the manifest's, downloads with the same SHA-256, bucket = backup (stray gone)
#  6. pre-restore directory created and valid
#  7. cleanup: deletes the test attachments, reruns the seed, makes one final backup (kept as an example)
#     and removes every other directory created by the test; api/web back to how they were
set -Eeuo pipefail

cd "$(dirname "$(readlink -f "$0")")/../.."

[[ "${1:-}" == "--yes" ]] || { echo "uso: $0 --yes   (apaga e restaura os dados locais)" >&2; exit 2; }
[[ -f .env ]] || { echo "falta o .env" >&2; exit 1; }

env_get() { sed -n "s/^$1=//p" .env | tail -n 1; }
HTTP_PORT="$(env_get HTTP_PORT)"; HTTP_PORT="${HTTP_PORT:-80}"
API="http://127.0.0.1:${HTTP_PORT}/api"
PG_USER="$(env_get POSTGRES_USER)"
PG_DB="$(env_get POSTGRES_DB)"
SEED_PASSWORD="$(env_get SEED_USER_PASSWORD)"
DEMO_EMAIL="demo@organizador.local"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

step() { printf '\n=== %s\n' "$*"; }
ok() { printf '  OK   %s\n' "$*"; }
fail() { printf '  FAIL %s\n' "$*" >&2; exit 1; }
check() { local what="$1" got="$2" want="$3"; [[ "$got" == "$want" ]] && ok "$what: $got" || fail "$what: $got (esperado $want)"; }

# stdin from /dev/null: `docker compose exec/run` would otherwise read the input of the loops below.
sql() { docker compose exec -T postgres psql -X -At -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DB" -c "$1" </dev/null; }
backup_tool() { docker compose run --rm -T backup python -m backuptool "$@" </dev/null 2>/dev/null; }
# Output captured first: `grep -q` in a pipeline can make it fail under pipefail (SIGPIPE).
is_running() {
    local services
    services="$(docker compose ps --status running --services 2>/dev/null </dev/null || true)"
    grep -x "$1" <<<"$services" >/dev/null
}
login() {
    curl -fsS -X POST "$API/auth/login" --data-urlencode "username=$DEMO_EMAIL" \
        --data-urlencode "password=$SEED_PASSWORD" | jq -r .access_token
}
auth() { curl -fsS -H "Authorization: Bearer $TOKEN" "$@"; }
backup_now() {
    local out
    out="$(docker compose run --rm -T backup backup-now </dev/null 2>/dev/null)"
    printf '%s\n' "$out" | sed 's/^/  | /' >&2
    sed -n 's/^BACKUP_DIR=//p' <<<"$out"
}

api_was_running=no web_was_running=no
is_running api && api_was_running=yes
is_running web && web_was_running=yes
dirs_before="$(cd backups && ls -1A | sort)"

# ------------------------------------------------------------------------------------------------------
step "1. Seed, api + web e 2 anexos pela API"
docker compose up -d --wait api web >/dev/null 2>&1
docker compose exec -T api python -m scripts.seed >/dev/null
TOKEN="$(login)"
TASK_ID="$(auth "$API/tasks?limit=1" | jq -r '.items[0].id')"
[[ "$TASK_ID" != null ]] || fail "o seed não criou tarefas"

# A valid 1x1 PNG and a minimal PDF, with random bytes so every run has new checksums.
printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82' > "$WORK/teste.png"
head -c 64 /dev/urandom >> "$WORK/teste.png"
{ printf '%%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n'
  printf '2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj\ntrailer << /Root 1 0 R >>\n%%%%EOF\n'
  printf '%% %s\n' "$(head -c 24 /dev/urandom | base64)"; } > "$WORK/teste.pdf"

declare -A FILE_SHA
for f in teste.png teste.pdf; do
    id="$(auth -F entity_type=task -F "entity_id=$TASK_ID" -F "file=@$WORK/$f" "$API/files" | jq -r .id)"
    FILE_SHA[$id]="$(sha256sum < "$WORK/$f" | cut -d' ' -f1)"
    ok "anexo $f enviado (id $id)"
done
TASKS_BEFORE="$(sql 'SELECT count(*) FROM tasks')"
FILES_BEFORE="$(sql 'SELECT count(*) FROM files')"
SHOPPING_BEFORE="$(sql 'SELECT count(*) FROM shopping_items')"
OBJECTS_BEFORE="$(backup_tool list-objects | wc -l)"
echo "  antes: tasks=$TASKS_BEFORE files=$FILES_BEFORE shopping_items=$SHOPPING_BEFORE objetos=$OBJECTS_BEFORE"

# ------------------------------------------------------------------------------------------------------
step "2. backup-now e conferência do backup"
NAME="$(backup_now)"
DIR="backups/$NAME"
[[ -d "$DIR" && -f "$DIR/manifest.json" && -f "$DIR/db.dump" ]] || fail "diretório $DIR incompleto"
ok "diretório $DIR"
check "last_success.json aponta para o backup" "$(jq -r .backup backups/last_success.json)" "$NAME"
check "objetos no manifest" "$(jq -r .files.count "$DIR/manifest.json")" "$OBJECTS_BEFORE"
check "linhas de files no manifest" "$(jq -r '.database.tables["public.files"]' "$DIR/manifest.json")" "$FILES_BEFORE"
check "linhas de tasks no manifest" "$(jq -r '.database.tables["public.tasks"]' "$DIR/manifest.json")" "$TASKS_BEFORE"
check "revisão Alembic" "$(jq -r .database.alembic_revision "$DIR/manifest.json")" "$(sql 'SELECT version_num FROM alembic_version')"
check "SHA-256 do db.dump (sha256sum no host)" \
    "$(sha256sum < "$DIR/db.dump" | cut -d' ' -f1)" "$(jq -r .database.dump.sha256 "$DIR/manifest.json")"
while IFS=$'\t' read -r path sha; do
    [[ "$(sha256sum < "$DIR/$path" | cut -d' ' -f1)" == "$sha" ]] || fail "SHA-256 de $path"
done < <(jq -r '.files.objects[] | [.path, .sha256] | @tsv' "$DIR/manifest.json")
ok "SHA-256 dos $(jq -r .files.count "$DIR/manifest.json") objeto(s) conferem (sha256sum no host)"
backup_tool verify "$NAME" >/dev/null || fail "backuptool verify"
ok "backuptool verify (manifest e SHA-256 dentro do container)"

# ------------------------------------------------------------------------------------------------------
step "3. Destruindo dados"
for id in "${!FILE_SHA[@]}"; do auth -X DELETE "$API/files/$id"; done
ok "anexos apagados pela API (e os objetos no bucket)"
deleted=0
while :; do
    ids="$(auth "$API/tasks?limit=100" | jq -r '.items[].id')"
    [[ -n "$ids" ]] || break
    for id in $ids; do auth -X DELETE "$API/tasks/$id"; deleted=$((deleted + 1)); done
done
ok "$deleted tarefa(s) do demo apagadas pela API"
sql 'DROP TABLE shopping_items CASCADE' >/dev/null
ok "DROP TABLE shopping_items"
docker compose run --rm -T backup python -c \
    "from backuptool.s3 import Bucket; Bucket().put_bytes('stray/teste-restore', b'lixo')" 2>/dev/null
ok "objeto estranho stray/teste-restore criado no bucket"
echo "  depois: tasks=$(sql 'SELECT count(*) FROM tasks') files=$(sql 'SELECT count(*) FROM files')" \
    "objetos=$(backup_tool list-objects | wc -l)"

# ------------------------------------------------------------------------------------------------------
step "4. restore.sh $DIR --yes"
infra/backup/restore.sh "$DIR" --yes

# ------------------------------------------------------------------------------------------------------
step "5. Conferência depois da restauração"
check "tasks" "$(sql 'SELECT count(*) FROM tasks')" "$TASKS_BEFORE"
check "files" "$(sql 'SELECT count(*) FROM files')" "$FILES_BEFORE"
check "shopping_items" "$(sql 'SELECT count(*) FROM shopping_items')" "$SHOPPING_BEFORE"
check "revisão Alembic" "$(sql 'SELECT version_num FROM alembic_version')" \
    "$(jq -r .database.alembic_revision "$DIR/manifest.json")"
check "chaves do bucket = manifest (sem o objeto estranho)" \
    "$(backup_tool list-objects | cut -f1 | sort | sha256sum | cut -c1-16)" \
    "$(jq -r '.files.objects[].key' "$DIR/manifest.json" | sort | sha256sum | cut -c1-16)"
docker compose up -d --wait api >/dev/null 2>&1
for id in "${!FILE_SHA[@]}"; do
    check "download do anexo $id (SHA-256)" "$(auth "$API/files/$id/download" | sha256sum | cut -d' ' -f1)" \
        "${FILE_SHA[$id]}"
done

# ------------------------------------------------------------------------------------------------------
step "6. Backup de segurança (pre-restore)"
PRE="$(cd backups && ls -1d pre-restore-* | sort | tail -n 1)"
[[ -n "$PRE" ]] || fail "nenhum backups/pre-restore-*"
backup_tool verify "$PRE" >/dev/null || fail "backups/$PRE inválido"
ok "backups/$PRE criado e válido"
check "pre-restore tem o estado destruído (tasks)" \
    "$(jq -r '.database.tables["public.tasks"]' "backups/$PRE/manifest.json")" "$((TASKS_BEFORE - deleted))"

# ------------------------------------------------------------------------------------------------------
step "7. Limpeza"
for id in "${!FILE_SHA[@]}"; do auth -X DELETE "$API/files/$id"; done
ok "anexos de teste apagados"
docker compose exec -T api python -m scripts.seed >/dev/null
ok "seed rodado de novo"
FINAL="$(backup_now)"
ok "backup final (exemplo): backups/$FINAL"
while read -r entry; do
    [[ -z "$entry" || "$entry" == "$FINAL" ]] && continue
    if ! grep -qxF "$entry" <<<"$dirs_before" && [[ -d "backups/$entry" ]]; then
        rm -rf "backups/${entry:?}"
        ok "removido backups/$entry"
    fi
done < <(cd backups && ls -1A | sort)
stop=()
[[ "$api_was_running" == no ]] && stop+=(api)
[[ "$web_was_running" == no ]] && stop+=(web)
if ((${#stop[@]})); then
    docker compose stop "${stop[@]}" >/dev/null 2>&1
    ok "parados de novo: ${stop[*]}"
fi

printf '\nTESTE DE BACKUP E RESTAURAÇÃO: OK\n'
