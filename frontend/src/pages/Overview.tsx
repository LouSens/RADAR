import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useNow } from "../api/market";
import type { Holding } from "../api/client";
import {
  useAssets,
  usePortfolio,
  usePortfolioAnalysis,
  useSavePortfolio,
  useSteps,
} from "../api/queries";
import { BriefCard } from "../components/BriefCard";
import { ComingUp } from "../components/ComingUp";
import { StepsCard } from "../components/StepsPanel";
import { LatestSignals } from "../components/LatestSignals";
import { MarketCard } from "../components/MarketCard";
import { Skeleton } from "../components/Skeleton";
import { Message } from "../components/ui";
import { levelColour } from "../components/viz";
import { formatMoney } from "../lib/format";

function ActionIcon({ children }: { children: ReactNode }) {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

/** The four things most worth doing with a portfolio, one tap each. */
const ACTIONS = [
  {
    to: "/portfolio/sources",
    label: "Your risk",
    icon: (
      <>
        <path d="M12 3.5a8.5 8.5 0 1 0 8.5 8.5H12V3.5Z" />
        <path d="M15.5 3.6a8.5 8.5 0 0 1 4.9 4.9h-4.9V3.6Z" />
      </>
    ),
  },
  {
    to: "/portfolio/ahead",
    label: "What's ahead",
    icon: (
      <>
        <path d="M3.5 12h5" />
        <path d="M8.5 12 20.5 5.5M8.5 12l12 6.5" />
      </>
    ),
  },
  {
    to: "/portfolio/try",
    label: "Try a mix",
    icon: (
      <>
        <path d="M4 7h10M18 7h2M4 17h2M10 17h10" />
        <circle cx="16" cy="7" r="2" />
        <circle cx="8" cy="17" r="2" />
      </>
    ),
  },
  {
    to: "/portfolio/buying",
    label: "Buy regularly",
    icon: (
      <>
        <path d="M4.5 19.5V15M9.5 19.5v-7.5M14.5 19.5V9M19.5 19.5v-15" />
      </>
    ),
  },
] as const;

/** A made-up starting portfolio, so a newcomer can try everything before typing anything. */
const EXAMPLE: Holding[] = [
  { symbol: "SPY", quantity: 4 },
  { symbol: "GLD", quantity: 3 },
  { symbol: "BTC/USD", quantity: 0.02 },
  { symbol: "USD", quantity: 1500 },
];
const EXAMPLE_KEY = "radar.example";

function isExample(): boolean {
  try {
    return window.localStorage.getItem(EXAMPLE_KEY) === "1";
  } catch {
    return false;
  }
}

function markExample(on: boolean) {
  try {
    if (on) window.localStorage.setItem(EXAMPLE_KEY, "1");
    else window.localStorage.removeItem(EXAMPLE_KEY);
  } catch {
    // It just will not be remembered.
  }
}

/** The first thing on Home: what you have, how risky it is, and what to do with it. */
function Hero() {
  const portfolio = usePortfolio().data;
  const analysis = usePortfolioAnalysis().data;
  const empty = portfolio !== undefined && portfolio.holdings.length === 0;
  const level = analysis?.risk_level?.label;
  const value = analysis ? formatMoney(analysis.value) : undefined;
  const [whole, cents] = value?.includes(".") ? value.split(".") : [value, undefined];
  const typical = analysis ? analysis.xray.daily_volatility * analysis.covered_value : undefined;
  const save = useSavePortfolio();
  const example = isExample() && portfolio?.source === "manual";

  // While the portfolio is on its way, hold its place.
  if (portfolio === undefined) {
    return (
      <section aria-label="Your portfolio" className="flex flex-col gap-3" aria-busy="true">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-12 w-56" />
        <Skeleton className="h-4 w-44" />
      </section>
    );
  }

  // Nothing held yet: show what RADAR does with one tap, before asking for anything.
  if (empty) {
    return (
      <section aria-label="Your portfolio" className="flex flex-col gap-4">
        <div>
          <p className="label">Your portfolio</p>
          <p className="display mt-1 text-[2rem] @xl:text-[2.6rem]">See your risk in one tap</p>
          <p className="mt-2 max-w-[44ch] text-sm text-muted">
            Start with an example portfolio and explore everything. Swap in your own holdings
            whenever you like.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn btn-primary press disabled:opacity-60"
            disabled={save.isPending}
            onClick={() => {
              markExample(true);
              save.mutate({ holdings: EXAMPLE });
            }}
          >
            {save.isPending ? "Setting it up…" : "Try an example"}
          </button>
          <Link to="/portfolio/holdings" className="btn btn-ghost press">
            Add my own
          </Link>
        </div>
        {save.isError && (
          <p className="text-sm text-[var(--alert)]" role="alert">
            That did not work. Please try again.
          </p>
        )}
      </section>
    );
  }

  return (
    <section aria-label="Your portfolio" className="flex flex-col gap-5">
      <Link to="/portfolio" className="press block self-start" aria-label="Open your portfolio">
        <span className="label block">{example ? "Example portfolio" : "Your portfolio"}</span>
        <span className="num price-xl mt-1.5 block">
          {whole ?? <Skeleton className="h-[1em] w-48" />}
          {cents && <span className="text-faint">.{cents}</span>}
        </span>
        <span className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
          {level && (
            <span
              className="rounded-full px-2.5 py-0.5 text-xs font-medium capitalize"
              style={{
                color: levelColour(level),
                background: `color-mix(in srgb, ${levelColour(level)} 15%, transparent)`,
              }}
            >
              {level} risk
            </span>
          )}
          {typical !== undefined && (
            <span className="num">±{formatMoney(typical)} on a typical day</span>
          )}
        </span>
      </Link>
      {example && (
        <p className="-mt-2 text-sm text-muted">
          These are made-up holdings.{" "}
          <Link
            to="/portfolio/holdings"
            className="font-medium text-ink underline underline-offset-4"
            onClick={() => markExample(false)}
          >
            Use my own
          </Link>
        </p>
      )}
      <nav aria-label="Portfolio shortcuts" className="grid grid-cols-4 gap-2 @xl:max-w-xl">
        {ACTIONS.map((action) => (
          <Link key={action.to} to={action.to} className="action press">
            <span className="action-icon">
              <ActionIcon>{action.icon}</ActionIcon>
            </span>
            <span className="text-center text-[11px] font-medium leading-tight @xl:text-xs">
              {action.label}
            </span>
          </Link>
        ))}
      </nav>
    </section>
  );
}

/** Home: your portfolio first, then the markets, then what is new. */
export function Overview() {
  const assets = useAssets();
  const now = useNow(60_000);
  const primary = assets.data?.filter((a) => a.is_primary) ?? [];
  const paxg = assets.data?.find((a) => a.symbol === "PAXG/USD");
  const steps = useSteps();
  const today = new Intl.DateTimeFormat("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(now);

  return (
    <div className="flex flex-col gap-6 @xl:gap-8">
      <header className="flex items-center justify-between gap-3">
        <h1 className="text-sm font-semibold tracking-[0.14em]">RADAR</h1>
        <p className="label">{today}</p>
      </header>

      <Hero />
      {steps.data && <StepsCard steps={steps.data} />}

      {assets.isError && <Message>Markets are unavailable right now.</Message>}

      <section aria-labelledby="home-markets">
        <div className="mb-2.5 flex items-baseline justify-between gap-3">
          <h2 id="home-markets" className="text-base font-semibold tracking-tight">
            Markets
          </h2>
          <Link to="/markets" className="press text-sm font-medium text-muted hover:text-ink">
            Compare
          </Link>
        </div>
        <div className="grid grid-cols-3 gap-2 @xl:gap-4">
          {primary.map((asset) => (
            <MarketCard
              key={asset.slug}
              asset={asset}
              priced={asset.symbol === "GLD" ? paxg : undefined}
            />
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 gap-4 @4xl:grid-cols-2 @xl:gap-6">
        <ComingUp />
        <LatestSignals assets={assets.data ?? []} />
      </div>
      <BriefCard assets={assets.data ?? []} />
    </div>
  );
}
