import { ChartBar } from "lucide-react";
import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartFrame, ChartTooltipBox } from "./ChartFrame";
import { prepareCategoryData, type CategoryDatum } from "./chartData";
import { useMonthSummary } from "./queries";

const ROW_HEIGHT = 40;
const BAR_COLOR = "#047857"; // emerald-700, the brand color

export function CategoryChart({ month }: { month: string }) {
  const query = useMonthSummary(month);
  const data = query.data ? prepareCategoryData(query.data.by_category) : [];

  return (
    <ChartFrame
      title="Despesas por categoria"
      icon={ChartBar}
      status={query.status}
      error={query.error}
      onRetry={() => void query.refetch()}
      isEmpty={data.length === 0}
      emptyText="Sem despesas neste mês"
      table={{
        caption: "Despesas do mês por categoria",
        headers: ["Categoria", "Total"],
        rows: data.map((item, index) => ({ key: `${index}-${item.category}`, cells: [item.category, item.label] })),
      }}
    >
      <ResponsiveContainer width="100%" height={data.length * ROW_HEIGHT + 16} initialDimension={{ width: 320, height: 200 }}>
        <BarChart data={data} layout="vertical" margin={{ top: 8, right: 96, bottom: 8, left: 0 }}>
          <XAxis type="number" hide domain={[0, "dataMax"]} />
          <YAxis
            type="category"
            dataKey="category"
            width={110}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "#334155", fontSize: 13 }}
          />
          <Tooltip
            cursor={{ fill: "#f1f5f9" }}
            content={({ active, payload }) => {
              const item = payload?.[0]?.payload as CategoryDatum | undefined;
              return active && item ? <ChartTooltipBox title={item.category} lines={[item.label]} /> : null;
            }}
          />
          <Bar dataKey="value" fill={BAR_COLOR} radius={[0, 4, 4, 0]} barSize={22} isAnimationActive={false}>
            <LabelList dataKey="label" position="right" fill="#0f172a" fontSize={13} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
