# Demo script (viva / presentation, ~7 minutes)

Time runs fast on purpose: **1 hotel minute = 2 real seconds**, so 10 hotel minutes = 20 seconds.
The clock in the top-right is hotel time (IST).

## Before you start (5 min earlier)

```powershell
cd "D:\secrect\Hostel Iot Project"
docker compose up -d --build        # Docker Desktop must be running ("Engine running")
```

1. Open **http://localhost:8080** (full screen, browser zoom 90 % on a laptop).
2. Wait ~2 minutes so the charts fill (60 hotel minutes of history).
3. Press **Clear all** in the fault bar so you start with no faults.
4. Optional backup tab: http://localhost:8000/docs (API) and [ml/evaluation_report.md](../ml/evaluation_report.md).

If something misbehaves: `docker compose restart backend simulator`, wait 2 minutes.

## The story

| # | Do | Point at | Say |
|---|---|---|---|
| 1 | Nothing | Header, KPI strip | "One console for a 20-room hotel in Bengaluru. 30 sensors stream live over MQTT; the green pill means the AI is watching all of them." |
| 2 | Click a blue room, then a grey one | Floor map + room detail | "Demo 1, rooms: blue = guest in, light blue = sold but out, grey = unsold. When a guest leaves, the thermostat sets back to 26 °C after 10 minutes, which is where the energy saving on the KPI comes from." |
| 3 | Hover the water chart | Water panel | "Demo 2, water: total flow with the daily pattern, every zone against its normal flow, leak probes dry." |
| 4 | Hover a sparkline | Cold chain panel | "Demo 3, HACCP: each fridge must stay inside its green band. Compliance is the KPI." |
| 5 | Press **Water leak** | Toast top-right, Laundry row | Within ~2 s: "The leak probe is wet and the flow is 2.5x normal. The AI raised a **critical** alert: rule and Random Forest agree. The notification says the **section** (Water & leaks), the **exact place** (Laundry, Basement), what to do, and **who** should act: Chief Engineer, and the GM because it is critical." |
| 6 | Click the toast | Laundry row flashes | "Every notification jumps to the place where the fault is." |
| 7 | Wait ~20 s, don't acknowledge | "Escalated to GM" chip, new toast | "Nobody acknowledged for 10 hotel minutes, so it escalated to the General Manager automatically." Then press **Acknowledge**: "Acknowledged, escalation stops, and everyone sees who took it." |
| 8 | Press **Chiller failure** | Walk-in chiller row | "Compressor fails; the temperature creeps up. Watch: **At risk, breach in ~N min**. That is the **forecast**: we warn *before* the food is unsafe." ~15 s later: "Now it has left the band; the **same alert** upgraded to critical, it did not create a second one." |
| 9 | Press **AC on in empty room** | Room 207 turns red | ~25 s: "Room 207 is empty but the AC keeps cooling below its setpoint, a stuck relay. Notification: Guest rooms, **Room 207, Floor 2**, for the Duty Manager." Click it: the room is selected. |
| 10 | Press **Sensor offline** | Bar fridge → Offline | ~6 s: "No data for 3 minutes: heartbeat rule, IT Manager informed." |
| 11 | Press **Clear all** | Alerts → resolved | "Faults gone; after 5 quiet minutes each alert resolves itself and that is announced too." |
| 12 | Toggle ☾ / shrink the window | Dark mode, phone layout | "Light and dark theme, works down to phone width." |

## The AI in one minute (have ml/README.md open)

- **Three layers.** Rules for the obvious (probe wet, out of band). **Random Forest** names the fault. **Isolation Forest** is a safety net for patterns nobody labelled. A **trend forecast** warns before a breach.
- **Data.** No public dataset has labelled hotel faults, so the simulator generated 21 days with 210 labelled faults. Real data was used three ways:
  - **UCI**: calibrated the room physics to match real sensors.
  - **NAB**: Isolation Forest found 3 of 4 real machine failures.
  - **LBNL**: Random Forest scored F1 0.83 on real HVAC faults, and 1.00 on "cooling valve stuck open".
- **Results** on an unseen test week: every fault type caught with **0 false alarms/day** by its best method. The forecast warns **6 minutes before** a chiller breach.
- **Honest limits.** Synthetic faults are cleaner than real ones. Small drips are the hardest. WhatsApp/SMS sending is built for later (message text and routing are ready); for the demo, management is notified on the dashboard.

## Likely questions

- **Why simulate time 30x faster?** So a 10-minute escalation or a 25-minute chiller failure fits in a live demo. Every threshold is in real hotel minutes.
- **Why both rules and ML?** Rules are certain but only catch what you wrote down. ML catches subtle or early signs (a drip that never wets the probe, a fridge heading out of band). The alert shows which layers agreed.
- **How do you avoid alarm fatigue?**
  - One alert per device and fault, updated in place.
  - Alerts resolve automatically when the fault is gone.
  - Every threshold was tuned on data. Each change is documented with before/after numbers in ml/README.md, e.g. the forecast went from 145 false alarms/day to 0.
- **What would production need?** Listed in README "Limits": InfluxDB token, MQTT TLS, dashboard login, a persistent alert history for HACCP audits, real WhatsApp/SMS (TRAI DLT + Meta templates), and real sensor data.
