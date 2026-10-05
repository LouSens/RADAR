import type { ReactNode } from "react";

import type { Asset, Summary, Trust } from "../api/client";
import { formatPrice, formatShare } from "../lib/format";
import { stepsLabel } from "../lib/outlook";
import { TrustBadge } from "./ui";

const TONE_WORD = (score: number | null | undefined) =>
  score == null
    ? "quiet"
    : score > 0.15
      ? "mostly positive"
      : score < -0.15
        ? "mostly negative"
        : "mixed";

const VERDICT: Record<string, string> = {
  "sentiment leads price": "Historically, news tone has tended to move before price.",
  "price leads sentiment": "Historically, price has moved first and the news has followed.",
  "no measurable relationship":
    "Historically, news tone has had no measurable link to later price moves.",
  "not enough events": "There is too little news to say whether it moves the price.",
};

const days = (n: number) => `${n} day${n === 1 ? "" : "s"}`;

function Line({ trust, href, children }: { trust: Trust; href: string; children: ReactNode }) {
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-1.5 border-t border-line py-3 first:border-t-0 first:pt-0">
      <p className="min-w-0 flex-1 basis-72 text-[15px] leading-relaxed">{children}</p>
      <span className="flex shrink-0 items-center gap-3">
        <TrustBadge trust={trust} />
        <a
          href={href}
          className="text-xs text-muted underline-offset-2 hover:text-ink hover:underline"
        >
          Evidence
        </a>
      </span>
    </li>
  );
}

const Figure = ({ children }: { children: ReactNode }) => (
  <span className="num font-semibold text-ink">{children}</span>
);

/** The top of a market page: the answers in a few sentences, and what changed this week. */
export function SummaryCard({ asset, summary }: { asset: Asset; summary: Summary }) {
  const { state, outlook, swings, risk, news, trust } = summary;
  if (!state && !outlook && !swings && !news) return null;

  return (
    <section className="glass p-5 @xl:p-7" aria-labelledby="in-brief">
      <h2 id="in-brief" className="text-base font-semibold tracking-tight">
        In brief
      </h2>
      <ul className="mt-4">
        {state && (
          <Line trust={trust.state} href="#market-state">
            The market is <Figure>{state.label}</Figure>, and has been for{" "}
            <Figure>{days(state.days_in_state)}</Figure>.
          </Line>
        )}
        {outlook && (
          <Line trust={trust.outlook} href="#outlook">
            Over the next {stepsLabel(outlook.steps, asset.trades_continuously)}, 8 in 10 simulated
            outcomes fall between{" "}
            <Figure>
              {formatPrice(outlook.low)} and {formatPrice(outlook.high)}
            </Figure>
            .
          </Line>
        )}
        {swings && (
          <Line trust={trust.swings} href="#swings">
            A typical day&apos;s move is expected to be about{" "}
            <Figure>±{formatShare(swings.forecast)}</Figure>, in either direction.
          </Line>
        )}
        {risk && (
          <Line trust={trust.risk} href="#risk">
            A one-day loss beyond <Figure>{formatShare(risk.limit, 1)}</Figure> should happen on
            about 1 day in 20.
          </Line>
        )}
        {news && (
          <Line trust={trust.news} href="#news">
            Recent news is <Figure>{TONE_WORD(news.current)}</Figure>.{" "}
            {news.verdict ? (VERDICT[news.verdict] ?? "") : ""}
          </Line>
        )}
      </ul>

      <div className="mt-5 border-t border-line pt-4">
        <h3 className="label">What changed this week</h3>
        {summary.changes.length === 0 ? (
          <p className="mt-1.5 text-sm text-muted">Nothing notable has changed in the past week.</p>
        ) : (
          <ul className="mt-1.5 space-y-1 text-sm">
            {summary.changes.map((change) => (
              <li key={change.topic}>{change.text}</li>
            ))}
          </ul>
        )}
      </div>

      <p className="mt-4 text-xs leading-relaxed text-faint">
        Solid, Fair, and Rough say how well each statement has held up when tested on data the
        models had not seen. These describe the market; they do not predict its direction.
      </p>
    </section>
  );
}
