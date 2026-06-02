# Stock Time Machine — Mô phỏng DCA / Lump-sum "Nhìn lại quá khứ"

> Nếu từ 2016 đến nay bạn đầu tư đều đặn (DCA) hoặc bỏ một cục tiền (Lump-sum) vào một tài sản,
> **hôm nay bạn có bao nhiêu tiền?** App web tĩnh, tương tác, trả lời câu hỏi đó bằng **con số THẬT** —
> đã gồm cổ tức, chia tách, cổ phiếu thưởng, tỷ giá, phí giao dịch và chênh lệch mua/bán (spread).

Kèm theo mỗi mã là một **câu chuyện ngắn** + **mốc sự kiện trên đồ thị** để dễ đọc, dễ hiểu, dễ chia sẻ.

---

## Tính năng chính

- **Hai chế độ:** DCA (đầu tư đều hằng tháng) và Lump-sum (mua một lần rồi giữ).
- **Con số chính xác:** quy hết về VND ngay trong pipeline (× tỷ giá từng ngày, làm tròn số nguyên),
  dùng giá đã điều chỉnh (Adjusted Close) nên cổ tức / split / cổ phiếu thưởng đã được tính sẵn.
- **Tính phí & thuế thật:** CP Việt Nam ~0,15% mua/bán + thuế bán 0,1%; CP Mỹ ~0% commission +
  spread đổi VND↔USD; vàng SJC có **chênh lệch mua/bán** (mua vào đắt, định giá theo giá bán rẻ →
  vừa mua đồ thị đã hụt, đúng thực tế).
- **So sánh công bằng:** mã lên sàn muộn chỉ DCA **từ ngày có giá** (không gom tiền mặt chờ),
  nên dùng **% lãi/vốn** và **CAGR** để so sánh giữa các mã.
- **Lợi nhuận thực:** trừ lạm phát (CPI) để biết sức mua thật sự tăng hay giảm.
- **Đường tham chiếu:** Bitcoin, S&P 500, VN-Index, gửi tiết kiệm ~6%/năm, lạm phát VN.
- **Presets 1-click:** "Sóng AI", "Crypto & MSTR", "Drama VN", "Siêu lợi nhuận", "Vàng & an toàn".
- **Câu chuyện cổ phiếu:** panel story hiện theo ngữ cảnh + mốc sự kiện trên timeline (bật/tắt được).
- **~42 tài sản** chia 5 tier (US, VN, hàng hóa, macro, drama, siêu tăng trưởng) — cấu hình bằng 1 file.

---

## Cách chạy

### 1. Cập nhật dữ liệu (pipeline Python)

Yêu cầu Python 3.12. Cài thư viện đã ghim version:

```bash
"C:\Program Files\Python312\python.exe" -m pip install -r requirements.txt
```

Chạy toàn bộ pipeline (fetch → quy VND → ghép trục thời gian → xuất `data.json` + `meta.json`):

```bash
"C:\Program Files\Python312\python.exe" scripts/update_data.py
```

Pipeline sẽ in phạm vi ngày và số dòng của từng mã để bạn kiểm tra. Kết quả ghi vào
`data/processed/data.json` và `data/processed/meta.json`. (File `web/data/insights.json`
là nội dung biên tay, **không** bị pipeline ghi đè.)

### 2. Mở web (chạy local)

App là web tĩnh, nhưng cần phục vụ qua HTTP để fetch được file JSON (mở trực tiếp `file://`
sẽ bị chặn CORS). Từ thư mục `web/`:

```bash
cd web
"C:\Program Files\Python312\python.exe" -m http.server 8000
```

Rồi mở trình duyệt tại **http://localhost:8000**.

### 3. Deploy GitHub Pages

App chỉ là HTML/CSS/JS tĩnh nên deploy rất gọn:

1. Push toàn bộ repo lên GitHub.
2. Vào **Settings → Pages**.
3. Chọn **Source: Deploy from a branch**, **Branch:** `main`, **Folder:** `/web`
   (nếu GitHub Pages không cho chọn thư mục con, có thể chuyển nội dung `web/` ra gốc,
   hoặc dùng một workflow Pages để publish thư mục `web/`).
4. Lưu lại; sau ít phút app sẽ chạy tại `https://<tài-khoản>.github.io/<repo>/`.

Lưu ý: GitHub Pages chỉ phục vụ **file tĩnh** — toàn bộ dữ liệu phải được build sẵn bằng pipeline
ở máy local rồi commit (`data/processed/*.json` và `web/data/*.json`). Pages **không** chạy Python.

---

## Nguồn dữ liệu & lưu ý độ chính xác

| Nhóm tài sản | Nguồn | Trường lấy | Ghi chú |
|---|---|---|---|
| CP Mỹ, BTC, S&P 500 | yfinance | Adjusted Close (`auto_adjust=True`) | tự gộp split + cổ tức (total return) |
| Vàng / bạc quốc tế | Stooq (`xauusd`, `xagusd`) | Close spot | miễn phí; fallback yfinance `GC=F` / `SI=F` |
| CP Việt Nam, VN-Index | vnstock3 (VCI/TCBS) | giá **đã điều chỉnh** | gộp cổ tức + cổ phiếu thưởng + split |
| Vàng SJC | CafeF (scrape, BeautifulSoup) | giá mua vào & bán ra | **try-catch + fallback giá hôm trước** (xem caveat) |
| USD/VND | yfinance `USDVND=X` | Close | tỷ giá **liên ngân hàng** (xem caveat) |
| Lạm phát VN | World Bank `FP.CPI.TOTL` | CPI năm (nội suy theo ngày) | số liệu chính thức |
| Lãi tiết kiệm | cấu hình (mặc định 6%/năm) | — | xấp xỉ, không phải lãi suất một ngân hàng cụ thể |
| Mã đã hủy niêm yết (ROS…) | **CSV thủ công** (CafeF/FireAnt) | Close | đọc `data/raw/manual/<MÃ>.csv`, **KHÔNG gọi API** |

