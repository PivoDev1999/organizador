import { useQuery } from "@tanstack/react-query";
import { Archive, CircleAlert, CircleCheck, CircleX, Database, HardDrive, RefreshCw, Server, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { ApiError, errorMessage, NetworkError } from "@/api/errors";
import { getSystemStatus, statusKeys } from "@/api/status";
import type { BackupState, CheckStatus, OverallStatus, SystemStatus } from "@/api/types";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Skeleton } from "@/components/Spinner";
import { TONE_STYLES, type Tone } from "@/components/tones";
import { cn } from "@/lib/cn";
import { formatDateTime, formatDuration, formatFileSize } from "@/lib/format";

/** While the page is open (and the tab visible), the status is fetched again every minute. */
export const STATUS_REFRESH_MS = 60_000;

const GRID = "grid grid-cols-1 gap-4 md:grid-cols-2";

const OVERALL: Record<OverallStatus, { tone: Tone; icon: LucideIcon; title: string }> = {
  ok: { tone: "success", icon: CircleCheck, title: "Tudo funcionando" },
  degraded: { tone: "warning", icon: CircleAlert, title: "Funcionando, com avisos" },
  down: { tone: "danger", icon: CircleX, title: "Sistema fora do ar" },
};

const CHECK: Record<CheckStatus, { tone: Tone; label: string }> = {
  ok: { tone: "success", label: "funcionando" },
  unavailable: { tone: "danger", label: "indisponível" },
};

const BACKUP: Record<BackupState, { tone: Tone; label: string }> = {
  ok: { tone: "success", label: "em dia" },
  stale: { tone: "warning", label: "atrasado" },
  missing: { tone: "danger", label: "nunca feito" },
  unreadable: { tone: "danger", label: "ilegível" },
};

/** What needs attention, in plain words, for the summary at the top. */
function problems(status: SystemStatus): string[] {
  const list: string[] = [];
  if (status.database.status !== "ok") list.push("O banco de dados não responde.");
  if (status.storage.status !== "ok") list.push("Os arquivos (anexos) estão indisponíveis.");
  if (status.backup.status === "stale") list.push(`O último backup tem mais de ${status.backup.max_age_hours} horas.`);
  if (status.backup.status === "missing") list.push("Nenhum backup foi feito ainda.");
  if (status.backup.status === "unreadable") list.push("Não foi possível ler as informações do último backup.");
  return list;
}

function formatLatency(ms: number | null): string {
  return ms === null ? "—" : `${ms.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} ms`;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap justify-between gap-x-4 gap-y-0.5 border-b border-slate-100 py-2 last:border-b-0">
      <dt className="text-slate-700">{label}</dt>
      <dd className="font-medium text-slate-900">{children}</dd>
    </div>
  );
}

