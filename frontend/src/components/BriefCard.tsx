import { Link } from "react-router-dom";

import type { Asset, Brief } from "../api/client";
import { useBrief } from "../api/queries";
import { formatDate } from "../lib/time";
import { assetColorVar } from "./ui";

const PORTFOLIO = "PORTFOLIO";
const ASSET_PAGE: Record<string, string> = {
  state: "/state",
  outlook: "/outlook",
  swings: "/swings",
  risk: "/risk",
};
const PORTFOLIO_PAGE: Record<string, string> = {
  portfolio: "/portfolio",
  outlook: "/portfolio/ahead",
  target: "/portfolio/try",
};

/** Where the evidence for one sentence lives. */
export function sentenceLink(
  item: Brief["items"][number],
  section: string,
  assets: Asset[],
): string {
  if (item.symbol === PORTFOLIO) return PORTFOLIO_PAGE[section] ?? "/portfolio";
  if (section === "signals") return "/signals";
  const slug = assets.find((a) => a.symbol === item.symbol)?.slug;
  return slug ? `/asset/${slug}${ASSET_PAGE[section] ?? ""}` : "/";
}

/** Today's brief: a few sentences per market, each leading to the page that backs it. */
export function BriefCard({ assets }: { assets: Asset[] }) {
  const brief = useBrief().data;
  if (!brief) return null;
  return (
    <section className="glass p-5 @xl:p-7" aria-labelledby="brief-title">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="brief-title" className="text-base font-semibold tracking-tight">
          Today in brief
        </h2>
        <p className="label text-xs">{formatDate(brief.day)}</p>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-x-8 gap-y-5 @4xl:grid-cols-2">
        {brief.items.map((item) => {
          const asset = assets.find((a) => a.symbol === item.symbol);
          return (
            <article key={item.symbol}>
              <h3 className="flex items-center gap-2 text-sm font-medium">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ background: asset ? `var(${assetColorVar(asset)})` : "var(--accent)" }}
                  aria-hidden="true"
                />
                {item.name}
              </h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">
                {item.sentences.map((sentence, i) => (
                  <span key={i}>
                    <Link
                      to={sentenceLink(item, sentence.section, assets)}
                      className="rounded-sm decoration-line-strong underline-offset-4 transition-colors hover:text-ink hover:underline"
                    >
                      {sentence.text}
                    </Link>{" "}
                  </span>
                ))}
              </p>
            </article>
          );
        })}
      </div>
      <p className="mt-4 text-xs leading-relaxed text-faint">
        Written from stored results; every figure is one shown elsewhere in RADAR, and each sentence
        leads to the page behind it. It describes what is and what has happened, and is not advice.
      </p>
    </section>
  );
}
