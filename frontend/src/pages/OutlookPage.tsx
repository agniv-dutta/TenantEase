/** Outlook page: cumulative collections curve with an uncertainty band, and an
 *  assumption based what-if. The assumption is always labelled as such. */

import { useMemo, useState } from "react";

import { ApiError } from "../lib/api";
import { formatINR } from "../lib/format";
import { useOutlook } from "../lib/queries";

const W = 760;
const H = 320;
const M = { top: 24, right: 24, bottom: 40, left: 76 };

export default function OutlookPage() {
  const { data, isLoading, error } = useOutlook();
  const [topN, setTopN] = useState(10);
  const [effectPct, setEffectPct] = useState(15);

  const chart = useMemo(() => {
    if (!data) return null;
    const days = data.points.map((p) => p.day);
    const xMin = Math.min(...days);
    const xMax = Math.max(...days);
    const yMax = data.total_due;
    const x = (d: number) => M.left + ((d - xMin) / Math.max(1, xMax - xMin)) * (W - M.left - M.right);
    const y = (v: number) => H - M.bottom - (v / yMax) * (H - M.top - M.bottom);
    const line = (key: "p10" | "expected" | "p90") =>
      data.points.map((p, i) => `${i === 0 ? "M" : "L"} ${x(p.day).toFixed(1)} ${y(p[key]).toFixed(1)}`).join(" ");
    const band =
      "M " +
      data.points.map((p) => `${x(p.day).toFixed(1)} ${y(p.p90).toFixed(1)}`).join(" L ") +
      " L " +
      [...data.points].reverse().map((p) => `${x(p.day).toFixed(1)} ${y(p.p10).toFixed(1)}`).join(" L ") +
      " Z";
    return { x, y, line, band, xMin, xMax };
  }, [data]);

  return (
    <>
      <h1 className="page-title">Outlook</h1>
      {isLoading && <p className="state-line">Loading the outlook…</p>}
      {error && (
        <p className="state-line">
          Could not load the outlook. {error instanceof ApiError ? error.message : "Check the API and try again."}
        </p>
      )}

      {data && chart && (
        <>
          <p>
            By the 10th we expect about{" "}
            <span className="num">
              {formatINR(data.points.reduce((best, p) => (Math.abs(p.day - 10) < Math.abs(best.day - 10) ? p : best), data.points[0]).expected)}
            </span>{" "}
            of <span className="num">{formatINR(data.total_due)}</span> collected;{" "}
            <span className="num">{data.likely_late_count}</span> leases are likely to be more than 5 days
            late. Rent arrives in waves around the due days (1st, 5th and 10th), so the line steps up there.
          </p>

          <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Cumulative collections by day">
            <defs>
              <pattern id="band-hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <line x1="0" y1="0" x2="0" y2="8" stroke="var(--indigo-soft)" strokeWidth="1" opacity="0.5" />
              </pattern>
            </defs>

            {[0, 0.25, 0.5, 0.75, 1].map((f) => (
              <g key={f}>
                <line x1={M.left} y1={chart.y(f * data.total_due)} x2={W - M.right} y2={chart.y(f * data.total_due)} stroke="var(--rule)" />
                <text x={M.left - 8} y={chart.y(f * data.total_due) + 4} textAnchor="end" fill="var(--indigo-soft)" style={{ fontFamily: "var(--font-body)", fontSize: 12 }}>
                  {formatINR(Math.round(f * data.total_due))}
                </text>
              </g>
            ))}

            <path d={chart.band} fill="url(#band-hatch)" stroke="none" />
            <path d={chart.line("expected")} fill="none" stroke="var(--indigo)" strokeWidth="2.5" />

            {[1, 5, 10].map((d) =>
              d >= chart.xMin && d <= chart.xMax ? (
                <g key={d}>
                  <line x1={chart.x(d)} y1={M.top} x2={chart.x(d)} y2={H - M.bottom} stroke="var(--rule)" strokeDasharray="3 3" />
                  <text x={chart.x(d)} y={H - M.bottom + 18} textAnchor="middle" fill="var(--indigo-soft)" style={{ fontFamily: "var(--font-body)", fontSize: 12 }}>
                    {d}
                  </text>
                </g>
              ) : null,
            )}
            <text x={W / 2} y={H - 6} textAnchor="middle" fill="var(--indigo-soft)" style={{ fontFamily: "var(--font-body)", fontSize: 12 }}>
              Day of the month
            </text>
          </svg>

          <hr className="rule" />
          <h2 className="subhead">What if reminders shift payment earlier</h2>
          <div className="controls">
            <label>
              Remind the top <span className="num">{topN}</span> leases
              <input type="range" min={0} max={40} value={topN} onChange={(e) => setTopN(Number(e.target.value))} />
            </label>
            <label>
              Assume <span className="num">{effectPct}%</span> of them pay about a week sooner
              <input type="range" min={0} max={40} value={effectPct} onChange={(e) => setEffectPct(Number(e.target.value))} />
            </label>
          </div>
          <p className="notice">Assumption based, not measured.</p>
          <p>
            With these settings, roughly <span className="num">{Math.round((topN * effectPct) / 100)}</span> more
            leases would land earlier in the month, bringing about{" "}
            <span className="num">
              {formatINR(
                Math.round(
                  (data.total_due * Math.min(topN, 40) * effectPct) / (100 * Math.max(1, data.likely_late_count) * 12),
                ),
              )}
            </span>{" "}
            forward into the first ten days. Treat it as a sketch of scale, not a forecast.
          </p>

          <table className="data">
            <caption className="small soft">Collections by day, for screen readers and copy-paste.</caption>
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col">Low</th>
                <th scope="col">Expected</th>
                <th scope="col">High</th>
              </tr>
            </thead>
            <tbody>
              {data.points.filter((p) => p.day % 5 === 0 || p.day === 1).map((p) => (
                <tr key={p.day}>
                  <td className="num">{p.day}</td>
                  <td className="num">{formatINR(Math.round(p.p10))}</td>
                  <td className="num">{formatINR(Math.round(p.expected))}</td>
                  <td className="num">{formatINR(Math.round(p.p90))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </>
  );
}
