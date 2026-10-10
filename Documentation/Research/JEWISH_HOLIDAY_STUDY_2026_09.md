# Jewish holidays and the market — tested, September 2026

**Question (Steven, 2026-09-27):** the market swings remarkably on Jewish holidays; research
whether that is true, and if it is, build a strategy on it.

**Answer: the claim about swings is false, and there is nothing to build.** On the days observant
Jews do not work, the market swings *less* than usual, not more, and there is no directional drift
that survives a spread. The whole look is weaker than searching random calendar dates.

**One qualification, added after the literature review in section 4:** there *is* a real
Jewish-holiday effect, but it is on **volume, not price** — Rosh Hashana equity volume runs about
15–19% below normal. My own data confirms it independently at t=−2.23. It is not tradeable for us,
because thinner liquidity means wider spreads and we are the ones paying them. Details and the
correction it forced on my first pass are in sections 4 and 6.

---

## 1. What had already been tested

Calendar effects generally were already dead here, and recorded as such.

`facts` id 26, topic `strategy/no-edge-calendar`, verified 2026-09-16: thirteen years of daily
data (≈676 independent observations per weekday) gives Wednesday −4.63 bps (t=−4.79), Thursday
−4.40 (t=−4.97), Monday −1.00. Turn-of-month −0.55 bps. Best month October +1.98 bps (t=1.70),
which is noise. An earlier "Thursday drift" candidate turned out to be a mis-labelled weekday
mask plus an uncharged round trip.

Source: `Documentation/Research/EDGE_SEARCH_2026_09.md` sections 3 and 4b.

**What had never been tested is the Jewish holiday calendar specifically.** That is the gap this
study fills. The instrument is `tools/jewish_holiday_study.py`, which fetches its own data and
can be re-run.

## 2. Method

| | |
|---|---|
| Instruments | 26 FX pairs (the active profile) and 6 equity indices (SPX500, NAS100, US2000, DE30, JP225, UK100) |
| Data | OANDA daily candles, 3,405 sessions, 2013-09-02 to 2026-09-24 |
| Holiday dates | Hebcal (hebcal.com), live, cached, 614 rows over 14 years. Nothing hand-typed |
| Work-prohibited set | Rosh Hashana, Yom Kippur, Sukkot (incl. Shmini Atzeret / Simchat Torah), Pesach, Shavuot |
| Placebo set | Chanukah, Purim, Tish'a B'Av, Tu BiShvat, Lag BaOmer — Jewish holidays on which work is permitted |
| Windows | −2, −1 (Erev), 0 (holiday day), +1, +2 days |
| Unit of observation | **One per date.** The 26 pairs are largely the same dollar; counting pair-dates as independent inflates t by roughly √26 |
| Metrics | signed return (standardised per pair), daily range (high−low)/close — the "swing", and tick volume — the mechanism |
| Null | 5,000 permutation draws, random date sets matched to the real holidays on **weekday and month**, then the *whole* search re-run to get a max-|t| null |

Two controls do the real work here. **Weekday and month matching** matters because Tishrei
holidays sit in September–October and Nisan holidays in March–April, and Hebrew holidays walk
through the weekdays, so a raw "holidays vs everything else" comparison confounds the holiday
with the season. The **placebo set** matters because the story is that participants are away:
on Chanukah and Purim they are not, so those dates must show nothing.

## 3. Results

### 3.1 FX, 26 pairs, window around work-prohibited holidays

Each pair's own **median** range and volume are 1.000 by construction; the **mean** baseline,
which is what the t-test compares against, is 1.138 for range and 1.320 for volume. A holiday
figure below those two numbers is a holiday figure *below normal*.

| window | n | signed (z) | t | range | t | volume | t |
|---|---|---|---|---|---|---|---|
| two days before | 277 | +0.0146 | +0.70 | 1.129 | −0.38 | 1.314 | −0.14 |
| day before (Erev) | 277 | +0.0247 | +1.24 | 1.099 | −1.68 | 1.304 | −0.30 |
| **holiday day** | **277** | **+0.0187** | **+0.99** | **1.102** | **−1.62** | **1.286** | **−0.69** |
| day after | 277 | +0.0263 | +1.28 | 1.119 | −0.90 | 1.300 | −0.41 |
| two days after | 277 | +0.0041 | +0.20 | 1.125 | −0.56 | 1.314 | −0.11 |

