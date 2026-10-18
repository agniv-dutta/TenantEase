/** Foundation page: a quiet check that fonts and figures render as intended. */

import Stamp from "../components/Stamp";

export default function FoundationPage() {
  return (
    <>
      <h1 className="page-title">Foundation</h1>
      <p className="soft">
        A small page to confirm the type and stamps render correctly. Not part of the main flow.
      </p>

      <h2 className="section-title">Display type</h2>
      <p style={{ fontFamily: "var(--font-display)", fontSize: "var(--fs-page)", lineHeight: "var(--lh-page)" }}>
        किराया बाकी है
      </p>
      <p style={{ fontFamily: "var(--font-display)", fontSize: "var(--fs-section)" }}>
        TenantEase Khata
      </p>

      <h2 className="section-title">Body type</h2>
      <p>किराया बाकी है — the Hindi renders in Mukta, and the Latin text sits beside it.</p>

      <h2 className="section-title">Tabular figures</h2>
      <table className="data" style={{ maxWidth: 320 }}>
        <tbody>
          {[111100, 99999, 12345, 4200, 700].map((n) => (
            <tr key={n}>
              <td className="num">₹{n.toLocaleString("en-IN")}</td>
              <td className="num">{n.toLocaleString("en-IN")}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2 className="section-title">Stamps</h2>
      <div style={{ display: "flex", gap: "var(--s-5)", flexWrap: "wrap", padding: "var(--s-4) 0" }}>
        <Stamp kind="late" detail="+9 days" seed="foundation-late" />
        <Stamp kind="overdue" seed="foundation-overdue" />
        <Stamp kind="due" seed="foundation-due" />
        <Stamp kind="approved" seed="foundation-approved" />
      </div>
    </>
  );
}
