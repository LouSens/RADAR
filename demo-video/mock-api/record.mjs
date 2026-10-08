// Record market data from the running RADAR API into mock-api/data/recorded/.
//
//   node mock-api/record.mjs            (the API must be on http://127.0.0.1:8000)
//
// Only GET requests, and only to the market addresses listed here. The account and
// portfolio addresses are never asked: a path that names one is refused before any
// request is made. The list of markets is cut down to the three the app always follows,
// because the full list also names whatever the account holds.

import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const API = process.env.RADAR_API ?? "http://127.0.0.1:8000";
const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), "data", "recorded");
const REFUSED = /portfolio|briefs|health|account|stream/;

const get = async (address) => {
  if (REFUSED.test(address)) throw new Error(`Not a market address: ${address}`);
  const response = await fetch(`${API}/api/v1/${address}`, { method: "GET" });
  if (response.status === 404) return undefined;
  if (!response.ok) throw new Error(`${response.status} for ${address}`);
  return response.json();
};

const keep = (name, body) => {
  if (body === undefined) {
    console.log(`nothing stored for ${name}`);
    return;
  }
  const file = path.join(OUT, `${name}.json`);
  mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, JSON.stringify(body));
  console.log(name);
};

const markets = (await get("assets")).filter((asset) => asset.is_primary);
keep("assets", markets);

for (const { slug } of markets) {
  const at = `assets/${slug}`;
  keep(`${at}/bars.1Hour`, await get(`${at}/bars?timeframe=1Hour&limit=5000`));
  keep(`${at}/bars.1Day`, await get(`${at}/bars?timeframe=1Day&limit=5000`));
  for (const page of [
    "regime",
    "simulation",
    "calibration",
    "volatility",
    "risk",
    "sentiment",
    "moves",
    "track-record",
    "summary",
    "drivers",
  ]) {
    keep(`${at}/${page}`, await get(`${at}/${page}`));
  }
}

const symbols = new Set(markets.map((asset) => asset.symbol));
const signals = await get("signals?limit=50");
keep("signals", {
  ...signals,
  signals: signals.signals.filter((signal) => symbols.has(signal.symbol)),
});
for (const kind of ["regime_change", "abnormal_move", "sentiment_shock"]) {
  keep(`signals/track-records/${kind}`, await get(`signals/track-records/${kind}`));
}
keep("events", await get("events"));
keep("relationships", await get("relationships"));