### Caveats (đọc kỹ)

- **Vàng SJC:** giá được **scrape từ CafeF** nên có thể đổi cấu trúc HTML bất cứ lúc nào. Pipeline đã
  bọc try-catch và **fallback về giá hôm trước** để không làm sập cả quá trình, nhưng đây vẫn là nguồn
  kém ổn định nhất. Chênh lệch mua/bán được giữ nguyên (mua đắt, bán rẻ).
- **USD/VND:** dùng tỷ giá **liên ngân hàng** từ yfinance. Tỷ giá bán USD tại quầy ngân hàng (VD Vietcombank)
  thường cao hơn ~1-2%; mô phỏng đã tách riêng `usd_vnd_spread` (~1%) khi mua tài sản định giá bằng USD.
- **ROS (FLC Faros) và mã hủy niêm yết:** vnstock không còn trả lịch sử các mã đã hủy niêm yết, nên dữ liệu
  được nạp **thủ công từ CSV** đặt tại `data/raw/manual/ROS.csv`. Đây là nguồn cần tự cập nhật/kiểm chứng.
- **DJT (Trump Media):** chỉ có dữ liệu từ 2024 (trước đó là SPAC mã DWAC) → chuỗi ngắn. **VTP/VGI** (họ Viettel)
  có dữ liệu UPCoM từ khoảng 2018. Mã lên sàn muộn để `null` ở đầu chuỗi và **chỉ DCA từ ngày đầu có giá**.
- **Lãi tiết kiệm 6%/năm** chỉ là con số xấp xỉ tham chiếu; **phí/thuế** đều cấu hình được trong `pipeline/config.py`.
- **GitHub Actions auto-update (tùy chọn, dễ gãy):** nếu bật workflow cập nhật tự động, lưu ý yfinance hay
  bị Yahoo chặn IP của trung tâm dữ liệu, vnstock có thể bị geo-block khi chạy từ runner ngoài Việt Nam,
  và scrape CafeF dễ hỏng. Vì vậy **chạy `update_data.py` ở máy local là nguồn dữ liệu chuẩn**; workflow chỉ
  nên đóng vai trò phụ và cảnh báo khi thất bại.

---

## Thêm một mã mới

Chỉ cần 2 bước:

1. **Thêm 1 dòng vào `pipeline/config.py`** trong dict `ASSETS`, ví dụ:

   ```python
   "AAPL": dict(name="Apple", market="US", type="stock", source="yfinance", ticker="AAPL", tier=4),
   ```

   - `source`: `yfinance` (Mỹ/crypto/index) · `stooq` (vàng/bạc quốc tế) · `vnstock` (CP VN) ·
     `cafef_sjc` (vàng SJC) · `manual` (mã hủy niêm yết, đọc CSV) · `worldbank` (macro) · `computed` (chuỗi tổng hợp).
   - Mã hủy niêm yết: đặt thêm file `data/raw/manual/<MÃ>.csv` (cột `Date`, `Close`).

2. **Thêm story vào `web/data/insights.json`** với đúng key:

   ```json
   "AAPL": {
     "name": "Apple",
     "story": "2-4 câu tiếng Việt: drama + bài học, đọc nhanh.",
     "events": [ { "date": "YYYY-MM-DD", "label": "Mốc sự kiện" } ]
   }
   ```

   Nếu không chắc một ngày/sự kiện, **để `events` rỗng** thay vì ghi sai — độ chính xác quan trọng hơn.

Sau đó chạy lại `scripts/update_data.py` để build lại dữ liệu.

---

## Cấu trúc thư mục

```
D:\Stock\
├─ README.md · requirements.txt · LICENSE · .gitignore
├─ pipeline/   config.py · fetch_*.py · normalize.py
├─ scripts/    update_data.py
├─ data/       raw/ · raw/manual/ (ROS.csv…) · processed/ (data.json + meta.json)
└─ web/        index.html · css/ · js/ · data/ (data.json · meta.json · insights.json)
```

---

## Miễn trừ trách nhiệm

Đây là **công cụ nhìn lại quá khứ để tham khảo và học hỏi**, KHÔNG phải khuyến nghị đầu tư.
Hiệu suất trong quá khứ **không** đảm bảo cho tương lai. Dữ liệu được tổng hợp từ nhiều nguồn miễn phí
và có thể chứa sai số (đặc biệt vàng SJC, tỷ giá và các mã hủy niêm yết). Hãy tự kiểm chứng trước khi
ra bất kỳ quyết định tài chính nào. Các phần "câu chuyện cổ phiếu" do người viết biên soạn dựa trên
thông tin công khai và có thể được chỉnh sửa trong `web/data/insights.json`.

---

## Giấy phép

Phát hành theo giấy phép [MIT](LICENSE) © 2026 Andrew Hayes (Hồ Gia Cường).
