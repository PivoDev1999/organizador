import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { errorMessage } from "@/api/errors";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { SectionCard } from "@/components/SectionCard";
import { Skeleton } from "@/components/Spinner";

export interface ChartTableRow {
  key: string;
  cells: string[];
}

export interface ChartFrameProps {
  title: string;
  icon: LucideIcon;
  /** Query state of the chart's data. */
  status: "pending" | "error" | "success";
  error: unknown;
  onRetry: () => void;
  emptyText: string;
  isEmpty: boolean;
  /** Same data as the chart, as a table for screen readers (the SVG is hidden from them). */
  table: { caption: string; headers: string[]; rows: ChartTableRow[] };
  /** Extra content above the chart (e.g. alerts). */
  before?: ReactNode;
  children: ReactNode;
}

/** Card of a chart: loading, error and empty states, plus an accessible text version of the data. */
export function ChartFrame({ title, icon, status, error, onRetry, emptyText, isEmpty, table, before, children }: ChartFrameProps) {
  return (
    <SectionCard title={title} icon={icon}>
      {status === "pending" && (
        <div role="status">
          <span className="sr-only">Carregando o gráfico...</span>
          <Skeleton className="h-48 w-full" />
        </div>
      )}
      {status === "error" && <ErrorState message={errorMessage(error)} onRetry={onRetry} />}
      {status === "success" &&
        (isEmpty ? (
          <EmptyState title={emptyText} />
        ) : (
          <>
            {before}
            <div aria-hidden="true">{children}</div>
            {/* sr-only on a wrapper: on the table itself, Firefox still paints the caption. */}
            <div className="sr-only">
              <table>
                <caption>{table.caption}</caption>
                <thead>
                  <tr>
                    {table.headers.map((header) => (
                      <th key={header} scope="col">
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.rows.map((row) => (
                    <tr key={row.key}>
                      {row.cells.map((cell, index) => (index === 0 ? <th key={index} scope="row">{cell}</th> : <td key={index}>{cell}</td>))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ))}
    </SectionCard>
  );
}

/** Tooltip box shared by the charts. */
export function ChartTooltipBox({ title, lines }: { title: string; lines: string[] }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-md">
      <p className="font-semibold text-slate-900">{title}</p>
      {lines.map((line) => (
        <p key={line} className="text-slate-700">
          {line}
        </p>
      ))}
    </div>
  );
}
