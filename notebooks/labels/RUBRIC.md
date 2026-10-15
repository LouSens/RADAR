# Headline tone: labelling rubric (version 2)

Every headline gets exactly one of three labels. The numbers are the class ids the model
uses; they follow the order of `ProsusAI/finbert`'s own output head, so the base model's
predictions and ours line up without remapping.

| id | label | meaning |
|---|---|---|
| 0 | positive | An investor holding the headline's main subject would read it as good news for its price |
| 1 | negative | The same investor would read it as bad news for its price |
| 2 | neutral | No clear effect on price, or no way to tell from the headline alone |

You see the headline only (no summary, no ticker). Judge the headline as written, not
what you know happened afterwards.

## 1. Whose price

The **main subject** is the asset, company, fund or market the headline is about: usually
the grammatical subject or the name in front. "Nvidia beats estimates" is about Nvidia;
"Fed raises rates" is about the market as a whole (rate rises read as negative for
stocks and gold unless the headline says markets cheered).

## 2. Facts against opinion (factuality vs bias)

Label **reported facts and events** by their likely effect on price:

- results above or below estimates, guidance raised or cut, dividends started or cut;
- an analyst **action**: upgrade, downgrade, price target raised or lowered. These are
  facts about the analyst, and they move prices;
- deals, approvals, lawsuits, fines, hacks, bankruptcies, layoffs, recalls;
- a price move the headline reports ("Bitcoin falls 8%", "Gold hits record high").

Label **opinion, promotion and speculation** neutral unless it reports one of the facts above:

- questions ("Is Bitcoin about to crash?", "Should you buy Apple?");
- lists and listicles ("3 stocks to buy now", "Top movers");
- predictions and could/may/might hype ("XRP could soar 500%", "Analyst says gold may hit $5,000");
- calls by unnamed or promotional sources, and sponsored content.

A named, sourced **forecast change** (a bank raising its year-end target) is an analyst
action: label it. A bare prediction is opinion: neutral.

## 3. The contrast rule

When a headline joins two clauses with *but, despite, even as, while, although, though,
yet, however*, the label follows the **main clause**: the one the headline is reporting.

- "Apple shares rise despite weak iPhone sales" → positive (the price rose).
- "Bitcoin slips even as ETF inflows hit a record" → negative.
- "Profit beats, but guidance disappoints" → follow what the headline leads with **and**
  what it reports about price if it does; if both halves carry equal weight and no price
  move is given → neutral.

## 4. Market impact

- A **reported price move** decides the label even when the reason is neutral:
  "Stocks fall as traders await jobs data" → negative.
- **Scheduled or routine notices** are neutral: "to report earnings on Thursday",
  "announces conference call", "files 10-Q", "ex-dividend date".
- **Market statistics with no direction** are neutral: volume reports, "X Bitcoin moved
  between wallets", unusual-options-activity lists, short-interest tables.
- **Sector or peer news** is labelled for the headline's own main subject, not for a
  stock it might affect indirectly.
- Size matters only for sign: "edges up 0.1%" is still positive.

## 5. When in doubt

Choose **neutral**. A wrong polar label (positive for a negative headline) is the costly
mistake; a neutral for a weakly polar headline is a small one.

## Output format

One line per headline: `<article_id>,<id>` where id is 0, 1 or 2. Nothing else.
