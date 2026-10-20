# What Gemini and Qwen suggested (20 Oct 2026)

The same question went to Gemini 3.1 Pro and Qwen in Brave. Answers copied verbatim from the pages.

## Prompt

I backtest trading ideas honestly on 1-minute bid/ask data (Exness retail MT5, real spreads). Data I have: FX (EURUSD, GBPUSD, USDJPY, EURJPY, AUDJPY, AUDUSD, EURGBP, GBPJPY, CADJPY, CHFJPY, USDCNH) and gold, silver from 2016; Bitcoin from 2019; US500, US30, USTEC, DAX, FTSE from 2019; daily closes of major indices back to 1950. Account EUR 1,000.

What already WORKS: USD/JPY "gotobi" (Japanese importers buy dollars at the 09:55 Tokyo fix on the 5th/10th/15th/20th/25th/30th), and GBP/USD rising into the month-end London 4 pm fix.

What already FAILED (after spread, out of sample): liquidity sweeps, ICT/order blocks, order-flow delta, M5 indicator rules, trend following on CFDs (financing kills it), turn of the month, overnight drift, pre-FOMC drift, pre-holiday, weekend gaps, all fixes/auctions other than those two (gold, silver, Shanghai, WM fix reversal, index closes, expiry auctions), China fix, Bitcoin funding times / CME gap / ETF NAV, Japanese toshin and fiscal year-end flows, BoJ days, tax days.

I want something DIFFERENT that might genuinely work for a retail trader: not calendar flows. Think cross-asset lead-lag, relative value / pairs, volatility regimes, statistical patterns with a real economic cause, carry, news-reaction asymmetries, anything. Give me your 5 best candidates with EXACT testable rules (instrument, signal, entry, exit, stop, timeframe, UTC times), the economic reason it should exist, the published evidence, and honestly how likely it survives retail spreads.

## Gemini 3.1 Pro

The fact that you have systematically debunked ICT, order blocks, and M5 indicator rules using 1-minute bid/ask out-of-sample data puts you ahead of 99% of retail traders. You have also correctly identified that CFD financing costs (swap) destroy traditional long-term trend following, and that most calendar anomalies are arbitraged away by HFTs before the retail spread allows entry.

With a EUR 1,000 account, you must trade micro-lots (0.01) to survive variance, and your edge must rely on structural market mechanics or institutional constraints that persist despite retail spreads.

Here are 5 candidates with testable rules that do not rely on calendar flows.

1. Macroeconomic News Post-Release Drift (PEAD for FX)

Institutions use TWAP/VWAP algorithms to execute massive orders following a fundamental surprise. They cannot dump their entire position at minute 1; they spread it over the session. Retail traders try to fade the initial spike and get crushed.

Instrument: EURUSD or USDJPY.

Timeframe: M15 (using M1 to enter exactly 15 mins after the print).

Signal: US Core CPI or NFP deviates from the Bloomberg consensus by > 0.2% (CPI) or > 50k (NFP).

Entry: Enter in the direction of the fundamental surprise exactly 15 minutes after the release (e.g., 12:45 or 13:45 UTC depending on US DST). Wait out the first 15 minutes.

Exit: 21:00 UTC the same day (London/US overlap clearing and end of algorithmic execution).

Stop: 2 pips beyond the extreme high/low of the initial 15-minute news candle.

Published Evidence: "Macroeconomic News Announcements and Price Drift" (various academic papers adapting Post-Earnings Announcement Drift to FX).

Retail Survival: High. By waiting 15 minutes, you completely bypass the spread-widening and slippage of minute 0. You are capturing the algorithmic digestion of the news.

2. Volatility-Gated Positive Carry (The Trend/Swap Solution)

Since CFD financing kills standard trend following, this strategy explicitly pairs momentum with positive swap, ensuring time works for you. It exploits the failure of Uncovered Interest Rate Parity, where high-yielders trend up smoothly in low-volatility regimes but crash violently in panics.

Instrument: USDJPY or GBPJPY (must have positive swap for long positions on your broker).

Timeframe: Daily (D1).

Signal: The VIX index closes < 20 (low global risk regime) AND the FX pair closes > 100-day EMA.

Entry: Buy at 22:00 UTC (New York close / start of Asian session).

Exit: The VIX closes > 22 (regime shift) OR the FX pair closes < 100-day EMA.

Stop: 2.5x ATR(14) trailing stop.

Published Evidence: "Carry Trades and Global Foreign Exchange Volatility" (Menkhoff et al., Journal of Finance).

