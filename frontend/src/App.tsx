import { Route, Routes } from "react-router-dom";

import { useLiveConnection } from "./api/live";
import { Layout } from "./components/Layout";
import { Notice } from "./components/ui";
import { AssetPage } from "./pages/AssetPage";
import { ComingSoon } from "./pages/ComingSoon";
import { Overview } from "./pages/Overview";
import { StatusPage } from "./pages/StatusPage";

export function App() {
  useLiveConnection();
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="asset/:slug" element={<AssetPage />} />
        <Route
          path="relationships"
          element={
            <ComingSoon title="Bitcoin vs gold" phase="Phase 5">
              <p>Whether Bitcoin and gold are moving together or apart, over time and by market regime.</p>
              <p>A grid of how every asset moves with every other, grouped so that similar assets sit together.</p>
            </ComingSoon>
          }
        />
        <Route
          path="portfolio"
          element={
            <ComingSoon title="Portfolio" phase="Phase 5">
              <p>Your holdings, entered by hand, by file, or read from Binance with a read-only key.</p>
              <p>Where your risk comes from, how other ways of splitting the same money would have behaved, and how your holdings fared in past crises.</p>
              <p>RADAR measures. It never places trades.</p>
            </ComingSoon>
          }
        />
        <Route
          path="signals"
          element={
            <ComingSoon title="Signals" phase="Phase 6">
              <p>Alerts when something changes, each with what followed the same situation in the past, including when nothing reliable did.</p>
            </ComingSoon>
          }
        />
        <Route path="status" element={<StatusPage />} />
        <Route path="*" element={<Notice>That page does not exist.</Notice>} />
      </Route>
    </Routes>
  );
}
