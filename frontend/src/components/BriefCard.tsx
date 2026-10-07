import { useState } from "react";
import { Link } from "react-router-dom";

import type { Asset, Brief } from "../api/client";
import { useBrief } from "../api/queries";
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

/**
 * Today's brief. Each subject shows its first sentence; the rest opens on request. Every
 * sentence leads to the page that backs it.
 */
export function BriefCard({ assets }: { assets: Asset[] }) {
  const brief = useBrief().data;
  const [open, setOpen] = useState(false);
  if (!brief) return null;
  return (
    <section className="glass p-4 @xl:p-7" aria-labelledby="brief-title">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="brief-title" className="text-base font-semibold tracking-tight">
          Today in brief
        </h2>
        <button
          type="button"
          className="press text-sm font-medium text-muted hover:text-ink"
          aria-expanded={open}
          onClick={() => setOpen((was) => !was)}
        >
          {open ? "Show less" : "Read all"}
        </button>
      </div>
      <div className="mt-3 grid grid-cols-1 gap-x-8 gap-y-4 @4xl:grid-cols-2">
        {brief.items.map((item) => {
          const asset = assets.find((a) => a.symbol === item.symbol);
          const shown = open ? item.sentences : item.sentences.slice(0, 1);
          return (
            <article key={item.symbol} className="flex gap-2.5">
              <span
                className="mt-[0.45rem] h-2 w-2 shrink-0 rounded-full"
                style={{ background: asset ? `var(${assetColorVar(asset)})` : "var(--accent)" }}
                aria-hidden="true"
              />
              <p className="text-sm leading-relaxed text-muted">
                {shown.map((sentence, i) => (
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
    </section>
  );
}
