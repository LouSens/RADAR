import { Navigate, Route, Routes } from "react-router-dom";

import { useLiveConnection } from "./api/live";
import { Layout } from "./components/Layout";
import { Message } from "./components/ui";
import { AssetPage } from "./pages/AssetPage";
import { Overview } from "./pages/Overview";
import { PortfolioPage } from "./pages/PortfolioPage";
import { SignalsPage } from "./pages/SignalsPage";
import { SystemPage } from "./pages/SystemPage";
import { TogetherPage } from "./pages/TogetherPage";

export function App() {
  useLiveConnection();
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="asset/:slug/:section?" element={<AssetPage />} />
        <Route path="together/:section?" element={<TogetherPage />} />
        <Route path="portfolio/:section?" element={<PortfolioPage />} />
        <Route path="signals/:type?" element={<SignalsPage />} />
        <Route path="system" element={<SystemPage />} />
        <Route path="status" element={<Navigate to="/system" replace />} />
        <Route path="*" element={<Message>That page does not exist.</Message>} />
      </Route>
    </Routes>
  );
}