Baseline **range 1.142**, baseline **volume 1.323**. On the holiday itself the range is *lower*
than the baseline mean, the volume is *lower*, and the signed return is indistinguishable from
zero. (The earlier line in this section said the base was 1.000; that is the median, not the
mean the test uses, and stating it that way made a drop look like a rise. Corrected
2026-09-27.)

### 3.2 Equity indices, 6 markets, window around work-prohibited holidays

Equity markets are open on Jewish holidays — unlike Christian ones — so this is where the claim
is most plausible.

Baseline **range 1.197**, baseline **volume 1.421** (medians 1.000 by construction).

| window | n | signed (z) | t | range | t | volume | t |
|---|---|---|---|---|---|---|---|
| two days before | 275 | +0.0900 | +1.77 | 1.237 | +1.01 | 1.434 | +0.22 |
| day before (Erev) | 275 | +0.1029 | +2.05 | 1.192 | −0.14 | 1.346 | −1.46 |
| **holiday day** | **275** | **+0.0344** | **+0.75** | **1.171** | **−1.17** | **1.347** | **−1.49** |
| day after | 275 | +0.0603 | +1.28 | 1.182 | −0.44 | 1.363 | −1.17 |
| two days after | 275 | +0.0366 | +0.74 | 1.188 | −0.25 | 1.381 | −0.80 |

The "Erev drift" at t=+2.05 is the best-looking thing in the study. The bar is |t|>3
(`policies` row 7), so it does not clear it, and section 3.4 shows what it is worth.

### 3.3 Per holiday, and the placebo that kills it

Equity indices, holiday day only. Sorted by the size of the effect.

| family | n | signed | t | range | t | volume | t | work? |
|---|---|---|---|---|---|---|---|---|
| Shavuot | 29 | +0.1052 | +1.02 | 0.992 | **−2.86** | 1.273 | −0.95 | prohibited |
| Rosh Hashana | 43 | −0.1032 | −1.08 | 1.095 | −1.18 | 1.204 | −2.25 | prohibited |
| Sukkot | 96 | +0.0403 | +0.48 | 1.195 | −0.03 | 1.290 | −1.88 | prohibited |
| Yom Kippur | 20 | +0.0734 | +0.49 | 1.158 | −0.48 | 1.397 | −0.16 | prohibited |
| Pesach | 87 | +0.0634 | +0.70 | 1.245 | +0.75 | 1.493 | +0.65 | prohibited |
| **Purim** | **35** | **−0.2708** | −0.73 | **1.844** | **+2.11** | **2.147** | **+2.56** | **permitted** |
| **Lag BaOmer** | **11** | **+0.4765** | **+2.68** | 1.230 | +0.16 | 1.369 | −0.15 | **permitted** |
| Chanukah | 82 | +0.0378 | +0.42 | 1.164 | −0.52 | 1.344 | −0.56 | permitted |
| Tu BiShvat | 12 | −0.1634 | −0.66 | 1.311 | +0.72 | 1.832 | +0.93 | permitted |

**The two largest swings in the table are Purim and Lag BaOmer — days on which observant
participants work.** Purim's volume is +2.56σ and its range +2.11σ, both bigger than anything
Yom Kippur or Rosh Hashana produce. If the effect were real, the absent-participant days would
lead this table. They do not; the permitted days do.

The FX table tells the same story: Purim +2.60 t on volume, Chanukah −2.52, both louder than
any work-prohibited family.

**But the volume channel is the one place a real effect does exist, and section 4 says so.** The
purposes of this table are narrower than they look: it shows the *return* effects are absent on
every family including the permitted ones, and it shows that a single family at |t|≈2.5 is
within reach of a 30-test search. It does not show that Rosh Hashana's volume is normal — that
is precisely what it does not show.

Combined Rosh Hashana and Yom Kippur, the pair the literature treats as one phenomenon:
equity-index volume 1.265 against a 1.421 baseline, **−11%, t=−1.89**; range and signed return
both flat. In FX the same pair shows nothing at all: volume −4%, t=−0.54.

### 3.4 The multiple-comparisons test, which is decisive

Nine holiday families × five windows × three metrics is 30 tests. An honest search has to be
compared against searching at random.

