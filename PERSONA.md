# Persona

**I build for:** Maintenance lead

**The decision my persona makes tonight:**

**What my system tells them (the actual output they'd act on):**

**The rules I believe the fleet follows (with the numbers I found):**
1. **No-start** = resting battery voltage the evening before < **12.25 V** AND overnight low (hourly, 18:00→08:00) <= **-10 °C**.
   11/11 road-call no-starts caught, 0 false alarms over 1,650 truck-mornings. Closest failure 12.24 V / -10.5 °C;
   closest survivor 12.25 V (cold) / -9.2 °C (weak battery). Most no-starts were ordinary mornings, not callouts.
2. **Hydraulic failure** = PTO hours since last hydraulic service/repair >= **181 h** AND snowfall >= **7.5 cm** that day.
   6/6 failures caught (181.8–191.4 h, all on 9.8–20.2 cm nights); heavy-night survivors <= 180.0 h;
   light-snow nights (<= 4.8 cm) had trucks at 189 h with no failure.
3. **Noise, not signal:** `HYD-PRESS-LOW` faults (vendor severity "low", 251 rows) do not separate failures from survivors.
   A battery replacement or hydraulic service resets the risk. Devices move between trucks (T-118 <-> T-129 on 2026-01-08).

Reproduce: `python -m stormtwin evidence` (writes `data/derived/evidence.json`). In-sample: thresholds were fit on this history.

**What I am NOT sure about, and how I'd check:**
