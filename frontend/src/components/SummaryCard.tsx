import type { Asset, Summary } from "../api/client";
import { formatPrice, formatShare } from "../lib/format";
import { stepsLabel } from "../lib/outlook";
import { assetColorVar } from "./ui";
import { Bars, Meter, OneIn, Tile, TileGrid, stateColour } from "./viz";

const TONE_WORD = (score: number | null | undefined) =>
  score == null
    ? "Quiet"
    : score > 0.15
      ? "Mostly positive"
      : score < -0.15
        ? "Mostly negative"
        : "Mixed";

const VERDICT: Record<string, string> = {
  "sentiment leads price": "News has moved first",
  "price leads sentiment": "Price has moved first",
  "no measurable relationship": "No measurable link to price",
  "not enough events": "Too little news to say",
};

const days = (n: number) => `${n} day${n === 1 ? "" : "s"}`;
const capital = (word: string) => word.charAt(0).toUpperCase() + word.slice(1);

/** The top of a market page: each answer as a figure with a small picture of it. */
export function SummaryCard({ asset, summary }: { asset: Asset; summary: Summary }) {
  const { state, outlook, swings, risk, news, trust } = summary;
  if (!state && !outlook && !swings && !news) return null;
  const base = `/asset/${asset.slug}`;
  const colour = `var(${assetColorVar(asset)})`;

  return (
    <section aria-label="In brief" className="flex flex-col gap-3 @xl:gap-4">
      <TileGrid>
        {state && (
          <Tile
            label="Market state"
            to={`${base}/state`}
            trust={trust.state}
            figure={<span style={{ color: stateColour(state.label) }}>{capital(state.label)}</span>}
            note={`for ${days(state.days_in_state)}`}
          >
            <Meter
              value={state.probability}
              min={0}
              max={1}
              band={[0, state.probability]}
              colour={stateColour(state.label)}
              left="How sure"
              right={formatShare(state.probability, 0)}
              label={`${formatShare(state.probability, 0)} sure`}
            />
          </Tile>
        )}
        {outlook && (
          <Tile
            label={`Likely range, next ${stepsLabel(outlook.steps, asset.trades_continuously)}`}
            to={`${base}/outlook`}
            trust={trust.outlook}
            figure={`${formatPrice(outlook.low)} – ${formatPrice(outlook.high)}`}
            note="8 in 10 simulated outcomes"
          >
            <Meter
              value={outlook.start_price}
              min={outlook.low - (outlook.high - outlook.low) * 0.25}
              max={outlook.high + (outlook.high - outlook.low) * 0.25}
              band={[outlook.low, outlook.high]}
              colour={colour}
              left={formatPrice(outlook.low)}
              right={formatPrice(outlook.high)}
              label={`Now ${formatPrice(outlook.start_price)}, between ${formatPrice(outlook.low)} and ${formatPrice(outlook.high)}`}
            />
          </Tile>
        )}
        {swings && (
          <Tile
            label="Typical day ahead"
            to={`${base}/swings`}
            trust={trust.swings}
            figure={`±${formatShare(swings.forecast)}`}
            note="in either direction"
          >
            <Bars
              format={(v) => `±${formatShare(v)}`}
              rows={[
                { key: "next", name: "Expected next", value: swings.forecast, colour },
                ...(swings.last_realised != null
                  ? [
                      {
                        key: "last",
                        name: "Last day was",
                        value: swings.last_realised,
                        colour: "var(--muted)",
                      },
                    ]
                  : []),
              ]}
            />
          </Tile>
        )}
        {risk && (
          <Tile
            label="One-day loss limit"
            to={`${base}/risk`}
            trust={trust.risk}
            figure={formatShare(risk.limit, 1)}
            note="passed on about 1 day in 20"
          >
            <OneIn lit={1} of={20} label="About 1 day in 20" />
          </Tile>
        )}
        {news && (
          <Tile
            label="News tone"
            to={`${base}/news`}
            trust={trust.news}
            figure={TONE_WORD(news.current)}
            note={news.verdict ? (VERDICT[news.verdict] ?? "") : ""}
          >
            <Meter
              value={news.current ?? 0}
              min={-1}
              max={1}
              tick={0}
              colour={
                (news.current ?? 0) > 0.15
                  ? "var(--calm)"
                  : (news.current ?? 0) < -0.15
                    ? "var(--alert)"
                    : "var(--muted)"
              }
              left="Negative"
              right="Positive"
              label={`News tone ${TONE_WORD(news.current).toLowerCase()}`}
            />
          </Tile>
        )}
      </TileGrid>

      {summary.changes.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="What changed this week">
          {summary.changes.map((change) => (
            <li key={change.topic} className="well px-3 py-2 text-sm">
              {change.text}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
