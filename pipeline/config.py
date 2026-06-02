"""
config.py — Asset registry & simulation parameters for the DCA / Lump-sum backtest app.

This is the single source of truth for which assets exist, where their data comes from,
and the fee / preset configuration. Add a new ticker = add one entry to ASSETS.

source values:
    yfinance    -> US stocks / ETFs / crypto / index (Adjusted Close, total return)
    stooq       -> international spot metals (XAUUSD / XAGUSD)
    vnstock     -> Vietnamese stocks & VN-Index (adjusted prices: dividends, bonus, splits)
    cafef_sjc   -> SJC gold (scraped, has buy/sell spread)
    manual      -> delisted / hard-to-fetch tickers, read from data/raw/manual/<KEY>.csv
    worldbank   -> macro (CPI inflation)
    computed    -> synthesised series (e.g. bank savings growth index)
"""

START_DATE = "2016-01-01"
BASE_CURRENCY = "VND"

# key -> metadata. `ticker` is the symbol passed to the data source.
ASSETS = {
    # ---------- Tier 1: Core US stocks ----------
    "NVDA": dict(name="NVIDIA",            market="US", type="stock", source="yfinance", ticker="NVDA",   tier=1),
    "TSM":  dict(name="TSMC",              market="US", type="stock", source="yfinance", ticker="TSM",    tier=1),
    "PLTR": dict(name="Palantir",          market="US", type="stock", source="yfinance", ticker="PLTR",   tier=1, note="IPO 09/2020"),
    "MSTR": dict(name="MicroStrategy",     market="US", type="stock", source="yfinance", ticker="MSTR",   tier=1, note="Proxy ôm Bitcoin"),
    "TSLA": dict(name="Tesla",             market="US", type="stock", source="yfinance", ticker="TSLA",   tier=1),

    # ---------- Tier 1: Core VN stocks ----------
    "VIC":  dict(name="Vingroup",          market="VN", type="stock", source="vnstock",  ticker="VIC",    tier=1),
    "NVL":  dict(name="Novaland",          market="VN", type="stock", source="vnstock",  ticker="NVL",    tier=1, note="Niêm yết 12/2016"),
    "VNM":  dict(name="Vinamilk",          market="VN", type="stock", source="vnstock",  ticker="VNM",    tier=1),
    "HPG":  dict(name="Hòa Phát",          market="VN", type="stock", source="vnstock",  ticker="HPG",    tier=1),
    "FPT":  dict(name="FPT",               market="VN", type="stock", source="vnstock",  ticker="FPT",    tier=1),
    "MWG":  dict(name="Thế Giới Di Động",  market="VN", type="stock", source="vnstock",  ticker="MWG",    tier=1),

    # ---------- Tier 1: Commodities ----------
    "XAUUSD": dict(name="Vàng quốc tế",    market="GLOBAL", type="gold",   source="stooq",     ticker="xauusd", tier=1),
    "XAGUSD": dict(name="Bạc quốc tế",     market="GLOBAL", type="silver", source="stooq",     ticker="xagusd", tier=1),
    "SJC":    dict(name="Vàng SJC",        market="VN",     type="gold",   source="cafef_sjc", ticker="SJC",    tier=1, has_spread=True),

    # ---------- Tier 2: Reference / macro ----------
    "BTC":     dict(name="Bitcoin",        market="GLOBAL", type="crypto", source="yfinance",  ticker="BTC-USD", tier=2),
    "SPX":     dict(name="S&P 500",        market="US",     type="index",  source="yfinance",  ticker="^GSPC",   tier=2),
    "VNINDEX": dict(name="VN-Index",       market="VN",     type="index",  source="vnstock",   ticker="VNINDEX", tier=2),
    "SAVINGS": dict(name="Gửi tiết kiệm",  market="VN",     type="rate",   source="computed",  ticker="SAVINGS", tier=2, annual_rate=0.06),
    "CPI":     dict(name="Lạm phát VN",    market="VN",     type="macro",  source="worldbank", ticker="FP.CPI.TOTL", tier=2),

    # ---------- Tier 3: Drama ----------
    "ROS":  dict(name="FLC Faros",         market="VN", type="stock", source="manual",   ticker="ROS",  tier=3, note="Hủy niêm yết 2022 -> CSV manual"),
    "DIG":  dict(name="DIC Corp",          market="VN", type="stock", source="vnstock",  ticker="DIG",  tier=3),
    "STB":  dict(name="Sacombank",         market="VN", type="stock", source="vnstock",  ticker="STB",  tier=3),
    "QCG":  dict(name="Quốc Cường Gia Lai",market="VN", type="stock", source="vnstock",  ticker="QCG",  tier=3),
    "EIB":  dict(name="Eximbank",          market="VN", type="stock", source="vnstock",  ticker="EIB",  tier=3),
    "GME":  dict(name="GameStop",          market="US", type="stock", source="yfinance", ticker="GME",  tier=3),
    "SMCI": dict(name="Super Micro",       market="US", type="stock", source="yfinance", ticker="SMCI", tier=3),
    "DJT":  dict(name="Trump Media",       market="US", type="stock", source="yfinance", ticker="DJT",  tier=3, note="Data từ 2024 (trước là DWAC)", min_date="2024-03-26"),

    # ---------- Tier 4: Story / super-growth ----------
    "META": dict(name="Meta",              market="US", type="stock", source="yfinance", ticker="META", tier=4),
    "LLY":  dict(name="Eli Lilly",         market="US", type="stock", source="yfinance", ticker="LLY",  tier=4),
    "AMD":  dict(name="AMD",               market="US", type="stock", source="yfinance", ticker="AMD",  tier=4),
    "AVGO": dict(name="Broadcom",          market="US", type="stock", source="yfinance", ticker="AVGO", tier=4, note="Split 10:1 năm 2024"),
    "VRT":  dict(name="Vertiv",            market="US", type="stock", source="yfinance", ticker="VRT",  tier=4),
    "DGC":  dict(name="Hóa chất Đức Giang",market="VN", type="stock", source="vnstock",  ticker="DGC",  tier=4),
    "HAG":  dict(name="HAGL",              market="VN", type="stock", source="vnstock",  ticker="HAG",  tier=4),
    "SSI":  dict(name="SSI",               market="VN", type="stock", source="vnstock",  ticker="SSI",  tier=4),
    "VGI":  dict(name="Viettel Global",    market="VN", type="stock", source="vnstock",  ticker="VGI",  tier=4),
    "VTP":  dict(name="Viettel Post",      market="VN", type="stock", source="vnstock",  ticker="VTP",  tier=4),

    # ---------- Tier 5: Bonus (off by default) ----------
    "COIN": dict(name="Coinbase",          market="US", type="stock", source="yfinance", ticker="COIN", tier=5),
    "CELH": dict(name="Celsius",           market="US", type="stock", source="yfinance", ticker="CELH", tier=5),
    "NVO":  dict(name="Novo Nordisk",      market="US", type="stock", source="yfinance", ticker="NVO",  tier=5),
    "L14":  dict(name="Licogi 14",         market="VN", type="stock", source="vnstock",  ticker="L14",  tier=5),
    "PNJ":  dict(name="PNJ",               market="VN", type="stock", source="vnstock",  ticker="PNJ",  tier=5),
}