function Summary({ status }: { status: SystemStatus }) {
  const { tone, icon: Icon, title } = OVERALL[status.overall];
  const list = problems(status);
  return (
    <section aria-label="Resumo" className={cn("mb-4 flex items-start gap-3 rounded-xl p-4", TONE_STYLES[tone])}>
      <Icon aria-hidden="true" className="mt-0.5 size-6 shrink-0" />
      <div>
        <p className="text-lg font-semibold">{title}</p>
        {list.length > 0 && (
          <ul className="mt-1 list-disc pl-5 text-sm">
            {list.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

/** 5xx (API or proxy) or no answer at all: the API, or the database it needs even to check the login, is
 * down. A 401 never gets here: the API client drops the session and the app goes to the login page. */
function isSystemDown(error: unknown): boolean {
  return error instanceof NetworkError || (error instanceof ApiError && error.status >= 500);
}

function SystemDown() {
  return (
    <section role="alert" aria-label="Resumo" className={cn("mb-4 flex items-start gap-3 rounded-xl p-4", TONE_STYLES.danger)}>
      <CircleX aria-hidden="true" className="mt-0.5 size-6 shrink-0" />
      <div>
        <p className="text-lg font-semibold">Sistema fora do ar</p>
        <p className="mt-1">Não foi possível falar com a API ou com o banco de dados.</p>
        <p className="mt-1 text-sm">
          No servidor, rode <code className="rounded bg-white/60 px-1">docker compose ps</code> para ver qual serviço está
          parado ou <em>unhealthy</em>. Depois, toque em “Atualizar”.
        </p>
      </div>
    </section>
  );
}

function StatusCards({ status }: { status: SystemStatus }) {
  const { database, storage, backup } = status;
  return (
    <div className={GRID}>
      <Card title="Aplicação" icon={Server}>
        <dl>
          <Row label="Versão">{status.version}</Row>
          <Row label="Horário do servidor">
            <time dateTime={status.server_time}>{formatDateTime(status.server_time, status.timezone)}</time>
          </Row>
          <Row label="Fuso horário">{status.timezone}</Row>
          <Row label="No ar há">{formatDuration(status.uptime_seconds)}</Row>
        </dl>
      </Card>

      <Card title="Banco de dados" icon={Database} actions={<Badge tone={CHECK[database.status].tone}>{CHECK[database.status].label}</Badge>}>
        <dl>
          <Row label="Tempo de resposta">{formatLatency(database.latency_ms)}</Row>
          <Row label="Revisão do banco">{database.alembic_revision ?? "—"}</Row>
        </dl>
      </Card>

      <Card title="Arquivos (Garage)" icon={HardDrive} actions={<Badge tone={CHECK[storage.status].tone}>{CHECK[storage.status].label}</Badge>}>
        <dl>
          <Row label="Tempo de resposta">{formatLatency(storage.latency_ms)}</Row>
        </dl>
      </Card>

      <Card title="Último backup" icon={Archive} actions={<Badge tone={BACKUP[backup.status].tone}>{BACKUP[backup.status].label}</Badge>}>
        {backup.last_success_at ? (
          <dl>
            <Row label="Terminou em">
              <time dateTime={backup.last_success_at}>{formatDateTime(backup.last_success_at, status.timezone)}</time>
            </Row>
            <Row label="Há quanto tempo">
              {backup.age_hours === null ? "—" : `há ${formatDuration(backup.age_hours * 3600)}`}
            </Row>
            <Row label="Tamanho">{backup.size_bytes === null ? "—" : formatFileSize(backup.size_bytes)}</Row>
            {backup.name && <Row label="Pasta">{backup.name}</Row>}
          </dl>
        ) : (
          <p className="text-slate-700">
            {backup.status === "missing"
              ? "Nenhum backup terminou até agora. O backup automático roda todo dia às 03:00."
              : "As informações do último backup não puderam ser lidas."}
          </p>
        )}
      </Card>
    </div>
  );
}

function StatusSkeleton() {
  return (
    <div role="status">
      <span className="sr-only">Carregando o status...</span>
      <Skeleton className="mb-4 h-20 w-full rounded-xl" />
      <div className={GRID}>
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-40 w-full rounded-xl" />
        ))}
      </div>
    </div>
  );
}

export function StatusPage() {
  const query = useQuery({
    queryKey: statusKeys.all,
    queryFn: getSystemStatus,
    refetchInterval: STATUS_REFRESH_MS,
    staleTime: 0,
  });
  const { data } = query;
  const down = query.isError && isSystemDown(query.error);
  const time = new Date(query.dataUpdatedAt).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  return (
    <>
      <PageHeader
        title="Status do sistema"
        description={
          data
            ? down
              ? `Última leitura bem-sucedida às ${time}. Tenta de novo a cada minuto.`
              : `Atualizado às ${time}. Atualiza sozinho a cada minuto.`
            : undefined
        }
        actions={
          <Button variant="secondary" size="sm" loading={query.isFetching} onClick={() => void query.refetch()}>
            {!query.isFetching && <RefreshCw aria-hidden="true" className="size-4" />}
            Atualizar
          </Button>
        }
      />
      {query.isPending && <StatusSkeleton />}
      {/* Down: only this message, even over an older reading, whose "funcionando" would now be wrong. */}
      {down && <SystemDown />}
      {query.isError && !data && !down && (
        <Card>
          <ErrorState
            title="Não foi possível carregar o status"
            message={errorMessage(query.error)}
            onRetry={() => void query.refetch()}
          />
        </Card>
      )}
      {data && !down && (
        <>
          {query.isError && (
            <p role="alert" className="mb-4 text-sm text-red-800">
              Não foi possível atualizar agora ({errorMessage(query.error)}). Abaixo, a última leitura.
            </p>
          )}
          <Summary status={data} />
          <StatusCards status={data} />
        </>
      )}
    </>
  );
}
