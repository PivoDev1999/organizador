#!/usr/bin/env bash
# Restore a backup of the Organizador: database + files bucket, exactly as they were in the backup.
#
#   infra/backup/restore.sh backups/2026-10-28_030000            (asks to type RESTAURAR)
#   infra/backup/restore.sh backups/2026-10-28_030000 --yes      (no question: scripts, tests)
#   infra/backup/restore.sh <dir> --yes --skip-safety-backup     (only if the current state cannot be dumped)
#
# Steps:
#   1. verify the manifest and every SHA-256 and show what will be replaced; 2. confirm;
#   3. stop `api` and `backup`;
#   4. one `backuptool restore` (a single lock, so no backup can start in the middle):
#      recover leftovers of an interrupted restore -> safety backup (backups/pre-restore-<ts>/) ->
#      pg_restore into <db>_restore -> upload the missing objects (additive) -> swap the databases by
#      renaming (<db> -> <db>_old, <db>_restore -> <db>, drop <db>_old) -> delete the extra objects ->
#      check the row counts;
#   5. migrate (`alembic upgrade head`) and start again what was running.
# A failure before the swap leaves database and bucket as they were (at most extra objects) and starts the
# services again; after that, the exact state and the recovery commands are printed.
# Idempotent: running it again with the same backup gives the same result.
# Needs only Docker and bash; run it as the owner of the repository (docker group).
set -Eeuo pipefail

log() { printf '%s restore: %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"; }
die() { log "ERRO: $*" >&2; exit 1; }
usage() { echo "uso: $0 <diretório do backup em backups/> [--yes] [--skip-safety-backup]" >&2; exit 2; }

target="" assume_yes=no safety=yes
for arg in "$@"; do
    case "$arg" in
        --yes|-y) assume_yes=yes ;;
        --skip-safety-backup) safety=no ;;
        -*) usage ;;
        *) [[ -z "$target" ]] || usage; target="$arg" ;;
    esac
done
[[ -n "$target" ]] || usage

