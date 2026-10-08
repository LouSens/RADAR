import fall from "./fixtures/fall.json";
import { C } from "./theme";
import { COPY, shot } from "./timing";
import { Ask, MARGIN, Small } from "./Type";
import { ASKED, type PingAt, landed } from "./World";

const at = {
  question: shot("question").from,
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

/** The day's fall as the film says it: one decimal, from the market's own figure. */
const FELL = Math.abs(fall.move * 100).toFixed(1);

/**
 * Every word in the film before the end card, on the film's own clock. A question
 * arrives on its shot's first beat and leaves, upwards, as the next one arrives.
 */
export const Questions: React.FC = () => (
  <>
    <Ask
      lines={[COPY.question.fell.replace("{fall}", FELL)]}
      at={at.question + 6}
      out={at.meet - 9}
      accent={C.alert}
      middle={210}
    />
    <Ask
      lines={[COPY.question.what]}
      at={at.question + 45}
      out={at.meet - 9}
      size={140}
      middle={400}
    />
    <Ask lines={[COPY.meet]} at={at.meet + 20} out={at.meet + 40} middle={850} />
    <Ask lines={[COPY.why]} at={at.why} dock={at.why + ASKED} out={at.level - 8} />
    <Ask
      lines={["Is this price", "*high or low?*"]}
      at={at.level}
      dock={at.level + ASKED}
      out={at.range - 8}
    />
    <Ask lines={[COPY.range]} at={at.range} dock={at.range + ASKED} out={at.risk - 8} />
    <Ask lines={[COPY.risk]} at={at.risk} dock={at.risk + ASKED} out={at.plan - 8} />
    <Ask lines={[COPY.plan.line]} at={at.plan} dock={at.plan + ASKED} out={at.calendar - 8} />
    <Small
      text={COPY.plan.small}
      at={landed("todo") + 30}
      out={at.calendar - 8}
      style={{ position: "absolute", left: MARGIN, top: 958 }}
    />
    <Ask lines={[COPY.calendar]} at={at.calendar} dock={at.calendar + 14} out={at.both - 8} />
    <Ask
      lines={[COPY.both]}
      at={at.both}
      size={112}
      middle={128}
    />
  </>
);

/**
 * The radar's ring on the figure that answers each question, in the page's own pixels.
 * Bitcoin's day had no scheduled event and no change of state, so shot 3 has one ring.
 */
export const PINGS: readonly PingAt[] = [
  { at: landed("moves") + 16, page: "moves", x: 376, y: 373 },
  { at: landed("check") + 34, page: "check", x: 635, y: 507 },
  { at: landed("range") + 40, page: "range", x: 425, y: 428 },
  { at: landed("risk") + 45, page: "risk", x: 995, y: 301 },
  { at: landed("todo") + 40, page: "todo", x: 430, y: 324 },
  { at: landed("calendar") + 12, page: "calendar", x: 460, y: 346 },
];
