import { Route, Routes } from "react-router-dom";

import Shell from "./components/Shell";
import FoundationPage from "./pages/FoundationPage";
import LedgerPage from "./pages/LedgerPage";
import ModelNotesPage from "./pages/ModelNotesPage";
import OutlookPage from "./pages/OutlookPage";
import OutboxPage from "./pages/OutboxPage";

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<LedgerPage />} />
        <Route path="/outlook" element={<OutlookPage />} />
        <Route path="/outbox" element={<OutboxPage />} />
        <Route path="/model-notes" element={<ModelNotesPage />} />
        <Route path="/foundation" element={<FoundationPage />} />
      </Routes>
    </Shell>
  );
}