# Transaction fees / taxes (configurable; reflected in the simulator).
FEES = {
    "vn_buy":         0.0015,   # phí mua CP VN ~0.15%
    "vn_sell":        0.0015,   # phí bán CP VN ~0.15%
    "vn_sell_tax":    0.001,    # thuế bán CP VN 0.1%
    "us_buy":         0.0,      # CP Mỹ ~0 commission
    "us_sell":        0.0,
    "usd_vnd_spread": 0.01,     # spread khi đổi VND<->USD (~1%), áp khi mua tài sản USD
}

# Curated comparison sets — 1-click presets to reduce cognitive load on the UI.
PRESETS = {
    "Sóng AI":        ["NVDA", "AMD", "SMCI", "AVGO", "TSM", "VRT"],
    "Crypto & MSTR":  ["BTC", "MSTR", "COIN"],
    "Drama VN":       ["ROS", "DIG", "L14", "STB", "QCG"],
    "Siêu lợi nhuận": ["NVDA", "LLY", "DGC", "META", "BTC"],
    "Vàng & an toàn": ["XAUUSD", "SJC", "SAVINGS"],
}

# Default DCA / Lump-sum amounts (VND).
DEFAULTS = {
    "dca_monthly":   1_000_000,    # 1 triệu / tháng
    "lumpsum":     100_000_000,    # 100 triệu một lần
}