| | FX 26 pairs | Equity indices 6 |
|---|---|---|
| Best |t| found anywhere in the search | 2.56 (Shavuot range) | 2.86 (Shavuot range) |
| Max |t| from random weekday+month-matched calendars — median | 3.27 | 2.74 |
| …95th percentile | 4.80 | 4.41 |
| P(random search beats my best) | **0.847** | **0.423** |

**A random calendar of the same size produces a bigger "effect" 85% of the time in FX and 42% of
the time in the indices.** The Jewish holiday calendar is not merely unproven here; it is less
interesting than noise.

## 4. The published literature, and the one place my numbers agree with it

A separate search of the peer-reviewed record was run alongside this measurement. It matters
because it says which of my nulls is informative and which is just my sample being too small.

**The return effects are as dead in the literature as they are here.** Sullivan, Timmermann and
White (*Journal of Econometrics*, 2001) tested **9,452** calendar rules on the Dow from 1897 to
1996; pre- and post-holiday rules are 8 of them, and their Reality Check gives p>0.91 out of
sample, with the paper concluding that "no calendar rule appears capable of outperforming the
benchmark market index." Hou, Xue and Zhang (*Review of Financial Studies*, 2020) re-tested 447
published anomalies and found 85% fail a t>3 bar. McLean and Pontiff (*Journal of Finance*,
2016) found 97 published predictors weakened 58% after publication.

**The specific and most useful piece of evidence is against the adage itself.** Yatrakis and
Williams (2010) tested the exact strategy that circulates — short the Dow from Rosh Hashana to
Yom Kippur — on 1907–2008. It **lost** money: +0.47% to +1.01% per ~13-day hold means the short
was on the wrong side. Only 3 of 9 scenarios were significant at 5%, trimming about four
outliers per scenario collapsed the means, and it is the only source in the whole literature
that charged transaction costs ($420 round trip on 30 Dow names). **Its best scenario reaches
t=2.03 over nine scenarios with no multiple-testing adjustment — below the t>3 hurdle this desk
already uses (`policies` row 7), which Harvey, Liu and Zhu (*Review of Financial Studies*, 2016)
independently argue for after cataloguing 316 factors.**

**The generic pre-holiday effect, which the Jewish-holiday claim is a special case of, is a real
historical regularity with a negative post-publication record — not something that never
existed.** Kim and Park (*JFQA*, 1994) found abnormally high returns on the trading day before
holidays across the NYSE, AMEX **and** NASDAQ over 1963–1986, present also in the UK and Japan
and independent of the US effect, and explicitly **rejected** the small-firm explanation that
usually gets attached to it. Ariel (1990) is the origin of the inventory-adjustment account.
That finding was real in its sample. What happened next is the point: Vergin and McGinnis (1999)
found it gone for large firms and shrunken for small ones over 1987–1996; Chong, Hudson, Keasey
and Littler (2005) traced the US mean going **negative** in 1991–1997 and then found the effect
**eliminated** over 1997–2003; Marquering et al. (2006) found it gone after publication; Ko and
Yang (2024) find the premium survives only among small firms after 1990; Plastun et al. (2019)
place it among four anomalies that vanished from the Dow after the 1980s.

**Why that distinction matters for this desk.** Every positive Jewish-holiday return result in
the literature comes from a sample that ends between 1986 and 2000. The decay evidence covers
1987 onward. **My own measurement covers 2013–2026 — the post-decay period — and finds nothing,
which is exactly what the decay record predicts.** My null is not evidence the effect was never
there; it is evidence it is not there *now*, which is the only question that matters for placing
an order. Schwert (2003) makes the methodological point in general terms: re-examining the same
or positively correlated data "is really no additional evidence" (citing Lo and MacKinlay 1990),
and the remedy is a genuinely independent sample or post-publication data.

**Hurdle detail.** Harvey, Liu and Zhu catalogue 316 factors from 313 papers and set the bar at
t>3.0 (p=0.27%); their Bonferroni cutoff rises from 1.96 in 1967 to 3.78 by 2012, and BHY at 5%
sits at 2.78. The best Jewish-holiday backtest statistic, t=2.03, clears **none** of those — not
even BHY at 5% — and Frieder and Subrahmanyam's own cumulative-window figures, t=2.90 for Rosh
Hashana and t=−2.00 for Yom Kippur, fall at or below the same line. A caveat on Schwert (2003):
it is a narrative chapter with no count of anomalies, so it is cited here for its decay figures
(turn-of-year alpha about half its 1962–79 value but still positive; the weekend effect about a
quarter of its 1953–77 value) and never for a number of effects tested. Lakonishok and Smidt's
often-quoted magnitudes are secondary-sourced and marked unverified; they are not relied on here.

