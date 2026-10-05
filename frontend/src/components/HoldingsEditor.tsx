import { useRef, useState } from "react";

import type { Holding, Portfolio } from "../api/client";
import { useSavePortfolio } from "../api/queries";
import { parseQuantity } from "../lib/portfolio";
import { Caption } from "./ui";

interface Row {
  id: number;
  symbol: string;
  quantity: string;
}

const field =
  "h-10 w-full min-w-0 rounded-xl border border-line bg-white/[0.04] px-3 text-sm text-ink outline-none transition-colors focus:border-line-strong";

let nextId = 1;
const row = (symbol: string, quantity: string): Row => ({ id: nextId++, symbol, quantity });

/**
 * Enter holdings by hand or load them from a CSV file. Saving replaces what was saved
 * before and recalculates everything on the other tabs.
 */
export function HoldingsEditor({ portfolio }: { portfolio: Portfolio }) {
  const save = useSavePortfolio();
  const file = useRef<HTMLInputElement>(null);
  const [rows, setRows] = useState<Row[]>(() =>
    portfolio.holdings.length > 0
      ? portfolio.holdings.map((h) => row(h.symbol, String(h.quantity)))
      : [row("", "")],
  );
  const [fileProblem, setFileProblem] = useState<string>();

  const filled = rows.filter((r) => r.symbol !== "" || r.quantity.trim() !== "");
  const invalid = filled.some((r) => r.symbol === "" || parseQuantity(r.quantity) === undefined);
  const update = (id: number, change: Partial<Row>) =>
    setRows((before) => before.map((r) => (r.id === id ? { ...r, ...change } : r)));

  function submit() {
    const holdings: Holding[] = filled.map((r) => ({
      symbol: r.symbol,
      quantity: parseQuantity(r.quantity) ?? 0,
    }));
    save.mutate(
      { holdings },
      {
        onSuccess: (saved) =>
          setRows(
            saved.holdings.length > 0
              ? saved.holdings.map((h) => row(h.symbol, String(h.quantity)))
              : [row("", "")],
          ),
      },
    );
  }

  async function load(chosen: File | undefined) {
    if (!chosen) return;
    setFileProblem(undefined);
    if (chosen.size > 150_000) {
      setFileProblem("That file is too large. A holdings file is a few lines long.");
      return;
    }
    const csv = await chosen.text();
    save.mutate(
      { csv },
      {
        onSuccess: (saved) =>
          setRows(
            saved.holdings.length > 0
              ? saved.holdings.map((h) => row(h.symbol, String(h.quantity)))
              : [row("", "")],
          ),
      },
    );
    if (file.current) file.current.value = "";
  }

  const result = save.data;
  return (
    <div className="flex flex-col gap-5">
      <ul className="flex flex-col gap-2.5">
        {rows.map((r, i) => (
          <li key={r.id} className="grid grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto] gap-2.5">
            <select
              aria-label={`Holding ${i + 1}`}
              value={r.symbol}
              onChange={(event) => update(r.id, { symbol: event.target.value })}
              className={field}
            >
              <option value="">Choose…</option>
              {portfolio.supported.map((asset) => (
                <option key={asset.symbol} value={asset.symbol}>
                  {asset.name} ({asset.symbol})
                </option>
              ))}
            </select>
            <input
              aria-label={`Quantity of holding ${i + 1}`}
              inputMode="decimal"
              placeholder="Quantity"
              value={r.quantity}
              onChange={(event) => update(r.id, { quantity: event.target.value })}
              className={`${field} num`}
            />
            <button
              type="button"
              aria-label={`Remove holding ${i + 1}`}
              onClick={() =>
                setRows((before) =>
                  before.length > 1 ? before.filter((x) => x.id !== r.id) : [row("", "")],
                )
              }
              className="grid h-10 w-10 place-items-center rounded-xl text-muted transition-colors hover:bg-white/8 hover:text-ink"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path
                  d="M6 6l12 12M18 6 6 18"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-center gap-2.5">
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => setRows((before) => [...before, row("", "")])}
        >
          Add a holding
        </button>
        <button type="button" className="btn btn-ghost" onClick={() => file.current?.click()}>
          Load a CSV file
        </button>
        <input
          ref={file}
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          aria-label="CSV file of holdings"
          onChange={(event) => void load(event.target.files?.[0])}
        />
        <button
          type="button"
          className="btn btn-primary ml-auto disabled:opacity-50"
          disabled={invalid || save.isPending}
          onClick={submit}
        >
          {save.isPending ? "Saving…" : "Save holdings"}
        </button>
      </div>

      <div aria-live="polite" className="flex flex-col gap-2 text-sm empty:hidden">
        {invalid && (
          <p className="text-muted">Each row needs an asset and a quantity above zero.</p>
        )}
        {fileProblem && <p className="text-alert">{fileProblem}</p>}
        {save.isError && <p className="text-alert">{save.error.message}</p>}
        {save.isSuccess && result && (
          <p className="text-muted">
            Saved {result.holdings.length} holding{result.holdings.length === 1 ? "" : "s"}.
          </p>
        )}
        {save.isSuccess && result && result.unsupported.length > 0 && (
          <div className="well px-4 py-3">
            <p className="font-medium">Left out</p>
            <ul className="mt-1 text-muted">
              {result.unsupported.map((item, i) => (
                <li key={`${item.symbol}-${i}`}>
                  <span className="text-ink">{item.symbol}</span>: {item.reason}
                </li>
              ))}
            </ul>
          </div>
        )}
        {(result?.problem ?? portfolio.problem) && (
          <p className="text-alert">{result?.problem ?? portfolio.problem}</p>
        )}
      </div>

      <Caption>
        Quantities are units held: coins, or shares. A CSV file needs a first row naming a symbol
        column and a quantity column, for example <span className="num">symbol,quantity</span>.
        Names such as BTC, BTCUSDT, or BTC/USD are all understood. Holdings stay on this
        computer&apos;s copy of RADAR. Nothing here can place a trade.
      </Caption>
    </div>
  );
}
