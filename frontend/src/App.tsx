import { Navigate, Route, Routes } from "react-router-dom";

import { useLiveConnection } from "./api/live";
import { Layout } from "./components/Layout";
import { Message } from "./components/ui";
import { AssetPage } from "./pages/AssetPage";
import { CalendarPage } from "./pages/CalendarPage";
import { MarketsPage } from "./pages/MarketsPage";
import { Overview } from "./pages/Overview";
import { PortfolioPage } from "./pages/PortfolioPage";
import { SignalsPage } from "./pages/SignalsPage";
import { SystemPage } from "./pages/SystemPage";

export function App() {
  useLiveConnection();
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="markets" element={<MarketsPage />} />
        <Route path="asset/:slug/:section?" element={<AssetPage />} />
        <Route path="portfolio/:section?" element={<PortfolioPage />} />
        <Route path="signals/:type?" element={<SignalsPage />} />
        <Route path="calendar" element={<CalendarPage />} />
        {/* Addresses of pages that were removed: send them to the nearest page that exists. */}
        <Route path="calendar/*" element={<Navigate to="/calendar" replace />} />
        <Route path="together/*" element={<Navigate to="/markets" replace />} />
        <Route path="system" element={<SystemPage />} />
        <Route path="status" element={<Navigate to="/system" replace />} />
        <Route path="*" element={<Message>That page does not exist.</Message>} />
      </Route>
    </Routes>
  );
}
