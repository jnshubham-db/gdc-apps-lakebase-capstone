import { ExternalLink } from "lucide-react";

import {
  ChurnDistributionChart,
  SegmentChurnChart,
  SegmentLtvChart,
  TicketsTrendChart,
  TopProductsChart,
} from "@/components/charts";
import { EmptyState, ErrorState, Skeleton } from "@/components/states";
import { Panel, PanelHeader } from "@/components/ui";
import { useConfig, useDashboardAnalytics } from "@/lib/queries";

function ChartPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Panel>
      <PanelHeader>
        <span className="font-display text-sm uppercase tracking-[0.14em] text-lum">{title}</span>
      </PanelHeader>
      <div className="p-4">{children}</div>
    </Panel>
  );
}

export default function Dashboard() {
  const cfg = useConfig();
  const { data, isLoading, isError, refetch } = useDashboardAnalytics();

  const workspaceUrl =
    cfg.data?.databricks_host && cfg.data?.dashboard_id
      ? `${cfg.data.databricks_host}/dashboardsv3/${cfg.data.dashboard_id}`
      : null;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl uppercase tracking-[0.12em] text-lum">
            Fleet Analytics
          </h1>
          <p className="font-mono text-xs text-muted">External feed · AI/BI · warehouse (OBO)</p>
        </div>
        {workspaceUrl && (
          <a
            href={workspaceUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-sm border border-bezel bg-face px-3 py-2 font-display text-xs uppercase tracking-[0.14em] text-lum/80 hover:border-lum/40 hover:text-lum"
          >
            <ExternalLink className="h-3.5 w-3.5" strokeWidth={2} />
            Open in AI/BI workspace
          </a>
        )}
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-80 w-full" />
          ))}
        </div>
      )}

      {isError && (
        <div className="bezel">
          <ErrorState
            message="Analytics feed unavailable. On the deployed app this reads live via your workspace session; locally it needs an OBO token."
            onRetry={() => refetch()}
          />
        </div>
      )}

      {data && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ChartPanel title="Avg LTV by Segment">
            <SegmentLtvChart data={data.segments} />
          </ChartPanel>
          <ChartPanel title="Avg Churn by Segment">
            <SegmentChurnChart data={data.segments} />
          </ChartPanel>
          <ChartPanel title="Top 15 Products by Revenue">
            {data.products.length ? (
              <TopProductsChart data={data.products} />
            ) : (
              <EmptyState title="No revenue" />
            )}
          </ChartPanel>
          <ChartPanel title="Churn-Risk Distribution">
            <ChurnDistributionChart data={data.churn_buckets} />
          </ChartPanel>
          <div className="lg:col-span-2">
            <ChartPanel title="Weekly Support Tickets by Category">
              <TicketsTrendChart data={data.tickets} />
            </ChartPanel>
          </div>
        </div>
      )}
    </div>
  );
}
