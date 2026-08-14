import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ChurnBucket, ProductRevenue, SegmentAgg, TicketPoint } from "@/lib/types";
import { usd } from "@/lib/utils";

const GREEN = "#39FF9A";
const AMBER = "#FFB000";
const ALERT = "#FF3B30";
const MUTED = "#6B7580";
const GRID = "#1A1E22"; // bezel
const FACE = "#111417";
const LUM = "#F2F5F2";

const AXIS = { stroke: MUTED, fontSize: 11, fontFamily: "'JetBrains Mono', monospace" } as const;

/** Shared dark tooltip in the panel idiom. */
function tip(formatter?: (v: number) => string) {
  return (
    <Tooltip
      cursor={{ fill: "rgba(255,255,255,0.04)" }}
      contentStyle={{
        background: FACE,
        border: `1px solid ${GRID}`,
        borderRadius: 2,
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 12,
        color: LUM,
      }}
      labelStyle={{ color: MUTED }}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      formatter={formatter ? (v: any) => formatter(v as number) : undefined}
    />
  );
}

const H = 260;

export function SegmentLtvChart({ data }: { data: SegmentAgg[] }) {
  return (
    <ResponsiveContainer width="100%" height={H}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="segment_name" tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false}
          interval={0} angle={-30} textAnchor="end" height={70} />
        <YAxis tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false}
          tickFormatter={(v) => usd(v)} width={70} />
        {tip((v) => usd(v))}
        <Bar dataKey="avg_ltv" fill={GREEN} radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function SegmentChurnChart({ data }: { data: SegmentAgg[] }) {
  return (
    <ResponsiveContainer width="100%" height={H}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="segment_name" tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false}
          interval={0} angle={-30} textAnchor="end" height={70} />
        <YAxis tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false} domain={[0, 1]} width={40} />
        {tip((v) => v.toFixed(3))}
        <Bar dataKey="avg_churn" radius={[2, 2, 0, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.avg_churn >= 0.7 ? ALERT : d.avg_churn >= 0.4 ? AMBER : GREEN} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

const truncate = (s: string, n = 22) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

export function TopProductsChart({ data }: { data: ProductRevenue[] }) {
  // Horizontal bars need vertical room per row, or the category labels collide.
  const height = Math.max(H, data.length * 30 + 40);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false}
          tickFormatter={(v) => usd(v)} />
        <YAxis type="category" dataKey="product_name" tick={AXIS} axisLine={{ stroke: GRID }}
          tickLine={false} width={170} interval={0} tickFormatter={(v) => truncate(String(v))} />
        {tip((v) => usd(v))}
        <Bar dataKey="revenue" fill={GREEN} radius={[0, 2, 2, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

const TICKET_TONE: Record<string, string> = {
  billing: ALERT,
  returns: AMBER,
  shipping: GREEN,
};

export function TicketsTrendChart({ data }: { data: TicketPoint[] }) {
  // Pivot long rows → one point per week with a column per category.
  const byWeek = new Map<string, Record<string, number | string>>();
  const cats = new Set<string>();
  for (const r of data) {
    cats.add(r.category);
    const wk = r.week.slice(0, 10);
    const row = byWeek.get(wk) ?? { week: wk };
    row[r.category] = r.tickets;
    byWeek.set(wk, row);
  }
  const rows = [...byWeek.values()].sort((a, b) => String(a.week).localeCompare(String(b.week)));
  const categories = [...cats];

  return (
    <ResponsiveContainer width="100%" height={H}>
      <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="week" tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false}
          minTickGap={40} />
        <YAxis tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false} width={40} />
        {tip()}
        {categories.map((c) => (
          <Line key={c} type="monotone" dataKey={c} stroke={TICKET_TONE[c] ?? MUTED}
            strokeWidth={1.75} dot={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function ChurnDistributionChart({ data }: { data: ChurnBucket[] }) {
  return (
    <ResponsiveContainer width="100%" height={H}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="bucket" tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false}
          tickFormatter={(v) => Number(v).toFixed(1)} />
        <YAxis tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false} width={50} />
        {tip()}
        <Bar dataKey="customers" radius={[2, 2, 0, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.bucket >= 0.8 ? ALERT : d.bucket >= 0.5 ? AMBER : GREEN} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
