/**
 * chart.js — ECharts wrapper for the backtest line chart.
 *
 * One line per selected ticker (portfolio VALUE) + a dashed "Vốn nạp" (contributed
 * capital) line. Event markers (markLine) come from insights.json and are toggleable
 * (default OFF). A "Play" control reveals the chart left→right. Re-renders on resize.
 *
 * Public API (window.BacktestChart):
 *   init(domEl)                         -> create the ECharts instance
 *   render(run, ctx)                    -> draw a full run result
 *   setMarkers(on)                      -> toggle event markers (re-render)
 *   play()/stop()                       -> animate the left→right reveal
 *   resize()                            -> forward to echarts.resize()
 *
 * `ctx` carries everything needed to label/colour/annotate:
 *   { dates, series, meta, insights, tickerColors, realTerms }
 */

(function () {
  'use strict';

  // High-contrast but not gaudy palette (dark bg). Stable order = stable colours.
  const PALETTE = [
    '#4ea1ff', // blue
    '#ff7a59', // coral
    '#36d399', // green
    '#f5c451', // amber
    '#b58cff', // violet
    '#ff6b9d', // pink
    '#4dd0e1', // cyan
    '#a3e635', // lime
  ];
  const CONTRIB_COLOR = '#7d8590'; // muted grey for the dashed contributed line
  const GRID_COLOR = '#222831';
  const AXIS_COLOR = '#3a4250';
  const TEXT_COLOR = '#c9d1d9';
  const TEXT_DIM = '#8b949e';

  // Format VND compactly for axis labels: tỷ / triệu / nghìn.
  function fmtAxisVnd(v) {
    const n = Math.abs(v);
    if (n >= 1e9) return (v / 1e9).toFixed(n >= 1e10 ? 0 : 1).replace('.', ',') + ' tỷ';
    if (n >= 1e6) return Math.round(v / 1e6) + ' tr';
    if (n >= 1e3) return Math.round(v / 1e3) + 'k';
    return String(Math.round(v));
  }

  // Full vi-VN formatting for tooltips.
  function fmtVnd(v) {
    return Math.round(v).toLocaleString('vi-VN') + ' ₫';
  }

  const BacktestChart = {
    chart: null,
    _lastRun: null,
    _lastCtx: null,
    _markersOn: false,
    _playTimer: null,

    init(domEl) {
      if (!domEl) throw new Error('[chart.js] init() needs a DOM element');
      // `echarts` is loaded from CDN before this script.
      this.chart = echarts.init(domEl, null, { renderer: 'canvas' });
      return this.chart;
    },

    setMarkers(on) {
      this._markersOn = !!on;
      if (this._lastRun) this.render(this._lastRun, this._lastCtx);
    },

    /**
     * Build the ECharts `series` array for a run.
     * @param {Object} run   result of Simulator.run()
     * @param {Object} ctx   labelling/colour context
     * @param {number} [limitIdx]  if set, only reveal data up to this axis index (Play)
     */
    _buildSeries(run, ctx, limitIdx) {
      const dates = ctx.dates;
      const series = [];
      const realTerms = !!ctx.realTerms;

      // ── One value line per ticker ──────────────────────────────────────────
      run.order.forEach((ticker, i) => {
        const res = run.byTicker[ticker];
        const color = (ctx.tickerColors && ctx.tickerColors[ticker]) || PALETTE[i % PALETTE.length];
        const valArr = realTerms ? res.real : res.value;

        // Convert to [dateString, value] pairs, only within this ticker's live range
        // (skip leading zeros so a late-lister's line starts at its IPO, not at 0).
        const start = res.metrics.startIndex;
        const end = res.metrics.endIndex;
        const data = [];
        const cap = (typeof limitIdx === 'number') ? Math.min(end, limitIdx) : end;
        for (let d = start; d <= cap; d++) {
          const y = valArr[d];
          data.push([dates[d], (y === null || y === undefined) ? null : Math.round(y)]);
        }

        // Event markers from insights (toggleable).
        let markLine;
        if (this._markersOn && ctx.insights && ctx.insights[ticker] && ctx.insights[ticker].events) {
          const evs = ctx.insights[ticker].events
            .filter(e => {
              const idx = ctx.dateIndex ? ctx.dateIndex[e.date] : null;
              // Only show events that fall within the rendered (and revealed) range.
              if (idx === null || idx === undefined) {
                // event date may not be an exact trading day; show if within [start,cap] by string compare
                return e.date >= dates[start] && e.date <= dates[cap];
              }
              return idx >= start && idx <= cap;
            })
            .map(e => ({ xAxis: e.date, label: { formatter: e.label } }));
          if (evs.length) {
            markLine = {
              symbol: ['none', 'none'],
              silent: false,
              lineStyle: { color: color, type: 'dashed', opacity: 0.5, width: 1 },
              label: {
                color: TEXT_DIM, fontSize: 10, fontFamily: 'Inter, sans-serif',
                formatter: (p) => p.data.label.formatter,
                position: 'insideEndTop', rotate: 0,
              },
              data: evs,
            };
          }
        }

        series.push({
          name: (ctx.meta.assets[ticker] && ctx.meta.assets[ticker].name) || ticker,
          type: 'line',
          smooth: false,
          showSymbol: false,
          symbolSize: 6,
          sampling: 'lttb',
          lineStyle: { width: 2.2, color },
          itemStyle: { color },
          emphasis: { focus: 'series', lineStyle: { width: 3.2 } },
          connectNulls: false,
          z: 5,
          data,
          markLine,
          // stash the ticker so tooltip can resolve metrics
          _ticker: ticker,
        });
      });

      // ── Dashed "Vốn nạp" (contributed capital) line ────────────────────────
      // Hidden in real-terms mode (contributed isn't inflation-adjusted here).
      if (!realTerms) {
        const c = run.contributedTotal;
        const startIdx = run.startIndex;
        const endIdx = run.endIndex;
        const cap = (typeof limitIdx === 'number') ? Math.min(endIdx, limitIdx) : endIdx;
        const data = [];
        for (let d = startIdx; d <= cap; d++) {
          data.push([dates[d], c[d] ? Math.round(c[d]) : 0]);
        }
        series.push({
          name: 'Vốn nạp',
          type: 'line',
          smooth: false,
          showSymbol: false,
          lineStyle: { width: 1.6, color: CONTRIB_COLOR, type: 'dashed' },
          itemStyle: { color: CONTRIB_COLOR },
          emphasis: { disabled: true },
          z: 3,
          data,
          _ticker: '__contrib',
        });
      }

      return series;
    },

    _buildOption(run, ctx, limitIdx) {
      const self = this;
      const series = this._buildSeries(run, ctx, limitIdx);
      const legendNames = series.map(s => s.name);

      return {
        backgroundColor: 'transparent',
        animation: true,
        animationDuration: 600,
        animationEasing: 'cubicOut',
        color: PALETTE,
        textStyle: { fontFamily: 'Inter, sans-serif', color: TEXT_COLOR },
        grid: { left: 64, right: 24, top: 40, bottom: 56 },
        legend: {
          data: legendNames,
          top: 4,
          textStyle: { color: TEXT_DIM, fontFamily: 'Inter, sans-serif', fontSize: 12 },
          inactiveColor: '#4a525e',
          icon: 'roundRect',
          itemWidth: 14, itemHeight: 4,
        },
        tooltip: {
          trigger: 'axis',
          backgroundColor: 'rgba(20,24,30,0.96)',
          borderColor: AXIS_COLOR,
          borderWidth: 1,
          padding: [10, 12],
          textStyle: { color: TEXT_COLOR, fontFamily: 'Inter, sans-serif', fontSize: 12 },
          axisPointer: { type: 'line', lineStyle: { color: AXIS_COLOR, type: 'dashed' } },
          formatter: function (paramsArr) {
            if (!paramsArr || !paramsArr.length) return '';
            const dateStr = paramsArr[0].axisValueLabel || paramsArr[0].axisValue;
            let html = '<div style="font-family:Inter;font-size:11px;color:' + TEXT_DIM +
                       ';margin-bottom:6px">' + dateStr + '</div>';
            paramsArr.forEach(p => {
              const val = (p.value && p.value[1] !== null && p.value[1] !== undefined)
                ? '<span style="font-family:\'JetBrains Mono\',monospace">' + fmtVnd(p.value[1]) + '</span>'
                : '—';
              html += '<div style="display:flex;justify-content:space-between;gap:16px;line-height:1.7">' +
                        '<span>' + p.marker + p.seriesName + '</span>' +
                        '<span>' + val + '</span></div>';
            });
            return html;
          },
        },
        xAxis: {
          type: 'time',
          boundaryGap: false,
          axisLine: { lineStyle: { color: AXIS_COLOR } },
          axisLabel: {
            color: TEXT_DIM, fontFamily: 'JetBrains Mono, monospace', fontSize: 11,
            formatter: { year: '{yyyy}', month: '{MMM}', day: '{d}/{M}' },
          },
          axisTick: { show: false },
          splitLine: { show: false },
        },
        yAxis: {
          type: 'value',
          scale: false,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: {
            color: TEXT_DIM, fontFamily: 'JetBrains Mono, monospace', fontSize: 11,
            formatter: fmtAxisVnd,
          },
          splitLine: { lineStyle: { color: GRID_COLOR, type: 'solid' } },
        },
        dataZoom: [
          { type: 'inside', filterMode: 'none' },
        ],
        series,
      };
    },

    render(run, ctx) {
      this._lastRun = run;
      this._lastCtx = ctx;
      if (!this.chart) return;
      this.stop(); // cancel any running animation
      const opt = this._buildOption(run, ctx);
      // `notMerge:true` so removed tickers/markers fully clear.
      this.chart.setOption(opt, { notMerge: true });
    },

    /**
     * Play: reveal the chart left→right by progressively extending the visible
     * index window, then settle on the full option.
     */
    play() {
      if (!this.chart || !this._lastRun) return;
      this.stop();
      const run = this._lastRun;
      const ctx = this._lastCtx;
      const from = run.startIndex;
      const to = run.endIndex;
      if (to <= from) { this.render(run, ctx); return; }

      const FRAMES = 48;
      let frame = 0;
      // During play, disable per-frame animation so the reveal is smooth/fast.
      const step = () => {
        frame++;
        const t = frame / FRAMES;
        const idx = Math.round(from + (to - from) * t);
        const opt = this._buildOption(run, ctx, idx);
        opt.animation = false;
        this.chart.setOption(opt, { notMerge: true, lazyUpdate: true });
        if (frame >= FRAMES) {
          this.stop();
          // Final full render WITH animation off (already fully revealed).
          const full = this._buildOption(run, ctx);
          full.animation = false;
          this.chart.setOption(full, { notMerge: true });
          return;
        }
        this._playTimer = window.setTimeout(step, 28);
      };
      step();
    },

    stop() {
      if (this._playTimer) {
        window.clearTimeout(this._playTimer);
        this._playTimer = null;
      }
    },

    resize() {
      if (this.chart) this.chart.resize();
    },

    // Expose palette so app.js can assign stable per-ticker colours for cards/table.
    paletteFor(order) {
      const map = {};
      order.forEach((t, i) => { map[t] = PALETTE[i % PALETTE.length]; });
      return map;
    },
  };

  window.BacktestChart = BacktestChart;
})();
