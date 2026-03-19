"""
IAEA / OE-III tracker and NOTAM routes.
"""

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from agents.iaea_tracker import fetch_notams, run_iaea_tracker

router = APIRouter()


@router.get("/iaea-tracker")
async def get_iaea_tracker():
    """
    GET /api/iaea-tracker
    Multisensor-Fusion für IAEO/OE-III (Rafael Grossi):
    - ADS-B: OE-III per Registration + ICAO-Hex (OEIII_ICAO_HEX), Boden-Modus, ORER-Erkennung.
    - NOTAMs: Autorouter.aero (NOTAM_API_URL).
    - Flugplan-Status: optional IAEA_FLIGHTPLAN_STATUS_URL.
    - IAEA-Press: RSS, Filter Grossi/DG; Cache TTL (IAEA_CACHE_TTL_MINUTES).
    - Telegram: optional IAEA_TELEGRAM_CHANNELS (Erbil/Kurdistan).
    Antwort: oeiii_adsb, notams, flight_plan_status, iaea_press_grossi,
    iaea_telegram_signals, ground_ops_signals, correlation_notes (hint + confidence), summary.
    """
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, run_iaea_tracker)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/notam")
async def get_notam(
    locations: str = "EDDS,LOWW,OIIE",
    limit: int = 10,
    offset: int = 0,
):
    """
    GET /api/notam?locations=EDDS,LOWW,OIIE&limit=10&offset=0
    NOTAMs für ICAO-Plätze (Autorouter.aero: itemas=["EDDS",...], offset, limit).
    """
    icao_list = [s.strip().upper() for s in locations.split(",") if s.strip()][:20]
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: fetch_notams(icao_locations=icao_list or None, limit=limit, offset=offset),
        )
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
