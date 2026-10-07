import { useState } from "react";
import { Link } from "react-router-dom";

import type { Portfolio, PortfolioAnalysis } from "../api/client";

const SEEN = "radar.seen.";
const HIDDEN = "radar.started.hidden";

function stored(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function store(key: string) {
  try {
    window.localStorage.setItem(key, "1");
  } catch {
    // It just will not be remembered.
  }
}

/** Remember that a page has been opened, so its step counts as done. */
export function markSeen(pathname: string) {
  if (pathname === "/portfolio/sources") store(`${SEEN}risk`);
  if (pathname === "/portfolio/buying") store(`${SEEN}buying`);
}

export interface Step {
  key: string;
  label: string;
  to: string;
  done: boolean;
}

/**
 * The few steps that make RADAR the user's own. The first is already done for everyone:
 * the markets are tracked whether or not anything is held.
 */
export function steps(
  portfolio: Portfolio | undefined,
  analysis: PortfolioAnalysis | null | undefined,
  markets: number,
): Step[] {
  const held = (portfolio?.holdings.length ?? 0) > 0;
  return [
    { key: "markets", label: `${markets} markets tracked for you`, to: "/markets", done: true },
    { key: "holdings", label: "Add what you hold", to: "/portfolio/holdings", done: held },
    {
      key: "risk",
      label: "See where your risk is",
      to: "/portfolio/sources",
      done: held && stored(`${SEEN}risk`),
    },
    {
      key: "target",
      label: "Set a target mix",
      to: "/portfolio/try",
      done: Boolean(analysis?.plan?.target),
    },
    {
      key: "buying",
      label: "Plan regular buying",
      to: "/portfolio/buying",
      done: stored(`${SEEN}buying`),
    },
  ];
}

/** Progress towards a set-up RADAR, with the one next step. Gone once all are done. */
export function GettingStarted({
  portfolio,
  analysis,
  markets,
}: {
  portfolio: Portfolio | undefined;
  analysis: PortfolioAnalysis | null | undefined;
  markets: number;
}) {
  const [hidden, setHidden] = useState(() => stored(HIDDEN));
  const all = steps(portfolio, analysis, markets);
  const done = all.filter((step) => step.done).length;
  const next = all.find((step) => !step.done);
  if (hidden || !next || portfolio === undefined) return null;
  return (
    <section className="glass p-4 @xl:p-6" aria-label="Make RADAR yours">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-base font-semibold tracking-tight">Make RADAR yours</h2>
        <p className="num text-sm text-muted">
          {done} of {all.length} done
        </p>
      </div>
      <div
        className="mt-3 flex gap-1.5"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={all.length}
        aria-valuenow={done}
        aria-label="Steps done"
      >
        {all.map((step) => (
          <span
            key={step.key}
            title={step.label}
            className={`h-1.5 flex-1 rounded-full transition-colors duration-500 ${
              step.done ? "bg-[var(--accent)]" : "bg-white/10"
            }`}
          />
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          Next: <span className="font-medium text-ink">{next.label}</span>
        </p>
        <span className="flex items-center gap-2">
          <button
            type="button"
            className="press px-2 py-1.5 text-sm text-faint hover:text-ink"
            onClick={() => {
              store(HIDDEN);
              setHidden(true);
            }}
          >
            Not now
          </button>
          <Link to={next.to} className="btn btn-primary press">
            Continue
          </Link>
        </span>
      </div>
    </section>
  );
}
