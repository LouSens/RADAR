// Photograph the app's pages for the film, with example data only.
//
//   node mock-api/server.mjs                                   (in one terminal)
//   RADAR_API_URL=http://127.0.0.1:8010 npm --prefix ../frontend run dev -- --port 5180
//   node scripts/capture.mjs [name...]                         (in a third)
//
// The app photographed must be the one fed by the mock API: the app on port 8080 shows a
// real account and is never photographed. This script refuses to run unless the address
// it is given answers with the example portfolio.

import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

const BASE = process.env.CAPTURE_BASE ?? "http://localhost:5180";

/** Each still: its file name, the page's address, and the composition (its size). */
const PAGES = [
  ["home", "", "Desk"],
  ["markets", "markets", "Desk"],
  ["bitcoin", "asset/btc-usd", "Desk"],
  ["moves", "asset/btc-usd/moves", "Desk"],
  ["check", "portfolio/check", "Desk"],
  ["range", "asset/btc-usd/outlook", "Desk"],
  ["risk", "portfolio/risk", "Desk"],
  ["todo", "portfolio/todo", "Desk"],
  ["calendar", "calendar", "Desk"],
  ["home-phone", "", "Capture"],
];

const example = JSON.parse(readFileSync("src/fixtures/portfolio.json", "utf8"));
const served = await fetch(`${BASE}/api/v1/portfolio/analysis`).then((r) => r.json());
if (served.value !== example.value) {
  throw new Error(`${BASE} is not showing the example portfolio. Nothing was photographed.`);
}

const wanted = process.argv.slice(2);
const dir = path.resolve("public/desk");
mkdirSync(dir, { recursive: true });
const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts") });

for (const [name, address, id] of PAGES) {
  if (wanted.length > 0 && !wanted.includes(name)) continue;
  const inputProps = { path: address, base: BASE };
  const composition = await selectComposition({ serveUrl, id, inputProps });
  const output = path.join(dir, `${name}.png`);
  await renderStill({
    composition,
    serveUrl,
    output,
    inputProps,
    scale: id === "Desk" ? 2 : 3,
    timeoutInMilliseconds: 60000,
  });
  console.log(output);
}
