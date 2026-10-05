import type { Asset, EventStudy, Sentiment } from "../api/client";
import { useEventStudy, useSentiment } from "../api/queries";
import { formatChange, formatCount, formatShare } from "../lib/format";
import { formatDate, formatDateTime, zoneLabel } from "../lib/time";
import { Caption, StatRow } from "./ui";

const TOPIC: Record<string, string> = {
  regulation: "Regulation and courts",
  funds_flows: "Funds and large investors",
  security: "Hacks, fraud, and failures",
  macro: "Economy and geopolitics",
  adoption: "Companies and adoption",
  price: "Price commentary",
  other: "Other",
};

const VERDICT: Record<string, string> = {
  "sentiment leads price": "News tone has tended to move before price.",
  "price leads sentiment": "Price has tended to move first, with news tone following it.",
  "no measurable relationship": "No measurable link between news tone and later price moves.",
  "not enough events": "There is too little news coverage of this asset to measure an effect.",
};

/** A plain word for a tone score between -1 and +1. */
export function toneWord(score: number | null | undefined): string {
  if (score == null) return "No recent news";
  if (score > 0.15) return "Mostly positive";
  if (score < -0.15) return "Mostly negative";
  return "Mixed";
}

const signed = (value: number) =>
  `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toFixed(2)}`;

function ToneChart({ sentiment }: { sentiment: Sentiment }) {
  const width = 600;
  const height = 120;
  const points = sentiment.daily;
  const first = points[0];
  const last = points.at(-1);
  if (!first || !last) return null;
  const step = width / points.length;
  const most = Math.max(...points.map((p) => p.article_count), 1);
  return (
    <div>
      <svg
        viewBox={`0 0 ${width} ${height + 34}`}
        preserveAspectRatio="none"
        className="h-44 w-full"
        role="img"
        aria-label="Daily news tone, with the number of articles each day beneath"
      >
        <line x1="0" x2={width} y1={height / 2} y2={height / 2} stroke="var(--line-strong)" />
        {points.map((point, i) => {
          const score = point.score_mean;
          const bar = score == null ? 0 : (Math.abs(score) * height) / 2;
          return (
            <g key={point.ts}>
              {score != null && (
                <rect
                  x={i * step}
                  width={Math.max(step - 1, 0.6)}
                  y={score >= 0 ? height / 2 - bar : height / 2}
                  height={Math.max(bar, 0.6)}
                  fill={score >= 0 ? "var(--calm)" : "var(--alert)"}
                  opacity="0.85"
                />
              )}
              <rect
                x={i * step}
                width={Math.max(step - 1, 0.6)}
                y={height + 34 - (point.article_count / most) * 26}
                height={(point.article_count / most) * 26}
                fill="var(--muted)"
                opacity="0.45"
              />
            </g>
          );
        })}
      </svg>
      <div className="num mt-2 flex justify-between text-xs text-faint">
        <span>{formatDate(first.ts)}</span>
        <span>{formatDate(last.ts)}</span>
      </div>
    </div>
  );
}

