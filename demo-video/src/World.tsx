import { AbsoluteFill, Img, staticFile, useCurrentFrame } from "remotion";
import { C, fade } from "./theme";
import { EASE, EASE_IN_OUT, shot, tween } from "./timing";

/**
 * The film's one world: the app itself. Every page is a still of the real interface,
 * photographed with example data (scripts/capture.mjs), on a pane of glass. The camera
 * goes from Home into the card a person would click, which opens the page that answers
 * the question, and back out again. Nothing here is cut: a page is always reached
 * through the card that leads to it.
 */

export type PageId =
  | "home"
  | "bitcoin"
  | "moves"
  | "check"
  | "range"
  | "risk"
  | "todo"
  | "calendar";

/** A rectangle, in the page's own pixels (1440 by 900) or in the frame's. */
export interface Rect {
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
}

/** Where a page is drawn: its scale, and where its top left corner is in the frame. */
interface Place {
  readonly s: number;
  readonly x: number;
  readonly y: number;
}

export const PAGE = { w: 1440, h: 900 } as const;

/** The frame below a docked question: a page at rest is fitted into this. */
const BELOW: Rect = { x: 128, y: 230, w: 1664, h: 800 };

/** The part of each page the camera rests on, and the room it is given in the frame. */
const REST: Readonly<Record<PageId, { view: Rect; room?: Rect }>> = {
  home: { view: { x: 0, y: 0, w: 1440, h: 810 }, room: { x: 0, y: 0, w: 1920, h: 1080 } },
  bitcoin: { view: { x: 292, y: 150, w: 1120, h: 560 } },
  moves: { view: { x: 292, y: 150, w: 1120, h: 560 } },
  // Its question stands on two lines, so the page starts lower.
  check: { view: { x: 292, y: 160, w: 1120, h: 480 }, room: { x: 128, y: 320, w: 1664, h: 700 } },
  range: { view: { x: 292, y: 150, w: 1120, h: 560 } },
  risk: { view: { x: 292, y: 150, w: 740, h: 330 } },
  // Room is left at the foot for the small line.
  todo: { view: { x: 292, y: 160, w: 880, h: 500 }, room: { x: 128, y: 215, w: 1664, h: 725 } },
  calendar: { view: { x: 292, y: 96, w: 1120, h: 560 } },
};

/** The cards on Home, and the one place on Bitcoin's page, that lead somewhere. */
const CARD = {
  bitcoin: { x: 292, y: 480, w: 362, h: 191 },
  check: { x: 618, y: 259, w: 288, h: 58 },
  risk: { x: 321, y: 259, w: 288, h: 58 },
  todo: { x: 959, y: 108, w: 453, h: 304 },
  calendar: { x: 292, y: 705, w: 453, h: 195 },
  // Bitcoin's page lists its pages below the fold: the camera goes on down into it.
  onward: { x: 292, y: 548, w: 1120, h: 352 },
} as const satisfies Record<string, Rect>;

const rest = (page: PageId): Place => {
  const { view, room = BELOW } = REST[page];
  const s = Math.min(room.w / view.w, room.h / view.h);
  return {
    s,
    x: room.x + (room.w - view.w * s) / 2 - view.x * s,
    y: room.y - view.y * s,
  };
};

/** How long the camera takes to go into a card, or back out of one. */
export const DIVE = 18;

/** One move of the camera: into `card` on page `from` to reach `to`, or back out. */
interface Leg {
  readonly at: number;
  readonly kind: "dive" | "pull";
  /** The page the camera leaves, and the one it arrives on. */
  readonly from: PageId;
  readonly to: PageId;
  /** The card, on whichever of the two pages is the outer one. */
  readonly card: Rect;
}

const start = {
  meet: shot("meet").from,
  why: shot("why").from,
  level: shot("level").from,
  range: shot("range").from,
  risk: shot("risk").from,
  plan: shot("plan").from,
  calendar: shot("calendar").from,
  both: shot("both").from,
  close: shot("close").from,
};

/** A question stands in the middle this long before it docks and the camera dives. */
export const ASKED = 20;
/** Bitcoin's own page is passed through: this long after the first dive begins. */
const ONWARD = DIVE + 8;

