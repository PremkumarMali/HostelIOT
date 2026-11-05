"""Pydantic schemas for every MQTT telemetry payload.

The "type" field picks the schema (thermostat / water / cold_chain).
Out-of-range values (e.g. humidity 140 %) are rejected, so bad sensor data
never reaches the database. Unknown extra fields are ignored.
"""
from typing import Annotated, Literal, Union

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter

Percent = Annotated[float, Field(ge=0, le=100)]


class Reading(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)   # a broken sensor sending NaN is rejected
    device_id: str = Field(min_length=1, max_length=64)
    ts: AwareDatetime                     # must include a timezone, e.g. +05:30
    battery_pct: Percent


class ThermostatReading(Reading):
    type: Literal["thermostat"]
    room: str
    temp_c: float = Field(ge=-10, le=60)
    setpoint_c: float = Field(ge=10, le=35)
    humidity_rh: Percent
    occupied: bool
    vacant_min: int = Field(ge=0)
    hvac_on: bool
    hvac_kw: float = Field(default=0.0, ge=0, le=10)   # optional: the ESP32 node has no power meter
    pms_sold: bool


class WaterReading(Reading):
    type: Literal["water"]
    zone: str
    flow_lpm: float = Field(ge=0, le=500)
    leak_wet: bool


class ColdChainReading(Reading):
    type: Literal["cold_chain"]
    unit: str
    temp_c: float = Field(ge=-40, le=40)
    door_open: bool
    safe_min_c: float
    safe_max_c: float


AnyReading = Annotated[Union[ThermostatReading, WaterReading, ColdChainReading],
                       Field(discriminator="type")]
_adapter = TypeAdapter(AnyReading)

# Influx table per device type, and the payload field that becomes the location tag
TABLE = {"thermostat": "room", "water": "water", "cold_chain": "cold_chain"}
LOCATION_FIELD = {"thermostat": "room", "water": "zone", "cold_chain": "unit"}


def parse(raw: bytes | str) -> Reading:
    """JSON bytes -> validated reading. Raises pydantic.ValidationError if invalid."""
    return _adapter.validate_json(raw)