function Articles({ title, articles }: { title: string; articles: Sentiment["most_positive"] }) {
  return (
    <div>
      <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
      {articles.length === 0 ? (
        <p className="mt-3 text-sm text-muted">None in this period.</p>
      ) : (
        <ul className="mt-2">
          {articles.map((article) => (
            <li key={article.id} className="border-t border-line py-2.5 first:border-t-0">
              {article.url ? (
                <a
                  href={article.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-sm leading-snug text-ink underline-offset-2 hover:underline"
                >
                  {article.headline}
                </a>
              ) : (
                <span className="text-sm leading-snug">{article.headline}</span>
              )}
              <p className="num mt-1 text-xs text-faint">
                {formatDate(article.created_at)} · tone {signed(article.score)}
                {article.topic ? ` · ${TOPIC[article.topic] ?? article.topic}` : ""}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const OFFSET_LABEL: Record<number, string> = {
  [-1]: "Day before",
  0: "News day",
  1: "+1 day",
  2: "+2 days",
  3: "+3 days",
};

function Paths({ study }: { study: EventStudy }) {
  const width = 600;
  const height = 150;
  const lines = [
    { path: study.baseline, color: "var(--muted)", dash: "5 5", band: false },
    { path: study.negative, color: "var(--alert)", dash: undefined, band: true },
    { path: study.positive, color: "var(--calm)", dash: undefined, band: true },
  ].filter((line) => line.path.n > 0);
  if (!lines.length) return null;
  const extreme = Math.max(
    ...lines.flatMap((l) => [...l.path.low, ...l.path.high, ...l.path.mean].map(Math.abs)),
    1e-6,
  );
  const offsets = study.positive.offsets;
  const x = (i: number) => (i / (offsets.length - 1)) * width;
  const y = (value: number) => height / 2 - (value / extreme) * (height / 2 - 4);
  const line = (values: number[]) =>
    values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <div>
      <div className="flex gap-3">
        <div className="num flex flex-col justify-between text-right text-xs text-faint">
          <span>{formatChange(extreme)}</span>
          <span>{formatChange(0)}</span>
          <span>{formatChange(-extreme)}</span>
        </div>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          className="h-40 min-w-0 flex-1"
          role="img"
          aria-label="Average price path around days with unusually positive or negative news"
        >
          <line x1="0" x2={width} y1={height / 2} y2={height / 2} stroke="var(--line-strong)" />
          {lines.map((l, i) => (
            <g key={i}>
              {l.band && (
                <path
                  d={`${line(l.path.high)} ${[...l.path.low]
                    .map((v, j) => `L${x(j).toFixed(1)},${y(v).toFixed(1)}`)
                    .reverse()
                    .join(" ")} Z`}
                  fill={l.color}
                  opacity="0.12"
                />
              )}
              <path
                d={line(l.path.mean)}
                fill="none"
                stroke={l.color}
                strokeWidth="2"
                strokeDasharray={l.dash}
                vectorEffect="non-scaling-stroke"
              />
            </g>
          ))}
        </svg>
      </div>
      <div className="mt-2 flex justify-between pl-14 text-xs text-faint">
        {offsets.map((offset) => (
          <span key={offset}>{OFFSET_LABEL[offset] ?? offset}</span>
        ))}
      </div>
    </div>
  );
}

function Lags({ study }: { study: EventStudy }) {
  const width = 600;
  const height = 110;
  const extreme = Math.max(...study.lags.map((l) => Math.abs(l.correlation)), 0.05);
  const step = width / study.lags.length;
  return (
    <div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="h-28 w-full"
        role="img"
        aria-label="Correlation between news tone and price moves a few days apart"
      >
        <line x1="0" x2={width} y1={height / 2} y2={height / 2} stroke="var(--line-strong)" />
        {study.lags.map((lag, i) => {
          const bar = (Math.abs(lag.correlation) / extreme) * (height / 2 - 4);
          return (
            <rect
              key={lag.lag}
              x={i * step + step * 0.2}
              width={step * 0.6}
              y={lag.correlation >= 0 ? height / 2 - bar : height / 2}
              height={Math.max(bar, 0.6)}
              rx="2"
              fill={lag.significant ? "var(--accent)" : "var(--muted)"}
              opacity={lag.significant ? 0.95 : 0.4}
            />
          );
        })}
      </svg>
      <div className="mt-2 flex justify-between text-xs text-faint">
        <span>Price moved first (up to 5 days)</span>
        <span>Same day</span>
        <span>News came first (up to 5 days)</span>
      </div>
    </div>
  );
}

function Study({ study }: { study: EventStudy }) {
  const enough = study.verdict !== "not enough events";
  const strongest = [...study.lags].sort(
    (a, b) => Math.abs(b.correlation) - Math.abs(a.correlation),
  )[0];
  return (
    <div className="border-t border-line pt-5">
      <h3 className="text-sm font-semibold tracking-tight">Does the news move the price?</h3>
      <p className="mt-2 text-base leading-relaxed">{VERDICT[study.verdict] ?? study.verdict}</p>
      <p className="mt-1 text-sm text-muted">
        <span className="num text-ink">{formatCount(study.n_events)}</span> days with unusually
        strong tone were found
        {study.first_day && study.last_day
          ? ` between ${formatDate(study.first_day)} and ${formatDate(study.last_day)}`
          : ""}
        ; at least <span className="num text-ink">{study.min_events}</span> are needed for a
        verdict.
      </p>
      {enough && (
        <div className="mt-5 grid grid-cols-1 gap-x-12 gap-y-7 lg:grid-cols-2">
          <div>
            <Paths study={study} />
            <Caption>
              Average price move, beyond the usual drift, around {formatCount(study.positive.n)}{" "}
              days of unusually positive news (green) and {formatCount(study.negative.n)} of
              unusually negative news (red). Shaded bands show the uncertainty. The dashed line is
              the same measure on {formatCount(study.baseline.n)} ordinary days in similar market
              states.
            </Caption>
          </div>
          <div>
            <Lags study={study} />
            <Caption>
              How closely a day&apos;s news tone tracks the price move a few days earlier or later,
              over {formatCount(strongest?.n ?? 0)} days. Bright bars are larger than chance would
              give; grey bars are not. The same-day bar cannot show which came first.
            </Caption>
          </div>
        </div>
      )}
    </div>
  );
}

export function NewsPanel({ asset }: { asset: Asset }) {
  const sentiment = useSentiment(asset.slug).data;
  const study = useEventStudy(asset.slug).data;
  if (!sentiment) return null;
  const accuracy = sentiment.accuracy;
  const labeller = accuracy?.labelled_by.includes("claude")
    ? "an AI model (Claude), not a person"
    : "hand";

  return (
    <section id="news" className="glass flex scroll-mt-24 flex-col gap-6 p-5 sm:p-7">
      <h2 className="text-base font-semibold tracking-tight">News</h2>

      <div className="grid grid-cols-1 gap-x-12 gap-y-7 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.4fr)]">
        <div>
          <p className="label">Tone of recent news</p>
          <p className="price-lg mt-2">{toneWord(sentiment.current)}</p>
          <dl className="mt-4">
            {sentiment.current != null && (
              <StatRow label="Tone score, from −1 to +1">{signed(sentiment.current)}</StatRow>
            )}
            <StatRow label="Articles in the last 24 hours">
              {formatCount(sentiment.articles_24h)}
            </StatRow>
            <StatRow label="Articles in the last 7 days">
              {formatCount(sentiment.articles_7d)}
            </StatRow>
          </dl>
          <p className="mt-3 text-xs leading-relaxed text-faint">
            Recent articles count for more: an article&apos;s weight halves every 24 hours. As of{" "}
            {formatDateTime(sentiment.as_of)} {zoneLabel()}.
          </p>
        </div>
        <div>
          <ToneChart sentiment={sentiment} />
          <Caption>
            Average tone of each day&apos;s articles (green positive, red negative) with the number
            of articles beneath. {formatCount(sentiment.articles_in_window)} articles on{" "}
            {formatCount(sentiment.days_with_news)} of the last{" "}
            {formatCount(sentiment.daily.length)} days. News for this market is measured from{" "}
            {formatDate(sentiment.news_start)}; before that there is too little of it.
          </Caption>
        </div>
      </div>

      {sentiment.topics.length > 0 && (
        <div className="border-t border-line pt-5">
          <h3 className="text-sm font-semibold tracking-tight">What the news is about</h3>
          <dl className="mt-2 grid grid-cols-1 gap-x-12 sm:grid-cols-2">
            {sentiment.topics.map((topic) => (
              <StatRow key={topic.topic} label={TOPIC[topic.topic] ?? topic.topic}>
                {formatCount(topic.article_count)}{" "}
                <span className={topic.score_mean >= 0 ? "text-calm" : "text-alert"}>
                  {signed(topic.score_mean)}
                </span>
              </StatRow>
            ))}
          </dl>
          <Caption>
            Number of articles on each subject in the same period, and their average tone.
          </Caption>
        </div>
      )}

      <div className="grid grid-cols-1 gap-x-12 gap-y-7 border-t border-line pt-5 lg:grid-cols-2">
        <Articles title="Most positive articles" articles={sentiment.most_positive} />
        <Articles title="Most negative articles" articles={sentiment.most_negative} />
      </div>

      {study && <Study study={study} />}

      <p className="border-t border-line pt-4 text-xs leading-relaxed text-faint">
        Tone is scored by a language model trained on financial text, from each article&apos;s
        headline and summary. All articles come from one provider.
        {accuracy && (
          <>
            {" "}
            On {formatCount(accuracy.model.n)} headlines labelled by {labeller}, the model agreed
            with the label {formatShare(accuracy.model.accuracy, 0)} of the time
            {accuracy.baseline
              ? `; simply counting positive and negative words agreed ${formatShare(accuracy.baseline.accuracy, 0)} of the time`
              : ""}
            .
            {accuracy.topics
              ? ` The subject it assigned matched ${formatShare(accuracy.topics.accuracy, 0)} of the time.`
              : ""}
          </>
        )}{" "}
        Such models misread sarcasm, negation, and headlines that only describe a price move.
      </p>
    </section>
  );
}
