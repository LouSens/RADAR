import { AbsoluteFill, useCurrentFrame } from "remotion";
import {
  BAR,
  DESK_CONTENT,
  IN_WINDOW,
  PHONE_CONTENT,
  PROOFS,
  PROOF_SCREEN,
  comesForward,
  lensAt,
  pullsBack,
  type Lens,
  type Proved,
} from "./Chain";
import { HANDOVER, SCREEN } from "./DeskLayer";
import film from "./fixtures/film.json";
import { lightAt } from "./Ground";
import { C, fade } from "./theme";
import { PHONE as MODEL, Phone } from "./three/Phone";
import { Stage, type View } from "./three/Stage";
import { useLoaded } from "./three/assets";
import { COPY, EASE, HEIGHT, LAST_SWEEP, WIDTH, shot, tween } from "./timing";
import { AT, PHONE, Sidebar } from "./ui/Desk";
import {
  MarketCard,
  TabBar,
  TopEdge,
  TrustBadge,
  base,
  formatMoney,
  formatPrice,
  glass,
  label,
} from "./ui/kit";

/**
 * The devices an answer is proved on: a desktop window and the phone. As an answer
 * pulls back (Chain), the page it belongs to is drawn round it by the same move, so it
 * is seen to be a card of the app. The pages are the app's own pieces, with the example
 * portfolio; nothing here is a photograph of the app.
 */

const { portfolio, range, level, moves } = film;
const worst = moves.days[moves.days.length - 1];
const bitcoin = portfolio.holdings[0];

interface Page {
  /** Which of the app's five places the page is in, and what it is called. */
  readonly place: number;
  readonly title: string;
  readonly card: string;
  readonly headline: string;
  readonly badge?: string;
  /** The other pages listed under the card, each with what it answers. */
  readonly more: readonly (readonly [string, string])[];
}

const ABOUT_BITCOIN = [
  ["Why it moved", "What moved it, day by day"],
  ["Before you buy", "Is the price high or low"],
  ["Price range ahead", "How far it could go"],
] as const;
const ABOUT_MONEY = [
  ["My risk", "Where the risk sits"],
  ["My plan", "The mix you set"],
  ["My trades", "Your record"],
] as const;
const WHERE: Readonly<Record<string, string>> = {
  high: "The price is high right now",
  middle: "The price is in the middle right now",
  low: "The price is low right now",
};

const PAGES: Readonly<Record<Proved, Page>> = {
  why: {
    place: 1,
    title: "Bitcoin",
    card: "Why it moved",
    headline: `Down ${Math.abs(worst.move * 100).toFixed(2)}%: larger than ${Math.round((worst.rank ?? 0) * 100)} of 100 days before it`,
    badge: moves.trust,
    more: ABOUT_BITCOIN,
  },
  level: {
    place: 1,
    title: "Bitcoin",
    card: "Before you buy",
    headline: WHERE[level.where],
    more: ABOUT_BITCOIN,
  },
  range: {
    place: 1,
    title: "Bitcoin",
    card: "Price range ahead",
    headline: `${formatPrice(range.low)} to ${formatPrice(range.high)}`,
    badge: "solid",
    more: ABOUT_BITCOIN,
  },
  risk: {
    place: 2,
    title: "Portfolio",
    card: "Your money, and where the risk sits",
    headline: `Bitcoin: ${Math.round(bitcoin.money * 100)}% of your money, ${Math.round(bitcoin.risk * 100)}% of your risk`,
    more: ABOUT_MONEY,
  },
  plan: {
    place: 2,
    title: "Portfolio",
    card: "What to do now",
    headline: COPY.plan.small,
    more: ABOUT_MONEY,
  },
};
const PLACE = ["Home", "Markets", "Portfolio"] as const;

