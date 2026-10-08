// Render chosen frames of the reel as PNGs, bundling once.
//
//   node scripts/stills.mjs out/look 100 112 131
//   node scripts/stills.mjs out/sheet every 30
//
// The second form renders one frame in every thirty, for a contact sheet.

import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import { mkdirSync } from "node:fs";
import path from "node:path";

const [dir, ...rest] = process.argv.slice(2);
if (!dir || rest.length === 0) {
  throw new Error("Usage: node scripts/stills.mjs <folder> <frame...> | every <n>");
}
mkdirSync(dir, { recursive: true });

const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts") });
// The 3D shots need a real graphics pipeline in the render browser.
const chromiumOptions = { gl: "angle" };
const composition = await selectComposition({
  serveUrl,
  id: "Reel",
  chromiumOptions,
});

const frames =
  rest[0] === "every"
    ? Array.from(
        { length: Math.ceil(composition.durationInFrames / Number(rest[1])) },
        (_, i) => i * Number(rest[1]),
      )
    : rest.map(Number);

for (const frame of frames) {
  const output = path.join(dir, `${String(frame).padStart(3, "0")}.png`);
  await renderStill({ composition, serveUrl, output, frame, chromiumOptions });
  console.log(output);
}
