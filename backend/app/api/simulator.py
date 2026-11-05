"""Demo-mode fault buttons: forwards requests to the simulator's HTTP API.

Not in the brief's file list: the dashboard's fault simulator bar needs it, and going
through the backend means the browser never talks to the simulator directly.
Disabled (404) when DEMO_MODE=false.
"""
import json
import os
import urllib.error
import urllib.request
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field


def demo_only():
    if os.getenv("DEMO_MODE", "true").lower() == "false":
        raise HTTPException(404, "not found")


router = APIRouter(prefix="/api/sim", tags=["simulator"], dependencies=[Depends(demo_only)])

FaultType = Literal["leak", "compressor_failure", "door_left_open", "hvac_stuck_on", "sensor_offline"]


class FaultRequest(BaseModel):
    type: FaultType
    target: str | None = Field(default=None, max_length=64)   # default target chosen by the simulator


class ClearRequest(BaseModel):
    target: str | None = Field(default=None, max_length=64)   # None = clear all faults


class PauseRequest(BaseModel):
    paused: bool | None = None                                 # None = toggle


def call_simulator(path, body=None):
    url = os.getenv("SIMULATOR_URL", "http://localhost:8001") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:                        # e.g. fault doesn't apply to target
        raise HTTPException(e.code, json.loads(e.read() or b"{}").get("error", "simulator error"))
    except OSError:
        raise HTTPException(503, "simulator is not running")


@router.get("/status")
def status():
    return call_simulator("/status")


@router.post("/faults")
def inject(req: FaultRequest):
    return call_simulator("/faults", req.model_dump(exclude_none=True))


@router.post("/clear")
def clear(req: ClearRequest | None = None):
    return call_simulator("/clear", (req or ClearRequest()).model_dump(exclude_none=True))


@router.post("/pause")
def pause(req: PauseRequest | None = None):
    return call_simulator("/pause", (req or PauseRequest()).model_dump(exclude_none=True))
