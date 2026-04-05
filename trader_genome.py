from functools import lru_cache

ASSET_CLASS_MAP = {
    "BTCUSDT": "crypto",
    "ETHUSDT": "crypto",
    "BNBUSDT": "crypto",
    "SOLUSDT": "crypto",
    "XRPUSDT": "crypto",
    "EURUSD": "forex",
    "GBPUSD": "forex",
    "USDJPY": "forex",
    "AUDUSD": "forex",
    "USDCAD": "forex",
    "USDCHF": "forex",
    "NZDUSD": "forex",
    "EURJPY": "forex",
    "GBPJPY": "forex",
    "EURGBP": "forex",
    "GOLD": "metals",
    "SILVER": "metals",
}

ROLE_LABELS = {
    "trend": "Trend Veteran",
    "reversal": "Mean Reversion Veteran",
    "scalp": "Scalp Executor",
    "breakout": "Breakout Hunter",
    "false_break": "False Break Detective",
    "session_guard": "Session Reader",
    "volatility": "Volatility Reader",
    "capital_preserver": "Capital Preserver",
    "no_trade": "No-Trade Guardian",
    "risk_architect": "Risk Architect",
}

ROLES = list(ROLE_LABELS.keys())
REGIME_FOCUS = ["trend", "mixed", "sideways", "all"]
ASSET_FOCUS = ["crypto", "forex", "metals", "all"]
SESSION_FOCUS = ["asia", "london", "newyork", "any"]
SENIORITY_LEVELS = ["senior", "principal"]

SENIORITY_WEIGHT = {
    "senior": 1.0,
    "principal": 1.15,
}


def asset_class_for(asset):
    return ASSET_CLASS_MAP.get(str(asset or "").upper(), "all")


def parse_session_bucket(analysis_time):
    try:
        text = str(analysis_time or "").strip()
        if ":" not in text:
            return "any"
        hour = int(text.split(":")[0])
    except Exception:
        return "any"

    if 0 <= hour <= 6:
        return "asia"
    if 7 <= hour <= 12:
        return "london"
    if 13 <= hour <= 18:
        return "newyork"
    return "asia"


@lru_cache(maxsize=1)
def build_trader_genome():
    profiles = []
    for role in ROLES:
        for regime in REGIME_FOCUS:
            for asset_focus in ASSET_FOCUS:
                for session in SESSION_FOCUS:
                    for seniority in SENIORITY_LEVELS:
                        ident = f"{seniority}_{role}_{regime}_{asset_focus}_{session}"
                        name = ROLE_LABELS.get(role, role.title())
                        profiles.append({
                            "id": ident,
                            "name": name,
                            "role": role,
                            "regime_focus": regime,
                            "asset_focus": asset_focus,
                            "session_focus": session,
                            "seniority": seniority,
                            "seniority_weight": SENIORITY_WEIGHT.get(seniority, 1.0),
                            "wealth_mindset": role in ("capital_preserver", "no_trade", "risk_architect", "session_guard"),
                            "veto_bias": role in ("capital_preserver", "no_trade", "risk_architect", "false_break"),
                        })
    return profiles