/**
 * The whole journey. A new question arrives as the camera pulls back to Home; the
 * question docks as the camera dives into the card that answers it.
 */
export const LEGS: readonly Leg[] = [
  { at: start.why + ASKED, kind: "dive", from: "home", to: "bitcoin", card: CARD.bitcoin },
  { at: start.why + ASKED + ONWARD, kind: "dive", from: "bitcoin", to: "moves", card: CARD.onward },
  { at: start.level - 2, kind: "pull", from: "moves", to: "home", card: CARD.bitcoin },
  { at: start.level + ASKED, kind: "dive", from: "home", to: "check", card: CARD.check },
  // Shots 5 and 6 are acted out by objects (shots/Range, shots/Risk): the pages give way
  // to them, and Home is there again when they are over.
  { at: start.range - 2, kind: "pull", from: "check", to: "home", card: CARD.check },
  { at: start.plan + ASKED, kind: "dive", from: "home", to: "todo", card: CARD.todo },
  { at: start.calendar - 2, kind: "pull", from: "todo", to: "home", card: CARD.todo },
  { at: start.calendar + 14, kind: "dive", from: "home", to: "calendar", card: CARD.calendar },
  { at: start.both - 2, kind: "pull", from: "calendar", to: "home", card: CARD.calendar },
];

/** The frame a dive into `page` is over, for whoever needs to land something on it. */
export const landed = (page: PageId): number => {
  const leg = LEGS.find((l) => l.kind === "dive" && l.to === page);
  if (!leg) {
    throw new Error(`The camera never dives into ${page}`);
  }
  return leg.at + DIVE;
};

const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

interface Drawn {
  readonly page: PageId;
  readonly place: Place;
  readonly opacity: number;
}

/**
 * Both pages of a move, `t` of the way in (0 on the outer page, 1 on the inner one).
 * The inner page starts exactly on the card and grows to its place; the outer page is
 * carried along so that its card stays under the inner page all the way.
 */
const through = (outer: PageId, inner: PageId, card: Rect, t: number): Drawn[] => {
  const a = rest(outer);
  const b = rest(inner);
  const s = a.s * (card.w / PAGE.w) * (b.s / (a.s * (card.w / PAGE.w))) ** t;
  const x = mix(a.x + card.x * a.s, b.x, t);
  const y = mix(a.y + card.y * a.s, b.y, t);
  const outerScale = (s * PAGE.w) / card.w;
  return [
    {
      page: outer,
      place: { s: outerScale, x: x - card.x * outerScale, y: y - card.y * outerScale },
      opacity: 1 - tween(t, 0.3, 0.7, 0, 1, (v) => v),
    },
    { page: inner, place: { s, x, y }, opacity: tween(t, 0.15, 0.55, 0, 1, (v) => v) },
  ];
};

/** Where Home's logo is, on its page: the mark of shot 2 lands on it. */
export const LOGO = { x: 47.5, y: 47, size: 30 } as const;
/** The mark on screen when shot 2 opens (three/Mark in shots/Meet): the centre and width
 * of the square the logo is drawn in, measured from a still. */
export const MARK_ON_SCREEN = { x: 944, y: 404, size: 499 } as const;
/** When the camera pulls back from the mark to the whole of Home, in film frames. */
export const REVEAL = [start.meet + 45, start.meet + 80] as const;

/** Home during shot 2: from so close that its logo is the mark, out to the whole page. */
const homeAt = (frame: number): Place => {
  const wide = rest("home");
  const t = tween(frame, REVEAL[0], REVEAL[1], 0, 1, EASE_IN_OUT);
  const close = MARK_ON_SCREEN.size / LOGO.size;
  const s = close * (wide.s / close) ** t;
  // The logo's centre travels in a straight line from the mark's centre to its own.
  const lx = mix(MARK_ON_SCREEN.x, wide.x + LOGO.x * wide.s, t);
  const ly = mix(MARK_ON_SCREEN.y, wide.y + LOGO.y * wide.s, t);
  return { s, x: lx - LOGO.x * s, y: ly - LOGO.y * s };
};

