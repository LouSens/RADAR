// Write the film's figures (src/fixtures/film.json) from the mock API's data, so that
// every number in the film is one the app itself would show for the same data.
//
//   node scripts/fixtures.mjs        (after mock-api/record.mjs and make_account.py)
//
// Market figures come from mock-api/data/recorded (the app's market addresses, recorded
// by GET); the account's come from mock-api/data/example, which is the made-up example
// portfolio. Nothing here is read from an account.

import { readFileSync, writeFileSync } from "node:fs";

const read = (name) => {
  for (const root of ["example", "recorded"]) {
    try {
      return JSON.parse(readFileSync(`mock-api/data/${root}/${name}.json`, "utf8"));
    } catch {
      // Look in the next place.
    }
  }
  throw new Error(`No data for ${name}`);
};

const TONE = { "BTC/USD": "btc", "PAXG/USD": "gold", SPY: "stock", USD: "cash" };
const NAME = { "BTC/USD": "Bitcoin", "PAXG/USD": "Gold", SPY: "US stocks", USD: "Cash" };

const markets = read("assets").map((asset) => {
  const at = `assets/${asset.slug}`;
  const hours = read(`${at}/bars.1Hour`).bars;
  const days = read(`${at}/bars.1Day`).bars;
  const price = hours.at(-1).close;
  const regime = read(`${at}/regime`);
  return {
    slug: asset.slug,
    symbol: asset.symbol,
    name: NAME[asset.symbol],
    tone: TONE[asset.symbol],
    price,
    // Since the last close: the newest daily bar that ended before the newest hour's day.
    sinceClose:
      price / days.filter((d) => d.ts.slice(0, 10) < hours.at(-1).ts.slice(0, 10)).at(-1).close - 1,
    weekCloses: hours.slice(-168).map((bar) => bar.close),
    state: regime.label,
  };
});

const simulation = read("assets/btc-usd/simulation");
const week = simulation.horizons.find((h) => h.horizon_days === 7);
const band = (level) => week.intervals.find((i) => i.level === level);
const range = {
  startPrice: simulation.start_price,
  paths: simulation.n_paths,
  days: 7,
  low: band(0.8).adjusted_low,
  high: band(0.8).adjusted_high,
  half: [band(0.5).adjusted_low, band(0.5).adjusted_high],
  most: [band(0.95).adjusted_low, band(0.95).adjusted_high],
  middle: week.quantiles["0.5"],
  dip: week.expected_worst_drawdown,
  edges: week.histogram_edges,
  counts: week.histogram_counts,
};

const moved = read("assets/btc-usd/moves");
const moves = {
  trust: moved.trust.grade,
  days: moved.days
    .map((d) => ({
      day: d.day,
      move: d.move,
      timesUsual: d.times_usual,
      rank: d.rank,
      events: d.events,
      headlines: d.headlines.length,
    }))
    .reverse(),
};

const check = read("portfolio/check/BTC");
const level = {
  coin: check.coin,
  price: check.price,
  where: check.where,
  moveDay: check.move_day,
  moveWeek: check.move_week,
  belowHigh: check.below_high,
  places: [
    ["Today", check.place_day],
    ["This week", check.place_week],
    ["This month", check.place_month],
    ["Last 3 months", check.place_quarter],
    ["Last year", check.place_year],
  ].map(([label, place]) => ({ label, place })),
};

const analysis = read("portfolio/analysis");
const risk = Object.fromEntries(analysis.xray.holdings.map((h) => [h.symbol, h.risk_share]));
const plan = Object.fromEntries(
  (analysis.plan?.moves ?? []).map((m) => [m.symbol, m.target_weight]),
);
const holdings = analysis.positions.map((p) => ({
  symbol: p.symbol,
  name: NAME[p.symbol],
  tone: TONE[p.symbol],
  money: p.weight,
  risk: risk[p.symbol] ?? 0,
  value: p.value,
}));
const invested = holdings.filter((h) => h.symbol !== "USD");
for (const holding of holdings) {
  holding.plan =
    holding.symbol === "USD"
      ? 1 - invested.reduce((sum, h) => sum + (plan[h.symbol] ?? h.money), 0)
      : (plan[holding.symbol] ?? holding.money);
}
const step = read("portfolio/steps").steps[0];
const portfolio = {
  value: analysis.value,
  riskLevel: analysis.risk_level.label,
  typicalDay: analysis.xray.daily_volatility * analysis.covered_value,
  holdings,
  step: {
    name: NAME[step.symbol],
    symbol: step.symbol,
    amount: step.amount,
    price: step.price,
    shareNow: step.share_now,
    sharePlan: step.share_plan,
    rungs: step.rungs,
  },
};

// The calendar, worded as the app words it (frontend/src/pages/CalendarPage.tsx): the
// day count is in the viewer's days (GMT+8, as the pages were photographed), and the
// line under an event names the markets that have moved more than usual on such days.
const events = read("events");
const HOURS_AHEAD = 8;
const localDay = (iso) =>
  Math.floor((Date.parse(iso) + HOURS_AHEAD * 3_600_000) / 86_400_000);
// "Today" is the day the data was recorded: the newest hour of prices.
const today = localDay(read("assets/btc-usd/bars.1Hour").bars.at(-1).ts);
const sizeLine = (key) => {
  const result = events.results.find((r) => r.key === key);
  const more = (result?.markets ?? [])
    .filter((m) => m.size.verdict === "moves more on these days")
    .map((m) => (events.names[m.symbol] ?? m.symbol).split(" (")[0]);
  return more.length > 0
    ? `${more.join(" and ")} moved more than usual on these days`
    : "No market has moved measurably more on these days";
};
const calendar = events.upcoming.slice(0, 5).map((event) => ({
  key: event.key,
  name: event.name,
  at: event.at,
  days: localDay(event.at) - today,
  line: sizeLine(event.key),
}));

const signals = read("signals")
  .signals.slice(0, 3)
  .map((s) => ({
    name: s.name,
    tone: TONE[s.symbol],
    what: `Change of state, ${s.variant}`,
    day: s.ts.slice(0, 10),
  }));

writeFileSync(
  "src/fixtures/film.json",
  `${JSON.stringify(
    {
      note: "The film's figures. Market figures are the app's own, recorded from its market addresses; the portfolio is the made-up example (mock-api/make_account.py). Nothing comes from an account. Written by scripts/fixtures.mjs.",
      asOf: simulation.as_of,
      markets,
      range,
      moves,
      level,
      portfolio,
      calendar,
      signals,
    },
    null,
    1,
  )}\n`,
);
console.log(markets.map((m) => `${m.name} ${m.price} ${m.state}`).join("; "));
console.log(calendar.map((c) => `${c.name}: ${c.days}: ${c.line}`).join("; "));
