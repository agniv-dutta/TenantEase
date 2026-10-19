/** Ledger page: the register of leases with stamps pressed into the months. */

import { useEffect, useMemo, useRef, useState } from "react";

import LedgerTable from "../components/LedgerTable";
import RegisterTabs from "../components/RegisterTabs";
import TenantDrawer from "../components/TenantDrawer";
import { ApiError } from "../lib/api";
import { formatDate, formatINR, monthShort } from "../lib/format";
import { useLedger, usePortfolioSummary } from "../lib/queries";

const stampedThisSession = new Set<number>();

export default function LedgerPage() {
  const [propertyId, setPropertyId] = useState<string>("all");
  const [riskFirst, setRiskFirst] = useState(true);
  const [needCallOnly, setNeedCallOnly] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const initialSequenceStarted = useRef(false);

  const summary = usePortfolioSummary();
  const ledger = useLedger(undefined, 6);

  const rows = ledger.data?.rows ?? [];

  const properties = useMemo(() => {
    const seen = new Map<number, string>();
    for (const r of rows) {
      if (!seen.has(r.property_id)) seen.set(r.property_id, r.property_name);
    }
    return Array.from(seen, ([id, name]) => ({ id: String(id), label: name }));
  }, [rows]);

  const visible = useMemo(() => {
    let list = rows;
    if (propertyId !== "all") list = list.filter((r) => String(r.property_id) === propertyId);
    if (needCallOnly) list = list.filter((r) => r.current.tier === "high");
    if (!riskFirst && !needCallOnly) {
      list = [...list].sort((a, b) =>
        a.unit_label.localeCompare(b.unit_label, undefined, { numeric: true }),
      );
    }
    return list;
  }, [rows, propertyId, needCallOnly, riskFirst]);

  const shouldAnimate = (leaseId: number) => !stampedThisSession.has(leaseId);

  useEffect(() => {
    if (initialSequenceStarted.current || rows.length === 0) return;
    initialSequenceStarted.current = true;
    rows.forEach((row) => stampedThisSession.add(row.lease_id));
  }, [rows]);

  const tabs = [{ id: "all", label: "All properties" }, ...properties];

  return (
    <>
      <h1 className="page-title">Khata</h1>
      <p className="soft">
        {summary.data
          ? `${summary.data.active_leases} active leases, ${monthShort(summary.data.cycle_month)} cycle, expected collection ${formatINR(summary.data.expected_collection_inr)} of ${formatINR(summary.data.total_rent_due_inr)}. Data as of ${formatDate(summary.data.as_of_date)}.`
          : "Loading portfolio…"}
      </p>

      <RegisterTabs
        items={tabs}
        activeId={propertyId}
        onChange={setPropertyId}
        ariaLabel="Property register"
      />

      <div
        className="controls"
        style={{ background: "var(--chuna-deep)", padding: "var(--s-2) var(--s-3)" }}
      >
        <label>
          <input type="checkbox" checked={riskFirst} onChange={(e) => setRiskFirst(e.target.checked)} />
          Highest risk first
        </label>
        <label>
          <input
            type="checkbox"
            checked={needCallOnly}
            onChange={(e) => setNeedCallOnly(e.target.checked)}
          />
          Only leases that need a call
        </label>
      </div>

      {ledger.isLoading && <p className="state-line">Loading the ledger…</p>}
      {ledger.error && (
        <p className="state-line">
          Could not load the ledger.{" "}
          {ledger.error instanceof ApiError ? ledger.error.message : "Check the API and try again."}
        </p>
      )}
      {ledger.data && <LedgerTable rows={visible} onOpen={setSelected} shouldAnimate={shouldAnimate} />}

      {selected !== null && <TenantDrawer leaseId={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
