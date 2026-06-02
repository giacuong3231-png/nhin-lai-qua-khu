/**
 * simulator.js — DCA / Lump-sum backtest engine (runs entirely in the browser).
 *
 * Implements DATA-CONTRACT.md §4 EXACTLY. All prices are integer VND on a single
 * shared daily date axis. `null` in a series = the asset was not yet listed on that
 * day (pre-IPO) → no buy, no valuation.
 *
 * Usage:
 *   const sim = new Simulator(dataset);   // dataset = { dates, series, meta, dateIndex }
 *   const run = sim.run({ mode:'dca', amount:1_000_000, start:'2016-01-01', end:'2026-04-01', tickers:['NVDA','VNM'] });
 *   // run.byTicker['NVDA'] -> { value:[], contributed:[], real:[], metrics:{...} }
 *   // run.contributedTotal -> combined contributed-capital array (for the dashed line)
 *   // run.startIndex / run.endIndex -> slice bounds into dataset.dates
 *
 * Design notes:
 *   - Money is fractional internally (shares can be fractional); only DISPLAY rounds.
 *   - "Vốn nạp" (contributed) is the GROSS amount paid out of pocket each buy
 *     (fees are a cost, not extra capital), accumulated over time.
 *   - SJC: buy uses "SJC__buy" (ask, dearer), valuation uses "SJC" (bid, cheaper)
 *     → the value line drops below contributed immediately after a buy (spread loss).
 */