/** Every page on screen at a frame of the film, the farther one first. */
export const drawnAt = (frame: number): Drawn[] => {
  let leg: Leg | undefined;
  for (const candidate of LEGS) {
    if (candidate.at <= frame) {
      leg = candidate;
    }
  }
  if (!leg) {
    return frame < REVEAL[0]
      ? []
      : [
          {
            page: "home",
            place: homeAt(frame),
            opacity: tween(frame, REVEAL[0], REVEAL[0] + 12, 0, 1, (v) => v),
          },
        ];
  }
  const t = tween(frame, leg.at, leg.at + DIVE, 0, 1, EASE_IN_OUT);
  if (t >= 1) {
    return [{ page: leg.to, place: rest(leg.to), opacity: 1 }];
  }
  return leg.kind === "dive"
    ? through(leg.from, leg.to, leg.card, t)
    : through(leg.to, leg.from, leg.card, 1 - t);
};

/** Where a point of a page is in the frame, if that page is on screen. */
export const onScreen = (
  frame: number,
  page: PageId,
  x: number,
  y: number,
): { x: number; y: number; s: number } | undefined => {
  const found = drawnAt(frame).find((d) => d.page === page);
  return found
    ? { x: found.place.x + x * found.place.s, y: found.place.y + y * found.place.s, s: found.place.s }
    : undefined;
};

/**
 * How far the whole pane is turned away from us: 1 while the dashboard is shown off as
 * an object (shots 2 and 9), 0 whenever a page is being read.
 */
const turnAt = (frame: number): number =>
  tween(frame, REVEAL[0] + 18, REVEAL[1] + 14, 0, 1, EASE_IN_OUT) *
    (1 - tween(frame, start.why - 4, start.why + 14, 0, 1, EASE_IN_OUT)) +
  tween(frame, start.both, start.both + 20, 0, 1, EASE_IN_OUT);

/** How much the page is dimmed while a question stands in the middle of the frame. */
const dimAt = (frame: number): number =>
  [start.why, start.level, start.plan, start.calendar].reduce(
    (most, at) =>
      Math.max(
        most,
        tween(frame, at - 2, at + 6, 0, 1, (v) => v) *
          (1 - tween(frame, at + (at === start.calendar ? 14 : ASKED), at + ASKED + 14, 0, 1, (v) => v)),
      ),
    0,
  ) + 0.4 * tween(frame, start.both, start.both + 12, 0, 1, (v) => v);

const Pane: React.FC<Drawn> = ({ page, place, opacity }) => (
  <div
    style={{
      position: "absolute",
      left: 0,
      top: 0,
      width: PAGE.w,
      height: PAGE.h,
      transformOrigin: "0 0",
      transform: `translate(${place.x}px, ${place.y}px) scale(${place.s})`,
      opacity,
      borderRadius: 14,
      overflow: "hidden",
      // A plain window: a hairline of light round the glass, and its shadow.
      boxShadow: `0 0 0 1px ${fade("#ffffff", 0.1)}, 0 30px 80px rgba(0, 0, 0, 0.55)`,
      backgroundColor: C.bg,
    }}
  >
    <Img
      src={staticFile(`desk/${page}.png`)}
      style={{ width: PAGE.w, height: PAGE.h, display: "block" }}
    />
  </div>
);

/** A phone showing the same Home, standing in front of the desk (shot 9). */
const PhoneInFront: React.FC<{ readonly frame: number }> = ({ frame }) => {
  const since = frame - start.both;
  if (since < 6) {
    return null;
  }
  const up = tween(since, 6, 28, 1, 0, EASE);
  return (
    <div
      style={{
        position: "absolute",
        left: 1340,
        top: 270 + up * 900,
        width: 366,
        height: 792,
        rotate: `${3 - up * 8}deg`,
        borderRadius: 54,
        padding: 9,
        background: "linear-gradient(160deg, #3a3d46, #17181d 40%, #2a2c33)",
        boxShadow: "0 40px 90px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(255, 255, 255, 0.14)",
      }}
    >
      <Img
        src={staticFile("desk/home-phone.png")}
        style={{ width: "100%", height: "100%", borderRadius: 46, display: "block" }}
      />
    </div>
  );
};

