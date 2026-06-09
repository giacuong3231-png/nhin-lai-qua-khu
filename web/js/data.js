/**
 * data.js — Load and expose market data, metadata, and insights.
 *
 * Load order:
 *   1. Try ./data/data.json (pipeline output — real data)
 *   2. Try ./data/meta.json
 *   3. Try ./data/insights.json
 *   4. On ANY missing file, fall back to embedded minimal mock + ./data/sample-data.json
 *
 * Exports a single promise: window.dataReady
 * Resolves with: { dates, series, meta, insights }
 */

(function () {
  'use strict';

  // ─── Embedded minimal mock (always available, no network) ────────────────────
  const MOCK_META = {
    generated_at: 'mock',
    base_currency: 'VND',
    assets: {
      NVDA:    { name: 'NVIDIA',        market: 'US',     type: 'stock', tier: 1, first_date: '2016-01-04', has_spread: false },
      VNM:     { name: 'Vinamilk',      market: 'VN',     type: 'stock', tier: 1, first_date: '2016-01-04', has_spread: false },
      XAUUSD:  { name: 'Vàng quốc tế',  market: 'GLOBAL', type: 'gold',  tier: 1, first_date: '2016-01-04', has_spread: false },
      SJC:     { name: 'Vàng SJC',      market: 'VN',     type: 'gold',  tier: 1, first_date: '2016-01-04', has_spread: true  },
      DJT:     { name: 'Trump Media',   market: 'US',     type: 'stock', tier: 3, first_date: '2024-01-04', has_spread: false },
      SAVINGS: { name: 'Gửi tiết kiệm', market: 'VN',     type: 'rate',  tier: 2, first_date: '2016-01-04', has_spread: false },
      CPI:     { name: 'Lạm phát VN',   market: 'VN',     type: 'macro', tier: 2, first_date: '2016-01-04', has_spread: false },
    },
    presets: {
      'Siêu lợi nhuận': ['NVDA', 'XAUUSD', 'VNM'],
      'Sóng AI':        ['NVDA'],
      'Vàng & an toàn': ['XAUUSD', 'SJC', 'SAVINGS'],
      'Drama':          ['DJT', 'NVDA'],
    },
    fees: {
      vn_buy: 0.0015, vn_sell: 0.0015, vn_sell_tax: 0.001,
      us_buy: 0.0,    us_sell: 0.0,    usd_vnd_spread: 0.01,
    },
  };

  const MOCK_INSIGHTS = {
    NVDA: {
      name: 'NVIDIA',
      story: 'Từ chip game thủ đến trung tâm cuộc cách mạng AI — NVDA tăng hơn 60× trong 10 năm. Nếu bạn DCA 1 triệu/tháng từ 2016 đến nay, khoản đầu tư đó đã nhân lên hàng chục lần. Bài học: đừng bán khi thị trường hoảng loạn.',
      events: [
        { date: '2022-10-14', label: 'Đáy COVID + chip crunch' },
        { date: '2023-05-25', label: 'Bùng nổ AI' },
        { date: '2024-06-10', label: 'Split 10:1' },
      ],
    },
    XAUUSD: {
      name: 'Vàng quốc tế',
      story: 'Vàng — kho trú ẩn truyền thống qua mọi cơn bão kinh tế. Đợt lạm phát 2022-2024 đẩy giá vàng lên đỉnh lịch sử. Lợi nhuận thực khiêm tốn hơn cổ phiếu nhưng biến động ít hơn nhiều.',
      events: [
        { date: '2020-03-16', label: 'COVID — vàng bán tháo' },
        { date: '2020-08-07', label: 'Đỉnh $2050' },
        { date: '2024-03-01', label: 'ATH mới $2100+' },
      ],
    },
    VNM: {
      name: 'Vinamilk',
      story: 'Cổ phiếu sữa quốc dân — từng là "vua" bluechip VN với cổ tức đều đặn. Nhưng 5 năm gần đây giá gần như đi ngang: tăng trưởng chậm lại, cạnh tranh gắt. Bài học: doanh nghiệp tốt chưa chắc là cổ phiếu tốt nếu mua ở định giá cao.',
      events: [
        { date: '2017-04-03', label: 'Đỉnh sóng bluechip' },
        { date: '2020-03-01', label: 'COVID bán tháo' },
        { date: '2022-06-01', label: 'Vùng đáy nhiều năm' },
      ],
    },
    SJC: {
      name: 'Vàng SJC',
      story: 'Vàng miếng SJC — kênh giữ tài sản truyền thống của người Việt. Có chênh lệch mua/bán (spread) lớn: vừa mua đã "lỗ" ngay vài phần trăm. Giá SJC còn bị đẩy cao hơn vàng thế giới do khan hiếm nguồn cung trong nước.',
      events: [
        { date: '2020-08-07', label: 'Sóng vàng COVID' },
        { date: '2024-04-01', label: 'SJC vượt 80 triệu/lượng' },
      ],
    },
    DJT: {
      name: 'Trump Media',
      story: 'Trump Media niêm yết 2024 sau sáp nhập SPAC — cổ phiếu biến động cực mạnh theo tin tức chính trị. Dữ liệu chỉ từ 2024. Rủi ro cao, đầu cơ thuần túy.',
      events: [
        { date: '2024-03-26', label: 'Niêm yết NASDAQ' },
        { date: '2024-11-05', label: 'Bầu cử Trump thắng' },
      ],
    },
    SAVINGS: {
      name: 'Gửi tiết kiệm',
      story: 'Lãi suất tiết kiệm ~6%/năm — không mất vốn, không cần theo dõi, nhưng lợi nhuận thực âm khi lạm phát cao. Đây là baseline để so sánh: mọi tài sản khác phải đánh bại con số này mới đáng mạo hiểm.',
      events: [],
    },
    CPI: {
      name: 'Lạm phát VN',
      story: 'Chỉ số CPI Việt Nam — dùng để tính lợi nhuận thực (real return). Bật "Lợi nhuận thực" để xem sau khi trừ lạm phát bạn thực sự kiếm được bao nhiêu.',
      events: [
        { date: '2022-06-01', label: 'Lạm phát đỉnh 2022' },
      ],
    },
  };

  // ─── Helpers ────────────────────────────────────────────────────────────────

  /**
   * Attempt to fetch a JSON file. Returns parsed object or null on failure.
   */
  async function tryFetch(url) {
    try {
      const resp = await fetch(url);
      if (!resp.ok) return null;
      return await resp.json();
    } catch (e) {
      console.warn('[data.js] Could not load', url, '—', e.message);
      return null;
    }
  }

  /**
   * Merge mock meta with real meta (real takes precedence, but mock fills gaps).
   */
  function mergeMeta(real) {
    if (!real) return MOCK_META;
    return {
      ...MOCK_META,
      ...real,
      // When real meta exists, assets & presets come ENTIRELY from real — mock is
      // only a fallback when real is missing them. This prevents mock-only entries
      // (e.g. the "Drama" demo preset, Trump Media) from leaking into the real UI.
      assets:  (real.assets  && Object.keys(real.assets).length)  ? real.assets  : MOCK_META.assets,
      presets: (real.presets && Object.keys(real.presets).length) ? real.presets : MOCK_META.presets,
      fees: { ...MOCK_META.fees, ...(real.fees || {}) },
    };
  }

  /**
   * Merge mock insights with real insights.
   */
  function mergeInsights(real) {
    if (!real) return MOCK_INSIGHTS;
    return { ...MOCK_INSIGHTS, ...real };
  }

  // ─── Main loader ─────────────────────────────────────────────────────────────

  window.dataReady = (async function () {
    // Attempt to load all three pipeline files in parallel.
    const [realData, realMeta, realInsights] = await Promise.all([
      tryFetch('./data/data.json'),
      tryFetch('./data/meta.json'),
      tryFetch('./data/insights.json'),
    ]);

    let dates, series;

    if (realData && realData.dates && realData.series) {
      // Full pipeline data available.
      dates  = realData.dates;
      series = realData.series;
      console.info('[data.js] Loaded real data.json —', dates.length, 'trading days');
    } else {
      // Fallback: try sample-data.json, then use empty mock.
      console.warn('[data.js] data.json missing or malformed — loading sample-data.json');
      const sample = await tryFetch('./data/sample-data.json');
      if (sample && sample.dates && sample.series) {
        dates  = sample.dates;
        series = sample.series;
        console.info('[data.js] Loaded sample-data.json —', dates.length, 'points');
      } else {
        // Last resort: minimal inline stub so the page never shows blank.
        console.warn('[data.js] sample-data.json also missing — using hardcoded stub');
        dates  = ['2016-01-04','2020-01-02','2024-01-02','2026-04-01'];
        series = {
          NVDA:      [150000,   450000,   1500000,  3900000],
          VNM:       [120000,   115000,   125000,   118000],
          XAUUSD:    [42500000, 52800000, 66800000, 103800000],
          SJC:       [43000000, 54000000, 68000000, 105000000],
          'SJC__buy':[44720000, 56160000, 70720000, 109200000],
          SAVINGS:   [1000000,  1268000,  1696000,  2063000],
          CPI:       [100000,   115800,   140200,   158100],
        };
      }
    }

    const meta     = mergeMeta(realMeta);
    const insights = mergeInsights(realInsights);

    // Build a fast date → index lookup map.
    const dateIndex = Object.create(null);
    for (let i = 0; i < dates.length; i++) dateIndex[dates[i]] = i;

    return { dates, series, meta, insights, dateIndex };
  })();

})();