Retail Survival: Excellent. You earn the spread/swap rather than paying it. Because the timeframe is Daily, the retail spread is a negligible fraction of the target ATR.

3. Dealer Gamma Mean Reversion (US500 RSI-2)

In a structural bull market, passive 401(k) inflows and dealer short-gamma hedging (options market makers buying spot to hedge sold puts as the market drops) force sharp mean-reversions on intraday dips.

Instrument: US500 (S&P 500 CFD).

Timeframe: M15 and D1.

Signal: D1 Close > 200 SMA (Bull regime filter). M15 RSI(2) drops below 10 (extreme short-term capitulation).

Entry: Buy exactly at the close of the M15 candle where RSI(2) < 10.

Exit: Sell when M15 RSI(2) closes > 70.

Stop: 3x M15 ATR(14) below the entry price.

Published Evidence: Larry Connors' Short-Term Trading Strategies (RSI-2 is heavily documented in equity index quant trading).

Retail Survival: Moderate to High. US500 spreads on Exness are generally very tight (under 1 point) during NY hours (13:30 to 20:00 UTC). As long as the signal fires during RTH (Regular Trading Hours), execution is clean.

4. Commodity FX Cointegration (Z-Score Pairs Trading)

Australia and New Zealand are heavily linked commodity-exporting economies. Supply/demand shocks isolate their currencies briefly before macroeconomic arbitrageurs force the exchange rate back to its historical mean.

Instrument: AUDNZD cross.

Timeframe: H1.

Signal: Calculate the spread difference from the mean using a 200-period H1 moving average. Calculate the Standard Deviation over the same 200 periods. The signal triggers when the Z-score hits -2.5 (extremely oversold relative to the mean) or +2.5 (overbought).

Entry: Buy (if Z < -2.5) or Sell (if Z > +2.5) at the H1 close.

Exit: Close the trade when the Z-score crosses 0 (reverts to the mean).

Stop: Z-score hits -4.0 or +4.0 (indicating a structural economic break, take the loss).

Published Evidence: "Pairs Trading: Performance of a Relative Value Arbitrage Rule" (Gatev et al.).

Retail Survival: Moderate. Spreads on cross pairs are wider than majors. However, because the target reversion is usually 50 to 100 pips over several days, the spread only eats ~5% of your expected value, which is survivable.

5. Microstructure Tick-Volume Capitulation

In retail MT5 data, "Tick Volume" measures the frequency of price updates, which has a >90% correlation with real institutional volume. When price moves violently outside normal bounds accompanied by a massive volume spike, it represents a liquidity cascade (margin calls and stop hunts). Once forced sellers are exhausted, price snaps back into the value area.

Instrument: Gold (XAUUSD) or GBPUSD.

Timeframe: M5.

Signal: An M5 candle closes entirely outside the Bollinger Bands (20, 2.5 standard deviations). AND the MT5 Tick Volume for that candle is > 3x the 50-period SMA of Tick Volume.

Entry: Fade the move on the exact close of the climax M5 candle (e.g., if it closed below the lower band, Buy).

Exit: Price touches the 20-period SMA (the center of the Bollinger Band).

Stop: 1.5x the height of the climax candle, placed below its extreme low/high.

Published Evidence: "Volume and Price Volatility" studies; concepts utilized heavily in VSA (Volume Spread Analysis).

Retail Survival: Moderate. The main risk here is that the retail spread might still be elevated by 2-3 pips right at the close of the climax candle. However, since the strategy specifically targets the structural vacuum left behind by the cascade, the snap-back is usually large enough to absorb the spread cost.




Pro

Gemini is AI and can make mistakes, including about people. Your privacy & Gemini
Opens in a new window

Refining trading strategy specifics
## Qwen

