/** Outbox page: every reminder drafted or approved, newest first. */

import { ApiError } from "../lib/api";
import { formatDate, monthShort } from "../lib/format";
import { useReminders } from "../lib/queries";
import Stamp from "../components/Stamp";

export default function OutboxPage() {
  const { data, isLoading, error } = useReminders();

  return (
    <>
      <h1 className="page-title">Outbox</h1>
      <p className="soft">Drafts and approved reminders, newest first. Nothing is ever sent automatically.</p>

      {isLoading && <p className="state-line">Loading the outbox…</p>}
      {error && (
        <p className="state-line">
          Could not load the outbox. {error instanceof ApiError ? error.message : "Check the API and try again."}
        </p>
      )}
      {data && data.length === 0 && <p className="state-line">No reminders yet. Draft one from a tenant in the ledger.</p>}

      {data &&
        data.map((r) => (
          <article
            key={r.id}
            style={{ borderBottom: "1px solid var(--rule)", padding: "var(--s-4) 0" }}
          >
            <div className="controls" style={{ margin: 0 }}>
              <span className="num small soft">
                Lease {r.lease_id} · {monthShort(r.cycle_month)} cycle
              </span>
              <span className="small soft">
                {r.channel} · {r.tone} · {r.language}
              </span>
              {r.status === "approved" ? (
                <Stamp kind="approved" seed={`ob-${r.id}`} />
              ) : (
                <span className="small soft">Draft</span>
              )}
            </div>
            <p style={{ margin: "var(--s-2) 0 0" }}>{r.message}</p>
            <div className="small soft">
              Drafted {formatDate(r.created_at.slice(0, 10))}
              {r.approved_at ? ` · approved ${formatDate(r.approved_at.slice(0, 10))}` : ""}
              {r.guardrails.length > 0
                ? ` · guardrails ${r.guardrails.filter((g) => g.passed).length}/${r.guardrails.length} passed`
                : ""}
              {r.fallback ? " · template fallback" : ""}
            </div>
          </article>
        ))}
    </>
  );
}