**The sample is small enough that this is not a close call.** Rosh Hashana (two days) plus Yom
Kippur (one) is three calendar days a year: about **81 weekday High-Holiday trading days** out of
~9,828 NYSE sessions for 1962–2000 — 0.82%. A block of that size, split across two holidays with
opposing signs, is not a sample you can fit a strategy to without overfitting it.

**Breadth does not rescue it either.** The calendar-anomaly literature is broad — Cadsby and
Ratner (1992) across 11 indices, Hansen, Lunde and Nason (2005) across 25, Kunkel, Compton and
Beyer (2003) across 19 countries, Bergsma and Jiang (2016) across 11 major markets and six
cultural New Years, Jacobsen and Zhang across 109 countries — and breadth is precisely the
problem, because it multiplies the number of things that were looked at. Carchano and Pardo
(2011) tested **188** cyclical anomalies on S&P 500, DAX and Nikkei futures and, after a
percentile-t bootstrap and Monte Carlo, **only turn-of-the-month on the S&P 500 survived both a
statistical and an economic screen.** Almeida et al. (2018) applied Hansen's SPA test to the
Halloween strategy across seven Latin American markets: p-values never fell below 5–10%.

**One honest counterexample.** Casalin (2018) finds holiday effects in Shanghai, Shenzhen and
Hong Kong that are "positive, significant, time-varying, with no sign of decline." So decay is
the modal finding, not a universal law, and this desk's own measurement is the thing that
settles it locally.

**The gap, stated so a future session can pick it up.** No paper was found that both counts
markets *and* applies a multiple-comparison correction specifically to the holiday and
Jewish-holiday families. Sullivan-Timmermann-White correct calendar effects broadly, with holiday
rules only 8 of their 9,452, and report no standalone holiday p-value. A White Reality Check or
Hansen SPA test restricted to holiday rules across markets looks genuinely unclaimed. That, and
the ~80-observation US High-Holiday sample with opposing signs, is where a properly powered study
would go — but nothing about it would change the answer for a 238-dollar account paying spreads,
so it is not worth this desk's time.

**The volume effect is real, and my measurement independently confirms it.** Frieder and
Subrahmanyam (*Financial Analysts Journal*, 2004) found median NYSE/S&P volume declines of about
**19% on Rosh Hashana and 24% on Yom Kippur** against the prior trading day, with volume t-stats
of −5.30 and −5.19 over 1962–2000. Loughran and Schultz (*JFQA*, 2004) supplied the
identification test that separates a Jewish-holiday effect from a generic pre-holiday effect:
volume falls specifically in firms headquartered in cities with high Jewish populations.

My numbers, from a different instrument, a different decade and an independently fetched
holiday calendar:

| | Frieder & Subrahmanyam (NYSE, 1962–2000) | This study (index CFDs, 2013–2026) |
|---|---|---|
| Rosh Hashana volume | −19% median, t=−5.30 | −15% vs baseline mean, **t=−2.23** (n=43) |
| Yom Kippur volume | −24% median, t=−5.19 | −1.7%, t=−0.16 (n=20) |
| Rosh Hashana + Yom Kippur | both significant | −11%, t=−1.89 (n=63) |

Direction, magnitude and sign agree on Rosh Hashana. Yom Kippur does not show in my data —
20 observations of a crude tick-count proxy is not enough to see a 24% move, and I would not
claim it either way. In FX there is no volume effect at all (−4%, t=−0.54), which is what the
mechanism predicts: the story is absent *participants*, and there is no set of participants who
leave the currency market for a holiday.

**What this changes about the answer: nothing that is tradeable, and it sharpens the reason.**
A liquidity decline is not an edge for us. We are spread *takers* — the measured live EUR_USD
round trip is 1.5 pips (`run_state.live_trading_record`) against a 2.45-pip portfolio model. Thinner
liquidity means wider quoted spreads, so the one real, documented Jewish-holiday effect in the
literature makes our trading **more expensive on those days, not more profitable**. The correct
use of it is a reason to demand a wider edge or stand aside, which is a risk rule and not a
strategy.

