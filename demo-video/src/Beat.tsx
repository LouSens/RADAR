import { useCurrentFrame } from "remotion";
import { C, fade } from "./theme";
import { EASE, EASE_IN_OUT, tween } from "./timing";
import { DOCK, Rise } from "./Type";
import { DESK, type Box } from "./ui/Desk";
import { TrustBadge, base, glass, label } from "./ui/kit";
import { Pop, pop } from "./ui/motion";

/**
 * What every answer has in common. A question lands in the middle of the frame over the
 * app's Home; the card that leads to its answer is lit and lifts; the question docks, and
 * only then does the answer open out of that card, into the frame below the question.
 * The top 200 pixels of the frame are the docked question's: nothing of an answer goes
 * there. When the next question
 * arrives the answer goes back into its card. So the film never leaves the app.
 */

/** A question stands in the middle this long before it starts for its dock. */
export const DOCKS = 14;
/** When its card opens: not before the question has finished docking. */
export const ASKED = DOCKS + DOCK;
/** How long a card takes to open out into its answer. */
export const OPENS = 14;
/** How long an answer takes to go back into its card, after its shot is over. */
export const LEAVES = 10;

/** The frame below a docked question, in the frame's own pixels. */
export const AREA: Box = { x: 128, y: 236, w: 1664, h: 776 };
/** An answer is laid out in the app's own pixels and drawn at twice the size. */
export const ZOOM = 2;

/** A box of Home, in the frame's pixels. */
export const onDesk = (box: Box): Box => ({
  x: box.x * DESK.zoom,
  y: box.y * DESK.zoom,
  w: box.w * DESK.zoom,
  h: box.h * DESK.zoom,
});

const mix = (a: number, b: number, t: number): number => a + (b - a) * t;
const between = (a: Box, b: Box, t: number): Box => ({
  x: mix(a.x, b.x, t),
  y: mix(a.y, b.y, t),
  w: mix(a.w, b.w, t),
  h: mix(a.h, b.h, t),
});

/**
 * An answer. `from` is the card of Home it opens out of (in the app's pixels) and goes
 * back into. With `card`, the card itself grows into the answer's frame and stays (card
 * expand). Without it, what grows is only a trace of the card, the data is drawn in the
 * open, and the card's edge, title and badge draw themselves round the data at `framed`
 * (build-around). Children are laid out in the app's pixels, `area` in the frame's.
 */
export const Answer: React.FC<{
  readonly duration: number;
  readonly from: Box;
  readonly area?: Box;
  readonly card?: boolean;
  /** When the edge, the title and the badge arrive. */
  readonly framed: number;
  readonly asked?: number;
  readonly title: string;
  readonly headline?: React.ReactNode;
  readonly badge?: string;
  readonly aside?: React.ReactNode;
  readonly children: React.ReactNode;
}> = ({
  duration,
  from,
  area = AREA,
  card = false,
  framed,
  asked = ASKED,
  title,
  headline,
  badge,
  aside,
  children,
}) => {
  const frame = useCurrentFrame();
  const source = onDesk(from);
  const opened = tween(frame, asked, asked + OPENS, 0, 1, EASE);
  const left = tween(
    frame,
    duration - 2,
    duration + LEAVES - 2,
    0,
    1,
    EASE_IN_OUT,
  );
  if (frame < asked - 1 || left >= 1) {
    return null;
  }
  const growing = between(source, area, opened);
  // The edge draws itself round the answer, from the top left corner, both ways.
  const edge = card
    ? opened
    : tween(frame, framed, framed + 14, 0, 1, EASE_IN_OUT);
  const body = card
    ? opened
    : tween(frame, framed + 2, framed + 14, 0, 1, (t) => t);
  // Going back into its card: the whole answer shrinks on to it and is gone.
  const k = mix(1, source.w / area.w, left);
  const shrink: React.CSSProperties = {
    position: "absolute",
    left: 0,
    top: 0,
    width: 1920,
    height: 1080,
    transformOrigin: "0 0",
    transform: `translate(${mix(0, source.x - area.x * k, left)}px, ${mix(0, source.y - area.y * k, left)}px) scale(${k})`,
    opacity: 1 - tween(left, 0.45, 1, 0, 1, (t) => t),
  };
  const radius = 40;
  return (
    <div style={shrink}>
      {/* The card opening out. As a trace it thins away as it reaches the frame. */}
      {opened < 1 && (
        <div
          style={{
            ...glass,
            position: "absolute",
            left: growing.x,
            top: growing.y,
            width: growing.w,
            height: growing.h,
            borderRadius: mix(24, radius, opened),
            opacity: card ? 1 : 1 - tween(opened, 0.35, 1, 0, 1, (t) => t),
          }}
        />
      )}
      {opened >= 1 && (
        <>
          <div
            style={{
              ...glass,
              position: "absolute",
              left: area.x,
              top: area.y,
              width: area.w,
              height: area.h,
              borderRadius: radius,
              border: "none",
              // Nearly solid: nothing of Home is read through an answer.
              background: `linear-gradient(180deg, rgba(255,255,255,0.065), rgba(255,255,255,0.022)), ${fade("#0c0e13", 0.94)}`,
              opacity: body,
            }}
          />
          <svg
            width={area.w}
            height={area.h}
            style={{
              position: "absolute",
              left: area.x,
              top: area.y,
              overflow: "visible",
            }}
          >
            <rect
              x="1"
              y="1"
              width={area.w - 2}
              height={area.h - 2}
              rx={radius}
              fill="none"
              stroke={
                edge < 1 ? fade(C.accent, 0.75) : "rgba(255,255,255,0.14)"
              }
              strokeWidth={edge < 1 ? 3 : 2}
              pathLength={1}
              strokeDasharray={`${edge} 1`}
            />
          </svg>
        </>
      )}
      {/* Placed first and enlarged inside: `zoom` would enlarge the placing as well. */}
      <div style={{ position: "absolute", left: area.x, top: area.y }}>
        <div
          style={{
            ...base,
            position: "relative",
            width: area.w / ZOOM,
            height: area.h / ZOOM,
            zoom: ZOOM,
          }}
        >
          <div
            style={{
              position: "absolute",
              left: 28,
              right: 28,
              top: 20,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
            }}
          >
            <div>
              <div style={label}>
                <Rise at={framed + 2}>{title}</Rise>
              </div>
              {headline && (
                <div
                  style={{
                    fontSize: 20,
                    fontWeight: 600,
                    letterSpacing: "-0.02em",
                    lineHeight: 1.35,
                  }}
                >
                  <Rise at={framed + 5}>{headline}</Rise>
                </div>
              )}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              {aside}
              {badge && (
                <Pop by={pop(frame, framed + 10)} origin="100% 50%">
                  <TrustBadge word={badge} />
                </Pop>
              )}
            </div>
          </div>
          {children}
        </div>
      </div>
    </div>
  );
};
