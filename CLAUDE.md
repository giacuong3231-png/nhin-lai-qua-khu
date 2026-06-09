# CLAUDE.md — Project "Nhìn lại quá khứ"

App backtest DCA / Lump-sum. Live: https://giacuong3231-png.github.io/nhin-lai-qua-khu/
Pipeline Python (`pipeline/`) → `data/processed/*.json` → web tĩnh (`web/`, ECharts + Alpine).
Windows: chạy pipeline với `$env:PYTHONUTF8=1`.

---

## Harness: UX & dữ liệu mã

**Mục tiêu:** cải thiện app liên tục — feedback UX qua panel persona + quản lý mã dễ dàng.

**Trigger:** việc liên quan **review UX / feedback người dùng / "đóng vai người dùng" / đề xuất tính năng-insight / thêm-sửa-xoá mã** (kể cả follow-up "chạy lại feedback", "thêm mã X") → dùng skill **`stock-harness`** (orchestrator). Câu hỏi đơn giản trả lời trực tiếp.

Agents & skills chi tiết ở `.claude/agents/` và `.claude/skills/` — orchestrator tự điều phối.

**Change log:**
| Ngày | Thay đổi | Đối tượng | Lý do |
|------|----------|-----------|-------|
| 2026-06-08 | Khởi tạo harness: 3 agents (persona-ux-reviewer, feedback-synthesizer, ticker-manager) + 3 skills (persona-ux-review, add-ticker, stock-harness) | toàn bộ | build mới — Goal 1 feedback persona, Goal 2 quản lý mã |
