import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiError, api } from "../lib/api";
import { formatINR } from "../lib/format";
import { useLedger } from "../lib/queries";
import type { PaymentConfirmation, PaymentParseResult } from "../lib/types";
import Stamp from "../components/Stamp";

export default function PaymentsPage() {
  const ledger = useLedger();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const presetLease = Number(searchParams.get("lease_id")) || null;
  const [message, setMessage] = useState("");
  const [parsed, setParsed] = useState<PaymentParseResult | null>(null);
  const [leaseId, setLeaseId] = useState<number | null>(presetLease);
  const [amount, setAmount] = useState("");
  const [paidDate, setPaidDate] = useState("");
  const [method, setMethod] = useState("upi");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmed, setConfirmed] = useState<PaymentConfirmation | null>(null);

  async function handleParse() {
    setBusy(true);
    setError("");
    setConfirmed(null);
    try {
      const result = await api.parsePayment(message);
      setParsed(result);
      setLeaseId((current) => current ?? result.matches[0]?.lease_id ?? null);
      setAmount(result.fields.amount?.toString() ?? "");
      setPaidDate(result.fields.paid_date ?? "");
      setMethod(result.fields.method ?? "upi");
      setReference(result.fields.reference ?? "");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not parse the message. Check the text and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm() {
    if (!parsed || leaseId === null || !ledger.data) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.recordPayment({
        lease_id: leaseId,
        cycle_month: ledger.data.cycle_month,
        amount: Number(amount),
        paid_date: paidDate,
        method,
        reference: reference || null,
      });
      setConfirmed(result);
      await queryClient.invalidateQueries({ queryKey: ["ledger"] });
      await queryClient.invalidateQueries({ queryKey: ["tenant", leaseId] });
      await queryClient.invalidateQueries({ queryKey: ["summary"] });
    } catch (cause) {
      setError(cause instanceof ApiError ? `${cause.message} Check the selected lease, amount and date.` : "Could not confirm the payment. Check the selected lease, amount and date.");
    } finally {
      setBusy(false);
    }
  }

  return <>
    <h1 className="page-title">Payments</h1>
    <p>Paste a payment message to extract its details. Review the match before you confirm; nothing is recorded automatically.</p>
    <label className="field">Payment message
      <textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Paste a synthetic payment message" aria-describedby="payment-message-help" />
    </label>
    <p id="payment-message-help" className="small soft">Use synthetic demo text. If an external parser is configured, phone numbers and payment handles are masked first.</p>
    <button className="primary" onClick={handleParse} disabled={busy || !message.trim()}>Parse message</button>
    {error && <p className="state-line" role="alert">{error}</p>}
    {confirmed && (
      <p className="state-line" role="status">
        Payment confirmed: {formatINR(confirmed.amount)} for lease {confirmed.lease_id}.{" "}
        {confirmed.status === "paid_late" ? (
          <>
            <Stamp kind="late" detail={`+${confirmed.days_late} days`} seed={`p-${confirmed.lease_id}-${confirmed.cycle_month}`} animateIn /> Paid late.
          </>
        ) : (
          "Recorded on time."
        )}
      </p>
    )}
    {parsed && <>
      <hr className="rule"/><h2 className="subhead">Review payment</h2>
      {parsed.flags.length > 0 && <p className="notice">Review these flags before confirming: {parsed.flags.join(", ")}.</p>}
      <div className="payment-fields">
        <label>Amount in INR<input inputMode="numeric" type="number" min="1" value={amount} onChange={(event) => setAmount(event.target.value)} /></label>
        <label>Paid date<input type="date" value={paidDate} onChange={(event) => setPaidDate(event.target.value)} /></label>
        <label>Method<select value={method} onChange={(event) => setMethod(event.target.value)}><option value="upi">UPI</option><option value="cash">Cash</option><option value="bank_transfer">Bank transfer</option><option value="cheque">Cheque</option></select></label>
        <label>Reference<input value={reference} onChange={(event) => setReference(event.target.value)} /></label>
      </div>
      <fieldset className="payment-matches"><legend>Choose the lease</legend>
        {parsed.matches.length === 0 && <p className="state-line">No lease matched. Check the message or choose a clearer payer name and parse it again.</p>}
        {parsed.matches.map((match) => <label key={match.lease_id} className="payment-match"><input type="radio" name="payment-lease" checked={leaseId === match.lease_id} onChange={() => setLeaseId(match.lease_id)} /><span>{match.tenant}, unit {match.unit}</span><span className="small soft">{match.reasons.join(" · ")}</span></label>)}
      </fieldset>
      <button className="primary" onClick={handleConfirm} disabled={busy || leaseId === null || !amount || !paidDate || !ledger.data}>Confirm payment</button>
    </>}
  </>;
}
