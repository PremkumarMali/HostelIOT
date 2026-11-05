"""Demo 2 endpoints: water zones."""
from fastapi import APIRouter

from backend.app.db import store

router = APIRouter(prefix="/api/water", tags=["water"])


@router.get("")
async def list_zones():
    return [store.water_view(z) for z in store.zones]


@router.get("/history")
async def water_history():
    """Last 60 simulated minutes: total flow, plus flow per zone."""
    return {
        "total": store.water_total_history(),
        "zones": {z: [{"ts": p["ts"], "flow_lpm": p["flow_lpm"], "leak_wet": p["leak_wet"]}
                      for p in store.history_of(cfg["device_id"])]
                  for z, cfg in store.zones.items()},
    }
