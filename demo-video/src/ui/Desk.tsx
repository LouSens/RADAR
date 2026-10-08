import film from "../fixtures/film.json";
import { C, fade } from "../theme";
import {
  Ladder,
  MarketCard,
  PLACES,
  RadarMark,
  Stroke,
  TabBar,
  TopEdge,
  base,
  formatMoney,
  glass,
  label,
  num,
  type Market,
} from "./kit";
import { Pop, Resolve, Skeleton, Swatch, Ticker, pop } from "./motion";

/**
 * The app's Home at desktop size (pages/Overview.tsx, components/Layout.tsx), rebuilt
 * from the app's own pieces so that it can build itself and reflow into the
 * phone's layout. It shows the made-up example portfolio. Its own pixels are the app's:
 * 1440 wide, drawn at four thirds of that to fill the frame.
 */

export const DESK = { width: 1440, height: 810, zoom: 4 / 3 } as const;

export interface Box {
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
}

/** Where each piece of Home is, in the app's pixels. */
export const AT = {
  side: { x: 12, y: 12, w: 252, h: 786 },
  title: { x: 292, y: 26, w: 400, h: 56 },
  note: { x: 1112, y: 46, w: 300, h: 20 },
  worth: { x: 292, y: 100, w: 642, h: 256 },
  todo: { x: 958, y: 100, w: 454, h: 256 },
  markets: { x: 292, y: 372, w: 300, h: 28 },
  btc: { x: 292, y: 406, w: 362, h: 180 },
  gold: { x: 671, y: 406, w: 362, h: 180 },
  stock: { x: 1050, y: 406, w: 362, h: 180 },
  coming: { x: 292, y: 606, w: 454, h: 192 },
  signals: { x: 770, y: 606, w: 642, h: 192 },
} as const satisfies Record<string, Box>;

export type Piece = keyof typeof AT;

/**
 * The phone's layout of the same pieces (one column, the places in a capsule at the
 * foot), in the pixels of a phone screen 390 wide. A piece keeps its shape and is made
 * smaller to fit the column, as a page does when its window narrows.
 */
export const PHONE = { width: 390, height: 844 } as const;
const column = (y: number, piece: Box, wide = 358): Box => ({
  x: 16,
  y,
  w: wide,
  h: (wide * piece.h) / piece.w,
});
export const ON_PHONE: Readonly<Record<Piece, Box>> = {
  side: { x: 20, y: 772, w: 350, h: 56 },
  title: { x: 16, y: 18, w: 180, h: 25 },
  note: { x: 214, y: 26, w: 160, h: 11 },
  worth: column(56, AT.worth),
  todo: column(210, AT.todo),
  markets: { x: 16, y: 424, w: 150, h: 14 },
  btc: { x: 16, y: 446, w: 114, h: 57 },
  gold: { x: 138, y: 446, w: 114, h: 57 },
  stock: { x: 260, y: 446, w: 114, h: 57 },
  coming: column(516, AT.coming),
  signals: column(680, AT.signals),
};

const { portfolio, markets, calendar, signals } = film;
const LEVEL: Readonly<Record<string, string>> = {
  low: C.calm,
  moderate: C.accent,
  high: C.gold,
};

const ACTIONS = [
  ["My risk", PLACES[2].icon],
  [
    "Before I buy",
    <path key="b" d="M3.5 12h5M8.5 12 20.5 5.5M8.5 12l12 6.5" />,
  ],
  [
    "My plan",
    <path
      key="p"
      d="M4 7h10M18 7h2M4 17h2M10 17h10M14 7a2 2 0 1 0 4 0 2 2 0 0 0-4 0M6 17a2 2 0 1 0 4 0 2 2 0 0 0-4 0"
    />,
  ],
  [
    "My trades",
    <path key="t" d="M4.5 19.5V15M9.5 19.5v-7.5M14.5 19.5V9M19.5 19.5v-15" />,
  ],
] as const;

const day = (iso: string): string =>
  new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });

const card: React.CSSProperties = {
  ...base,
  ...glass,
  height: "100%",
  boxSizing: "border-box",
};

