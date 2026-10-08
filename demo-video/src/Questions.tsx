import { ASKED } from "./Beat";
import fall from "./fixtures/fall.json";
import * as Cal from "./shots/Calendar";
import { SHRINKS } from "./shots/Meet";
import { WORDS } from "./shots/Question";
import { C } from "./theme";
import { COPY, shot } from "./timing";
import { Ask } from "./Type";

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
};

/** The day's fall as the film says it: one decimal, from the market's own figure. */
const FELL = Math.abs(fall.move * 100).toFixed(1);

/** Shot 1's words. They are swept away with its picture. */
export const Opening: React.FC = () => (
  <>
    <Ask
      lines={[COPY.question.fell.replace("{fall}", FELL)]}
      at={at.question + 6}
      accent={C.alert}
      middle={210}
    />
    <Ask
      lines={[COPY.question.what]}
      at={at.question + WORDS[0]}
      // A word a beat: each one knocks the coin (shots/Question).
      wordsAt={[WORDS[0], WORDS[1], WORDS[2], WORDS[2] + 3].map(
        (w) => at.question + w,
      )}
      size={140}
      middle={400}
    />
  </>
);

/**
 * Every other word in the film before the end card, on the film's own clock. A question
 * arrives on its shot's first beat, docks as its answer opens, and leaves, upwards, as
 * the next one arrives.
 */
export const Questions: React.FC = () => (
  <>
    <Ask
      lines={[COPY.meet]}
      at={at.meet + 22}
      out={at.meet + SHRINKS - 2}
      middle={850}
    />
    <Ask
      lines={[COPY.why]}
      at={at.why}
      dock={at.why + ASKED}
      out={at.level - 8}
    />
    <Ask
      lines={["Is this price", "*high or low?*"]}
      at={at.level}
      dock={at.level + ASKED}
      out={at.range - 8}
    />
    <Ask
      lines={[COPY.range]}
      at={at.range}
      dock={at.range + ASKED}
      out={at.risk - 8}
    />
    <Ask
      lines={[COPY.risk]}
      at={at.risk}
      dock={at.risk + ASKED}
      out={at.plan - 8}
    />
    <Ask
      lines={[COPY.plan.line]}
      at={at.plan}
      dock={at.plan + ASKED}
      out={at.calendar - 8}
    />
    <Ask
      lines={[COPY.calendar]}
      at={at.calendar}
      dock={at.calendar + Cal.ASKED}
      out={at.both - 6}
    />
    <Ask
      lines={["On your desk.", "On your *phone.*"]}
      // Once Home has started across to the phone and the left of the frame is clear.
      at={at.both + 9}
      size={140}
      centre={620}
      middle={520}
    />
  </>
);
