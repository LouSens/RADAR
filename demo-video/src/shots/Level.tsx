import { useCurrentFrame } from "remotion";
import { Lock, MORPH, Pulled, Smear, filmFrame, rate } from "../Chain";
import film from "../fixtures/film.json";
import { C, fade } from "../theme";
import { EASE_IN, EASE_IN_OUT, shot, tween } from "../timing";
import { Rise } from "../Type";
import { base, num } from "../ui/kit";
import { Ticker, pop, settle } from "../ui/motion";
import { Chart, LEFT, MIDDLE, RIGHT, Tip } from "./Why";

const { level } = film;
const COUNT = level.places.length;

// The five bars, in the frame's own pixels, above their question.
const TOP = 84;
const PITCH = 150;
export const THICK = 24;
/** The top of each bar's track, and where its bead comes to rest. */
export const trackY = (i: number): number => TOP + 78 + i * PITCH;
export const beadAt = (i: number): { x: number; y: number } => ({
  x: LEFT + (level.places[i].place ?? 0) * (RIGHT - LEFT),
  y: trackY(i) + THICK / 2,
});
export const BEAD = 44;
export const TRACK = "rgba(255,255,255,0.13)";

/** When the thirty bars have fallen flat, and when their line has split in five. */
const FLAT = 7;
const SPLIT = [6, MORPH] as const;
/** When the first bead sets off, and how long after it each of the others does. */
export const BEADS = 14;
export const EVERY = 4;
export const LOCKED = BEADS + (COUNT - 1) * EVERY + 16;

/** One of the app's range bars (CheckPanel.tsx), at the film's size. */
export const Track: React.FC<{
  readonly y: number;
  readonly thick?: number;
  readonly opacity?: number;
  readonly colour?: string;
}> = ({ y, thick = THICK, opacity = 1, colour = TRACK }) => (
  <span
    style={{
      position: "absolute",
      left: LEFT,
      top: y,
      width: RIGHT - LEFT,
      height: thick,
      borderRadius: 999,
      background: colour,
      opacity,
    }}
  />
);

/** The bead of a range bar: where the price sits between the lowest and the highest. */
export const Bead: React.FC<{
  readonly x: number;
  readonly y: number;
  readonly size?: number;
  readonly opacity?: number;
}> = ({ x, y, size = BEAD, opacity = 1 }) => (
  <span
    style={{
      position: "absolute",
      left: x,
      top: y,
      width: size,
      height: size,
      translate: "-50% -50%",
      borderRadius: "50%",
      background: C.accent,
      border: `5px solid ${C.bg}`,
      boxSizing: "border-box",
      boxShadow: `0 0 26px ${fade(C.accent, 0.6)}`,
      opacity,
    }}
  />
);

/**
 * Shot 4. The thirty bars of shot 3 fall flat into their line, and the line splits into
 * the app's five range bars, one for each period. A bead slides to where the price sits
 * in each: a little past it, then back. Figures: the app's "before you buy" check of
 * Bitcoin, from public prices (fixtures/film.json).
 */
export const Level: React.FC = () => {
  const frame = useCurrentFrame();
  const leaves = shot("level").duration - 8;
  const fallen = tween(frame, 0, FLAT, 0, 1, EASE_IN);
  const split = tween(frame, SPLIT[0], SPLIT[1], 0, 1, EASE_IN_OUT);

  return (
    <Pulled film={filmFrame("level", frame)}>
      {frame < FLAT + 1 && (
        <>
          <Smear y={rate(frame, 0, FLAT, EASE_IN) * 200}>
            <Chart
              grown={() => 1 - fallen}
              laid={1}
              notes={1 - tween(frame, 0, 4, 0, 1, (t) => t)}
            />
          </Smear>
          <Tip by={1 - tween(frame, 0, 4, 0, 1, EASE_IN)} />
        </>
      )}
      {/* The one line becomes five, each going to its own row and thickening. */}
      {frame >= FLAT && (
        <Smear y={rate(frame, SPLIT[0], SPLIT[1]) * 300}>
          {level.places.map((period, i) => (
            <Track
              key={period.label}
              y={MIDDLE - 2 + (trackY(i) - MIDDLE + 2) * split}
              thick={4 + (THICK - 4) * split}
              colour={split < 1 ? "rgba(255,255,255,0.3)" : TRACK}
              opacity={split < 1 ? 0.45 + 0.55 * split : 1}
            />
          ))}
        </Smear>
      )}

      {level.places.map((period, i) => {
        const at = BEADS + i * EVERY;
        // The bead overshoots its place a little and settles.
        const slid = settle(frame, at, 11);
        const rest = beadAt(i);
        const first = i === 0;
        return (
          <div key={period.label}>
            <div
              style={{
                ...base,
                position: "absolute",
                left: LEFT,
                width: RIGHT - LEFT,
                top: TOP + i * PITCH,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                fontSize: 46,
                lineHeight: 1.3,
              }}
            >
              <span style={{ fontWeight: 600 }}>
                <Rise at={10 + i * 2} out={leaves}>
                  {period.label}
                </Rise>
              </span>
              <span
                style={{
                  ...num,
                  position: "relative",
                  color: C.muted,
                  opacity: frame >= at ? 1 : 0,
                }}
              >
                <Rise at={at - 30} out={leaves}>
                  <Ticker
                    value={
                      Math.round((period.place ?? 0) * 100) *
                      tween(frame, at, at + 14, 0, 1, EASE_IN_OUT)
                    }
                    places={2}
                    style={{ color: C.ink, fontWeight: 700 }}
                  />{" "}
                  out of 100
                </Rise>
                {first && <Lock frame={frame} at={LOCKED} out={leaves} />}
              </span>
            </div>
            {frame >= at - 2 && (
              <Bead
                x={LEFT + (rest.x - LEFT) * slid}
                y={rest.y}
                size={BEAD * Math.min(pop(frame, at - 2), 1.1)}
              />
            )}
          </div>
        );
      })}
      {(["Lowest", "Highest"] as const).map((end, i) => (
        <span
          key={end}
          style={{
            ...base,
            position: "absolute",
            left: i ? undefined : LEFT,
            right: i ? 1920 - RIGHT : undefined,
            top: trackY(COUNT - 1) + THICK + 10,
            fontSize: 34,
            color: C.muted,
          }}
        >
          <Rise at={BEADS + 4} out={leaves}>
            {end}
          </Rise>
        </span>
      ))}
    </Pulled>
  );
};
