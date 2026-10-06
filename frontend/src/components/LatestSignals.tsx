import { Link } from "react-router-dom";

import type { Asset } from "../api/client";
import { useSignals } from "../api/queries";
import { DIRECTION_WORDS, SIZE_WORDS, isFinding, kindName, type SignalType } from "../lib/signals";
import { formatDate } from "../lib/time";
import { assetColorVar, shortName } from "./ui";

/** The few newest signals on the Overview, each leading to its track record. */
export function LatestSignals({ assets }: { assets: Asset[] }) {
  const data = useSignals({ limit: 5 }).data;
  if (!data || data.signals.length === 0) return null;
  return (
    <section className="glass p-5 @xl:p-7" aria-labelledby="latest-signals-title">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="latest-signals-title" className="text-base font-semibold tracking-tight">
          Latest signals
        </h2>
        <Link to="/signals" className="text-sm font-medium text-muted hover:text-ink">
          See all
        </Link>
      </div>
      <ul className="mt-2 flex flex-col">
        {data.signals.map((signal) => {
          const asset = assets.find((a) => a.symbol === signal.symbol);
          const record = signal.record;
          const finding =
            record && isFinding(record.size_verdict)
              ? SIZE_WORDS[record.size_verdict]
              : record
                ? DIRECTION_WORDS[record.verdict]
                : undefined;
          return (
            <li key={signal.id} className="border-t border-line first:border-t-0">
              <Link
                to={`/signals/${signal.type}`}
                className="group flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-3 text-sm"
              >
                <span className="flex min-w-0 items-center gap-2.5">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ background: asset ? `var(${assetColorVar(asset)})` : "var(--accent)" }}
                    aria-hidden="true"
                  />
                  <span className="font-medium group-hover:text-accent">
                    {shortName(signal)} · {kindName(signal.type as SignalType, signal.variant)}
                  </span>
                </span>
                <span className="num text-muted">
                  {formatDate(signal.ts)}
                  {finding ? ` · ${finding}` : ""}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
