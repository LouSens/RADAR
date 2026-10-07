import type { Sentiment } from "../api/client";
import { useSentiment } from "../api/queries";
import { formatCount, formatShare } from "../lib/format";
import { formatDate, formatDateTime, zoneLabel } from "../lib/time";
import { Evidence, Caption, Panel, StatRow, type PanelProps } from "./ui";

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

function Headlines({ articles }: { articles: Sentiment["recent"] }) {
  return (
    <div className="border-t border-line pt-5">
      <h3 className="text-sm font-semibold tracking-tight">Recent headlines</h3>
      {articles.length === 0 ? (
        <p className="mt-3 text-sm text-muted">None yet.</p>
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
              <p className="num mt-1 text-xs text-faint">{formatDateTime(article.created_at)}</p>
            </li>
          ))}
        </ul>
      )}
      <Caption
        facts={[
          { label: "Shows", value: `The latest ${articles.length} articles, newest first` },
          {
            label: "Not ranked",
            value: "And not coloured by tone: the tone of any single article is too often wrong",
          },
        ]}
      />
    </div>
  );
}

const range = (low: number | null | undefined, high: number | null | undefined) =>
  low == null || high == null ? "" : ` (${formatShare(low, 0)} to ${formatShare(high, 0)})`;

function Trust({ accuracy }: { accuracy: NonNullable<Sentiment["accuracy"]> }) {
  const model = accuracy.model;
  const byAi = accuracy.labelled_by.includes("claude");
  return (
    <div className="well p-4">
      <dl className="mt-2">
        <StatRow label={`Agreed with the label, on ${formatCount(model.n)} headlines`}>
          {formatShare(model.accuracy, 0)}
          <span className="text-muted">{range(model.accuracy_low, model.accuracy_high)}</span>
        </StatRow>
        {accuracy.direction && (
          <StatRow label="Got the direction backwards">
            {formatShare(accuracy.direction.opposite_rate, 0)}
          </StatRow>
        )}
        {accuracy.original && (
          <StatRow label="An earlier version, same headlines">
            {formatShare(accuracy.original.accuracy, 0)}
          </StatRow>
        )}
        {accuracy.baseline && (
          <StatRow label="Counting positive and negative words">
            {formatShare(accuracy.baseline.accuracy, 0)}
          </StatRow>
        )}
        {accuracy.topics && (
          <StatRow label={`Subject matched, on ${formatCount(accuracy.topics.n)} headlines`}>
            {formatShare(accuracy.topics.accuracy, 0)}
            <span className="text-muted">
              {range(accuracy.topics.accuracy_low, accuracy.topics.accuracy_high)}
            </span>
          </StatRow>
        )}
      </dl>
      <Caption
        facts={[
          { label: "Most common error", value: "Calling a mild article neutral, or the reverse" },
          {
            label: "Daily figures",
            value: "Average many articles, which is steadier than any one of them",
          },
          {
            label: "These headlines",
            value: accuracy.held_out
              ? "Are all newer than anything the model was trained on"
              : "Were labelled before the model scored them",
          },
          ...(byAi
            ? [
                {
                  label: "Labelled by",
                  value:
                    "An AI model (Claude), not a person, so this measures agreement with that labeller",
                },
              ]
            : []),
          {
            label: "Brackets",
            value: "Where the true figure plausibly lies, given the sample size",
          },
        ]}
      />
    </div>
  );
}

export function NewsPanel({ asset, trust }: PanelProps) {
  const sentiment = useSentiment(asset.slug).data;
  if (!sentiment) return null;
  const accuracy = sentiment.accuracy;

  return (
    <Panel id="news" title="News" trust={trust} headline={toneWord(sentiment.current)}>
      <div className="grid grid-cols-1 gap-x-12 gap-y-7 @4xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.4fr)]">
        <div>
          <p className="label">Tone of recent news</p>
          <p className="price-lg mt-2">{toneWord(sentiment.current)}</p>
          <dl className="mt-4">
            {sentiment.current != null && (
              <StatRow label="Tone, from −1 to +1">{signed(sentiment.current)}</StatRow>
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
          <Caption
            facts={[
              {
                label: "Shows",
                value: "Average tone of each day's articles, green positive, red negative",
              },
              { label: "Beneath", value: "How many articles that day" },
              {
                label: "Sample",
                value: `${formatCount(sentiment.articles_in_window)} articles on ${formatCount(sentiment.days_with_news)} of the last ${formatCount(sentiment.daily.length)} days`,
              },
              {
                label: "News starts",
                value: `${formatDate(sentiment.news_start)}; before that there is too little of it`,
              },
            ]}
          />
        </div>
      </div>

      <Headlines articles={sentiment.recent} />

      {accuracy && (
        <Evidence summary="How the tone reading was checked">
          <Trust accuracy={accuracy} />
        </Evidence>
      )}

      <details className="about">
        <summary>How this works</summary>
        <p className="prose mt-3 text-xs leading-relaxed text-muted">
          Tone is scored by a language model trained on financial text
          {accuracy?.fine_tuned ? " and then fine-tuned on headlines like these" : ""}, from each
          article&apos;s headline and summary. All articles come from one provider. Such models
          misread sarcasm, negation, and headlines that only describe a price move.
        </p>
      </details>
    </Panel>
  );
}