const card: React.CSSProperties = {
  ...base,
  ...glass,
  position: "absolute",
  boxSizing: "border-box",
  // A step lighter than the ground, so a card reads as a surface.
  background:
    "linear-gradient(180deg, rgba(255,255,255,0.1), rgba(255,255,255,0.045))",
};

const light = (frame: number): string =>
  `radial-gradient(110% 62% at 50% -14%, ${fade(lightAt(frame), 0.26)}, transparent 62%), ${C.bg}`;

/**
 * How the device is drawn at a moment of the proof: by the answer's own move as it
 * pulls back, and then dropping away from the camera, smaller and down and out, as the
 * answer comes out of it.
 */
const moved = (lens: Lens): React.CSSProperties => ({
  position: "absolute",
  left: 0,
  top: 0,
  width: WIDTH,
  height: HEIGHT,
  transformOrigin: "0 0",
  transform: [
    `translate(${WIDTH / 2}px, ${HEIGHT / 2 + lens.away * 520}px)`,
    `scale(${1 - 0.4 * lens.away})`,
    `translate(${-WIDTH / 2}px, ${-HEIGHT / 2}px)`,
    `translate(${lens.device.x}px, ${lens.device.y}px)`,
    `scale(${lens.device.k})`,
  ].join(" "),
  opacity:
    tween(lens.held, 0.03, 0.4, 0, 1, (t) => t) *
    (1 - tween(lens.away, 0.35, 1, 0, 1, (t) => t)),
});

/** The page's own heading and its card, with room in the card for the answer. */
const Heading: React.FC<{ readonly page: Page; readonly phone?: boolean }> = ({
  page,
  phone = false,
}) => (
  <>
    <span
      style={{
        ...base,
        position: "absolute",
        left: phone ? 16 : 292,
        top: phone ? 54 : 22,
        fontSize: phone ? 13 : 14,
        color: C.muted,
      }}
    >
      ‹ {PLACE[page.place]}
    </span>
    <span
      style={{
        ...base,
        position: "absolute",
        left: phone ? 16 : 292,
        top: phone ? 72 : 40,
        fontSize: phone ? 28 : 38,
        fontWeight: 700,
        letterSpacing: "-0.04em",
        lineHeight: 1.3,
      }}
    >
      {page.title}
    </span>
  </>
);

const Card: React.FC<{
  readonly page: Page;
  readonly box: React.CSSProperties;
  readonly phone?: boolean;
}> = ({ page, box, phone = false }) => (
  <div style={{ ...card, ...box, padding: phone ? "14px 12px" : "20px 28px" }}>
    <TopEdge />
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
        gap: 12,
      }}
    >
      <div>
        <div style={label}>{page.card}</div>
        <div
          style={{
            fontSize: phone ? 15 : 20,
            fontWeight: 600,
            letterSpacing: "-0.02em",
            lineHeight: 1.35,
          }}
        >
          {page.headline}
        </div>
      </div>
      {page.badge && !phone && <TrustBadge word={page.badge} />}
    </div>
  </div>
);

const More: React.FC<{
  readonly page: Page;
  readonly box: React.CSSProperties;
  readonly phone?: boolean;
}> = ({ page, box, phone = false }) => (
  <div
    style={{
      ...card,
      ...box,
      padding: phone ? "6px 14px" : "10px 28px",
      display: "flex",
      flexDirection: phone ? "column" : "row",
      gap: phone ? 0 : 28,
    }}
  >
    {page.more.map(([name, hint], i) => (
      <span
        key={name}
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          borderTop: phone && i ? `1px solid ${C.line}` : undefined,
          borderLeft: !phone && i ? `1px solid ${C.line}` : undefined,
          paddingLeft: !phone && i ? 28 : 0,
          opacity: name === page.card ? 1 : 0.8,
        }}
      >
        <span style={{ fontSize: phone ? 15 : 16, fontWeight: 600 }}>
          {name}
        </span>
        <span style={{ fontSize: phone ? 13 : 14, color: C.muted }}>
          {hint}
        </span>
      </span>
    ))}
  </div>
);

