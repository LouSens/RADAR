// A stand-in for RADAR's API, for photographing the app with example data.
//
//   node mock-api/server.mjs            (listens on 127.0.0.1:8010)
//
// It answers /api/v1/... from the JSON files under mock-api/data/: the address
// /api/v1/assets/btc-usd/moves is the file data/assets/btc-usd/moves.json. Market data is
// recorded by record.mjs into data/recorded/ (not committed); the account is the made-up
// example in data/example/. Nothing here reads an account, and nothing is ever sent on.
// Node's own modules only.

import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { createServer } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.MOCK_PORT ?? 8010);
const HERE = path.dirname(fileURLToPath(import.meta.url));
/** Looked in from first to last: the example account wins over anything recorded. */
const ROOTS = ["example", "recorded"].map((name) => path.join(HERE, "data", name));
const BASE = "/api/v1";

const read = (name) => {
  if (!/^[a-z0-9._/-]+$/i.test(name) || name.includes("..")) return undefined;
  for (const root of ROOTS) {
    const file = path.join(root, `${name}.json`);
    if (existsSync(file)) return JSON.parse(readFileSync(file, "utf8"));
  }
  return undefined;
};

/** Bars are recorded once per timeframe; the newest `limit` after `start` are returned. */
const bars = (name, query) => {
  const all = read(`${name}.${query.get("timeframe") ?? "1Day"}`);
  if (!all) return undefined;
  const start = query.get("start");
  const limit = Number(query.get("limit") ?? 1000);
  const kept = start ? all.bars.filter((bar) => bar.ts >= start) : all.bars;
  return { ...all, bars: kept.slice(-limit) };
};

const answer = (method, url) => {
  const name = url.pathname.slice(BASE.length + 1);
  if (method === "GET" && name.endsWith("/bars")) return bars(name, url.searchParams);
  if (method === "GET") return read(name === "" ? "index" : name);
  // The pages photographed send nothing that changes anything; a request that would is
  // answered from a file of the same name if there is one, and refused otherwise.
  return read(`${name}.${method.toLowerCase()}`);
};

const server = createServer((request, response) => {
  const url = new URL(request.url ?? "/", "http://localhost");
  const send = (status, body) => {
    response.writeHead(status, { "Content-Type": "application/json" });
    response.end(JSON.stringify(body));
  };
  if (!url.pathname.startsWith(`${BASE}/`)) return send(404, { detail: "Not found" });
  const body = answer(request.method ?? "GET", url);
  if (body === undefined) {
    console.log(`no file for ${request.method} ${url.pathname}${url.search}`);
    return send(404, { detail: "Not found" });
  }
  return send(200, body);
});

// The app keeps one WebSocket open for live prices and shows a fault without it. This
// accepts the connection and sends each market's newest recorded price as a live bar.
const frame = (text) => {
  const payload = Buffer.from(text, "utf8");
  const head =
    payload.length < 126
      ? Buffer.from([0x81, payload.length])
      : Buffer.from([0x81, 126, payload.length >> 8, payload.length & 255]);
  return Buffer.concat([head, payload]);
};

const liveBars = () =>
  (read("assets") ?? []).flatMap((asset) => {
    const last = read(`assets/${asset.slug}/bars.1Hour`)?.bars.at(-1);
    return last
      ? [{ type: "bar", symbol: asset.symbol, timeframe: "1Min", ...last, ts: new Date().toISOString() }]
      : [];
  });

server.on("upgrade", (request, socket) => {
  const key = request.headers["sec-websocket-key"];
  if (!key || !request.url?.startsWith(`${BASE}/stream`)) return socket.destroy();
  const accept = createHash("sha1")
    .update(`${key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`)
    .digest("base64");
  socket.write(
    "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n" +
      `Sec-WebSocket-Accept: ${accept}\r\n\r\n`,
  );
  const push = () => liveBars().forEach((bar) => socket.write(frame(JSON.stringify(bar))));
  push();
  const timer = setInterval(push, 30_000);
  const stop = () => clearInterval(timer);
  socket.on("close", stop);
  socket.on("error", stop);
  // Whatever the browser sends (pings, a close) needs no reply for a still.
  socket.on("data", () => {});
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`mock API on http://127.0.0.1:${PORT}${BASE}`);
});
