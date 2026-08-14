import * as Tabs from "@radix-ui/react-tabs";
import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { Gauge } from "@/components/Gauge";
import { EmptyState, ErrorState, Skeleton } from "@/components/states";
import { ToneNav } from "@/components/DetailTabs";
import { ChurnReadout, Panel } from "@/components/ui";
import { useCustomerDetail } from "@/lib/queries";
import { segmentName } from "@/lib/segments";
import { fmtDate, usd } from "@/lib/utils";
import { MetricsTab } from "@/components/tabs/MetricsTab";
import { ActivityTab } from "@/components/tabs/ActivityTab";
import { NotesTab } from "@/components/tabs/NotesTab";
import { SegmentTab } from "@/components/tabs/SegmentTab";

export default function CustomerDetail() {
  const { id = "" } = useParams();
  const { data, isPending, isError, error, refetch } = useCustomerDetail(id);

  return (
    <div className="space-y-6">
      <Link
        to="/"
        className="inline-flex items-center gap-2 font-display text-xs uppercase tracking-[0.14em] text-muted transition-colors hover:text-green"
      >
        <ArrowLeft className="h-4 w-4" strokeWidth={2} />
        All customers
      </Link>

      {isPending ? (
        <HeaderSkeleton />
      ) : isError ? (
        <div className="bezel">
          <ErrorState message={(error as Error)?.message} onRetry={() => refetch()} />
        </div>
      ) : (
        <>
          <ProfileHeader profile={data.profile} />

          <Tabs.Root defaultValue="metrics" className="space-y-5">
            <ToneNav
              tabs={[
                { value: "metrics", label: "Metrics" },
                { value: "activity", label: "Activity" },
                { value: "notes", label: "Notes" },
                { value: "segment", label: "Segment" },
              ]}
            />

            <Tabs.Content value="metrics" className="focus:outline-none">
              <MetricsTab id={id} />
            </Tabs.Content>
            <Tabs.Content value="activity" className="focus:outline-none">
              <ActivityTab transactions={data.transactions} />
            </Tabs.Content>
            <Tabs.Content value="notes" className="focus:outline-none">
              <NotesTab id={id} />
            </Tabs.Content>
            <Tabs.Content value="segment" className="focus:outline-none">
              <SegmentTab id={id} current={data.profile.segment_id} />
            </Tabs.Content>
          </Tabs.Root>
        </>
      )}
    </div>
  );
}

function ProfileHeader({ profile }: { profile: import("@/lib/types").CustomerSummary }) {
  const name = [profile.first_name, profile.last_name].filter(Boolean).join(" ") || "—";
  return (
    <Panel className="p-5 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl">{name}</h1>
            <span className="readout text-xs text-muted">{profile.customer_id}</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 font-mono text-xs text-muted">
            <span>{profile.email ?? "—"}</span>
            <span>{profile.phone ?? "—"}</span>
            <span>
              {[profile.city, profile.country].filter(Boolean).join(", ") || "—"}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-6">
          <Stat label="Segment" value={segmentName(profile.segment_id)} />
          <Stat label="Lifetime value" value={usd(profile.lifetime_value)} glow />
          <div className="flex flex-col gap-1">
            <span className="placard">Churn risk</span>
            <ChurnReadout score={profile.churn_score} />
          </div>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 border-t border-bezel pt-3 font-mono text-xs text-muted">
        <span>Signed up {fmtDate(profile.signup_date)}</span>
        <span>Last purchase {fmtDate(profile.last_purchase_date)}</span>
        {profile.age != null && <span>Age {profile.age}</span>}
      </div>
    </Panel>
  );
}

function Stat({ label, value, glow }: { label: string; value: string; glow?: boolean }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="placard">{label}</span>
      <span className={`readout text-sm ${glow ? "text-green text-glow-green" : "text-lum"}`}>
        {value}
      </span>
    </div>
  );
}

function HeaderSkeleton() {
  return (
    <div className="space-y-5">
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-10 w-96" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}