/** The desktop window round the answers of shots 3 and 6. */
export const Window: React.FC = () => {
  const frame = useCurrentFrame();
  const lens = lensAt(frame);
  if (!lens || PROOFS[lens.id].device !== "desk") {
    return null;
  }
  const at = PROOFS[lens.id].at;
  const page = PAGES[lens.id];
  return (
    <div style={moved(lens)}>
      <div
        style={{
          position: "absolute",
          left: at.x,
          top: at.y,
          width: at.w,
          height: at.h,
          borderRadius: 18,
          overflow: "hidden",
          background: light(frame),
          boxShadow: `0 0 0 1.5px rgba(255,255,255,0.2), 0 50px 120px -30px rgba(0,0,0,0.9)`,
        }}
      >
        <div
          style={{
            ...base,
            height: BAR,
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "0 14px",
            background: "rgba(255,255,255,0.06)",
            borderBottom: `1px solid ${C.line}`,
            fontSize: 13,
            color: C.muted,
          }}
        >
          {[0, 1, 2].map((dot) => (
            <span
              key={dot}
              style={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                background: "rgba(255,255,255,0.2)",
              }}
            />
          ))}
          <span style={{ marginLeft: 10 }}>RADAR</span>
        </div>
        <div
          style={{
            position: "absolute",
            left: 0,
            top: BAR,
            width: 1440,
            height: 810,
            transformOrigin: "0 0",
            scale: String(IN_WINDOW),
          }}
        >
          <div
            style={{
              position: "absolute",
              left: AT.side.x,
              top: AT.side.y,
              width: AT.side.w,
              height: AT.side.h,
            }}
          >
            <Sidebar here={page.place} />
          </div>
          <Heading page={page} />
          <span
            style={{
              ...base,
              ...label,
              position: "absolute",
              right: 28,
              top: 46,
            }}
          >
            {COPY.example} · {formatMoney(portfolio.value)}
          </span>
          <Card
            page={page}
            box={{
              left: 292,
              top: 108,
              width: 1120,
              height: DESK_CONTENT.y + DESK_CONTENT.h + 18 - 108,
            }}
          />
          <More
            page={page}
            box={{ left: 292, top: 636, width: 1120, height: 96 }}
          />
        </div>
      </div>
    </div>
  );
};

const both = shot("both").from;
const close = shot("close").from;

/** The lens: straight on, so that the phone's screen is a true rectangle in the frame. */
const FOV = 28;
/** The lit screen is the phone less its bezel (blender/build_assets.py). */
const LIT = { w: MODEL.width - 0.06, h: MODEL.height - 0.06 } as const;
/** How far away the phone is, for its screen to be as tall as its place in the frame. */
const PER_UNIT = SCREEN.h / LIT.h;
const FAR = HEIGHT / 2 / Math.tan((FOV * Math.PI) / 360) / PER_UNIT;
const STANDS = {
  x: (SCREEN.x + SCREEN.w / 2 - WIDTH / 2) / PER_UNIT,
  y: -(SCREEN.y + SCREEN.h / 2 - HEIGHT / 2) / PER_UNIT,
} as const;
const camera = (): View => ({
  position: [0, 0, FAR],
  target: [0, 0, 0],
  fov: FOV,
});

/** In shot 9 the phone comes up into the frame first, before anything of Home moves. */
export const SLIDES = [0, 12] as const;
/** When the phone is first wanted. It is made a little before. */
export const PHONE_FROM = pullsBack("level")[0] - 4;
/** Proving an answer, the phone stands in the middle and near: the camera is close. */
const NEARER = PROOF_SCREEN.h / SCREEN.h;
const close_ = (): View => ({
  position: [0, 0, FAR / NEARER],
  target: [0, 0, 0],
  fov: FOV,
});

