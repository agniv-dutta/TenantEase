import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import LedgerTable from "../components/LedgerTable";
import sample from "../data/landing-sample.json";
import { api } from "../lib/api";
import type { LedgerRow, ModelCardResponse } from "../lib/types";

const sampleRows = sample.rows as LedgerRow[];

/** Render the API-independent product overview and its optional live metrics. */
export default function LandingPage() {
  const [spotlight, setSpotlight] = useState<number | null>(null);
  const [model, setModel] = useState<ModelCardResponse | null>(null);
  const animationStarted = useRef(false);
  const [animate, setAnimate] = useState(false);
  useEffect(() => {
    if (!animationStarted.current) {
      animationStarted.current = true;
      setAnimate(true);
    }
    api.spotlight().then((lease) => setSpotlight(lease.lease_id)).catch(() => undefined);
    api.modelCard().then(setModel).catch(() => undefined);
  }, []);
  const metrics = model?.metrics as { models?: Record<string, { pr_auc?: number; top_k?: Record<string, { precision?: number }> }> } | undefined;
  const pr = metrics?.models?.M_lgbm_shipped?.pr_auc;
  const baseline = metrics?.models?.B0_rule_baseline?.pr_auc;
  const precision = metrics?.models?.M_lgbm_shipped?.top_k?.["10"]?.precision;
  const metricText = pr != null && baseline != null && precision != null
    ? <>On three held-out months of synthetic data, the model reached a PR-AUC of {pr.toFixed(3)} against {baseline.toFixed(3)} for a 'late last month' rule. Following up with the top 10 percent of leases reached {precision.toFixed(3)} precision. A simple logistic model came close behind, which is expected because the synthetic data was built with logistic effects.</>
    : <>Model numbers are unavailable right now. <Link to="/app/model-notes">See Model notes</Link>.</>;
  const shouldAnimate = useMemo(() => () => animate, [animate]);
  return <div className="landing">
    <header className="landing-top">
      <Link className="landing-brand" to="/">TenantEase Khata</Link>
      <nav aria-label="Page sections"><a href="#how-it-works">How it works</a><a href="#limits">Limits</a></nav>
      <Link className="landing-button" to="/app/ledger">Open the ledger</Link>
    </header>
    <main>
      <section className="landing-hero">
        <div><h1>Know who is likely to pay late before the month begins</h1>
          <p>Khata adds a late-payment score, a reminder plan and drafted messages to the TenantEase rent ledger. Messages come in English, Hindi and Hinglish, and nothing is sent until you approve it.</p>
          <div className="hero-actions"><Link className="landing-button" to="/app/ledger">Open the ledger</Link><Link to={spotlight ? `/app/ledger?lease=${spotlight}` : "/app/ledger"}>See a high-risk tenant</Link></div>
          <p className="small soft">Runs on synthetic data. No sign-in needed.</p>
        </div>
        <div className="mini-ledger" aria-label="Sample ledger preview"><LedgerTable rows={sampleRows} onOpen={() => undefined} shouldAnimate={shouldAnimate} /></div>
      </section>
      <section id="how-it-works" className="landing-section"><h2>From score to approved message</h2><ol className="process-list">
        <li><span>1</span><div><b>Score</b><p>Each lease gets a chance of paying more than 5 days late next cycle, with the top reasons in plain words.</p></div></li>
        <li><span>2</span><div><b>Plan</b><p>The score sets how early and how personally to remind: one nudge, two, or a nudge plus a call for you.</p></div></li>
        <li><span>3</span><div><b>Draft</b><p>A message is drafted in the tenant's language and checked for the amount, the date, the tone and banned phrases.</p></div></li>
        <li><span>4</span><div><b>Approve</b><p>You read it, edit it if you like, and approve it. Nothing is sent automatically.</p></div></li>
      </ol></section>
      <section className="landing-section"><h2>What changes for TenantEase</h2><div className="comparison" role="table" aria-label="TenantEase features"><div role="row" className="comparison-head"><b role="columnheader">As described on cynbit.in</b><b role="columnheader">With Khata</b></div>{[
        ["Reminders","Automated system reminders","Timing, channel and tone depend on each lease's score"],
        ["Pending dues","A list of pending dues","A day-by-day forecast of what will arrive, with a range"],
        ["Payment history","Full digital payment history","The same history, plus why a lease is flagged"],
        ["Messages","Not described","Drafts in three languages that you approve"],
      ].map(([label,left,right])=><div role="row" className="comparison-row" key={label}><b role="rowheader">{label}</b><span role="cell">{left}</span><span role="cell">{right}</span></div>)}</div><p className="small soft">The left column paraphrases Cynbit's public product page, which describes features, not how they work.</p></section>
      <section className="landing-section"><h2>How well it works</h2><p>{metricText}</p><Link to="/app/model-notes">Read the model notes</Link></section>
      <section id="limits" className="landing-section"><h2>What this prototype does not do</h2><ul className="limits-list"><li>It uses synthetic data, so accuracy here says nothing about real tenants.</li><li>It never sends a message.</li><li>The score decides how early and how personally we remind. It is never used for eviction, pricing or screening.</li><li>The effect of a reminder on behaviour is assumed in the sliders, not measured.</li></ul></section>
      <section className="landing-section closing"><h2>Try it on a synthetic portfolio</h2><Link className="landing-button" to="/app/ledger">Open the ledger</Link><a href="https://www.cynbit.in/products#inquiry" target="_blank" rel="noopener noreferrer">Talk to Cynbit about TenantEase</a><p className="small soft">Built by Agniv Dutta as an AI/ML internship submission. This is a prototype, not an official Cynbit product.</p></section>
    </main>
    <footer className="footer-line landing-footer">Demo data is synthetic. Scores are for scheduling reminders only.</footer>
  </div>;
}
