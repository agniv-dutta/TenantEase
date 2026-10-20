/** App shell: left rail for primary navigation, the ruled sheet in the middle,
 *  and a persistent footer disclaimer. */

import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Overview" },
  { to: "/app/ledger", label: "Ledger" },
  { to: "/app/portfolio", label: "Portfolio" },
  { to: "/app/outlook", label: "Outlook" },
  { to: "/app/outbox", label: "Outbox" },
  { to: "/app/model-notes", label: "Model notes" },
];

export default function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="shell">
      <aside className="rail">
        <div className="product">TenantEase Khata</div>
        <nav aria-label="Sections">
          {LINKS.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.to === "/"}>
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="rail-foot small soft">
          Demo data is synthetic.
        </div>
      </aside>
      <main className="main-wrap">{children}</main>
      <div className="footer-line">
        Demo data is synthetic. Scores are for scheduling reminders only.
      </div>
    </div>
  );
}
