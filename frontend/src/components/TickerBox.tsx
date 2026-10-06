import { useState } from "react";

import { useLookup } from "../api/queries";
import { Segmented } from "./ui";

const KINDS = [
  { value: "stock", label: "Stock" },
  { value: "crypto", label: "Crypto" },
] as const;

export interface Found {
  symbol: string;
  name: string;
}

/** Type any ticker to bring an asset in, even one RADAR has not seen before. */
export function TickerBox({ onFound }: { onFound: (asset: Found) => void }) {
  const lookup = useLookup();
  const [ticker, setTicker] = useState("");
  const [kind, setKind] = useState<(typeof KINDS)[number]["value"]>("stock");
  const ready = ticker.trim().length > 0 && !lookup.isPending;

  function find() {
    if (!ready) return;
    lookup.mutate(
      { ticker: ticker.trim(), kind },
      {
        onSuccess: (asset) => {
          setTicker("");
          onFound(asset);
        },
      },
    );
  }

  return (
    <div>
      <p className="label mb-2">Or find one by its ticker</p>
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          find();
        }}
      >
        <input
          type="text"
          value={ticker}
          onChange={(event) => setTicker(event.target.value.toUpperCase())}
          placeholder={kind === "stock" ? "NVDA" : "ETH"}
          aria-label="Ticker"
          maxLength={12}
          autoCapitalize="characters"
          spellCheck={false}
          className="num h-9 w-28 rounded-xl border border-line bg-white/[0.04] px-3 text-sm text-ink outline-none transition-colors placeholder:text-faint focus:border-line-strong"
        />
        <Segmented options={KINDS} value={kind} onChange={setKind} label="Kind of asset" />
        <button type="submit" className="btn btn-ghost disabled:opacity-50" disabled={!ready}>
          {lookup.isPending ? "Looking…" : "Find"}
        </button>
      </form>
      {lookup.isPending && (
        <p className="mt-2 text-sm text-muted">
          Fetching its price history. The first time, this can take up to a minute.
        </p>
      )}
      {lookup.isError && (
        <p className="mt-2 text-sm text-[var(--alert)]" role="alert">
          {lookup.error.message || "That ticker could not be looked up."}
        </p>
      )}
      <p className="mt-2 text-xs text-faint">
        US stocks and funds, and the crypto coins Alpaca carries.
      </p>
    </div>
  );
}