Here are 5 rigorously defined, non-calendar, economically grounded trading candidates tailored to your data, account size, and constraints. I have explicitly designed these to avoid the "retail traps" you’ve already identified (liquidity sweeps, indicator rules, financing drag) and focused on structural market microstructure, cross-asset lead-lag, and statistical mean reversion.
Candidate 1: EUR/GBP Statistical Mean Reversion (Pairs Trading)
Instrument: EUR/GBP
Signal: Calculate the 20-period (H1) Z-Score of the closing price. Enter when Z-Score > +2.0 (Short) or < -2.0 (Long).
Entry: Market order at the close of the H1 bar where the threshold is crossed.
Exit: When Z-Score crosses 0.0 (mean reversion achieved).
Stop: Z-Score reaches 3.5 (indicates a structural macroeconomic break, e.g., unexpected BoE/ECB divergence).
Timeframe: H1 for signal generation, M1 for precise execution to minimize slippage.
UTC Times: Only take signals generated between 07:00 and 16:00 UTC (London session). Ignore signals during the Asian session to avoid low-liquidity whipsaws.
Economic Reason: EUR and GBP are deeply cointegrated due to highly synchronized business cycles, massive bilateral trade volume, and overlapping monetary policy expectations. Extreme deviations are almost always arbitraged away by institutional relative-value desks.
Published Evidence: Gatev, Goetzmann, and Rouwenhorst (2006) "Pairs Trading: Performance of a Relative Value Arbitrage Rule"; numerous quant studies identify EUR/GBP as the most mean-reverting major FX pair due to Purchasing Power Parity (PPP) enforcement.
Retail Spread Survival: High. Exness EUR/GBP spreads are typically 1.0–1.5 pips. The mean reversion target is usually 30–50 pips, providing a massive 20:1+ reward-to-spread buffer.
Candidate 2: Cross-Asset Lead-Lag: USD/CNH leading AUD/USD
Instrument: AUD/USD (triggered by USD/CNH data).
Signal: USD/CNH makes a new 20-period (H1) low (CNH strengthening) or high, while AUD/USD has not yet made a corresponding new 20-period (H1) high or low.
Entry: Market order on AUD/USD in the direction of the CNH move (e.g., if USD/CNH made a new low, go Long AUD/USD) at the close of the next 15-minute bar.
Exit: 3 hours after entry, OR when AUD/USD achieves a 0.25% profit, whichever comes first.
Stop: 0.15% adverse move in AUD/USD from entry price.
Timeframe: H1 for USD/CNH signal detection, M15 for AUD/USD entry and management.
UTC Times: 01:00 to 08:00 UTC (Asian session, when CNH is most liquid and informative).
Economic Reason: China is Australia’s largest export market. CNH is the direct pricing mechanism for Chinese capital flows. When CNH strengthens, it immediately improves Australia’s terms of trade. AUD/USD, being dominated by global macro funds, often lags the initial CNH move by 15–60 minutes as cross-asset arbitrage desks slowly rebalance their books.
Published Evidence: Reserve Bank of Australia (RBA) research bulletins on the "AUD-CNH nexus"; academic literature on information transmission between Chinese exchange rates and commodity currencies (e.g., Fratzscher, 2012).
Retail Spread Survival: High. AUD/USD is one of the tightest spreads (~0.6–1.0 pip on Exness). A 0.25% move is ~18 pips, easily clearing the spread and minor slippage.
Candidate 3: Intraday Volatility Regime: The "London Morning Overextension Fade"
Instrument: GBP/USD
Signal: The cumulative return of GBP/USD between 07:00 and 09:00 UTC is > +0.25% or < -0.25% (an unusually large morning move, >1.5x the 20-day average for that window).
Entry: At 09:00 UTC close, enter a market order fading the 07:00–09:00 move (i.e., if it rallied 0.25%, go Short).
Exit: 12:00 UTC close (exactly 3 hours later).
Stop: 0.15% adverse move from the entry price.
Timeframe: H1 for signal calculation, M1 for execution.
UTC Times: Signal evaluated at 09:00 UTC, hard exit at 12:00 UTC.
Economic Reason: The 07:00–09:00 window captures the London open and morning corporate flows. Large moves here are often driven by lumpy, one-sided institutional flow or option delta hedging. Once this flow is exhausted (by 09:00), market makers pull liquidity, and proprietary traders take profits. This causes a natural mean reversion toward the session VWAP before the US pre-open (12:30 UTC) introduces new directional catalysts.
Published Evidence: Anatolyev & Khrapov (2018) "Intraday patterns in FX returns"; market microstructure literature on the "midday lull" and morning overreaction reversals.
Retail Spread Survival: Medium-High. GBP/USD spread is ~1.2 pips. A 0.15% stop is ~11 pips. The 3-hour mean reversion often yields 10–20 pips. Requires strict M1 execution to avoid wick slippage.
Candidate 4: Cross-Asset Divergence: Gold (XAU/USD) vs. USD/JPY (Yield Proxy)
Instrument: XAU/USD
Signal: USD/JPY makes a new 1-hour high, but XAU/USD fails to make a new 1-hour low (or posts a positive return) in that same 1-hour window. (Their baseline correlation is strongly negative).
Entry: Long XAU/USD at the M1 close of the hour where this divergence is confirmed.
Exit: 2 hours after entry, OR when XAU/USD gains 0.25%.
Stop: XAU/USD drops 0.20% below the entry price.
Timeframe: H1 for divergence check, M1 for execution.
UTC Times: 12:00 to 16:00 UTC (US session, when yield dynamics dominate pricing).
Economic Reason: Gold is inversely correlated with US real yields. USD/JPY is the highest-frequency, most liquid proxy for US nominal yields. When yields rise (USD/JPY up) but Gold refuses to fall, it signals latent, non-yield-sensitive demand (e.g., central bank physical buying, geopolitical hedging, or algo exhaustion). This divergence often precedes a catch-up rally in Gold once the yield move stalls.
Published Evidence: World Gold Council research on "Gold's reaction to real yield anomalies"; quant studies on correlation breakdowns between USD/JPY and XAU/USD as a leading indicator for Gold direction.
Retail Spread Survival: Medium. Exness Gold spreads are ~15–25 cents ($1.5–$2.5 per oz). A 0.25% move on $2,600 Gold is $6.50, easily covering the spread. However, the 0.20% stop requires disciplined M1 execution, as Gold is prone to brief, violent wicks.
Candidate 5: Relative Value: US30 vs. USTEC Intraday Ratio Catch-Up
Instrument: US30 or USTEC (Single-leg execution to preserve margin on a €1k account).
Signal: Calculate the 20-day rolling Z-Score of the (US30 / USTEC) ratio using daily closes. If Z-Score > +2.0, US30 is extremely expensive relative to USTEC. If Z-Score < -2.0, USTEC is extremely expensive relative to US30.
Entry: At 14:30 UTC (US cash open), go Long the laggard. (If Z > 2.0, Long USTEC. If Z < -2.0, Long US30).
Exit: 19:00 UTC (end of main US session), OR if a 0.4% profit is hit.
Stop: 0.25% adverse move from entry.
Timeframe: Daily (for Z-Score calculation), M5 (for execution at 14:30 UTC).
UTC Times: Entry 14:30 UTC, hard exit 19:00 UTC.
Economic Reason: Sector rotation mean reversion. Extreme divergences in the Value (US30) vs. Growth (USTEC) ratio are often overdone intraday by retail FOMO or single-sided institutional flow. By the end of the day, portfolio rebalancing algos (VWAP/TWAP) and statistical arbitrage desks force the ratio back toward its mean, lifting the laggard index.
Published Evidence: Gatev, Goetzmann, Rouwenhorst (2006); widely applied to intraday index futures by quant funds as "intraday mean reversion in US equity index spreads."
Retail Spread Survival: Medium. Index CFD spreads are wider (e.g., 1.0–2.0 points). However, a 0.4% move on USTEC (e.g., 18,000 → 72 points) dwarfs the spread. Because it is strictly intraday, you completely avoid the CFD financing/swap drag that killed your previous trend-following ideas.
⚠️ Crucial Reality Check for a €1,000 Account
Position Sizing is Non-Negotiable: With €1,000, a 0.25% stop on Gold or Indices is €2.50. You must trade micro-lots (0.01 lots for FX, 0.01 or 0.1 for indices depending on broker contract size). If your broker's minimum lot size forces a stop loss > €15 (1.5% of account), the edge is mathematically destroyed by risk of ruin.
Model Slippage, Not Just Spread: You have real spread data, which is excellent. But at 09:00 UTC, 14:30 UTC, or during news, MT5 retail execution suffers slippage. In your backtest, add a synthetic 1.5-pip (or 1.5-point) slippage penalty to every entry and exit. If the strategy survives that, it is genuinely robust.
Avoid Overfitting the Z-Score: For Candidates 1 and 5, do not optimize the Z-Score threshold (e.g., changing 2.0 to 1.8 because it looks better in-sample). Use 2.0 and 3.5 as fixed, out-of-sample parameters derived from standard statistical practice.
MT5 Implementation: Do not visually backtest these. Write a simple MQL5 script or use a robust strategy tester to loop through your 1-minute bid/ask CSV data, calculating the rolling Z-scores and lead-lag conditions programmatically.
These 5 candidates rely on structural market mechanics (arbitrage, cointegration, flow exhaustion) rather than retail chart patterns. They are your best statistical shot at finding a persistent edge that survives retail friction.