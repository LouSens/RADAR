# RADAR demo film: storyboard

A 46-second product film for RADAR, built in Remotion (`demo-video/`). It works as an ad
(sound off, captions carry it) and as the opening of a longer walkthrough.

- **Format:** 1920 × 1080, 30 fps, 1,380 frames. A 1080 × 1920 cut reuses the same scenes.
- **Audience:** someone who holds a few assets and feels behind on them; and anyone
  judging the engineering.
- **One idea:** *RADAR tells you what is true and leaves the decision to you.*
- **Tone:** calm, exact, a little dry. No hype words, no promises of return.
- **Every figure on screen is invented or is a published test result.** No real account
  appears anywhere in the film.

## Look

| Element | Choice |
|---|---|
| Background | Near-black blue `#0b0e17` with one soft light from the top left |
| Ink | `#eef0f6`; muted `#8a8fa3` |
| Accent | Teal `#1f9bb8`; calm green `#2f9e6e`; alert red `#d9534f`; gold `#c9952b`; Bitcoin orange `#e8843c` |
| Type | Inter, 700 for headlines, 500 for support. Headlines 96 to 132 px, support 44 to 52 px |
| Motion | Things arrive with a short spring and leave by fading. Nothing bounces. Numbers count up. Lines draw themselves |
| Cuts | A 12-frame fade between scenes; one hard cut, into the reveal |

## Scenes

| # | Time | On screen | Copy (headline / support) | Motion | Sound |
|---|---|---|---|---|---|
| 1 | 0:00 to 0:05 | A single price line crossing a dark frame. It drops sharply. | **Your portfolio just moved.** / Do you know why? | The line draws left to right, then falls; the frame nudges down with it. The question fades in on the fall. | Low pad; a soft thud on the drop |
| 2 | 0:05 to 0:10 | A wall of shouting labels: "BUY NOW", "100x", "SELL!", "DIP?", "MOON". | **Everyone has a call.** / We tested them. None held up. | Labels pop in at random, then a line strikes through each in turn and they dim. | Rising chatter cut dead on the last strike |
| 3 | 0:10 to 0:15 | Black. A radar sweep turns once; the chart-line mark and the word RADAR resolve from it. | **RADAR** / The analyst that never trades. | Hard cut in. One sweep of a teal arc; the mark draws; the line under it settles. | A single clean tone |
| 4 | 0:15 to 0:22 | An account card: a total, then four bars (US stocks, gold, Bitcoin, cash), each with a thin marker for the plan. | **It reads your account.** / Read-only. Every few minutes. Nothing to type. | The total counts up; the bars grow; the plan markers slide in; the short bars pulse once. | Soft ticks on each bar |
| 5 | 0:22 to 0:29 | Three steps going down a price line, each with an amount. | **It turns your plan into a list.** / What to put in, and at what price. | Steps drop in one at a time from the right; a dot travels down the line to each. | Three descending notes |
| 6 | 0:29 to 0:36 | A fan of faint paths spreading from today, with a shaded band. | **10,000 possible futures.** / So you know how bad a bad day can be. | Paths draw outward in a stagger; the band fills; a marker shows the low edge. | A swell under the paths |
| 7 | 0:36 to 0:41 | Three large counters side by side. | **Tested before trusted.** / 6 of 6 · 35 of 36 · 61% | Each counter counts up and locks with a small tick; its caption fades in beneath. | Tick, tick, tick |
| 8 | 0:41 to 0:46 | The mark, the name, the line, the address. | **You decide. RADAR shows you what is true.** / github.com/LouSens/RADAR | Everything settles to centre; the sweep passes once more behind it. | The opening pad resolves |

Captions under the counters in scene 7: "forecast of how much it moves, best of every
method tried", "loss limits that held as often as they said", "right on news tone, against 52%
before training, on 700 unseen headlines".

## Copy, alone

> Your portfolio just moved. Do you know why?
> Everyone has a call. We tested them. None held up.
> RADAR. The analyst that never trades.
> It reads your account. Read-only. Every few minutes. Nothing to type.
> It turns your plan into a list. What to put in, and at what price.
> 10,000 possible futures. So you know how bad a bad day can be.
> Tested before trusted.
> You decide. RADAR shows you what is true.

**Shorter cuts.** 15 seconds: scenes 1, 3, 5, 8. Six seconds: scene 3 with the line
"The analyst that never trades."

## Assets

The first build draws everything in code (SVG and CSS), so it renders with no outside
file. The table lists where richer assets would come from. Nothing has been downloaded:
each needs its licence checked and the user's go-ahead before it enters this public
repository.

| Asset | Used in | Source to look at | Licence to require |
|---|---|---|---|
| 3D gold bar | 4, behind the gold bar of the chart | Poly Pizza, Sketchfab (filter: downloadable, CC0) | CC0 or CC BY with credit in the film |
| 3D coin (plain, no logo) | 4, 5 | Poly Pizza, Kenney | CC0. The Bitcoin logo itself is public domain |
| 3D radar dish or sweep | 3, 8 | Built in code with `@remotion/three`; a model is optional | n/a |
| Inter | all | Google Fonts through `@remotion/google-fonts` | SIL Open Font License |
| Music bed, about 50 s, calm and steady | all | Pixabay Music, Uppbeat (free tier needs credit) | Free for commercial use; keep the licence note |
| Ticks, thud, tone | 1, 4, 5, 7 | Remotion's built-in sound effects; Freesound (CC0 filter) | CC0 |
| App screens | a longer walkthrough, not this film | Recorded from the app running on example data | Own |

3D models go in `demo-video/public/models/` as `.glb` and are loaded with
`@remotion/three` and `useGLTF`.

## What is built

`demo-video/` holds the film as a Remotion project: one composition, `RadarDemo`, made
of eight scene components, each also registered on its own so it can be opened and
edited alone. Run it with:

```
cd demo-video
npm run dev
```

Render with `npx remotion render RadarDemo out/radar-demo.mp4`.

Not in the first build: music, sound effects, voiceover, 3D models, the vertical cut.
