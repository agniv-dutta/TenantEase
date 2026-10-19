/** React Query hooks around the API client. */

import { useQuery } from "@tanstack/react-query";

import { api } from "./api";

export function usePortfolioSummary() {
  return useQuery({ queryKey: ["summary"], queryFn: api.portfolioSummary });
}

export function useLedger(propertyId?: number, months = 6) {
  return useQuery({
    queryKey: ["ledger", propertyId ?? "all", months],
    queryFn: () => api.ledger(propertyId, months),
  });
}

export function useTenant(leaseId: number | null) {
  return useQuery({
    queryKey: ["tenant", leaseId],
    queryFn: () => api.tenant(leaseId as number),
    enabled: leaseId !== null,
  });
}

export function useOutlook() {
  return useQuery({ queryKey: ["outlook"], queryFn: api.outlook });
}

export function useReminders(leaseId?: number) {
  return useQuery({
    queryKey: ["reminders", leaseId ?? "all"],
    queryFn: () => api.reminders(leaseId),
  });
}

export function useMaintenance(leaseId: number | null) {
  return useQuery({
    queryKey: ["maintenance", leaseId],
    queryFn: () => api.maintenance(leaseId as number),
    enabled: leaseId !== null,
  });
}

export function useModelCard() {
  return useQuery({ queryKey: ["model-card"], queryFn: api.modelCard });
}
