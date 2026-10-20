/** Typed API client with an error type matching the backend error body. */

import type {
  Guardrail,
  LedgerResponse,
  MaintenanceRequest,
  ModelCardResponse,
  OutlookResponse,
  PortfolioSummary,
  Reminder,
  TenantDetail,
} from "./types";

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError("network", "Could not reach the server. Check that the API is running.", 0);
  }
  if (!res.ok) {
    let code = "error";
    let message = `Request failed with status ${res.status}.`;
    try {
      const body = await res.json();
      if (body?.error?.code) code = body.error.code;
      if (body?.error?.message) message = body.error.message;
    } catch {
      /* keep defaults */
    }
    throw new ApiError(code, message, res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  portfolioSummary: () => request<PortfolioSummary>("/api/portfolio/summary"),
  occupancy: () => request<any>("/api/portfolio/occupancy"),
  revenue: () => request<any>("/api/portfolio/revenue?months=24"),
  collectionEfficiency: () => request<any>("/api/portfolio/collection-efficiency"),
  spotlight: () => request<{ lease_id: number }>("/api/portfolio/spotlight"),
  ledger: (propertyId?: number, months = 6) =>
    request<LedgerResponse>(
      `/api/ledger?months=${months}${propertyId ? `&property_id=${propertyId}` : ""}`,
    ),
  tenant: (leaseId: number) => request<TenantDetail>(`/api/tenants/${leaseId}`),
  outlook: () => request<OutlookResponse>("/api/portfolio/outlook"),
  reminders: (leaseId?: number) =>
    request<Reminder[]>(`/api/reminders${leaseId ? `?lease_id=${leaseId}` : ""}`),
  draftReminder: (leaseId: number, language: string, tone: string) =>
    request<Reminder>("/api/reminders/draft", {
      method: "POST",
      body: JSON.stringify({ lease_id: leaseId, language, tone }),
    }),
  approveReminder: (id: number) =>
    request<Reminder>(`/api/reminders/${id}/approve`, { method: "POST" }),
  checkMessage: (leaseId: number, language: string, message: string) =>
    request<Guardrail[]>("/api/reminders/check", {
      method: "POST",
      body: JSON.stringify({ lease_id: leaseId, language, message }),
    }),
  modelCard: () => request<ModelCardResponse>("/api/model/card"),
  maintenance: (leaseId?: number) =>
    request<MaintenanceRequest[]>(`/api/maintenance${leaseId ? `?lease_id=${leaseId}` : ""}`),
  createMaintenance: (leaseId: number, text: string) =>
    request<MaintenanceRequest>("/api/maintenance", {
      method: "POST",
      body: JSON.stringify({ lease_id: leaseId, text }),
    }),
};
