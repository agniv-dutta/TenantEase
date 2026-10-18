/** The ledger: one row per lease, months as columns, stamps pressed into the
 *  cells. The tenant and unit column stays put while the months scroll. */

import { formatDate, monthShort } from "../lib/format";
import type { LedgerRow, PaymentCell, Tier } from "../lib/types";
import RiskStroke from "./RiskStroke";
import Stamp from "./Stamp";

interface LedgerTableProps {
  rows: LedgerRow[];
  onOpen: (leaseId: number) => void;
  shouldAnimate: (leaseId: number) => boolean;
}

function Cell({ cell, seed, animate }: { cell: PaymentCell; seed: string; animate: boolean }) {
  const detail = cell.days_late ? `+${cell.days_late} days` : undefined;
  switch (cell.status) {
    case "paid_late":
      return <Stamp kind="late" detail={detail} seed={seed} animateIn={animate} />;
    case "unpaid_overdue":
      return <Stamp kind="overdue" seed={seed} animateIn={animate} />;
    case "open":
      return <Stamp kind="due" seed={seed} animateIn={animate} />;
    case "paid_on_time":
      return <span className="num cell-paid">{cell.paid_date ? formatDate(cell.paid_date) : "—"}</span>;
    default:
      return <span className="num soft">{formatDate(cell.due_date)}</span>;
  }
}

export default function LedgerTable({ rows, onOpen, shouldAnimate }: LedgerTableProps) {
  if (rows.length === 0) {
    return <p className="state-line">No active leases for this register in the open cycle.</p>;
  }
  const months = rows[0].cycles.map((c) => c.cycle_month);

  return (
    <table className="ledger">
      <thead>
        <tr>
          <th className="tenant-col" scope="col">
            Tenant and unit
          </th>
          {months.map((m, i) => (
            <th key={m} scope="col" className={i < months.length - 2 ? "hide-narrow" : undefined}>
              <span className="num">{monthShort(m)}</span>
            </th>
          ))}
          <th scope="col">This cycle</th>
          <th className="cell-risk" scope="col">
            Late risk
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, rowIndex) => {
          const animate = shouldAnimate(row.lease_id);
          const delay = animate ? Math.min(rowIndex, 11) * 60 : 0;
          const tier: Tier | null = row.current.tier ?? null;
          return (
            <tr
              key={row.lease_id}
              tabIndex={0}
              onClick={() => onOpen(row.lease_id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onOpen(row.lease_id);
                }
              }}
            >
              <td className="tenant-col margin-rule">
                <div>{row.tenant_name}</div>
                <div className="small soft num">{row.unit_label}</div>
              </td>
              {row.cycles.map((cell, i) => (
                <td key={cell.cycle_month} className={`cycle-cell${i < months.length - 2 ? " hide-narrow" : ""}`}>
                  <span style={animate ? { animation: `stamp-in 160ms ease-out ${delay}ms both` } : undefined}>
                    <Cell cell={cell} seed={`${row.lease_id}-${cell.cycle_month}`} animate={false} />
                  </span>
                </td>
              ))}
              <td className="cycle-cell">
                <Cell cell={row.current} seed={`${row.lease_id}-open`} animate={animate} />
              </td>
              <td className="cell-risk cycle-cell">
                {row.current.probability != null && tier ? (
                  <RiskStroke probability={row.current.probability} tier={tier} seed={`${row.lease_id}`} />
                ) : (
                  <span className="small soft">Not enough history yet</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
