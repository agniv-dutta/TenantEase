/** Model notes page: honest metrics, calibration, capacity and slices, plus the
 *  full model card. */

import { useMemo } from "react";

import { ApiError } from "../lib/api";
import { Markdown } from "../lib/markdown";
import { useModelCard } from "../lib/queries";

interface ModelMetrics {
  pr_auc: number;
  roc_auc: number;
  brier: number;
  ece: number;
  calibration_curve: { mean_predicted: number; fraction_positive: number; n: number }[];
  top_k: Record<string, { precision: number; recall: number }>;
}

interface Metrics {
  synthetic_data: boolean;
  note: string;
  n_test_rows: number;
  test_base_rate: number;
  operating_threshold: number;
  models: Record<string, ModelMetrics>;
  calibration_note: string;
  ablation_no_occupation: { pr_auc: number; roc_auc: number };
}

interface SliceBucket {
  n: number;
  late_rate: number;
  recall: number;
  fpr: number;
}

interface Slices {
  slices: Record<string, Record<string, SliceBucket>>;
  gap_flags: { slice: string; metric: string; a: string; b: string; gap_pp: number }[];
  threshold: number;
}

const MODEL_LABELS: Record<string, string> = {
  B0_rule_baseline: "B0 · rule baseline",
  B1_logistic: "B1 · logistic",
  M_lgbm_raw: "M · LightGBM (raw)",
  M_lgbm_isotonic: "M · LightGBM (isotonic)",
};

const GROUP_LABELS: Record<string, string> = {
  occupation_type: "Occupation",
  tenure_group: "Tenure",
  rent_band: "Rent band",
  preferred_language_audit_only: "Language (audit only)",
};

function CalibrationPlot({ model }: { model: ModelMetrics }) {
  const W = 340;
  const H = 340;
  const pad = 36;
  const x = (v: number) => pad + v * (W - pad * 2);
  const y = (v: number) => H - pad - v * (H - pad * 2);
  const line = model.calibration_curve
    .map((p, i) => `${i === 0 ? "M" : "L"} ${x(p.mean_predicted).toFixed(1)} ${y(p.fraction_positive).toFixed(1)}`)
    .join(" ");

  return (
    <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Calibration curve">
      <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="var(--rule)" strokeDasharray="4 4" />
      <line x1={pad} y1={H - pad} x2={W - pad} y2={H - pad} stroke="var(--indigo)" />
      <line x1={pad} y1={pad} x2={pad} y2={H - pad} stroke="var(--indigo)" />
      <path d={line} fill="none" stroke="var(--indigo)" strokeWidth="2.5" />
      {model.calibration_curve.map((p) => (
        <circle key={p.mean_predicted} cx={x(p.mean_predicted)} cy={y(p.fraction_positive)} r="3" fill="var(--verdigris)" />
      ))}
      <text x={W / 2} y={H - 6} textAnchor="middle" fill="var(--indigo-soft)" style={{ fontFamily: "var(--font-body)", fontSize: 12 }}>
        Predicted probability
      </text>
      <text x={12} y={H / 2} textAnchor="middle" transform={`rotate(-90 12 ${H / 2})`} fill="var(--indigo-soft)" style={{ fontFamily: "var(--font-body)", fontSize: 12 }}>
        Share that were actually late
      </text>
    </svg>
  );
}