(function () {
  'use strict';

  /** Number of whole/fractional years between two ISO date strings. */
  function yearsBetween(isoA, isoB) {
    const a = new Date(isoA + 'T00:00:00Z').getTime();
    const b = new Date(isoB + 'T00:00:00Z').getTime();
    const days = (b - a) / 86400000;
    return days / 365.25;
  }

  /** "YYYY-MM" key for grouping a date into its calendar month. */
  function monthKey(iso) {
    return iso.slice(0, 7);
  }

  class Simulator {
    /**
     * @param {{dates:string[], series:Object<string,(number|null)[]>, meta:Object, dateIndex?:Object}} dataset
     */
    constructor(dataset) {
      this.dates = dataset.dates;
      this.series = dataset.series;
      this.meta = dataset.meta || { assets: {}, fees: {} };
      this.fees = (this.meta && this.meta.fees) || {};
      // Build (or reuse) a date → index lookup.
      if (dataset.dateIndex) {
        this.dateIndex = dataset.dateIndex;
      } else {
        this.dateIndex = Object.create(null);
        for (let i = 0; i < this.dates.length; i++) this.dateIndex[this.dates[i]] = i;
      }
    }

    /** Asset metadata with safe defaults. */
    _assetMeta(ticker) {
      return (this.meta.assets && this.meta.assets[ticker]) || {};
    }

    /**
     * Buy-side fee RATE for an asset, expressed as a fraction of the gross amount.
     *   VN market   -> vn_buy
     *   US / other  -> us_buy + usd_vnd_spread (foreign-currency assets pay FX spread)
     * SJC is market 'VN' (vn_buy) and additionally carries its bid/ask spread in prices.
     */
    _buyFeeRate(ticker) {
      const m = this._assetMeta(ticker);
      const f = this.fees;
      if (m.market === 'VN') {
        return (f.vn_buy || 0);
      }
      // US, GLOBAL, or unknown → treat as foreign-denominated.
      return (f.us_buy || 0) + (f.usd_vnd_spread || 0);
    }

    /**
     * Sell-side fee RATE (optional — for an "after-tax cash in hand" display).
     *   VN -> vn_sell + vn_sell_tax ; US/other -> us_sell
     */
    _sellFeeRate(ticker) {
      const m = this._assetMeta(ticker);
      const f = this.fees;
      if (m.market === 'VN') {
        return (f.vn_sell || 0) + (f.vn_sell_tax || 0);
      }
      return (f.us_sell || 0);
    }

    /** Series used to BUY (ask). SJC/has_spread → "<KEY>__buy", else "<KEY>". */
    _buySeries(ticker) {
      const m = this._assetMeta(ticker);
      if (m.has_spread && this.series[ticker + '__buy']) {
        return this.series[ticker + '__buy'];
      }
      return this.series[ticker];
    }

    /** Series used to VALUE the holding (bid for SJC) → always "<KEY>". */
    _valueSeries(ticker) {
      return this.series[ticker];
    }

    /**
     * Clamp a requested [start,end] to the data axis AND to the asset's first
     * non-null day. Returns inclusive integer indices, or null if no overlap.
     */
    _effectiveRange(ticker, start, end) {
      const dates = this.dates;
      // Locate window bounds on the global axis (inclusive).
      let lo = 0;
      while (lo < dates.length && dates[lo] < start) lo++;
      let hi = dates.length - 1;
      while (hi >= 0 && dates[hi] > end) hi--;
      if (lo > hi) return null;

      // Advance past leading nulls (pre-listing) for THIS ticker.
      const val = this._valueSeries(ticker);
      if (!val) return null;
      while (lo <= hi && (val[lo] === null || val[lo] === undefined)) lo++;
      if (lo > hi) return null;
      return { lo, hi };
    }

    /**
     * Run a backtest for a single ticker.
     * @returns {{value:number[], contributed:number[], real:(number|null)[], shares:number, metrics:Object}|null}
     *          Arrays are FULL-LENGTH (dataset.dates length); entries before the
     *          first purchase / outside the range are 0 (value & contributed) or
     *          null (real, when CPI missing). null when the ticker never trades.
     */
    runTicker(ticker, params) {
      const { mode, amount, start, end } = params;
      const N = this.dates.length;
      const range = this._effectiveRange(ticker, start, end);

      // Pre-fill full-length arrays with 0 so multi-ticker charts align on the axis.
      const value = new Array(N).fill(0);
      const contributed = new Array(N).fill(0);
      const real = new Array(N).fill(null);
      if (!range) return null;

      const { lo, hi } = range;
      const buyPx = this._buySeries(ticker);
      const valPx = this._valueSeries(ticker);
      const feeRate = this._buyFeeRate(ticker);
      const cpi = this.series.CPI || null;
      const cpiBase = cpi ? cpi[lo] : null; // CPI at effective start (real-return base)

      let shares = 0;
      let investedGross = 0; // cumulative out-of-pocket (gross of fees)

      // --- Build the list of BUY indices ---------------------------------------
      const buyIdx = [];
      if (mode === 'lumpsum') {
        // One buy on the first valid (non-null) day in range.
        buyIdx.push(lo);
      } else {
        // DCA: first trading day with a price in each calendar month within range.
        let seenMonth = null;
        for (let i = lo; i <= hi; i++) {
          if (buyPx[i] === null || buyPx[i] === undefined) continue; // need a buy price
          const mk = monthKey(this.dates[i]);
          if (mk !== seenMonth) {
            buyIdx.push(i);
            seenMonth = mk;
          }
        }
      }
      const buySet = new Set(buyIdx);

      // --- Walk the axis day by day, applying buys and valuing the holding ------
      let maxValue = 0;
      let maxDrawdown = 0;
      let firstBuyIso = null;

      for (let i = lo; i <= hi; i++) {
        // Skip pre-listing gaps mid-series (null valuation) — carry nothing forward.
        const px = valPx[i];
        const isNull = (px === null || px === undefined);

        // Apply a scheduled buy (only if a real buy price exists, guaranteed by buyIdx).
        if (buySet.has(i)) {
          const bpx = buyPx[i];
          if (bpx && bpx > 0) {
            const net = amount * (1 - feeRate);
            shares += net / bpx;
            investedGross += amount;
            if (!firstBuyIso) firstBuyIso = this.dates[i];
          }
        }

        contributed[i] = investedGross;

        if (!isNull) {
          const v = shares * px;
          value[i] = v;
          // Real (inflation-adjusted) value relative to start-of-window CPI.
          if (cpi && cpiBase && cpi[i]) {
            real[i] = v / (cpi[i] / cpiBase);
          }
          // Max drawdown tracked on the (nominal) value series, post-first-buy.
          if (v > maxValue) maxValue = v;
          if (maxValue > 0) {
            const dd = (maxValue - v) / maxValue;
            if (dd > maxDrawdown) maxDrawdown = dd;
          }
        } else {
          // Hold last known value through a gap so the line doesn't drop to 0.
          value[i] = (i > lo) ? value[i - 1] : 0;
          real[i] = (i > lo) ? real[i - 1] : null;
        }
      }

      const finalValue = value[hi] || 0;
      const pctReturn = investedGross > 0 ? (finalValue - investedGross) / investedGross : 0;

      // CAGR over the actual holding horizon (first buy → window end).
      const holdYears = firstBuyIso ? yearsBetween(firstBuyIso, this.dates[hi]) : 0;
      let cagr = 0;
      if (investedGross > 0 && finalValue > 0 && holdYears > 0) {
        // Total-return CAGR on contributed capital (approximation for DCA — the
        // standard money-weighted return is XIRR; CAGR here treats invested as a
        // single notional principal, consistent with the reference video's framing).
        cagr = Math.pow(finalValue / investedGross, 1 / holdYears) - 1;
      }

      // Real final value (today's money in start-of-window terms).
      const finalReal = (real[hi] !== null && real[hi] !== undefined) ? real[hi] : finalValue;

      // Optional "cash in hand" after sell-side fees/tax.
      const sellFeeRate = this._sellFeeRate(ticker);
      const cashOut = finalValue * (1 - sellFeeRate);

      return {
        value,
        contributed,
        real,
        shares,
        buyIdx,
        metrics: {
          ticker,
          invested: investedGross,
          finalValue,
          profit: finalValue - investedGross,
          pctReturn,
          cagr,
          maxDrawdown,
          finalReal,
          cashOut,
          holdYears,
          buys: buyIdx.length,
          firstBuy: firstBuyIso,
          lastDate: this.dates[hi],
          startIndex: lo,
          endIndex: hi,
        },
      };
    }

    /**
     * Run for many tickers at once.
     * @param {{mode:string, amount:number, start:string, end:string, tickers:string[]}} params
     * @returns {{byTicker:Object, contributedTotal:number[], order:string[],
     *            startIndex:number, endIndex:number}}
     */
    run(params) {
      const tickers = params.tickers || [];
      const N = this.dates.length;
      const byTicker = {};
      const order = [];

      let globalLo = N - 1;
      let globalHi = 0;

      for (const t of tickers) {
        const res = this.runTicker(t, params);
        if (!res) continue;
        byTicker[t] = res;
        order.push(t);
        globalLo = Math.min(globalLo, res.metrics.startIndex);
        globalHi = Math.max(globalHi, res.metrics.endIndex);
      }

      if (order.length === 0) {
        // No valid ticker → empty result clamped to the requested window.
        const r = this._windowIndices(params.start, params.end);
        return { byTicker, contributedTotal: new Array(N).fill(0), order,
                 startIndex: r.lo, endIndex: r.hi };
      }

      // Combined contributed line: per identical schedule the contributed amount is
      // the SAME for every ticker (amount × #buys), but late-listers buy fewer times.
      // We expose the MAX contributed across tickers as the headline "Vốn nạp" line
      // so it represents the fullest-history asset; per-ticker contributed is in metrics.
      const contributedTotal = new Array(N).fill(0);
      for (let i = 0; i < N; i++) {
        let best = 0;
        for (const t of order) {
          const c = byTicker[t].contributed[i];
          if (c > best) best = c;
        }
        contributedTotal[i] = best;
      }

      return { byTicker, contributedTotal, order, startIndex: globalLo, endIndex: globalHi };
    }

    /** Window [start,end] → inclusive indices on the axis (no null-skipping). */
    _windowIndices(start, end) {
      const dates = this.dates;
      let lo = 0;
      while (lo < dates.length && dates[lo] < start) lo++;
      let hi = dates.length - 1;
      while (hi >= 0 && dates[hi] > end) hi--;
      if (lo > hi) { lo = 0; hi = Math.max(0, dates.length - 1); }
      return { lo, hi };
    }
  }

  // Expose globally (no module system in this no-build app).
  window.Simulator = Simulator;
})();
