"""Glue between the live store and the AI engine (not in the brief's file list: it keeps
main.py small and gives the alerts API one shared AlertManager).

Every time the simulated clock moves on a minute:
  1. copy the recent readings (on the asyncio thread, where the store lives)
  2. run the detector in a worker thread (pandas + scikit-learn take ~0.1 s)
  3. hand the findings to the alert manager (back on the asyncio thread)
"""
import asyncio

from ai_engine.alert_manager import AlertManager
from ai_engine.detector import Detector
from ai_engine.model_loader import load_models
from backend.app.db import load_yaml, store

_rules = load_yaml("alert_rules.yaml")
detector = Detector(_rules, store.devices, load_models())
manager = AlertManager(store, _rules["escalation"]["critical_unacked_min"],
                       _rules["escalation"]["resolve_after_min"])


async def detection_loop():
    last = None
    while True:
        await asyncio.sleep(0.5)
        if store.sim_now is None or store.sim_now == last:
            continue
        await asyncio.sleep(0.3)               # let the rest of this minute's readings arrive
        last = now = store.sim_now
        histories = {did: list(h) for did, h in store.history.items()}
        silent = store.silent_devices()
        try:
            findings, eta = await asyncio.to_thread(detector.detect, histories, silent)
        except Exception as e:                 # a bad model or reading must never stop monitoring
            print(f"[ai] detection failed: {e!r}")
            continue
        store.breach_eta = eta
        manager.process(findings, now)
