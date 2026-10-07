import { useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import type { Signal, SignalRecord } from "../api/client";
import { useAssets, useSignalRecords, useSignals } from "../api/queries";
import { PageSkeleton, Skeleton } from "../components/Skeleton";
import { SectionMenu, Tabs } from "../components/Tabs";
import { Caption, Message, Panel, Segmented, assetColorVar, shortName } from "../components/ui";
import { formatCount, formatShare } from "../lib/format";
import {
  DIRECTION_WORDS,
  SIGNAL_PAGES,
  SIZE_WORDS,
  TYPE_NAME,
  isFinding,
  isSignalType,
  kindName,
  signalDetail,
  type SignalType,
} from "../lib/signals";
import { formatDate } from "../lib/time";

const BASE = "/signals";
const KINDS = [
  { value: "all", label: "All" },
  { value: "regime_change", label: "Change of state" },
  { value: "abnormal_move", label: "Abnormal move" },
] as const;
const PORTFOLIO_WORDS: Record<string, string> = {
  drift: "A holding has drifted more than 5 points from its target share",
  turbulent: "Part of your portfolio is in a market that is turbulent right now",
  above_band: "Your portfolio is moving more than your target's range",
  below_band: "Your portfolio is moving less than your target's range",
};

function Chip({ children, strong = false }: { children: string; strong?: boolean }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${
        strong
          ? "bg-[color-mix(in_srgb,var(--accent)_18%,transparent)] text-ink"
          : "bg-white/6 text-muted"
      }`}
    >
      {children}
    </span>
  );
}

function FeedRow({ signal, colour }: { signal: Signal; colour: string }) {
  const record = signal.record;
  const type = signal.type as SignalType;
  const detail = signalDetail(signal);
  return (
    <li className="border-t border-line first:border-t-0">
      <Link
        to={`${BASE}/${signal.type}`}
        className="group flex flex-col gap-2 py-4 transition-colors hover:bg-white/[0.02] @xl:flex-row @xl:items-center @xl:justify-between @xl:gap-6"
        aria-label={`${signal.name}: ${kindName(type, signal.variant)}, ${formatDate(signal.ts)}. See its track record`}
      >
        <span className="flex min-w-0 items-start gap-3">
          <span
            className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full"
            style={{ background: colour }}
            aria-hidden="true"
          />
          <span className="min-w-0">
            <span className="block font-medium group-hover:text-accent">
              {shortName(signal)} · {kindName(type, signal.variant)}
            </span>
            <span className="num mt-0.5 block text-sm text-muted">
              {formatDate(signal.ts)}
              {detail ? ` · ${detail}` : ""}
            </span>
          </span>
        </span>
        {record && (
          <span className="flex flex-wrap items-center gap-1.5 pl-5.5 @xl:justify-end @xl:pl-0">
            <Chip strong={isFinding(record.verdict)}>
              {DIRECTION_WORDS[record.verdict] ?? record.verdict}
            </Chip>
            {record.verdict !== "not enough occurrences" && (
              <Chip strong={isFinding(record.size_verdict)}>
                {SIZE_WORDS[record.size_verdict] ?? record.size_verdict}
              </Chip>
            )}
            <span className="num text-xs text-faint">{formatCount(record.n)} past cases</span>
          </span>
        )}
      </Link>
    </li>
  );
}

/** How many signals the feed opens with, how many more a tap adds, and how far back. */
const FIRST = 5;
const MORE = 10;
const RECENT_DAYS = 90;

function Feed() {
  const assets = useAssets().data ?? [];
  const primary = assets.filter((a) => a.is_primary);
  const [market, setMarket] = useState("all");
  const [kind, setKind] = useState<(typeof KINDS)[number]["value"]>("all");
  const signals = useSignals({
    symbol: market === "all" ? undefined : market,
    type: kind === "all" ? undefined : kind,
  });
  const markets = [
    { value: "all", label: "All markets" },
    ...primary.map((a) => ({ value: a.slug, label: shortName(a) })),
  ];
  const colourOf = (symbol: string) => {
    const asset = assets.find((a) => a.symbol === symbol);
    return asset ? `var(${assetColorVar(asset)})` : "var(--accent)";
  };
  const data = signals.data;
  // A short list first: the last three months, a few at a time. A long feed is tiring and
  // the newest few are what matter.
  const [shown, setShown] = useState(FIRST);
  const [older, setOlder] = useState(false);
  const [opened] = useState(() => Date.now());
  const cutoff = opened - RECENT_DAYS * 86_400_000;
  const all = data?.signals ?? [];
  const recent = all.filter((signal) => Date.parse(signal.ts) >= cutoff);
  const list = older ? all : recent;
  const visible = list.slice(0, shown);
  // While the next set is fetched the one on screen stays and dims. Only the very first
  // load has nothing to show, and that is where the skeletons belong.
  const busy = signals.isPlaceholderData || (signals.isFetching && !data);
  return (
    <>
      {data && data.portfolio.length > 0 && (
        <Link to="/portfolio/try" className="well block px-4 py-3 text-sm hover:bg-white/[0.04]">
          <span className="label">Your portfolio against your target</span>
          <ul className="mt-1.5 flex flex-col gap-1">
            {[...new Set(data.portfolio.map((s) => PORTFOLIO_WORDS[s.kind] ?? s.kind))].map(
              (text) => (
                <li key={text}>{text}.</li>
              ),
            )}
          </ul>
        </Link>
      )}
      <Panel
        id="feed"
        title="Latest signals"
        headline={
          !data || data.signals.length > 0
            ? "What changed, newest first, with what has followed each kind before"
            : "Nothing has fired for this choice"
        }
      >
        <div className="flex flex-wrap gap-3">
          <Segmented
            options={markets}
            value={market}
            onChange={(value) => {
              setMarket(value);
              setShown(FIRST);
            }}
            label="Market"
          />
          <Segmented
            options={KINDS}
            value={kind}
            onChange={(value) => {
              setKind(value);
              setShown(FIRST);
            }}
            label="Kind of signal"
          />
        </div>
        {!data && !signals.isError && (
          <div role="status" aria-label="Loading" className="flex flex-col gap-4">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        )}
        {signals.isError && <Message>Signals are unavailable right now.</Message>}
        {data && data.signals.length > 0 && (
          <ul className="-my-2 flex flex-col" data-busy={busy} aria-busy={busy}>
            {visible.map((signal) => (
              <FeedRow key={signal.id} signal={signal} colour={colourOf(signal.symbol)} />
            ))}
          </ul>
        )}
        {data && all.length > 0 && visible.length === 0 && (
          <p className="text-sm text-muted">Nothing in the last 3 months.</p>
        )}
        {data && (list.length > visible.length || (!older && all.length > recent.length)) && (
          <div className="flex flex-wrap gap-2">
            {list.length > visible.length && (
              <button
                type="button"
                className="btn btn-ghost press"
                onClick={() => setShown(shown + MORE)}
              >
                Show {Math.min(MORE, list.length - visible.length)} more
              </button>
            )}
            {!older && all.length > recent.length && (
              <button type="button" className="btn btn-ghost press" onClick={() => setOlder(true)}>
                Include older ones ({all.length - recent.length})
              </button>
            )}
          </div>
        )}
        <Caption
          facts={[
            { label: "Shows", value: "What changed, newest first. Not a forecast of direction." },
            {
              label: "Abnormal move",
              value: "An hour's move over 5 times the usual size for the market's state",
            },
            { label: "Date", value: "The day the signal describes" },
            { label: "Showing", value: "The last 3 months first, a few at a time" },
          ]}
        >
          Each signal links to its track record: what the market did after every earlier signal of
          the same kind, set against what it does on any day.
        </Caption>
      </Panel>
    </>
  );
}

type HorizonRecord = SignalRecord["horizons"][number];

/** After the signal against all days: how often the next period ended higher. */
function DirectionBar({ horizon }: { horizon: HorizonRecord }) {
  const { signal, baseline } = horizon;
  if (signal.share_positive == null || baseline.share_positive == null) return null;
  const at = (share: number) => `${share * 100}%`;
  const judged = horizon.verdict !== "not enough occurrences";
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="text-muted">Ended higher after {horizon.label}</span>
        <span className="num font-medium">
          {formatShare(signal.share_positive, 0)}{" "}
          <span className="font-normal text-muted">
            any day {formatShare(baseline.share_positive, 0)}
          </span>
        </span>
      </div>
      <div
        className="relative mt-2 h-2 rounded-full bg-white/8"
        role="img"
        aria-label={`Ended higher ${formatShare(signal.share_positive, 0)} of the time after the signal, plausibly between ${formatShare(signal.share_low ?? 0, 0)} and ${formatShare(signal.share_high ?? 0, 0)}; ${formatShare(baseline.share_positive, 0)} on any day`}
      >
        <span
          className="absolute inset-y-0 rounded-full"
          style={{
            left: at(signal.share_low ?? signal.share_positive),
            right: `calc(100% - ${at(signal.share_high ?? signal.share_positive)})`,
            background: judged
              ? "color-mix(in srgb, var(--accent) 45%, transparent)"
              : "rgba(255,255,255,0.18)",
          }}
        />
        <span
          className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-bg"
          style={{
            left: at(signal.share_positive),
            background: judged ? "var(--accent)" : "var(--muted)",
          }}
        />
        <span
          className="absolute -inset-y-1 w-0.5 bg-ink"
          style={{ left: at(baseline.share_positive) }}
          aria-hidden="true"
        />
      </div>
    </div>
  );
}

/** Typical size of the move that followed, against any day. */
function SizeBars({ horizon }: { horizon: HorizonRecord }) {
  const after = horizon.signal.mean_size;
  const usual = horizon.baseline.mean_size;
  if (after == null || usual == null) return null;
  const reach = Math.max(after, usual) || 1;
  const rows = [
    {
      key: "after",
      name: `Typical move after ${horizon.label}`,
      value: after,
      colour: "var(--accent)",
    },
    { key: "usual", name: "On any day", value: usual, colour: "rgba(255,255,255,0.35)" },
  ];
  return (
    <div className="flex flex-col gap-2">
      {rows.map((row) => (
        <div key={row.key} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3">
          <span className="min-w-0">
            <span className="block text-xs text-muted">{row.name}</span>
            <span className="mt-1 block h-1.5 rounded-full bg-white/8">
              <span
                className="block h-full rounded-full"
                style={{ width: `${(row.value / reach) * 100}%`, background: row.colour }}
              />
            </span>
          </span>
          <span className="num text-sm font-medium">±{formatShare(row.value, 2)}</span>
        </div>
      ))}
    </div>
  );
}

function RecordCard({ record, type }: { record: SignalRecord; type: SignalType }) {
  const judged = record.verdict !== "not enough occurrences";
  return (
    <li className="well flex flex-col gap-4 px-4 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="font-medium">
          {shortName(record)} · {kindName(type, record.variant).split(", ")[1]}
        </h3>
        <p className="num text-sm text-muted">
          {formatCount(record.n)} past cases
          {record.first_day && record.last_day
            ? `, ${formatDate(record.first_day)} to ${formatDate(record.last_day)}`
            : ""}
        </p>
      </div>
      <div className="flex flex-wrap gap-1.5">
        <Chip strong={isFinding(record.verdict)}>
          {DIRECTION_WORDS[record.verdict] ?? record.verdict}
        </Chip>
        {judged && (
          <Chip strong={isFinding(record.size_verdict)}>
            {SIZE_WORDS[record.size_verdict] ?? record.size_verdict}
          </Chip>
        )}
      </div>
      {record.n > 0 && (
        <div className="grid grid-cols-1 gap-x-8 gap-y-5 @3xl:grid-cols-2">
          {record.horizons.map((horizon) => (
            <div key={horizon.steps} className="flex flex-col gap-4">
              <DirectionBar horizon={horizon} />
              <SizeBars horizon={horizon} />
            </div>
          ))}
        </div>
      )}
    </li>
  );
}

function Records({ type }: { type: SignalType }) {
  const query = useSignalRecords(type);
  const data = query.data;
  if (!data)
    return query.isPending ? (
      <PageSkeleton />
    ) : (
      <Message>This track record is unavailable right now.</Message>
    );
  const findings = data.records.filter(
    (r) => isFinding(r.verdict) || isFinding(r.size_verdict),
  ).length;
  const judged = data.records.filter((r) => r.verdict !== "not enough occurrences").length;
  return (
    <Panel
      id="record"
      title={TYPE_NAME[type]}
      trust={data.records.length > 0 ? data.trust : undefined}
      headline={
        data.records.length === 0
          ? "This signal has not fired in the stored history"
          : findings > 0
            ? `${findings} of ${data.records.length} kinds were followed by something measurable`
            : judged > 0
              ? "Nothing measurable has followed this signal"
              : "Too few past cases to judge yet"
      }
    >
      {!data.in_feed && (
        <p className="well px-4 py-3 text-sm text-muted">
          This one is not shown as a signal. It has been tested three ways and has never carried
          information about what prices do next, so showing it would only add noise. Its record is
          kept here as the evidence.
        </p>
      )}
      <ul
        className="flex flex-col gap-3"
        data-busy={query.isPlaceholderData}
        aria-busy={query.isPlaceholderData}
      >
        {data.records.map((record) => (
          <RecordCard key={`${record.symbol}-${record.variant}`} record={record} type={type} />
        ))}
      </ul>
      <Caption
        facts={[
          {
            label: "Shows",
            value: "What followed every past signal of this kind, against any day",
          },
          { label: "Found with", value: "Only what was known on the signal's day" },
          { label: "Measured from", value: "The close of the signal's day" },
          {
            label: "Each bar",
            value:
              "Dot, how often it ended higher; band, where that share could lie; line, any day",
          },
          {
            label: "Allowing for",
            value: `${data.tested} comparisons looked at together across all signals`,
          },
          { label: "Not judged", value: "Kinds with fewer than 30 past cases" },
        ]}
      >
        A band that covers the line means no edge. The findings about the size of the move were
        looked for after the direction test found nothing, so treat them as provisional until they
        hold on new data.
      </Caption>
    </Panel>
  );
}

export function SignalsPage() {
  const { type } = useParams();
  if (type !== undefined && !isSignalType(type)) return <Navigate to={BASE} replace />;
  return (
    <div className="flex flex-col gap-4 @xl:gap-6">
      <header>
        <h1 className="title">Signals</h1>
      </header>
      <Tabs base={BASE} items={SIGNAL_PAGES} label="Signal pages" />
      {type === undefined ? (
        <>
          <Feed />
          <SectionMenu base={BASE} items={SIGNAL_PAGES} title="What has followed each kind" />
        </>
      ) : (
        <Records type={type} />
      )}
    </div>
  );
}