# A path is resolved from the caller's folder, before moving to the repository.
given_parent=""
if [[ "$target" == */* ]]; then
    given_parent="$(cd "$(dirname "$target")" 2>/dev/null && pwd -P)" || die "pasta não encontrada: $target"
fi

cd "$(dirname "$(readlink -f "$0")")/../.."
[[ -f .env ]] || die "arquivo .env não encontrado na raiz do repositório"
if [[ "$assume_yes" != yes && ! -t 0 ]]; then
    die "sem terminal para confirmar: use --yes"
fi

name="$(basename "${target%/}")"
if [[ -n "$given_parent" && "$given_parent" != "$(cd backups && pwd -P)" ]]; then
    die "recusado: $target não está diretamente na pasta backups/ do repositório (copie o backup para lá)"
fi
[[ -L "backups/$name" ]] && die "recusado: backups/$name é um link simbólico (copie o diretório de verdade)"
[[ -d "backups/$name" ]] || die "backup não encontrado: backups/$name"

env_get() { sed -n "s/^$1=//p" .env | tail -n 1; }
PG_USER="$(env_get POSTGRES_USER)"
PG_DB="$(env_get POSTGRES_DB)"

# Only for the failure tests (README): passes BACKUP_TEST_HOOK on to the container.
hook_env=()
[[ -n "${BACKUP_TEST_HOOK:-}" ]] && hook_env=(-e "BACKUP_TEST_HOOK=$BACKUP_TEST_HOOK")
# stdin from /dev/null: `docker compose run` would otherwise eat what the user types at the prompt.
backup_tool() { docker compose run --rm -T "${hook_env[@]}" backup python -m backuptool "$@" </dev/null; }

# Captured once (no `grep -q` in a pipeline: with pipefail, an early exit of grep can fail the pipeline).
running_services="$(docker compose ps --status running --services 2>/dev/null </dev/null || true)"
was_running() { grep -x "$1" <<<"$running_services" >/dev/null; }

restart_services() {
    local services=()
    was_running api && services+=(api)
    was_running backup && services+=(backup)
    if ((${#services[@]})); then
        log "Subindo de novo o que estava no ar: ${services[*]}" >&2
        docker compose up -d "${services[@]}" </dev/null >/dev/null 2>&1 \
            || log "Não consegui subir ${services[*]}: rode 'docker compose up -d ${services[*]}'" >&2
    fi
}

print_recovery() {
    local databases
    databases="$(docker compose exec -T postgres psql -X -At -U "$PG_USER" -d postgres -c \
        "SELECT string_agg(datname, ' ' ORDER BY datname) FROM pg_database
         WHERE datname IN ('$PG_DB', '${PG_DB}_old', '${PG_DB}_restore')" </dev/null 2>/dev/null || echo "?")"
    log "Bancos existentes agora: ${databases:-nenhum}" >&2
    log "Recuperação automática (recomendada): docker compose run --rm backup python -m backuptool recover" >&2
    log "Ou à mão, em: docker compose exec postgres psql -U $PG_USER -d postgres" >&2
    log "  - $PG_DB ausente e ${PG_DB}_old presente: ALTER DATABASE \"${PG_DB}_old\" RENAME TO \"$PG_DB\";" >&2
    log "  - $PG_DB e ${PG_DB}_old presentes (troca feita): DROP DATABASE \"${PG_DB}_old\" WITH (FORCE);" >&2
    log "  - ${PG_DB}_restore presente: DROP DATABASE \"${PG_DB}_restore\" WITH (FORCE);" >&2
    if grep -w -- "$PG_DB" <<<"$databases" >/dev/null; then
        log "O banco $PG_DB existe. Para repetir esta restauração: $0 backups/$name --yes" >&2
        [[ -z "$pre_restore" ]] || \
            log "Para voltar ao estado de antes: $0 backups/$pre_restore --yes --skip-safety-backup" >&2
    else
        log "O banco $PG_DB NÃO existe: rode a recuperação acima antes de qualquer outra coisa." >&2
    fi
    log "api e backup ficaram parados: depois de resolver, 'docker compose up -d api backup'." >&2
}

step="verificação" restore_state="" pre_restore="" out_file=""
on_exit() {
    local code=$?
    trap - EXIT INT TERM
    [[ -z "$out_file" ]] || rm -f "$out_file"
    ((code == 0)) && return 0
    log "ERRO na etapa: $step (código $code)." >&2
    case "$step" in
        verificação|confirmação)
            log "Nada foi alterado e nenhum serviço foi parado." >&2 ;;
        parada)
            log "Nada foi alterado no banco nem no bucket." >&2
            restart_services ;;
        restauração)
            case "$restore_state" in
                untouched)
                    log "Nada foi alterado: o banco e os arquivos são os de antes. No máximo ficaram objetos a" >&2
                    log "mais no bucket (órfãos inofensivos; 'docker compose exec api python -m scripts.cleanup_orphans')." >&2
                    restart_services ;;
                database-restored)
                    log "O banco JÁ é o do backup; falhou a limpeza do bucket ou a conferência (veja o log acima)." >&2
                    print_recovery ;;
                *)
                    log "Falha durante a troca dos bancos (ou o processo morreu): estado a conferir." >&2
                    print_recovery ;;
            esac ;;
        migração)
            log "Banco e arquivos restaurados, mas a migração ou a subida do api falhou." >&2
            log "Veja 'docker compose logs api' e suba com 'docker compose up -d api backup'." >&2 ;;
    esac
    exit "$code"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

log "1/5 Verificando backups/$name (manifest e SHA-256 de cada arquivo)"
backup_tool describe "$name"

step="confirmação"
if [[ "$assume_yes" != yes ]]; then
    echo
    echo "ATENÇÃO: o banco e TODOS os arquivos do bucket serão substituídos pelo conteúdo deste backup."
    read -r -p "Digite RESTAURAR para continuar: " answer
    [[ "$answer" == "RESTAURAR" ]] || { log "Cancelado: nada foi alterado."; exit 0; }
fi

step="parada"
log "2/5 Parando api e backup (o web continua no ar e responde 'API indisponível')"
docker compose stop api backup </dev/null

step="restauração"
safety_flag=()
if [[ "$safety" == yes ]]; then
    log "3/5 Backup de segurança (backups/pre-restore-*) e restauração de backups/$name"
    safety_flag=(--safety-backup)
else
    log "3/5 Restauração de backups/$name SEM backup de segurança (--skip-safety-backup)"
fi
out_file="$(mktemp)"
set +e
backup_tool restore "$name" "${safety_flag[@]}" | tee "$out_file"
rc="${PIPESTATUS[0]}"
set -e
pre_restore="$(sed -n 's/^PRE_RESTORE_DIR=//p' "$out_file")"
restore_state="$(sed -n 's/^RESTORE_STATE=//p' "$out_file")"
if ((rc != 0)); then
    restore_state="${restore_state:-unknown}"
    exit "$rc"
fi

step="migração"
if was_running api; then
    log "4/5 Subindo o api (roda alembic upgrade head antes do uvicorn)"
    docker compose up -d --wait api </dev/null
else
    log "4/5 api estava parado: só aplicando as migrations (alembic upgrade head)"
    docker compose run --rm -T --no-deps --entrypoint alembic api upgrade head </dev/null
fi
if was_running backup; then
    docker compose up -d backup </dev/null
fi

step="fim"
log "5/5 Restauração de backups/$name concluída."
[[ -z "$pre_restore" ]] || \
    log "Estado anterior guardado em backups/$pre_restore (não é apagado sozinho: apague quando não precisar mais)."
