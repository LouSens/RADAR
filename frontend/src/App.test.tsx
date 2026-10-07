import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PORTFOLIO_SECTIONS } from "./lib/portfolio";
import { SECTIONS } from "./lib/sections";
import { SIGNAL_PAGES } from "./lib/signals";

vi.mock("./api/live", () => ({ useLiveConnection: () => undefined }));
vi.mock("./components/Layout", async () => {
  const { Outlet } = await import("react-router-dom");
  return { Layout: () => <Outlet /> };
});
const page = (name: string) => () => <p>{name}</p>;
vi.mock("./pages/Overview", () => ({ Overview: page("home") }));
vi.mock("./pages/MarketsPage", () => ({ MarketsPage: page("markets") }));
vi.mock("./pages/AssetPage", () => ({ AssetPage: page("asset") }));
vi.mock("./pages/PortfolioPage", () => ({ PortfolioPage: page("portfolio") }));
vi.mock("./pages/SignalsPage", () => ({ SignalsPage: page("signals") }));
vi.mock("./pages/CalendarPage", () => ({ CalendarPage: page("calendar") }));
vi.mock("./pages/SystemPage", () => ({ SystemPage: page("system") }));

const { App } = await import("./App");

const lands = (path: string) => {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
  const text = document.body.textContent ?? "";
  cleanup();
  return text;
};

describe("App routes", () => {
  afterEach(cleanup);

  it("has a page for every address the app links to", () => {
    const addresses = [
      "/",
      "/markets",
      "/portfolio",
      "/signals",
      "/calendar",
      "/system",
      ...SECTIONS.map((s) => `/asset/btc-usd/${s.path}`),
      ...PORTFOLIO_SECTIONS.map((s) => `/portfolio/${s.path}`),
      ...SIGNAL_PAGES.map((s) => `/signals/${s.path}`),
    ];
    for (const address of addresses) {
      expect(lands(address), address).not.toMatch(/does not exist/);
    }
  });

  it("sends the addresses of removed pages to the nearest page that exists", () => {
    expect(lands("/together")).toBe("markets");
    expect(lands("/together/weekends")).toBe("markets");
    expect(lands("/calendar/fed")).toBe("calendar");
    expect(lands("/status")).toBe("system");
  });

  it("says so for an address that was never a page", () => {
    render(
      <MemoryRouter initialEntries={["/nowhere"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText("That page does not exist.")).toBeVisible();
  });
});