/** The card above the answer's own on a phone page, which is scrolled down to it. */
const Above: React.FC<{ readonly page: Page }> = ({ page }) =>
  page.place === 1 ? (
    <MarketCard
      market={film.markets[0]}
      copy="proof"
      style={{ position: "absolute", left: 16, top: 116, width: 358 }}
    />
  ) : (
    <div
      style={{ ...card, left: 16, top: 116, width: 358, padding: "14px 12px" }}
    >
      <TopEdge />
      <div style={label}>Your portfolio</div>
      <div
        style={{
          fontSize: 30,
          fontWeight: 700,
          letterSpacing: "-0.04em",
          lineHeight: 1.2,
        }}
      >
        {formatMoney(portfolio.value)}
      </div>
      <div
        style={{ fontSize: 13, color: C.muted, textTransform: "capitalize" }}
      >
        {portfolio.riskLevel} risk · {COPY.example}
      </div>
    </div>
  );

/**
 * The phone. It proves the answers of shots 4, 5 and 7, with the answer's page on its
 * screen; and in shot 9 it comes up on the right, Home's pieces arrive on its screen
 * (DeskLayer, DeskOnPhone), its own screen takes over, and it stands clear and still
 * until the radar's line. `from` is the frame of the film this layer starts on.
 */
export const PhoneLayer: React.FC<{ readonly from: number }> = ({ from }) => {
  const frame = useCurrentFrame() + from;
  const assets = useLoaded();
  if (!assets) {
    return null;
  }
  const lens = lensAt(frame);
  const proving = lens && PROOFS[lens.id].device === "phone" ? lens : null;
  const nine = frame >= both && frame <= close + LAST_SWEEP;
  const up = tween(frame, both + SLIDES[0], both + SLIDES[1], 0, 1, EASE);
  const lit = nine ? tween(frame, HANDOVER[0], HANDOVER[1], 0, 1, (t) => t) : 0;
  const page = proving ? PAGES[proving.id] : null;
  const wrap: React.CSSProperties = proving
    ? moved(proving)
    : { position: "absolute", inset: 0, opacity: nine ? 1 : 0 };

  return (
    <AbsoluteFill>
      <div style={wrap}>
        <Stage
          room={assets.room}
          light={C.accent}
          camera={proving ? close_ : camera}
          turn={0.5}
        >
          <group
            position={
              proving ? [0, 0, 0] : [STANDS.x, STANDS.y - (1 - up) * 2.6, 0]
            }
          >
            <Phone
              object={assets.phone}
              screen={assets.screens.home}
              lit={lit}
            />
          </group>
        </Stage>
        {page && (
          <div
            style={{
              position: "absolute",
              left: PROOF_SCREEN.x,
              top: PROOF_SCREEN.y,
              width: PROOF_SCREEN.w,
              height: PROOF_SCREEN.h,
              borderRadius: 46 * NEARER,
              overflow: "hidden",
              background: light(frame),
            }}
          >
            <div
              style={{
                position: "absolute",
                left: 0,
                top: 0,
                width: PHONE.width,
                height: PHONE.height,
                transformOrigin: "0 0",
                scale: String(PROOF_SCREEN.w / PHONE.width),
              }}
            >
              <Heading page={page} phone />
              <Above page={page} />
              <Card
                page={page}
                phone
                box={{
                  left: 16,
                  top: 296,
                  width: 358,
                  height: PHONE_CONTENT.y + PHONE_CONTENT.h + 16 - 296,
                }}
              />
              <More
                page={page}
                phone
                box={{ left: 16, top: 542, width: 358, height: 192 }}
              />
              <div
                style={{ position: "absolute", left: 20, top: 772, width: 350 }}
              >
                <TabBar here={PLACE[page.place]} />
              </div>
            </div>
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};

/** When each answer has pulled back into its device, for the sound. */
export const PROVES = (Object.keys(PROOFS) as Proved[]).map(
  (id) => [pullsBack(id)[0], comesForward(id)[0]] as const,
);