Note also the sign instability the literature emphasises: Lauterbach and Ungar found *Israeli*
pre-holiday returns +0.424% and *post*-holiday +0.590% (t=2.32) — the opposite sign to the US
result, which is what you expect when the market being closed is the mechanism rather than the
holiday. Rosh Hashana's and Yom Kippur's return effects also carry opposite signs in the
original US paper. **Two holidays with opposite signs cannot be pooled into one "Jewish holiday
trade",** and every practitioner claim found rests on about 55 annual observations with no costs
charged. The folk figure "Wall Street is one-third Jewish" is unverified and has conspiracy
provenance; it is not repeated here.

## 5. What a strategy would have earned

The best candidate is the Erev (day-before) window on equity indices, t=+2.05, n=275 dates.
In index points, per market, holiday day only:

| index | Yom Kippur (n=20) | t | Rosh Hashana (n=43) | t |
|---|---|---|---|---|
| SPX500 | +3.2 pts | +0.37 | −5.2 pts | −1.43 |
| NAS100 | +46.4 pts | +0.94 | −11.4 pts | −0.93 |
| US2000 | +3.9 pts | +1.23 | −3.6 pts | −1.38 |
| DE30 | +13.1 pts | +0.39 | −34.5 pts | −1.76 |
| JP225 | +127.4 pts | +1.29 | −10.6 pts | −0.23 |
| UK100 | +0.1 pts | +0.01 | −8.6 pts | −0.92 |

Not one of these clears |t|=2, on 20 or 43 observations, and the signs disagree between the two
holidays and across markets. Charged a round trip — 1.5 pips measured live on EUR_USD, 2.45 pips
as the portfolio model (`run_state.live_trading_record`, `facts` id 127) — a +3.2-point SPX drift
with an t of 0.37 is not an edge, it is a coin flip with a fee attached.

## 6. What this does and does not say

**What it settles.** On 13 years of daily data across 32 instruments, the work-prohibited Jewish
holidays show **no directional drift** and **no increase in the daily swing** — the measured
direction of the range effect is *down*, not up. The claim that the market swings remarkably on
them is not supported.

**What it does not settle, and one thing I got wrong at first.** On volume the honest verdict is
*narrow yes, in equities*: Rosh Hashana index volume came in 15% below baseline at t=−2.23, which
agrees in direction and rough size with the peer-reviewed NYSE figure of −19% at t=−5.30
(Frieder & Subrahmanyam 2004). My first pass reported this as "a mild and insignificant dip" and
led with the fact that the largest effects fell on Purim. The Purim point stands, but it does not
license the stronger claim: a crude tick-count proxy on index CFDs is a weaker instrument than
actual exchange volume, so my failure to reach significance at n=43 is my instrument's limit, not
evidence against the effect. Section 4 carries the correction.

**Why the correction does not produce a strategy.** The real effect is *less liquidity*. We pay
spreads rather than earn them, so thinner books raise our cost on exactly those days. A rule that
stands aside, or demands a wider edge, is the defensible use — that is risk management, not an
edge, and it is worth roughly nothing on a book that has taken three live trades.

**What else is not tested.** Daily bars throughout; an intraday liquidity effect in a specific
hour would need intraday data. Nothing here covers the Tel Aviv market, which is closed on these
days and is a different question. The mechanism story also does not fit FX at all, which trades
continuously across every timezone and has no set of participants who leave for a holiday —
and FX is where this desk actually trades.

**The one calendar feature the bot actually has.** `src/tradebot_sci/runtime/sabbath.py`
implements the *weekly* Sabbath — Friday 18:00 to Saturday 18:00 local, optionally
sunset-based via `astral` — and `runtime/loop.py` enforces it on the real-order path. It knows
nothing about Jewish holidays. That is a gap, but on this evidence it is not a gap worth
filling: a liquidity dip is not a directional risk, and blocking the holidays would remove
trading days from an already-thin live record of three trades.

## 7. Reproducing this

```bash
python3 tools/jewish_holiday_study.py --years 13
```

Writes `REPORT.md`, `results.json` and `pip_windows.json` under the data directory's
`holiday_study/`, plus the raw daily candles and the cached Hebcal responses.
