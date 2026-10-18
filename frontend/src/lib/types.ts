/** API types mirroring the FastAPI schemas. */

export type Tier = "low" | "medium" | "high";

export type CellStatus =
  | "paid_on_time"
  | "paid_late"
  | "unpaid_overdue"
  | "unpaid_upcoming"
  | "open";

export interface PaymentCell {
  cycle_month: string;
  due_date: string;
  status: CellStatus;
  paid_date: string | null;
  days_late: number | null;
  amount: number;
  probability?: number | null;
  tier?: Tier | null;
}

export interface LedgerRow {
  lease_id: number;
  tenant_name: string;
  unit_label: string;
  property_name: string;
  property_id: number;
  occupation_type: string;
  preferred_language: string;
  preferred_channel: string;
  cycles: PaymentCell[];
  current: PaymentCell;
}

export interface LedgerResponse {
  cycle_month: string;
  rows: LedgerRow[];
}

export interface TierCounts {
  low: number;
  medium: number;
  high: number;
}

export interface PortfolioSummary {
  properties: number;
  active_leases: number;
  expected_collection_inr: number;
  total_rent_due_inr: number;
  tiers: TierCounts;
  cycle_month: string;
}

export interface Factor {
  feature: string;
  template_value: string;
  direction: "raises" | "lowers";
  contribution: number;
}

export interface PlanStep {
  offset_days: number;
  date: string;
  channel: string;
  tone: string;
  owner: "system" | "manager";
}

export interface Guardrail {
  name: string;
  passed: boolean;
  reason: string;
}

export interface Reminder {
  id: number;
  lease_id: number;
  cycle_month: string;
  channel: string;
  tone: string;
  language: string;
  message: string;
  status: "draft" | "approved";
  created_at: string;
  approved_at: string | null;
  guardrails: Guardrail[];
  fallback: boolean;
}

export interface TenantDetail {
  lease_id: number;
  tenant_id: number;
  tenant_name: string;
  unit_label: string;
  property_name: string;
  rent_inr: number;
  due_day: number;
  occupation_type: string;
  preferred_language: string;
  preferred_channel: string;
  tenure_months: number;
  prior_cycles: number;
  history: PaymentCell[];
  probability: number | null;
  tier: Tier | null;
  factors: Factor[];
  plan: PlanStep[];
  reminders: Reminder[];
  cold_start: boolean;
}

export interface OutlookPoint {
  day: number;
  p10: number;
  expected: number;
  p90: number;
}

export interface OutlookResponse {
  cycle_month: string;
  total_due: number;
  points: OutlookPoint[];
  likely_late_count: number;
}

export interface ModelCardResponse {
  metrics: Record<string, unknown>;
  slices: Record<string, unknown>;
  card_markdown: string;
}