/** The app's sidebar (components/Layout.tsx). `here` is the place it has lit. */
export const Sidebar: React.FC<{
  readonly logo?: number;
  readonly here?: number;
}> = ({ logo = 1, here = 0 }) => (
  <div
    style={{
      ...card,
      borderRadius: 26,
      padding: "20px 12px 12px",
      display: "flex",
      flexDirection: "column",
    }}
  >
    <TopEdge />
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "0 8px",
      }}
    >
      {/* The mark of shot 2 lands here: the logo is drawn once it has. */}
      <span style={{ opacity: logo, display: "flex" }}>
        <RadarMark size={30} />
      </span>
      <span style={{ fontSize: 14, fontWeight: 700, letterSpacing: "0.16em" }}>
        RADAR
      </span>
    </div>
    <span style={{ ...label, margin: "26px 10px 10px" }}>Menu</span>
    {PLACES.map((place, i) => (
      <span
        key={place.label}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          height: 40,
          marginBottom: 4,
          padding: "0 10px",
          borderRadius: 12,
          fontSize: 14,
          fontWeight: 500,
          color: i === here ? C.ink : C.muted,
          background:
            i === here
              ? `color-mix(in srgb, ${C.accent} 16%, rgba(255,255,255,0.05))`
              : undefined,
          boxShadow:
            i === here ? `inset 0 0 0 1px ${fade(C.accent, 0.34)}` : undefined,
        }}
      >
        <Stroke>{place.icon}</Stroke>
        {place.label}
      </span>
    ))}
    <div
      style={{
        marginTop: "auto",
        padding: 14,
        borderRadius: 16,
        border: `1px solid ${C.line}`,
        background: "rgba(0,0,0,0.22)",
        display: "flex",
        flexDirection: "column",
        gap: 2,
      }}
    >
      <span style={label}>Your account</span>
      <span style={{ ...num, fontSize: 21, fontWeight: 600 }}>
        {formatMoney(portfolio.value)}
      </span>
      <span
        style={{ fontSize: 12, color: C.muted, textTransform: "capitalize" }}
      >
        {portfolio.riskLevel} risk
      </span>
      <span
        style={{
          marginTop: 8,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "7px 12px",
          borderRadius: 10,
          background: "rgba(255,255,255,0.05)",
          fontSize: 12,
          fontWeight: 600,
        }}
      >
        1 thing to do
        <span
          style={{
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: C.accent,
          }}
        />
      </span>
    </div>
  </div>
);

/** How far each piece has come: 0 not there, up to 1 a placeholder, up to 2 its content. */
export type Built = (piece: Piece) => number;

/**
 * Home. `built` says how far each piece has arrived, `frame` drives what moves inside
 * (the price, the lines, the chips). `view` draws Home smaller and
 * elsewhere; `towards` says how far each piece has gone to its place in the phone's
 * layout, which is at `phone` (a box in the frame's own pixels); with `arriving`, only
 * the pieces on their way there are drawn.
 */
