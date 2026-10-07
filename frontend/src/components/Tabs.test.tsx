import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { PORTFOLIO_SECTIONS } from "../lib/portfolio";
import { SECTIONS } from "../lib/sections";
import { SIGNAL_PAGES } from "../lib/signals";
import { SectionMenu, Tabs } from "./Tabs";

const at = (path: string, node: React.ReactNode) =>
  render(<MemoryRouter initialEntries={[path]}>{node}</MemoryRouter>);

describe("Tabs", () => {
  afterEach(cleanup);

  it("shows nothing on a subject's own page: there is nowhere to go back to", () => {
    const { container } = at(
      "/portfolio",
      <Tabs base="/portfolio" items={PORTFOLIO_SECTIONS} label="Portfolio pages" />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("gives one way back from a page inside a subject, and no strip of tabs", () => {
    at(
      "/portfolio/limits",
      <Tabs base="/portfolio" items={PORTFOLIO_SECTIONS} label="Portfolio pages" />,
    );
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAccessibleName("Back to Portfolio");
    expect(links[0]).toHaveAttribute("href", "/portfolio");
  });

  it("uses the name it is given for the way back", () => {
    at("/asset/gld/risk", <Tabs base="/asset/gld" items={SECTIONS} label="x" parent="Gold" />);
    expect(screen.getByRole("link", { name: "Back to Gold" })).toHaveAttribute(
      "href",
      "/asset/gld",
    );
  });
});

describe("SectionMenu", () => {
  afterEach(cleanup);

  it("offers a few pages as tiles, each with what it answers, and leaves the rest out", () => {
    at(
      "/portfolio",
      <SectionMenu base="/portfolio" items={PORTFOLIO_SECTIONS} title="Your portfolio" />,
    );
    const menu = screen.getByRole("navigation", { name: "Your portfolio" });
    const plan = within(menu).getByRole("link", { name: /^My plan/ });
    expect(plan).toHaveAttribute("href", "/portfolio/try");
    expect(within(plan).getByText("How much goes into each thing")).toBeVisible();
    // The subject's own page is not listed, and neither are pages reached from inside.
    expect(within(menu).queryByRole("link", { name: /^Summary/ })).toBeNull();
    expect(within(menu).queryByRole("link", { name: /^Possible loss/ })).toBeNull();
    expect(within(menu).getAllByRole("link")).toHaveLength(6);
  });

  it("every page of every subject says what it is for, briefly", () => {
    for (const pages of [SECTIONS, PORTFOLIO_SECTIONS, SIGNAL_PAGES]) {
      for (const page of pages) {
        if (page.path === "") continue;
        expect(page.hint.length, page.label).toBeGreaterThan(10);
        expect(page.hint.length, page.label).toBeLessThanOrEqual(48);
      }
    }
  });
});
