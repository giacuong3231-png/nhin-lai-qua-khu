/**
 * app.js — Alpine.js state + glue between controls, Simulator, and the ECharts chart.
 *
 * Alpine holds only PLAIN state (mode, amount, range, selected tickers, toggles) and
 * derived summary rows/cards. The heavy ECharts instance lives in BacktestChart (a
 * non-reactive singleton) so Alpine never proxies it. Any relevant change calls
 * recompute() → Simulator.run() → BacktestChart.render() + refresh table/cards.
 *
 * Registered as a global factory used by  <div x-data="backtestApp()">.
 */

/* global Simulator, BacktestChart */

// ─── vi-VN number formatting helpers ──────────────────────────────────────────

/** Compact, human "₫ / triệu / tỷ" formatting for headline cards. */
function fmtMoney(v) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  const n = Math.abs(v);
  const sign = v < 0 ? '-' : '';
  if (n >= 1e9) return sign + (n / 1e9).toLocaleString('vi-VN', { maximumFractionDigits: 2 }) + ' tỷ';
  if (n >= 1e6) return sign + (n / 1e6).toLocaleString('vi-VN', { maximumFractionDigits: 1 }) + ' triệu';
  return sign + Math.round(n).toLocaleString('vi-VN') + ' ₫';
}

/** Exact VND with thousands separators (for table cells). */
function fmtVndExact(v) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  return Math.round(v).toLocaleString('vi-VN') + ' ₫';
}

/** Signed percentage, 1 decimal, vi-VN. */
function fmtPct(frac) {
  if (frac === null || frac === undefined || isNaN(frac)) return '—';
  const sign = frac > 0 ? '+' : '';
  return sign + (frac * 100).toLocaleString('vi-VN', { maximumFractionDigits: 1 }) + '%';
}

// ─── Alpine component factory ──────────────────────────────────────────────────

