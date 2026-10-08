import { Asked, QUESTION_FOOT, QUESTION_TOP, pullsBack } from "./Chain";
import { HANDOVER } from "./DeskLayer";
import fall from "./fixtures/fall.json";
import * as Cal from "./shots/Calendar";
import { SHRINKS } from "./shots/Meet";
import { CLEARS, WORDS } from "./shots/Question";
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
};

/** The day's fall as the film says it: one decimal, from the market's own figure. */
const FELL = Math.abs(fall.move * 100).toFixed(1);
/** A question has left by the time its answer pulls back into its card. */
const leaves = (id: Parameters<typeof pullsBack>[0]): number =>
  pullsBack(id)[0] - 8;

/** Shot 1's words. They leave for the coin to stand alone. */
export const Opening: React.FC = () => (
  <>
    <Ask
      lines={[COPY.question.fell.replace("{fall}", FELL)]}
      at={at.question + 6}
      out={at.question + CLEARS}
      accent={C.alert}
      size={150}
      middle={150}
      left
    />
    <Ask
      lines={[COPY.question.what]}
      at={at.question + WORDS[0]}
      out={at.question + CLEARS}
      // A word a beat: each one knocks the coin (shots/Question).
      wordsAt={[WORDS[0], WORDS[1], WORDS[2], WORDS[2] + 3].map(
        (w) => at.question + w,
      )}
      size={104}
      middle={296}
      left
    />
  </>
);

/**
 * Every other word in the film before the end card, on the film's own clock. A question
 * rises in the space beside its answer, above it or below it by turns, stands still,
 * and has left by the time its answer pulls back to be proved, so nothing crosses it.
 */
export const Questions: React.FC = () => (
  <>
    <Ask
      lines={[COPY.meet]}
      at={at.meet + 24}
      // It stays as the mark flies to the sidebar, and has gone before the cards come.
      out={at.meet + SHRINKS + 10}
      middle={850}
    />
    <Asked line={COPY.why} at={at.why} out={leaves("why")} top={QUESTION_TOP} />
    <Asked
      line={COPY.level}
      at={at.level + 6}
      out={leaves("level")}
      top={QUESTION_FOOT}
    />
    <Asked
      line={COPY.range}
      at={at.range + 8}
      out={leaves("range")}
      top={QUESTION_TOP}
    />
    <Asked
      line={COPY.risk}
      // Once the outcomes of shot 5 have left the foot of the frame.
      at={at.risk + 12}
      out={leaves("risk")}
      top={QUESTION_FOOT}
    />
    <Asked
      line={COPY.plan.line}
      at={at.plan + 6}
      out={leaves("plan")}
      top={QUESTION_TOP}
    />
    <Asked
      line={COPY.calendar}
      at={at.calendar + 3}
      out={at.calendar + Cal.FLIES - 6}
      top={QUESTION_FOOT}
    />
    <Ask
      lines={["On your desk.", "On your *phone.*"]}
      // As the last cards leave the left of the frame for the phone: the words are
      // rising while the phone's screen settles, so the phone is never there alone.
      at={HANDOVER[0] - 6}
      wordsAt={[0, 2, 4, 8, 10, 12].map((w) => HANDOVER[0] - 6 + w)}
      size={140}
      centre={620}
      middle={520}
    />
  </>
);
