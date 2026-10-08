import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import "./index.css";

const queryClient = new QueryClient({
  // Coming back to the window asks again for anything older than half a minute, so a
  // screen left open does not show an hour-old account.
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true, staleTime: 30_000 } },
});

const root = document.getElementById("root");
if (!root) throw new Error("The page is missing its root element.");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