function backtestApp() {
  return {
    // ----- state -----
    ready: false,
    loadError: '',

    mode: 'dca',                 // 'dca' | 'lumpsum'
    amount: 1000000,             // VND; default depends on mode (set on init/mode change)
    amountDca: 1000000,
    amountLump: 100000000,

    start: '2016-01-01',
    end: '2026-04-01',
    minDate: '2016-01-01',
    maxDate: '2026-04-01',

    tickers: [],                 // selected ticker keys
    markersOn: false,
    realTerms: false,
    isPlaying: false,

    presets: {},                 // name -> [tickers]
    activePreset: '',
    tiers: [],                   // [{ tier, label, assets:[{key,name,market,...}] }]
    storyTicker: '',             // ticker whose story is shown in the side panel

    // derived/display
    summaryRows: [],             // per-ticker metric rows for the table
    cards: null,                 // headline cards for the "best"/aggregate view
    colors: {},                  // ticker -> colour (mirrors chart palette)

    // non-reactive handles
    _dataset: null,
    _sim: null,
    _lastRun: null,

    // ----- lifecycle -----
    async init() {
      try {
        const d = await window.dataReady;
        this._dataset = d;
        this._sim = new Simulator(d);

        // Date bounds from the data axis.
        this.minDate = d.dates[0];
        this.maxDate = d.dates[d.dates.length - 1];
        this.start = this.minDate;
        this.end = this.maxDate;

        this.presets = (d.meta && d.meta.presets) || {};
        this._buildTiers();

        // Init the ECharts instance.
        const el = this.$refs.chart;
        BacktestChart.init(el);

        // Default to ONE preset to reduce cognitive load.
        const presetNames = Object.keys(this.presets);
        const preferred = presetNames.find(n => n === 'Toàn cảnh')
          || presetNames.find(n => n === 'Siêu lợi nhuận')
          || presetNames[0];
        if (preferred) {
          this.applyPreset(preferred);
        } else {
          // No presets → pick the first 1-2 valid tickers.
          this.tickers = this._allTickerKeys().slice(0, 2);
          this.recompute();
        }

        // Default story = first selected ticker.
        if (this.tickers.length) this.storyTicker = this.tickers[0];

        // Responsive: re-fit chart on window resize.
        window.addEventListener('resize', () => BacktestChart.resize());

        this.ready = true;
        // One more resize after layout settles so the chart sizes correctly —
        // twice, because on mobile the flex layout height lands a tick late.
        this.$nextTick(() => {
          BacktestChart.resize();
          window.setTimeout(() => BacktestChart.resize(), 250);
        });
      } catch (e) {
        console.error('[app.js] init failed', e);
        this.loadError = e && e.message ? e.message : String(e);
      }
    },

    // ----- asset grouping -----
    _buildTiers() {
      const assets = (this._dataset.meta && this._dataset.meta.assets) || {};
      const series = this._dataset.series || {};
      const labels = {
        1: 'Cốt lõi',
        2: 'Tham chiếu',
        3: 'Drama',
        4: 'Tăng trưởng',
        5: 'Bonus',
      };
      const groups = {};
      Object.keys(assets).forEach(key => {
        // Only list tickers we actually have a price series for (so checkboxes never break).
        if (!series[key]) return;
        // CPI is a macro index used internally for real-return; don't offer as a buyable line.
        if (key === 'CPI') return;
        const a = assets[key];
        const tier = a.tier || 9;
        (groups[tier] = groups[tier] || []).push({
          key,
          name: a.name || key,
          market: a.market || '',
          type: a.type || '',
          hasSpread: !!a.has_spread,
        });
      });
      this.tiers = Object.keys(groups)
        .map(Number)
        .sort((x, y) => x - y)
        .map(t => ({ tier: t, label: labels[t] || ('Nhóm ' + t), assets: groups[t] }));
    },

    _allTickerKeys() {
      const out = [];
      this.tiers.forEach(g => g.assets.forEach(a => out.push(a.key)));
      return out;
    },

    // ----- user actions -----
    setMode(m) {
      if (this.mode === m) return;
      this.mode = m;
      // Swap to the sensible default amount for the new mode (only if user hasn't customised).
      this.amount = (m === 'dca') ? this.amountDca : this.amountLump;
      this.recompute();
    },

    onAmountInput() {
      // Keep per-mode memory so toggling modes restores the right default.
      if (this.mode === 'dca') this.amountDca = this.amount;
      else this.amountLump = this.amount;
      this.recompute();
    },

    toggleTicker(key) {
      const i = this.tickers.indexOf(key);
      if (i >= 0) {
        this.tickers.splice(i, 1);
        if (this.storyTicker === key) {
          this.storyTicker = this.tickers[0] || '';
        }
      } else {
        // Soft cap to keep the chart legible (reduce cognitive load).
        if (this.tickers.length >= 8) return;
        this.tickers.push(key);
        this.storyTicker = key; // show the just-added ticker's story
      }
      this.activePreset = ''; // manual change clears the active-preset highlight
      this.recompute();
    },

    isSelected(key) {
      return this.tickers.indexOf(key) >= 0;
    },

    applyPreset(name) {
      const list = (this.presets[name] || []).filter(k => !!this._dataset.series[k]);
      // Respect the 8-line soft cap.
      this.tickers = list.slice(0, 8);
      this.activePreset = name;
      this.storyTicker = this.tickers[0] || '';
      this.recompute();
    },

    toggleMarkers() {
      this.markersOn = !this.markersOn;
      BacktestChart.setMarkers(this.markersOn);
    },

    toggleRealTerms() {
      this.realTerms = !this.realTerms;
      this.recompute();
    },

    setStory(key) {
      this.storyTicker = key;
    },

    play() {
      if (!this._lastRun) return;
      this.isPlaying = true;
      BacktestChart.play();
      // Re-enable controls after the reveal finishes (~48 frames × 28ms + buffer).
      window.setTimeout(() => { this.isPlaying = false; }, 48 * 28 + 400);
    },

    setRange() {
      // Guard: start must precede end.
      if (this.start > this.end) {
        const t = this.start; this.start = this.end; this.end = t;
      }
      this.recompute();
    },

    quickRange(years) {
      // Set start = maxDate - N years (clamped to minDate). years=0 → full history.
      if (!years) {
        this.start = this.minDate;
      } else {
        const end = new Date(this.maxDate + 'T00:00:00Z');
        end.setUTCFullYear(end.getUTCFullYear() - years);
        const iso = end.toISOString().slice(0, 10);
        this.start = iso < this.minDate ? this.minDate : iso;
      }
      this.end = this.maxDate;
      this.recompute();
    },

    // ----- the core recompute → render path -----
    recompute() {
      if (!this._sim) return;
      const params = {
        mode: this.mode,
        amount: Number(this.amount) || 0,
        start: this.start,
        end: this.end,
        tickers: this.tickers.slice(),
      };
      const run = this._sim.run(params);
      this._lastRun = run;

      // Stable colours per ticker (mirror the chart palette).
      this.colors = BacktestChart.paletteFor(run.order);

      // Render the chart.
      BacktestChart.render(run, {
        dates: this._dataset.dates,
        dateIndex: this._dataset.dateIndex,
        series: this._dataset.series,
        meta: this._dataset.meta,
        insights: this._dataset.insights,
        tickerColors: this.colors,
        realTerms: this.realTerms,
      });
      // Markers state may have been reset by notMerge render → re-apply if on.
      if (this.markersOn) BacktestChart.setMarkers(true);

      this._buildSummary(run);
    },

    _buildSummary(run) {
      const assets = this._dataset.meta.assets || {};
      const real = this.realTerms;
      const rows = run.order.map(t => {
        const m = run.byTicker[t].metrics;
        // In real-terms mode the displayed "final value" is the inflation-adjusted
        // value (today's money expressed in start-of-window purchasing power). Invested
        // stays nominal (approximation, matches the real chart line). Derive profit /
        // % / CAGR from that real final so cards + table change with the toggle.
        const finalShown = real ? m.finalReal : m.finalValue;
        const profit = finalShown - m.invested;
        const pctReturn = m.invested > 0 ? profit / m.invested : 0;
        const cagr = (m.invested > 0 && finalShown > 0 && m.holdYears > 0)
          ? Math.pow(finalShown / m.invested, 1 / m.holdYears) - 1
          : 0;
        return {
          key: t,
          name: (assets[t] && assets[t].name) || t,
          color: this.colors[t],
          invested: m.invested,
          finalValue: finalShown,
          profit,
          pctReturn,
          cagr,
          maxDrawdown: m.maxDrawdown,   // drawdown stays nominal
          finalReal: m.finalReal,
          buys: m.buys,
          // formatted
          fInvested: fmtVndExact(m.invested),
          fFinal: fmtVndExact(finalShown),
          fProfit: fmtVndExact(profit),
          fPct: fmtPct(pctReturn),
          fCagr: fmtPct(cagr),
          fDd: fmtPct(-m.maxDrawdown),
          fReal: fmtVndExact(m.finalReal),
          up: profit >= 0,
        };
      });
      // Sort by final (displayed) value descending so the "winner" is on top.
      rows.sort((a, b) => b.finalValue - a.finalValue);
      this.summaryRows = rows;

      // Headline cards = AGGREGATE across all selected tickers (like the video's summary).
      let totInv = 0, totVal = 0, worstDD = 0;
      run.order.forEach(t => {
        const m = run.byTicker[t].metrics;
        totInv += m.invested;
        totVal += real ? m.finalReal : m.finalValue;
        if (m.maxDrawdown > worstDD) worstDD = m.maxDrawdown;
      });
      const totProfit = totVal - totInv;
      const totPct = totInv > 0 ? totProfit / totInv : 0;
      this.cards = {
        invested: fmtMoney(totInv),
        value: fmtMoney(totVal),
        profitPct: fmtPct(totPct),
        diff: fmtMoney(totProfit),
        up: totProfit >= 0,
        nTickers: run.order.length,
        // Worst single-ticker drawdown across the selection (nominal). Shown red.
        worstDrawdown: run.order.length ? fmtPct(-worstDD) : '—',
        realTerms: real,
      };
    },

    // ----- display helpers exposed to the template -----
    fmtMoney, fmtVndExact, fmtPct,

    modeLabel() { return this.mode === 'dca' ? 'DCA hằng tháng' : 'Mua một lần'; },

    currentStory() {
      const t = this.storyTicker;
      if (!t) return null;
      const ins = (this._dataset && this._dataset.insights && this._dataset.insights[t]) || null;
      const a = (this._dataset && this._dataset.meta.assets && this._dataset.meta.assets[t]) || {};
      if (!ins) return { name: a.name || t, story: 'Chưa có dữ liệu câu chuyện cho mã này.', color: this.colors[t] };
      return { name: ins.name || a.name || t, story: ins.story || '', color: this.colors[t] };
    },

    // The amount input shows triệu for readability; keep raw VND in state.
    amountHint() {
      const v = Number(this.amount) || 0;
      return fmtMoney(v);
    },
  };
}

// Make the factory discoverable by Alpine (which initialises on its own).
window.backtestApp = backtestApp;
