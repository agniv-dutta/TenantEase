/** Outbox page: every reminder drafted or approved, newest first. */

import { ApiError } from "../lib/api";
import { useState } from "react";

import { formatDate, monthShort } from "../lib/format";
import { useReminders } from "../lib/queries";
import Stamp from "../components/Stamp";

export default function OutboxPage() {
  const { data, isLoading, error } = useReminders();
  const [filter, setFilter] = useState<"all" | "draft" | "approved">("all");
  const reminders = (data ?? []).filter((reminder) => filter === "all" || reminder.status === filter);

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

      {data && data.length > 0 && (
        <div className="controls" aria-label="Filter reminders">
          {(["all", "draft", "approved"] as const).map((status) => (
            <button
              key={status}
              className="text-button text-filter"
              aria-pressed={filter === status}
              onClick={() => setFilter(status)}
            >
              {status === "all" ? "All" : status === "draft" ? "Drafts" : "Approved"}
            </button>
          ))}
        </div>
      )}
      {data && data.length > 0 && reminders.length === 0 && <p className="state-line">No {filter} reminders.</p>}

      {data &&
        reminders.map((r) => (
          <article
            key={r.id}
            style={{ borderBottom: "1px solid var(--rule)", padding: "var(--s-4) 0" }}
          >
            <div className="controls" style={{ margin: 0 }}>
              <span className="num small soft">
                {r.tenant_name}, {r.unit_label}, {monthShort(r.cycle_month)} {r.cycle_month.slice(0, 4)} cycle
              </span>
              <span className="small soft">
                {r.channel}, {r.tone}, {r.language}
              </span>
              {r.status === "approved" ? (
                <Stamp kind="approved" seed={`ob-${r.id}`} />
              ) : (
                <span className="small soft">Draft</span>
              )}
            </div>
            <p style={{ margin: "var(--s-2) 0 0" }}>
              {r.message.split("{PAY_LINK}").map((part, index, parts) => (
                <span key={index}>
                  {part}
                  {index < parts.length - 1 && (
                    <span className="pay-link-label" title="{PAY_LINK}">Pay link</span>
                  )}
                </span>
              ))}
            </p>
            <div className="small soft">
              Drafted {formatDate(r.created_at.slice(0, 10))}
              {r.approved_at ? `, approved ${formatDate(r.approved_at.slice(0, 10))}` : ""}
              {r.guardrails.length > 0
                ? `, guardrails ${r.guardrails.filter((g) => g.passed).length}/${r.guardrails.length} passed`
                : ""}
              {r.fallback ? ", template fallback" : ""}
            </div>
          </article>
        ))}
    </>
  );
}
