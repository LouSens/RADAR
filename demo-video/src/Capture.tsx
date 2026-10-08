import { useEffect, useState } from "react";
import { AbsoluteFill, continueRender, delayRender, IFrame } from "remotion";

/**
 * A still of one real page of the running app, at phone size. Used only to photograph
 * the interface for the film: `npx remotion still Capture --props='{"path":"markets"}'`.
 * The app must be running on localhost:8080.
 */
export const Capture: React.FC<{ readonly path: string }> = ({ path }) => {
  // The page fetches its data after it loads, so give it time to finish drawing.
  const [handle] = useState(() =>
    delayRender("Letting the page load its data", {
      timeoutInMilliseconds: 40000,
    }),
  );
  useEffect(() => {
    const timer = setTimeout(() => continueRender(handle), 9000);
    return () => clearTimeout(timer);
  }, [handle]);

  return (
    <AbsoluteFill style={{ backgroundColor: "#090a0e" }}>
      <IFrame
        src={`http://localhost:8080/${path}`}
        style={{ width: "100%", height: "100%", border: "none" }}
      />
    </AbsoluteFill>
  );
};
