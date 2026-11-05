"""Demo 1 endpoints: guest rooms."""
from fastapi import APIRouter, HTTPException

from backend.app.db import store

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


def check(room):
    if room not in store.rooms:
        raise HTTPException(404, f"unknown room {room}")


@router.get("")
async def list_rooms():
    return [store.room_view(r) for r in store.rooms]


@router.get("/{room}")
async def get_room(room: str):
    check(room)
    return store.room_view(room)


@router.get("/{room}/history")
async def room_history(room: str):
    """Last 60 simulated minutes of readings."""
    check(room)
    return store.history_of(f"thermo-{room}")
