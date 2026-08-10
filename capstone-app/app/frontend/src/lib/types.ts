// Mirrors the FastAPI response models (backend/models.py).

export interface CustomerSummary {
  customer_id: string;
  first_name: string | null;
  last_name: string | null;
  email: string | null;
  country: string | null;
  city: string | null;
  age: number | null;
  gender: string | null;
  signup_date: string | null;
  segment_id: string | null;
  lifetime_value: number | null;
  last_purchase_date: string | null;
  churn_score: number | null;
  phone: string | null;
  updated_at: string | null;
}

export interface Transaction {
  transaction_id: string;
  customer_id: string;
  product_id: string | null;
  transaction_date: string | null;
  channel: string | null;
  status: string | null;
  amount: number | null;
}

export interface CustomerDetail {
  profile: CustomerSummary;
  transactions: Transaction[];
}

export interface CategorySpend {
  category: string;
  amount: number;
}

export interface CustomerMetrics {
  customer_id: string;
  segment_name: string | null;
  lifetime_spend: number;
  top_categories: CategorySpend[];
  spend_30d: number;
  spend_90d: number;
  open_tickets: number;
  avg_csat: number | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface CustomerFilters {
  segment?: string;
  min_ltv?: number;
  max_churn?: number;
  page?: number;
  page_size?: number;
}

export interface AppConfig {
  databricks_host: string;
  dashboard_id: string | null;
  genie_space_id: string | null;
}

export interface SegmentAgg {
  segment_name: string;
  customers: number;
  avg_ltv: number;
  avg_churn: number;
}

export interface ProductRevenue {
  product_name: string;
  category: string;
  revenue: number;
  units: number;
}

export interface TicketPoint {
  week: string;
  category: string;
  tickets: number;
}

export interface ChurnBucket {
  bucket: number;
  customers: number;
}

export interface DashboardAnalytics {
  segments: SegmentAgg[];
  products: ProductRevenue[];
  tickets: TicketPoint[];
  churn_buckets: ChurnBucket[];
}

export interface GenieResult {
  columns: string[];
  rows: unknown[][];
}

export interface GenieMessageOut {
  status: string;
  text: string | null;
  result: GenieResult | null;
  error: string | null;
}

export interface GenieStartOut {
  conversation_id: string;
  message_id: string;
}

export interface GenieFollowUpOut {
  message_id: string;
}
