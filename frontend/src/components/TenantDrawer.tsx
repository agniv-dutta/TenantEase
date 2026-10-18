/** Tenant drawer: history, a plain-language explanation of the score, the
 *  reminder plan, and the reminder draft with guardrails and approval. */

import { useEffect, useRef, useState } from "react";

import { api, ApiError } from "../lib/api";
import { formatINR, formatDate, percent, weekdayDate } from "../lib/format";
import { useTenant } from "../lib/queries";
import type { Guardrail, Reminder } from "../lib/types";
import RiskStroke from "./RiskStroke";
import Stamp from "./Stamp";

const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "hi", label: "Hindi" },
  { value: "hinglish", label: "Hinglish" },
];

const TONES = [
  { value: "friendly", label: "Friendly" },
  { value: "neutral", label: "Neutral" },
  { value: "polite_firm", label: "Polite firm" },
];

interface TenantDrawerProps {
  leaseId: number;
  onClose: () => void;
}

export default function TenantDrawer({ leaseId, onClose }: TenantDrawerProps) {
  const { data, isLoading, error } = useTenant(leaseId);
  const [language, setLanguage] = useState("en");
  const [tone, setTone] = useState("friendly");
  const [reminder, setReminder] = useState<Reminder | null>(null);
  const [message, setMessage] = useState("");
  const [guardrails, setGuardrails] = useState<Guardrail[]>([]);
  const [edited, setEdited] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (data) {
      setLanguage(data.preferred_language || "en");
      setTone("friendly");
      setReminder(null);
      setMessage("");
      setGuardrails([]);
      setEdited(false);
    }
  }, [data]);

  if (isLoading) {
    return (
      <Shell wrapper onClose={onClose}>
        <p className="state-line">Loading tenant…</p>
      </Shell>
    );
  }
  if (error || !data) {
    return (
      <Shell wrapper onClose={onClose}>
        <p className="state-line">
          Could not load this tenant. {error instanceof ApiError ? error.message : "Try again."}
        </p>
      </Shell>
    );
  }

  const allPassed = guardrails.length > 0 && guardrails.every((g) => g.passed);
  const approved = reminder?.status === "approved";

  async function handleDraft() {
    setBusy(true);
    try {
      const r = await api.draftReminder(leaseId, language, tone);
      setReminder(r);
      setMessage(r.message);
      setGuardrails(r.guardrails);
      setEdited(false);
    } catch (e) {
      setToast(e instanceof ApiError ? e.message : "Draft failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleEdit(value: string) {
    setMessage(value);
    setEdited(true);
    if (reminder) {
      try {
        setGuardrails(await api.checkMessage(leaseId, language, value));
      } catch {
        /* keep previous results */
      }
    }
  }

  async function handleApprove() {
    if (!reminder) return;
    setBusy(true);
    try {
      const updated = await api.approveReminder(reminder.id);
      setReminder(updated);
      setToast("Reminder approved");
    } catch (e) {
      setToast(e instanceof ApiError ? e.message : "Approval failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell wrapper onClose={onClose}>
      <div className="subhead soft">
        {data.property_name} · {data.unit_label}
      </div>
      <h2>{data.tenant_name}</h2>
      <p className="small soft">
        Rent {formatINR(data.rent_inr)} · due day {data.due_day} · {data.occupation_type} · tenure{" "}
        {data.tenure_months} months
      </p>

      {data.cold_start && (
        <p className="notice">
          Not enough history yet. We use the building average until 3 cycles are recorded.
        </p>
      )}

      <hr className="rule" />
      <h3 className="subhead">Payment history</h3>
      <div className="history-strip">
        {data.history.length === 0 && <span className="small soft">No prior cycles.</span>}
        {data.history.map((cell) => (
          <div key={cell.cycle_month} className="history-cell">
            <span className="num small soft">{formatDate(cell.cycle_month)}</span>
            {cell.status === "paid_late" ? (
              <Stamp kind="late" detail={cell.days_late ? `+${cell.days_late}` : undefined} seed={`h-${leaseId}-${cell.cycle_month}`} />
            ) : cell.status === "unpaid_overdue" ? (
              <Stamp kind="overdue" seed={`h-${leaseId}-${cell.cycle_month}`} />
            ) : (
              <span className="num">{cell.paid_date ? formatDate(cell.paid_date) : formatDate(cell.due_date)}</span>
            )}
          </div>
        ))}
      </div>

      {!data.cold_start && data.probability != null && data.tier && (
        <>
          <hr className="rule" />
          <h3 className="subhead">Why this score</h3>
          <p>
            <RiskStroke probability={data.probability} tier={data.tier} seed={`d-${leaseId}`} /> chance this
            cycle is paid late.
          </p>
          {data.factors.slice(0, 3).map((f) => (
            <div className="factor" key={f.feature}>
              <div>
                {f.template_value} — {f.direction === "raises" ? "raises" : "lowers"} the late risk
              </div>
              <div className="dir">
                {f.direction === "raises" ? "raises" : "lowers"} · weight{" "}
                <span className="num">{percent(Math.min(1, Math.abs(f.contribution)))}</span>
              </div>
            </div>
          ))}
          <p className="small soft">
            This score only decides how early and how personally we remind. It is not a judgment of the
            tenant.
          </p>
        </>
      )}

      <hr className="rule" />
      <h3 className="subhead">Reminder plan</h3>
      <ul className="guardrail-list">
        {data.plan.map((step) => (
          <li key={`${step.offset_days}-${step.channel}`}>
            {weekdayDate(step.date)}:{" "}
            {step.owner === "manager"
              ? `call task for you (${step.tone})`
              : `${step.channel}, ${step.tone}`}
          </li>
        ))}
      </ul>

      <hr className="rule" />
      <h3 className="subhead">Reminder</h3>
      <div className="controls">
        <label>
          Language
          <select value={language} onChange={(e) => setLanguage(e.target.value)}>
            {LANGUAGES.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Tone
          <select value={tone} onChange={(e) => setTone(e.target.value)}>
            {TONES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        <button className="primary" onClick={handleDraft} disabled={busy}>
          Draft reminder
        </button>
      </div>

      {reminder && (
        <>
          <textarea value={message} onChange={(e) => handleEdit(e.target.value)} aria-label="Reminder message" />
          <ul className="guardrail-list">
            {guardrails.map((g) => (
              <li key={g.name}>{g.passed ? g.reason : `Needs fixing: ${g.reason}`}</li>
            ))}
          </ul>
          {reminder.fallback && (
            <p className="small soft">
              The provider was unavailable, so a template was used. The draft still passes every guardrail.
            </p>
          )}
          <div className="controls">
            <button className="primary" onClick={handleApprove} disabled={busy || !allPassed || approved}>
              Approve
            </button>
            {edited && !approved && <span className="small soft">Edited — re-checking guardrails.</span>}
            {approved && <Stamp kind="approved" seed={`a-${reminder.id}`} animateIn />}
          </div>
        </>
      )}

      {toast && <div className="toast">{toast}</div>}
    </Shell>
  );
}

function Shell({
  children,
  onClose,
  wrapper,
}: {
  children: React.ReactNode;
  onClose: () => void;
  wrapper?: boolean;
}) {
  const asideRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!wrapper || !asideRef.current) return;
    const aside = asideRef.current;
    const restoreTo = document.activeElement as HTMLElement | null;
    const focusables = () =>
      Array.from(
        aside.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => !el.hasAttribute("disabled"));

    focusables()[0]?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) return;
      const firstEl = items[0];
      const lastEl = items[items.length - 1];
      if (e.shiftKey && document.activeElement === firstEl) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && document.activeElement === lastEl) {
        e.preventDefault();
        firstEl.focus();
      }
    };
    aside.addEventListener("keydown", onKey);
    return () => {
      aside.removeEventListener("keydown", onKey);
      restoreTo?.focus();
    };
  }, [wrapper]);

  if (!wrapper) return <>{children}</>;
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Tenant detail" ref={asideRef}>
        <div className="controls">
          <button onClick={onClose}>Close</button>
        </div>
        {children}
      </aside>
    </>
  );
}
