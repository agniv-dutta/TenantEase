/** API types mirroring the FastAPI schemas. */

export type Tier = "low" | "medium" | "high";

export type CellStatus =
  | "paid_on_time"
  | "paid_late"
  | "unpaid_overdue"
  | "unpaid_upcoming"
  | "open"
  | "vacant";

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
  as_of_date: string;
}

export type FactorStrength = "main" | "moderate" | "minor";

export interface Factor {
  feature: string;
  sentence: string;
  direction: "raises" | "lowers";
  strength: FactorStrength;
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
  tenant_name: string;
  unit_label: string;
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
  top_factors: Factor[];
  plan: PlanStep[];
  reminders: Reminder[];
  cold_start: boolean;
}

export type Urgency = "emergency" | "soon" | "routine";

export interface MaintenanceRequest {
  id: number;
  lease_id: number;
  text: string;
  category: string;
  urgency: Urgency;
  suggested_trade: string;
  summary: string;
  method: string;
  forced_emergency: boolean;
  created_at: string;
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
  as_of_date: string;
}

export interface ModelCardResponse {
  metrics: Record<string, unknown>;
  slices: Record<string, unknown>;
  card_markdown: string;
}

export type AuditKind = "reminder_drafted" | "reminder_edited" | "reminder_approved" | "payment_recorded" | "payment_parsed";

export interface AuditEvent {
  id: number;
  at: string;
  actor: string;
  kind: AuditKind;
  lease_id: number | null;
  summary: string;
  details: Record<string, unknown>;
}

export interface PaymentParseResult {
  fields: {
    payer_name_guess: string | null;
    amount: number | null;
    paid_date: string | null;
    method: string | null;
    reference: string | null;
    language: string;
    confidence: number;
  };
  matches: Array<{ lease_id: number; tenant: string; unit: string; cycle_month: string | null; reasons: string[] }>;
  flags: string[];
}

export interface PaymentConfirmation {
  lease_id: number;
  cycle_month: string;
  amount: number;
  paid_date: string;
  method: string;
  reference: string | null;
  days_late: number;
  status: string;
  rescored: number;
  flags: string[];
}
