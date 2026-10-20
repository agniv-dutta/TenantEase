import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../lib/api";
import type { AuditEvent, AuditKind } from "../lib/types";

const KINDS: AuditKind[] = ["reminder_drafted", "reminder_edited", "reminder_approved", "payment_recorded", "payment_parsed"];

function csvCell(value: unknown): string {
  const text = typeof value === "string" ? value : JSON.stringify(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

export default function AuditPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["audit-events"], queryFn: api.auditEvents });
  const [leaseFilter, setLeaseFilter] = useState("");
  const [kindFilter, setKindFilter] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const leaseOptions = useMemo(() => [...new Set((data ?? []).map((event) => event.lease_id).filter((id): id is number => id !== null))].sort((a, b) => a - b), [data]);
  const filtered = useMemo(() => (data ?? []).filter((event) =>
    (!leaseFilter || event.lease_id === Number(leaseFilter)) &&
    (!kindFilter || event.kind === kindFilter) &&
    event.summary.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()),
  ), [data, leaseFilter, kindFilter, search]);

  function exportCsv() {
    const header = ["id", "at", "actor", "kind", "lease_id", "summary", "details"];
    const rows = filtered.map((event) => [event.id, event.at, event.actor, event.kind, event.lease_id, event.summary, event.details]);
    const csv = `\uFEFF${[header, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n")}`;
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "tenantease-audit.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return <>
    <h1 className="page-title">Audit</h1>
    <p>Server recorded reminder and payment actions, newest first.</p>
    {isLoading && <p className="state-line">Loading audit events…</p>}
    {error && <p className="state-line">Could not load audit events. {error instanceof ApiError ? error.message : "Check the API and try again."}</p>}
    {data && <>
      <div className="controls audit-filters">
        <label>Lease
          <select value={leaseFilter} onChange={(event) => setLeaseFilter(event.target.value)}><option value="">All leases</option>{leaseOptions.map((id) => <option key={id} value={id}>{id}</option>)}</select>
        </label>
        <label>Kind
          <select value={kindFilter} onChange={(event) => setKindFilter(event.target.value)}><option value="">All kinds</option>{KINDS.map((kind) => <option key={kind} value={kind}>{kind.replaceAll("_", " ")}</option>)}</select>
        </label>
        <label>Search summary
          <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search events" />
        </label>
        <button onClick={exportCsv}>Export CSV</button>
      </div>
      {filtered.length === 0 ? <p className="state-line">No matching events. Change the filters or complete a reminder or payment action.</p> :
        <div className="audit-table-wrap"><table className="data audit-table"><thead><tr><th>Time</th><th>Actor</th><th>Kind</th><th>Lease</th><th>Summary</th><th>Details</th></tr></thead><tbody>
          {filtered.map((event) => <tr key={event.id}><td>{event.at.replace("T", " ").replace("+00:00", " UTC")}</td><td>{event.actor}</td><td>{event.kind.replaceAll("_", " ")}</td><td>{event.lease_id ?? "—"}</td><td>{event.summary}</td><td><button className="text-button" onClick={() => setSelected(event)}>Open details</button></td></tr>)}
        </tbody></table></div>}
    </>}
    {selected && <div className="drawer-backdrop" role="presentation" onClick={() => setSelected(null)}>
      <section className="drawer audit-drawer" role="dialog" aria-modal="true" aria-labelledby="audit-details-title" onClick={(event) => event.stopPropagation()}>
        <button onClick={() => setSelected(null)}>Close</button>
        <h2 id="audit-details-title">Event details</h2>
        <p>{selected.summary}</p>
        {selected.kind === "reminder_edited" && <>
          <h3 className="subhead">Before</h3><pre className="audit-value">{String(selected.details.before ?? "")}</pre>
          <h3 className="subhead">After</h3><pre className="audit-value">{String(selected.details.after ?? "")}</pre>
        </>}
        <pre className="audit-value">{JSON.stringify(selected.details, null, 2)}</pre>
      </section>
    </div>}
  </>;
}
