import { AbsoluteFill, useCurrentFrame } from "remotion";
import { ASKED, AREA, Answer, ZOOM } from "../Beat";
import film from "../fixtures/film.json";
import { C } from "../theme";
import { EASE_IN_OUT, shot, tween } from "../timing";
import { BUTTON } from "../ui/Desk";
import { formatPrice } from "../ui/kit";
import { Ping, RangeBar, pop, settle } from "../ui/motion";

const { level } = film;

/** When the first bead sets off, and how long after it each of the others does. */
export const BEADS = ASKED + 6;
export const EVERY = 5;
/** When the card draws itself round the bars, and when the ring spreads. */
export const FRAMED = ASKED + 36;
export const PINGED = ASKED + 46;

const TOP = 92;
const PITCH = 55;
const WORDS: Readonly<Record<string, string>> = {
  high: "The price is high right now",
  middle: "The price is in the middle right now",
  low: "The price is low right now",
};

/**
 * Shot 4. The app's five range bars, one for each period, and a bead that slides to
 * where the price sits in each: a little past it, then back. Then the app's own card
 * draws itself round them. Figures: the app's "before you buy" check of Bitcoin, from
 * public prices (fixtures/film.json).
 */
export const Level: React.FC = () => {
  const frame = useCurrentFrame();
  const duration = shot("level").duration;
  return (
    <AbsoluteFill>
      <Answer
        duration={duration}
        from={BUTTON.check}
        framed={FRAMED}
        title="Before you buy"
        headline={
          <>
            {WORDS[level.where]}
            <span style={{ color: C.muted, fontWeight: 500 }}>
              {" "}
              · {level.coin} {formatPrice(level.price)}
            </span>
          </>
        }
      >
        {level.places.map((period, i) => {
          const at = BEADS + i * EVERY;
          // The bead overshoots its place a little and settles.
          const slid = settle(frame, at, 11);
          return (
            <div
              key={period.label}
              style={{
                position: "absolute",
                left: 28,
                right: 28,
                top: TOP + i * PITCH,
                opacity: pop(frame, at - 6),
              }}
            >
              <RangeBar
                name={period.label}
                place={(period.place ?? 0) * slid}
                shown={
                  Math.round((period.place ?? 0) * 100) *
                  tween(frame, at, at + 14, 0, 1, EASE_IN_OUT)
                }
                ends={i === level.places.length - 1}
                lit={Math.min(pop(frame, at - 2), 1)}
              />
            </div>
          );
        })}
      </Answer>
      <Ping
        since={frame - PINGED}
        x={AREA.x + (28 + 36) * ZOOM}
        y={AREA.y + (TOP + PITCH + 9) * ZOOM}
      />
    </AbsoluteFill>
  );
};