export default function ModelNotesPage() {
  const { data, isLoading, error } = useModelCard();

  const metrics = data?.metrics as unknown as Metrics | undefined;
  const slices = data?.slices as unknown as Slices | undefined;

  const calibrationModel = useMemo(() => metrics?.models?.M_lgbm_isotonic, [metrics]);

  return (
    <>
      <h1 className="page-title">Model notes</h1>

      {isLoading && <p className="state-line">Loading the model card…</p>}
      {error && (
        <p className="state-line">
          Could not load the model card.{" "}
          {error instanceof ApiError ? error.message : "Run make train and make eval, then try again."}
        </p>
      )}

      {data && metrics && (
        <>
          <p className="notice">{metrics.note}</p>

          <h2 className="section-title">Model comparison</h2>
          <table className="data">
            <thead>
              <tr>
                <th scope="col">Model</th>
                <th scope="col">PR-AUC</th>
                <th scope="col">ROC-AUC</th>
                <th scope="col">Brier</th>
                <th scope="col">ECE</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(metrics.models).map(([name, m]) => (
                <tr key={name}>
                  <td>{MODEL_LABELS[name] ?? name}</td>
                  <td className="num">{m.pr_auc.toFixed(3)}</td>
                  <td className="num">{m.roc_auc.toFixed(3)}</td>
                  <td className="num">{m.brier.toFixed(3)}</td>
                  <td className="num">{m.ece.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="small soft">
            Ablation without occupation: PR-AUC {metrics.ablation_no_occupation.pr_auc.toFixed(3)}, ROC-AUC{" "}
            {metrics.ablation_no_occupation.roc_auc.toFixed(3)}. {metrics.calibration_note}
          </p>

          <h2 className="section-title">Capacity: top share of leases per cycle</h2>
          <table className="data">
            <thead>
              <tr>
                <th scope="col">Follow-up</th>
                {Object.keys(metrics.models.M_lgbm_isotonic.top_k).map((k) => (
                  <th key={k} scope="col" className="num">
                    {k}%
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Precision</td>
                {Object.values(metrics.models.M_lgbm_isotonic.top_k).map((v, i) => (
                  <td key={i} className="num">{v.precision.toFixed(3)}</td>
                ))}
              </tr>
              <tr>
                <td>Recall</td>
                {Object.values(metrics.models.M_lgbm_isotonic.top_k).map((v, i) => (
                  <td key={i} className="num">{v.recall.toFixed(3)}</td>
                ))}
              </tr>
            </tbody>
          </table>

          <h2 className="section-title">Calibration</h2>
          {calibrationModel && <CalibrationPlot model={calibrationModel} />}

          {slices && (
            <>
              <h2 className="section-title">Slices</h2>
              {Object.entries(slices.slices).map(([group, buckets]) => {
                const flags = slices.gap_flags.filter((f) => f.slice === group);
                return (
                  <div key={group} style={{ marginBottom: "var(--s-5)" }}>
                    <h3 className="subhead">{GROUP_LABELS[group] ?? group}</h3>
                    <table className="data">
                      <thead>
                        <tr>
                          <th scope="col">Bucket</th>
                          <th scope="col">n</th>
                          <th scope="col">Late rate</th>
                          <th scope="col">Recall</th>
                          <th scope="col">False positive rate</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(buckets).map(([bucket, s]) => (
                          <tr key={bucket}>
                            <td>{bucket}</td>
                            <td className="num">{s.n}</td>
                            <td className="num">{(s.late_rate * 100).toFixed(1)}%</td>
                            <td className="num">{(s.recall * 100).toFixed(1)}%</td>
                            <td className="num">{(s.fpr * 100).toFixed(1)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {flags.map((f, fi) => (
                      <p key={fi} className="small gap-flag">
                        {f.metric} gap of <span className="num">{f.gap_pp.toFixed(1)}</span> points between{" "}
                        {f.a} and {f.b} — {f.gap_pp > 10 ? "a gap above 10 points" : "within normal noise"}.{" "}
                        Investigate this slice before trusting it.
                      </p>
                    ))}
                  </div>
                );
              })}
            </>
          )}

          <h2 className="section-title">What this does not show</h2>
          <ul>
            <li>These are synthetic results with planted effects, not production accuracy.</li>
            <li>Slice gaps above are real inside the demo data; with about {metrics.n_test_rows} test rows they are noisy.</li>
            <li>No claim is made that a reminder changes behaviour. The what-if on the outlook page is assumption based.</li>
          </ul>

          <hr className="rule" />
          <Markdown source={data.card_markdown} />
        </>
      )}
    </>
  );
}
