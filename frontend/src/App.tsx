import { Navigate, Route, Routes } from "react-router-dom";

import Shell from "./components/Shell";
import FoundationPage from "./pages/FoundationPage";
import LedgerPage from "./pages/LedgerPage";
import ModelNotesPage from "./pages/ModelNotesPage";
import OutlookPage from "./pages/OutlookPage";
import OutboxPage from "./pages/OutboxPage";
import LandingPage from "./pages/LandingPage";
import PortfolioPage from "./pages/PortfolioPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/app" element={<Navigate to="/app/ledger" replace />} />
      <Route path="/app/ledger" element={<Shell><LedgerPage /></Shell>} />
      <Route path="/app/portfolio" element={<Shell><PortfolioPage /></Shell>} />
      <Route path="/app/outlook" element={<Shell><OutlookPage /></Shell>} />
      <Route path="/app/outbox" element={<Shell><OutboxPage /></Shell>} />
      <Route path="/app/model-notes" element={<Shell><ModelNotesPage /></Shell>} />
      <Route path="/app/foundation" element={<Shell><FoundationPage /></Shell>} />
      <Route path="/ledger" element={<Navigate to="/app/ledger" replace />} />
      <Route path="/outlook" element={<Navigate to="/app/outlook" replace />} />
      <Route path="/outbox" element={<Navigate to="/app/outbox" replace />} />
      <Route path="/model-notes" element={<Navigate to="/app/model-notes" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