export const Desk: React.FC<{
  readonly frame: number;
  readonly built: Built;
  /** The frame the content of the cards started to arrive, for what counts and draws. */
  readonly alive: number;
  readonly logo?: number;
  readonly towards?: (piece: Piece) => number;
  readonly phone?: Box;
  readonly view?: {
    readonly k: number;
    readonly x: number;
    readonly y: number;
  };
  readonly arriving?: boolean;
  /** How far the sidebar has collapsed into the phone's capsule of places. */
  readonly capsule?: number;
  /** How much the rows of "Coming up" show, where they are waited for. */
  readonly coming?: number;
  /** Tells two drawings of Home apart, so that their own drawings do not share names. */
  readonly copy?: string;
}> = ({
  frame,
  built,
  alive,
  logo = 1,
  towards,
  phone,
  view = { k: 1, x: 0, y: 0 },
  arriving = false,
  capsule = 0,
  coming = 1,
  copy = "",
}) => {
  const since = frame - alive;
  const btc = markets[0];
  // The Bitcoin price ticks through the last hours as the card arrives.
  const hours = btc.weekCloses;
  const price =
    hours[
      Math.min(
        hours.length - 1,
        hours.length - 12 + Math.max(Math.floor(since / 3), 0),
      )
    ];

  /** A piece's box in the frame: the desk's own, or on its way to the phone's. */
  const place = (piece: Piece): React.CSSProperties => {
    const from = AT[piece];
    const there = built(piece);
    const arrive = Math.min(there, 1);
    let scale = DESK.zoom * view.k;
    let x = view.x + from.x * scale;
    let y = view.y + from.y * scale;
    const morph = towards?.(piece) ?? 0;
    if (morph > 0 && phone) {
      const to = ON_PHONE[piece];
      const k = phone.w / PHONE.width;
      x += (phone.x + to.x * k - x) * morph;
      y += (phone.y + to.y * k - y) * morph;
      scale += ((to.w * k) / from.w - scale) * morph;
    }
    return {
      position: "absolute",
      left: 0,
      top: 0,
      width: from.w,
      height: from.h,
      transformOrigin: "0 0",
      transform: `translate(${x}px, ${y + (1 - arrive) * 26}px) scale(${scale})`,
      opacity: arriving && morph <= 0 ? 0 : arrive,
    };
  };
  const content = (piece: Piece): number =>
    Math.min(Math.max(built(piece) - 1, 0), 1);
  const market = (
    m: Market,
    piece: "btc" | "gold" | "stock",
  ): React.ReactNode => {
    const shown = content(piece);
    return (
      <div key={m.slug} style={{ ...place(piece) }}>
        {shown <= 0 ? (
          <div style={{ ...card, borderRadius: 18, padding: 19 }}>
            <Skeleton frame={frame} style={{ width: 90, height: 14 }} />
            <Skeleton
              frame={frame}
              style={{ width: 130, height: 26, marginTop: 12 }}
            />
            <Skeleton
              frame={frame}
              style={{ width: "100%", height: 44, marginTop: 30 }}
            />
          </div>
        ) : (
          <MarketCard
            market={piece === "btc" ? { ...m, price } : m}
            wide
            copy={`desk${copy}`}
            drawn={Math.min(Math.max((since - 4) / 22, 0), 1)}
            stated={pop(
              frame,
              alive + 24 + (piece === "btc" ? 0 : piece === "gold" ? 3 : 6),
            )}
            style={{ height: "100%", boxSizing: "border-box", opacity: shown }}
          />
        )}
      </div>
    );
  };

  // On the phone the places are a capsule at the foot: the sidebar becomes it where it
  // stands, at its own foot, and then goes across.
  const gone = towards?.("side") ?? 0;
  const foot = (AT.side.h - 56 * (AT.side.w / 350)) * (1 - gone);

  return (
    <>
      <div style={place("side")}>
        <div style={{ height: "100%", opacity: 1 - capsule }}>
          <Sidebar logo={logo} />
        </div>
        {capsule > 0 && (
          <div
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              width: 350,
              translate: `0 ${foot}px`,
              transformOrigin: "0 0",
              scale: AT.side.w / 350,
              opacity: capsule,
            }}
          >
            <TabBar here="Home" />
          </div>
        )}
      </div>

      <div style={{ ...place("title"), ...base }}>
        <span
          style={{
            fontSize: 38,
            fontWeight: 700,
            letterSpacing: "-0.04em",
            lineHeight: 1.3,
          }}
        >
          Home
        </span>
      </div>

      {/* Home shows the example portfolio, and says so, as the app does. */}
      <div style={{ ...place("note"), ...base, ...label, textAlign: "right" }}>
        Example portfolio
      </div>

      <div style={place("worth")}>
        <div style={{ ...card, padding: "26px 28px" }}>
          <TopEdge />
          <span style={label}>Your portfolio</span>
          <Resolve
            by={content("worth")}
            frame={frame}
            shape={{ width: 190, height: 46 }}
          >
            <span
              style={{
                ...num,
                display: "block",
                fontSize: 50,
                fontWeight: 700,
                lineHeight: 1.1,
                letterSpacing: "-0.04em",
              }}
            >
              <Ticker
                value={portfolio.value * Math.min(Math.max(since / 16, 0), 1)}
                prefix="$"
              />
            </span>
          </Resolve>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              marginTop: 4,
              opacity: content("worth"),
            }}
          >
            <Pop by={pop(frame, alive + 14)} origin="0 50%">
              <span
                style={{
                  padding: "1px 9px",
                  borderRadius: 999,
                  fontSize: 12,
                  fontWeight: 600,
                  textTransform: "capitalize",
                  color: LEVEL[portfolio.riskLevel],
                  background: fade(LEVEL[portfolio.riskLevel], 0.14),
                }}
              >
                {portfolio.riskLevel} risk
              </span>
            </Pop>
            <span style={{ ...num, fontSize: 14, color: C.muted }}>
              ±{formatMoney(portfolio.typicalDay)} on a typical day
            </span>
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 11,
              marginTop: 18,
              opacity: content("worth"),
            }}
          >
            {ACTIONS.map(([name, icon]) => {
              return (
                <span
                  key={name}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    height: 46,
                    padding: "0 10px",
                    borderRadius: 14,
                    border: `1px solid ${C.line}`,
                    background: "rgba(255,255,255,0.025)",
                    fontSize: 14,
                    fontWeight: 600,
                  }}
                >
                  <span
                    style={{
                      display: "flex",
                      width: 30,
                      height: 30,
                      alignItems: "center",
                      justifyContent: "center",
                      borderRadius: 9,
                      border: `1px solid ${C.line}`,
                      background: "rgba(255,255,255,0.04)",
                    }}
                  >
                    <Stroke>{icon}</Stroke>
                  </span>
                  {name}
                </span>
              );
            })}
          </div>
        </div>
      </div>

      <div style={place("todo")}>
        <div style={{ ...card, padding: "26px 28px" }}>
          <TopEdge />
          <span style={label}>What to do now</span>
          <Resolve
            by={content("todo")}
            frame={frame}
            shape={{ width: 230, height: 22 }}
          >
            <span
              style={{
                display: "block",
                fontSize: 18,
                fontWeight: 600,
                margin: "4px 0 14px",
                letterSpacing: "-0.02em",
              }}
            >
              Buy {formatMoney(portfolio.step.amount)} of {portfolio.step.name}
            </span>
          </Resolve>
          <div style={{ opacity: content("todo") }}>
            <Ladder rungs={portfolio.step.rungs} />
            <span
              style={{
                display: "block",
                marginTop: 14,
                fontSize: 14,
                color: C.muted,
              }}
            >
              See every price and the reasons
            </span>
          </div>
        </div>
      </div>

      <div style={{ ...place("markets"), ...base }}>
        <span style={{ fontSize: 16, fontWeight: 600 }}>Markets</span>
      </div>
      {market(markets[0], "btc")}
      {market(markets[1], "gold")}
      {market(markets[2], "stock")}

      <div style={place("coming")}>
        <div style={{ ...card, padding: "22px 28px" }}>
          <TopEdge />
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginBottom: 8,
            }}
          >
            <span style={{ fontSize: 16, fontWeight: 600 }}>Coming up</span>
            <span style={{ fontSize: 14, color: C.muted }}>Calendar</span>
          </div>
          <div style={{ opacity: coming }}>
            {calendar.slice(0, 3).map((event, i) => (
              <Resolve
                key={event.at}
                by={content("coming")}
                frame={frame}
                shape={{ height: 16, top: 12 }}
              >
                <span
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "10px 0",
                    borderTop: i ? `1px solid ${C.line}` : undefined,
                    fontSize: 14,
                  }}
                >
                  <span style={{ fontWeight: 600 }}>{event.name}</span>
                  <span style={{ ...num, color: C.muted }}>
                    In {event.days} days
                  </span>
                </span>
              </Resolve>
            ))}
          </div>
        </div>
      </div>

      <div style={place("signals")}>
        <div style={{ ...card, padding: "22px 28px" }}>
          <TopEdge />
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginBottom: 8,
            }}
          >
            <span style={{ fontSize: 16, fontWeight: 600 }}>
              Latest signals
            </span>
            <span style={{ fontSize: 14, color: C.muted }}>See all</span>
          </div>
          {signals.map((signal, i) => (
            <Resolve
              key={signal.day}
              by={content("signals")}
              frame={frame}
              shape={{ height: 16, top: 12 }}
            >
              <span
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "10px 0",
                  borderTop: i ? `1px solid ${C.line}` : undefined,
                  fontSize: 14,
                }}
              >
                <Swatch tone={signal.tone} size={8} />
                <span style={{ fontWeight: 600 }}>
                  {signal.name} · {signal.what}
                </span>
                <span style={{ ...num, marginLeft: "auto", color: C.muted }}>
                  {day(signal.day)}
                </span>
              </span>
            </Resolve>
          ))}
        </div>
      </div>
    </>
  );
};
