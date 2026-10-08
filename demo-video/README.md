# RADAR film

A Remotion project for RADAR's advertisement. No film is built yet: earlier attempts
were removed on 2026-10-08 so that the next one starts clean.

## What is here

| Where | What |
| --- | --- |
| `src/Capture.tsx` | Photographs a page of the running app at phone size |
| `public/ui/` | Pages photographed that way: Markets, the Bitcoin chart, the price range ahead, Calendar. Market data only, nothing personal |

## Photographing a page

The app must be running on http://localhost:8080.

```bash
cd demo-video
printf '{"path":"asset/btc-usd"}' > props.json
npx remotion still Capture public/ui/bitcoin.png --props=props.json --scale=3
```

The repository is public: never photograph a page that shows real holdings.
