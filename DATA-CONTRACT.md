# DATA CONTRACT — interface giữa pipeline (Python) và frontend (JS)

> Đọc kỹ file này trước khi code. Đây là hợp đồng cố định để pipeline và frontend ăn khớp.
> Mọi giá **quy về VND, số nguyên** (`.round(0)`), trên **một trục thời gian chung, theo ngày**.

## 1. `data/processed/data.json` (compact, columnar)

```jsonc
{
  "dates": ["2016-01-04", "2016-01-05", ...],   // ISO date, ngày giao dịch hợp nhất (union, sorted)
  "series": {
    "NVDA":     [12000, 12050, ...],   // giá VND / 1 đơn vị; null nếu chưa có dữ liệu (trước niêm yết)
    "SJC":      [...],                 // giá ĐỊNH GIÁ danh mục (bid = giá mua vào, rẻ hơn)
    "SJC__buy": [...],                 // giá MUA khi DCA (ask = giá bán ra, đắt hơn) — chỉ asset has_spread
    "SAVINGS":  [...],                 // chỉ số giá trị: 1 VND gửi tiết kiệm tích lũy lãi 6%/năm
    "CPI":      [...]                  // chỉ số CPI nội suy theo ngày (để tính lợi nhuận thực)
  }
}
```

- Trục `dates`: hợp nhất mọi ngày giao dịch, **forward-fill** giá gần nhất cho ngày nghỉ của từng asset.
- `null` ở đầu chuỗi = asset chưa niêm yết (PLTR trước 09/2020, NVL trước 12/2016, DJT trước 2024, ...).
- Asset `has_spread=true` (chỉ SJC): có thêm khóa `"<KEY>__buy"`.

## 2. `data/processed/meta.json`

```jsonc
{
  "generated_at": "2026-06-02",
  "base_currency": "VND",
  "assets": {
    "NVDA": { "name": "NVIDIA", "market": "US", "type": "stock",
              "source": "yfinance", "tier": 1, "first_date": "2016-01-04", "has_spread": false }
    // ... mọi key trong ASSETS
  },
  "presets": { "Sóng AI": ["NVDA","AMD",...], ... },
  "fees":    { "vn_buy": 0.0015, "vn_sell": 0.0015, "vn_sell_tax": 0.001, "us_buy": 0.0, "us_sell": 0.0, "usd_vnd_spread": 0.01 }
}
```

## 3. `web/data/insights.json` (do agent nội dung viết)

```jsonc
{
  "NVDA": {
    "name": "NVIDIA",
    "story": "2-4 câu: drama + bài học, đọc nhanh.",
    "events": [
      { "date": "2024-06-10", "label": "Chia tách 10:1" },
      { "date": "2023-05-25", "label": "Bùng nổ AI" }
    ]
  }
  // ... mọi key trong ASSETS
}
```

## 4. Quy tắc Simulator (chạy ở frontend, JS)

Đầu vào: `mode` (`dca` | `lumpsum`), `amount` (VND), `start`, `end`, danh sách `tickers`.

- **DCA**: từ `max(start, first_date)` đến `end`, mỗi tháng mua tại **ngày giao dịch đầu tiên ≥ mùng 1**.
  - `gia_mua = series["<KEY>__buy"]` nếu `has_spread`, ngược lại `series["<KEY>"]`.
  - `tien_rong = amount - phi_mua` (phí theo `market`: VN dùng `vn_buy`; US dùng `us_buy` + `usd_vnd_spread`).
  - `shares += tien_rong / gia_mua` (fractional, cho phép lẻ).
- **Lump-sum**: mua 1 lần tại `start` với toàn bộ `amount`.
- **Định giá hằng ngày**: `value[d] = shares * series["<KEY>"][d]` (SJC dùng giá bid → **lỗ spread ngay khi mua**).
- **Mã lên sàn muộn**: bỏ qua ngày `series == null` (không mua, không định giá). **DCA chỉ chạy từ ngày có giá** (không gom tiền mặt chờ).
- **Đường "vốn nạp"**: lũy kế tổng tiền đã bỏ vào (vẽ đè như video).
- **Metrics / asset**: vốn nạp, giá trị cuối, **% lãi/vốn**, **CAGR**, **max drawdown**;
  lợi nhuận thực `real[d] = value[d] / (CPI[d] / CPI[start])`.
- **Phí bán** (tùy chọn khi hiển thị "tiền về tay"): VN `vn_sell + vn_sell_tax`; US `us_sell`.

## 5. Ghi chú nguồn (độ chính xác)

- US/crypto/index: yfinance Adjusted Close (`auto_adjust=True`) — tự gộp split + cổ tức.
- VN: vnstock giá đã điều chỉnh — gộp cổ tức + cổ phiếu thưởng + split.
- Vàng/bạc quốc tế: Stooq spot; fallback yfinance `GC=F` / `SI=F`.
- SJC: scrape CafeF (bs4) + **try-catch, fallback giá hôm trước**, không để pipeline chết.
- **ROS** (hủy niêm yết): **KHÔNG gọi API** — đọc `data/raw/manual/ROS.csv`.
- USD/VND: yfinance `USDVND=X`.
