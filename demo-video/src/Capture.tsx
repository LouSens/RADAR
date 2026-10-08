import { useEffect, useState } from "react";
import { AbsoluteFill, continueRender, delayRender, IFrame } from "remotion";

/**
 * A still of one page of the app, used only to photograph the interface for the film:
 * `Capture` at phone size, `Desk` at 1440 by 900 (render at twice the scale). The app
 * photographed is the one fed by the mock API (mock-api/server.mjs) on localhost:5180,
 * never the one that shows an account: see scripts/capture.mjs.
 */
export const Capture: React.FC<{
  readonly path: string;
  readonly base?: string;
}> = ({ path, base = "http://localhost:5180" }) => {
  // The page fetches its data after it loads, so give it time to finish drawing.
  const [handle] = useState(() =>
    delayRender("Letting the page load its data", {
      timeoutInMilliseconds: 40000,
    }),
  );
  useEffect(() => {
    const timer = setTimeout(() => continueRender(handle), 14000);
    return () => clearTimeout(timer);
  }, [handle]);

  return (
    <AbsoluteFill style={{ backgroundColor: "#090a0e" }}>
      <IFrame
        src={`${base}/${path}`}
        style={{ width: "100%", height: "100%", border: "none" }}
      />
    </AbsoluteFill>
  );
};
