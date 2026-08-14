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
