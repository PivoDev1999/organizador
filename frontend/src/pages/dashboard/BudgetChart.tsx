import { Gauge, TriangleAlert } from "lucide-react";
import { Bar, BarChart, Cell, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { BudgetAlert } from "@/api/types";
import { Badge } from "@/components/Badge";
import type { BudgetLevel } from "@/lib/decimal";
import { formatMoney, formatPercent } from "@/lib/format";
import { ChartFrame, ChartTooltipBox } from "./ChartFrame";
import { BUDGET_LEVEL_LABELS, prepareBudgetData, type BudgetDatum } from "./chartData";
import { useBudgets } from "./queries";

const ROW_HEIGHT = 40;
// emerald-700, amber-500 and red-700: distinct for the usual color blindness, and the level is also in text.
const LEVEL_COLORS: Record<BudgetLevel, string> = { normal: "#047857", warning: "#f59e0b", exceeded: "#b91c1c" };

const LEGEND: Array<{ level: BudgetLevel; text: string }> = [
  { level: "normal", text: "abaixo de 80%" },
  { level: "warning", text: "atenção (80% a 100%)" },
  { level: "exceeded", text: "estourado (acima de 100%)" },
];

function spentOf(item: { spent: string; amount: string }): string {
  return `${formatMoney(item.spent)} de ${formatMoney(item.amount)}`;
}

function BudgetAlerts({ alerts, total }: { alerts: BudgetAlert[]; total: number }) {
  if (total === 0) return null;
  return (
    <div className="mb-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2">
      <h3 className="flex items-center gap-1.5 font-semibold text-amber-900">
        <TriangleAlert aria-hidden="true" className="size-4" />
        Alertas ({total})
      </h3>
      <ul className="mt-1 space-y-1">
        {alerts.map((alert) => (
          <li key={alert.id} className="flex flex-wrap items-center justify-between gap-x-2 text-sm text-slate-900">
            <span className="flex items-center gap-2">
              <span className="font-medium">{alert.category}</span>
              <Badge tone={alert.level === "exceeded" ? "danger" : "warning"}>{BUDGET_LEVEL_LABELS[alert.level]}</Badge>
            </span>
            <span className="text-slate-700">
              {spentOf(alert)}
              {alert.percent_used !== null && ` (${formatPercent(alert.percent_used)})`}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function BudgetChart({ month, alerts }: { month: string; alerts: { items: BudgetAlert[]; total: number } }) {
  const query = useBudgets(month);
  const data = query.data ? prepareBudgetData(query.data) : [];
  const maxValue = Math.max(100, ...data.map((item) => item.value));

  return (
    <ChartFrame
      title="Uso dos orçamentos"
      icon={Gauge}
      status={query.status}
      error={query.error}
      onRetry={() => void query.refetch()}
      isEmpty={data.length === 0}
      emptyText="Nenhum orçamento neste mês"
      before={<BudgetAlerts alerts={alerts.items} total={alerts.total} />}
      table={{
        caption: "Uso dos orçamentos do mês",
        headers: ["Categoria", "Uso", "Gasto", "Situação"],
        rows: data.map((item) => ({
          key: item.id,
          cells: [item.category, item.label, spentOf(item), BUDGET_LEVEL_LABELS[item.level]],
        })),
      }}
    >
      <ResponsiveContainer width="100%" height={data.length * ROW_HEIGHT + 16} initialDimension={{ width: 320, height: 200 }}>
        <BarChart data={data} layout="vertical" margin={{ top: 8, right: 96, bottom: 8, left: 0 }}>
          <XAxis type="number" hide domain={[0, maxValue]} />
          <YAxis
            type="category"
            dataKey="category"
            width={110}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "#334155", fontSize: 13 }}
          />
          <ReferenceLine x={100} stroke="#64748b" strokeDasharray="4 4" />
          <Tooltip
            cursor={{ fill: "#f1f5f9" }}
            content={({ active, payload }) => {
              const item = payload?.[0]?.payload as BudgetDatum | undefined;
              return active && item ? (
                <ChartTooltipBox
                  title={item.category}
                  lines={[`${item.label} · ${BUDGET_LEVEL_LABELS[item.level]}`, spentOf(item)]}
                />
              ) : null;
            }}
          />
          <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={22} isAnimationActive={false}>
            {data.map((item) => (
              <Cell key={item.id} fill={LEVEL_COLORS[item.level]} />
            ))}
            <LabelList dataKey="label" position="right" fill="#0f172a" fontSize={13} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-700">
        {LEGEND.map(({ level, text }) => (
          <li key={level} className="flex items-center gap-1.5">
            <span className="size-3 rounded-sm" style={{ backgroundColor: LEVEL_COLORS[level] }} />
            {text}
          </li>
        ))}
      </ul>
    </ChartFrame>
  );
}
