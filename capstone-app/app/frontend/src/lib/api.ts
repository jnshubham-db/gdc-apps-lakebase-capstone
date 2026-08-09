import type {
  CustomerDetail,
  CustomerFilters,
  CustomerMetrics,
  CustomerSummary,
  Page,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, String(detail));
  }
  return res.json() as Promise<T>;
}

function qs(filters: CustomerFilters): string {
  const p = new URLSearchParams();
  if (filters.segment) p.set("segment", filters.segment);
  if (filters.min_ltv != null) p.set("min_ltv", String(filters.min_ltv));
  if (filters.max_churn != null) p.set("max_churn", String(filters.max_churn));
  p.set("page", String(filters.page ?? 1));
  p.set("page_size", String(filters.page_size ?? 25));
  return p.toString();
}

export const api = {
  listCustomers: (filters: CustomerFilters) =>
    request<Page<CustomerSummary>>(`/customers?${qs(filters)}`),

  getCustomer: (id: string) => request<CustomerDetail>(`/customers/${id}`),

  getMetrics: (id: string) => request<CustomerMetrics>(`/customers/${id}/metrics`),

  addNote: (id: string, note_text: string) =>
    request<{ note_id: string; created_at: string }>(`/customers/${id}/notes`, {
      method: "POST",
      body: JSON.stringify({ note_text }),
    }),

  overrideSegment: (id: string, override_segment: string, reason?: string) =>
    request<{ override_id: string; override_segment: string }>(`/customers/${id}/segment`, {
      method: "POST",
      body: JSON.stringify({ override_segment, reason }),
    }),
};