/** One ring of the radar, spreading from the figure that answers the question. */
export interface PingAt {
  readonly at: number;
  readonly page: PageId;
  readonly x: number;
  readonly y: number;
}

/** How long a ping takes to spread and go. */
export const PING = 20;

/**
 * The ring itself, spreading from a point of the frame, `since` frames after it starts.
 * The 3D shots use it too, with the point their own camera puts the answer at.
 */
export const Ring: React.FC<{
  readonly since: number;
  readonly x: number;
  readonly y: number;
  readonly reach?: number;
}> = ({ since, x, y, reach = 150 }) => {
  if (since < 0 || since > PING) {
    return null;
  }
  const spread = tween(since, 0, PING, 0, 1, EASE);
  return (
    <>
      {[1, 0.55].map((part) => {
        const r = 14 + spread * reach * part;
        return (
          <div
            key={part}
            style={{
              position: "absolute",
              left: x - r,
              top: y - r,
              width: r * 2,
              height: r * 2,
              borderRadius: "50%",
              border: `${4 * part + 1.5}px solid ${C.accent}`,
              boxShadow: `0 0 28px ${fade(C.accent, 0.6)}, inset 0 0 28px ${fade(C.accent, 0.3)}`,
              opacity: 1 - spread * spread,
            }}
          />
        );
      })}
    </>
  );
};

const Ping: React.FC<{ readonly ping: PingAt; readonly frame: number }> = ({
  ping,
  frame,
}) => {
  const point = onScreen(frame, ping.page, ping.x, ping.y);
  return point ? (
    <Ring since={frame - ping.at} x={point.x} y={point.y} />
  ) : null;
};

export const World: React.FC<{ readonly pings: readonly PingAt[] }> = ({ pings }) => {
  const frame = useCurrentFrame();
  const drawn = drawnAt(frame);
  const present =
    1 -
    tween(frame, start.range - 6, start.range, 0, 1, (v) => v) +
    tween(frame, start.plan - 4, start.plan + 2, 0, 1, (v) => v);
  if (drawn.length === 0 || present <= 0) {
    return null;
  }
  const turn = turnAt(frame);
  // A page being read gives up the top of the frame to its question: it is veiled above
  // the place it rests at, so the question never has the page's own title behind it.
  const inner = drawn[drawn.length - 1];
  const hidden = inner && inner.page !== "home" ? inner.opacity : 0;
  const edge = inner ? (REST[inner.page].room ?? BELOW).y : 0;
  const veil = `linear-gradient(to bottom, rgba(0,0,0,${1 - hidden}) ${edge - 44}px, #000 ${edge - 4}px)`;
  // Turned, the pane drifts a little the whole time, so a held dashboard is never dead.
  // In shot 9 the desk sits lower, under its line of words.
  const both = tween(frame, start.both, start.both + 20, 0, 1, EASE_IN_OUT);
  const drift = Math.sin((frame - start.meet) / 46);
  return (
    <AbsoluteFill style={{ perspective: 2600, opacity: present }}>
      <AbsoluteFill
        style={{
          transform: `translateY(${both * 120}px) scale(${1 - 0.1 * turn - 0.06 * both}) rotateY(${turn * (-9 + drift * 2.5)}deg) rotateX(${turn * (4.5 + drift)}deg)`,
          transformOrigin: "50% 46%",
        }}
      >
        <AbsoluteFill style={{ maskImage: veil, WebkitMaskImage: veil }}>
          {drawn.map((pane) => (
            <Pane key={pane.page} {...pane} />
          ))}
        </AbsoluteFill>
        {pings.map((ping) => (
          <Ping key={ping.at} ping={ping} frame={frame} />
        ))}
      </AbsoluteFill>
      <AbsoluteFill style={{ backgroundColor: fade(C.bg, 0.72), opacity: Math.min(dimAt(frame), 1) }} />
      <PhoneInFront frame={frame} />
    </AbsoluteFill>
  );
};
