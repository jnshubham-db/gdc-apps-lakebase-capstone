import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import type { CustomerFilters } from "./types";

// staleTime tiers per the engineering bar: list short, detail medium,
// metrics long (expensive warehouse query, slow-changing).
export const customerKeys = {
  list: (f: CustomerFilters) => ["customers", "list", f] as const,
  detail: (id: string) => ["customers", "detail", id] as const,
  metrics: (id: string) => ["customers", "metrics", id] as const,
};

export function useCustomers(filters: CustomerFilters) {
  return useQuery({
    queryKey: customerKeys.list(filters),
    queryFn: () => api.listCustomers(filters),
    staleTime: 10_000,
    gcTime: 5 * 60_000,
    placeholderData: (prev) => prev, // keep page visible while paginating
  });
}

export function useCustomerDetail(id: string) {
  return useQuery({
    queryKey: customerKeys.detail(id),
    queryFn: () => api.getCustomer(id),
    staleTime: 30_000,
  });
}

export function useCustomerMetrics(id: string) {
  return useQuery({
    queryKey: customerKeys.metrics(id),
    queryFn: () => api.getMetrics(id),
    staleTime: 60_000,
    retry: 1,
  });
}

export function useAddNote(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (note_text: string) => api.addNote(id, note_text),
    onSuccess: () => qc.invalidateQueries({ queryKey: customerKeys.detail(id) }),
  });
}

export function useOverrideSegment(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { override_segment: string; reason?: string }) =>
      api.overrideSegment(id, v.override_segment, v.reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: customerKeys.detail(id) }),
  });
}

export function useConfig() {
  return useQuery({
    queryKey: ["config"] as const,
    queryFn: () => api.getConfig(),
    staleTime: 5 * 60_000,
  });
}

export function useDashboardAnalytics() {
  return useQuery({
    queryKey: ["dashboard", "analytics"] as const,
    queryFn: () => api.getDashboardAnalytics(),
    staleTime: 60_000,
    retry: 1,
  });
}

const TERMINAL_RUN = new Set(["TERMINATED", "SKIPPED", "INTERNAL_ERROR"]);

export function useForwardEtlRuns() {
  return useQuery({
    queryKey: ["jobs", "runs"] as const,
    queryFn: () => api.jobs.listRuns(),
    staleTime: 5_000,
    retry: 1,
  });
}

export function useRunForwardEtl() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.jobs.runForwardEtl(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs", "runs"] }),
  });
}

// Polls one run while its state is non-terminal; refreshes the runs list when
// it settles. `enabled` gates polling to an in-flight run id.
export function useForwardEtlRun(runId: number | null, enabled: boolean) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: ["jobs", "run", runId] as const,
    queryFn: () => api.jobs.getRun(runId as number),
    enabled: enabled && runId != null,
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      if (state && TERMINAL_RUN.has(state)) {
        qc.invalidateQueries({ queryKey: ["jobs", "runs"] });
        return false;
      }
      return 2_000;
    },
  });
}
