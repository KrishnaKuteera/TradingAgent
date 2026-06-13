"""Constants and configuration shared across all modules."""

from pathlib import Path

# Root folder (parent of src/) — resolves to PortfolioReport/
FOLDER      = Path(__file__).parent.parent
CONFIG_DIR  = FOLDER / "Config"
DATA_DIR    = FOLDER / "Data"
REPORTS_DIR = FOLDER / "Reports"

ACCOUNT_LABELS = {
    "52854708": "RESP",
    "53224816": "Spousal RRSP",
    "53417370": "RRSP",
    "53718281": "TFSA",
    "29232920": "Margin",
    "53076602": "RRSP",
    "53718191": "TFSA",
}

# Chandu and Nandu account numbers
CHANDU_ACCOUNTS = ["52854708", "53224816", "53417370", "53718281"]  # RESP, Spousal RRSP, RRSP, TFSA
NANDU_ACCOUNTS  = ["29232920", "53076602", "53718191"]              # Margin, RRSP, TFSA

SECTOR_COLORS = {
    "Technology":             "#4e79a7",
    "Semiconductors":         "#00bcd4",
    "Healthcare":             "#e15759",
    "Financial Services":     "#f28e2b",
    "Consumer Cyclical":      "#59a14f",
    "Consumer Defensive":     "#76b7b2",
    "Energy":                 "#e7b84b",
    "Industrials":            "#b07aa1",
    "Basic Materials":        "#9c755f",
    "Real Estate":            "#d37295",
    "Communication Services": "#bab0ac",
    "Utilities":              "#ff9da7",
    "Commodities":            "#f0c040",
    "Aerospace & Defense":    "#8cd17d",
    "Cash":                   "#c9f0cd",
    "Hedge":                  "#c084fc",
    "Unknown":                "#dddddd",
}

# yfinance uses different ticker symbols for some Canadian listings
YF_TICKER_MAP = {
    "VFV":   "VFV.TO",
    "VIU":   "VIU.TO",
    "CGL.C": "CGL-C.TO",
    "ZXLE":  "ZXLE.TO",
}

# Symbols always classified as ETF regardless of suffix
ETF_SYMBOLS = {"VFV", "VIU", "VOO", "GLD", "CGL.C", "ZXLE", "CASH", "DRAM", "NASA", "SOXX", "VOLT", "XSW"}

# Normalize yfinance sectorWeightings keys → display names
SECTOR_NAMES = {
    "realestate":             "Real Estate",
    "consumer_cyclical":      "Consumer Cyclical",
    "technology":             "Technology",
    "healthcare":             "Healthcare",
    "financial_services":     "Financial Services",
    "energy":                 "Energy",
    "basic_materials":        "Basic Materials",
    "industrials":            "Industrials",
    "utilities":              "Utilities",
    "communication_services": "Communication Services",
    "consumer_defensive":     "Consumer Defensive",
}
