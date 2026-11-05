"""Demo 3 endpoints: fridges and freezers."""
from fastapi import APIRouter, HTTPException

from backend.app.db import store

router = APIRouter(prefix="/api/cold-chain", tags=["cold chain"])


@router.get("")
async def list_units():
    return [store.cold_view(u) for u in store.units]


@router.get("/{unit}/history")
async def unit_history(unit: str):
    """Last 60 simulated minutes of temperature and door readings."""
    if unit not in store.units:
        raise HTTPException(404, f"unknown unit {unit}")
    return [{"ts": p["ts"], "temp_c": p["temp_c"], "door_open": p["door_open"]}
            for p in store.history_of(store.units[unit]["device_id"])]
