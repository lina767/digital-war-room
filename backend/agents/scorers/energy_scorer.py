from typing import Any, Dict, List, Optional


EXPOSED_COUNTRIES = ["Egypt", "Yemen", "Somalia", "Djibouti", "Ethiopia", "Sudan"]
GLOBAL_IMPACT_OIL_THRESHOLD_PCT = 2.0


def compute_food_security_risk(
    food_commodities: List[Dict[str, Any]],
    fao_fpi: Dict[str, Any],
    fertilizer: Dict[str, Any],
) -> float:
    base = 20.0
    for c in food_commodities:
        raw = c.get("change_pct_raw")
        if raw is not None and abs(raw) > 10:
            base += 20
        elif raw is not None and abs(raw) > 5:
            base += 10
        elif raw is not None and abs(raw) > 3:
            base += 5
    yoy = fao_fpi.get("yoy_change_pct")
    if yoy is not None:
        if yoy > 15:
            base += 25
        elif yoy > 10:
            base += 15
        elif yoy > 5:
            base += 8
    urea = fertilizer.get("urea_price")
    dap = fertilizer.get("dap_price")
    if urea and urea > 400:
        base += 10
    if dap and dap > 700:
        base += 10
    return min(100.0, max(0.0, base))


def compute_energy_score(commodities: List[Dict[str, Any]]) -> float:
    base = 30.0
    for c in commodities:
        raw = c.get("change_pct_raw")
        if raw is not None and abs(raw) > 10:
            base += 15
        elif raw is not None and abs(raw) > 5:
            base += 8
    return min(100.0, max(0.0, base))


def build_energy_summary(
    commodities: List[Dict[str, Any]],
    food_commodities: List[Dict[str, Any]],
    fao_fpi: Dict[str, Any],
    food_risk: float,
    conflict: str = "",
    wb_country: Optional[Dict[str, Any]] = None,
) -> str:
    parts = []
    valid_c = [c for c in commodities if c.get("price") and "error" not in c]
    if valid_c:
        parts.append("Oil: " + ", ".join(f"{c.get('symbol', '')} {c.get('change_pct', '')}" for c in valid_c[:2]))
    valid_food = [c for c in food_commodities if c.get("price") and "error" not in c]
    if valid_food:
        parts.append("Food: " + ", ".join(f"{c.get('symbol', '')} {c.get('change_pct', '')}" for c in valid_food[:3]))
    fpi_val = fao_fpi.get("index")
    if fpi_val:
        yoy = fao_fpi.get("yoy_change_pct")
        yoy_str = f" ({yoy:+.1f}% YoY)" if yoy is not None else ""
        parts.append(f"FAO FPI: {fpi_val:.1f}{yoy_str}")
    if food_risk >= 60:
        parts.append(f"Food security risk: {food_risk:.0f}/100 (exposed: {', '.join(EXPOSED_COUNTRIES[:3])})")
    if wb_country and wb_country.get("indicators") and not wb_country.get("error"):
        iso = wb_country.get("country_iso3") or "?"
        lines = []
        for ind in wb_country.get("indicators") or []:
            if ind.get("error"):
                continue
            v = ind.get("value")
            if v is None:
                continue
            lbl = ind.get("key") or ind.get("label") or ""
            d = ind.get("date") or ""
            lines.append(f"{lbl} {v:.1f}" + (f" ({d})" if d else ""))
        if lines:
            parts.append(f"WB macro ({iso}): " + "; ".join(lines[:6]))
    if not parts:
        return "ENERGY: No commodity data (set EIA_API_KEY/FRED_API_KEY for oil/food, or ALPHAVANTAGE_API_KEY)."
    out = "ENERGY: " + " ".join(parts)
    if conflict and "iran" in conflict.lower():
        max_up = max(
            (c.get("change_pct_raw") for c in valid_c if c.get("change_pct_raw") is not None),
            default=None,
        )
        if max_up is not None and max_up >= GLOBAL_IMPACT_OIL_THRESHOLD_PCT:
            out += " Global impact (Iran): Oil move may reflect Strait of Hormuz / chokepoint risk."
    return out


def build_global_impact_note(
    conflict: str,
    oil_commodities: List[Dict[str, Any]],
    food_risk: float,
    inflation_cpi_pct: Optional[float] = None,
    inflation_date_label: Optional[str] = None,
) -> Optional[str]:
    if not conflict or "iran" not in conflict.lower():
        return None
    valid_c = [
        c
        for c in oil_commodities
        if c.get("price") and "error" not in c and c.get("change_pct_raw") is not None
    ]
    max_up = max((c.get("change_pct_raw") for c in valid_c), default=None)
    global_impact_note = None
    if max_up is not None and max_up >= GLOBAL_IMPACT_OIL_THRESHOLD_PCT:
        pct_str = f"{max_up:+.1f}%"
        global_impact_note = f"Brent/WTI {pct_str} – potential Hormuz chokepoint risk premium"
    if food_risk >= 50 and not global_impact_note:
        global_impact_note = (
            f"Food security risk {food_risk:.0f}/100 – chokepoint disruption threatens "
            f"grain/fertilizer flows to {', '.join(EXPOSED_COUNTRIES[:3])}"
        )
    elif food_risk >= 50 and global_impact_note:
        global_impact_note += f"; Food security risk {food_risk:.0f}/100"
    if inflation_cpi_pct is not None:
        date_suffix = f" ({inflation_date_label})" if inflation_date_label else ""
        inflation_note = f"Inflation (CPI) {inflation_cpi_pct:+.1f}% YoY{date_suffix}"
        if global_impact_note:
            global_impact_note += f"; {inflation_note}"
        else:
            global_impact_note = inflation_note
    return global_impact_note
