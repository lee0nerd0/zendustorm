# Persona

**I build for:** Maintenance lead

**The decision my persona makes tonight:**
Which trucks go out at the callout, which get fixed first in the time before it, and which are held back so a
failure doesn't strand a route halfway through the storm.

**What my system tells them (the actual output they'd act on):**
`python -m stormtwin whatif --forecast config/forecast.json` prints, for tonight's plan:
- **Trucks ready** at callout (e.g. 23/30).
- **Fix first**: every truck predicted `no_start` or `hydraulic`, with the reason in numbers, ordered by the most
  urgent road class it is planned to clear.
- **Routes that need another truck**: the planned routes those trucks would have cleared, with their provincial
  clear-within hours and whether a tandem is required.
- **Watch list**: trucks that are ok tonight but within a margin of a threshold.
- `--fix T-109:battery` re-runs the night as if a repair were done, so the lead can see what each repair buys.

Tonight, after the 9:30 p.m. update (callout 00:30, low -19 °C, 25–30 cm):
1. **Replace batteries now on T-109, T-110, T-116** (12.16–12.22 V). A swap takes 0.8–1.0 h in the shop records, so
   all three fit before 00:30 → 26/30 ready. T-109 first: it carries R-35, the only class 1 route at risk (4 h standard).
   T-110 next: R-20 needs a tandem.
2. **Hold back T-111, T-114, T-119, T-128** (184–206 PTO h since hydraulic service). A hydraulic service takes 4–5 h,
   so none can be done by 00:30. Sent out, they would lose hydraulics ~1.5 h into a route and be towed.
   Give R-01, R-37 (class 2) and R-13, R-32 (class 3) to other trucks from the start; service these four overnight.
3. **Root cause:** all four hydraulic trucks skipped this season's pre-season hydraulic service.

What changed from the 4:30 bulletin: **not which trucks fail** (-14 and -19 °C are both below -10 °C; 20 and 25–30 cm
are both above 7.5 cm), but **the time to act**: 3 h instead of 4.5 h, so hydraulic work is no longer possible before
callout and those trucks must be held back rather than serviced.

**The rules I believe the fleet follows (with the numbers I found):**
1. **No-start** = resting battery voltage the evening before < **12.25 V** AND overnight low (hourly, 18:00→08:00) <= **-10 °C**.
   11/11 road-call no-starts caught, 0 false alarms over 1,650 truck-mornings. Closest failure 12.24 V / -10.5 °C;
   closest survivor 12.25 V (cold) / -9.2 °C (weak battery). Most no-starts were ordinary mornings, not callouts.
2. **Hydraulic failure** = PTO hours since last hydraulic service/repair >= **181 h** AND snowfall >= **7.5 cm** that day.
   6/6 failures caught (181.8–191.4 h, all on 9.8–20.2 cm nights); heavy-night survivors <= 180.0 h;
   light-snow nights (<= 4.8 cm) had trucks at 189 h with no failure.
3. **Noise, not signal:** `HYD-PRESS-LOW` faults (vendor severity "low", 251 rows) do not separate failures from survivors.
   A battery replacement or hydraulic service resets the risk. Devices move between trucks (T-118 <-> T-129 on 2026-01-08).

Backtest on all 11 callouts: 327/327 truck-nights correct (6 hydraulic, 3 no-start, 318 ok).
Reproduce: `python -m stormtwin evidence` (writes `data/derived/evidence.json`). In-sample: thresholds were fit on this history.

**What I am NOT sure about, and how I'd check:**
1. **Wind (NW 40 km/h gusting 70).** Wind is not in either rule; last winter never tested gusts like this.
   Wind chill does not cool a parked engine below air temperature, but wind could raise hydraulic load (drifts, packed
   snow) or lengthen shifts. *Check:* add hourly wind to the evidence table and look for failures that only appear on
   windy nights; with the current history, no failure is unexplained without wind.
2. **Blowing snow / snow dispersion.** The hydraulic rule uses snowfall at Pearson. In 70 km/h gusts, snow drifts:
   open rural routes can carry much more than the gauge says, sheltered streets less. The rule only needs "above
   7.5 cm" so tonight is not close, but drift could push a light-snow night over the line on exposed routes.
   *Check:* compare failure locations (ExceptionEvent / road-call route) against route exposure; split routes into
   open and sheltered.
3. **Pearson vs the township.** All weather is from TORONTO INTL A. The south yard is ~3.5 km from it, the north
   yard ~15 km north-west and further inland, where nights can be colder and snow totals different.
   The thresholds are calibrated on Pearson numbers; if the judges' replay weather comes from another source,
   nights near -10 °C or 5–10 cm could flip. *Check:* pull a second station near the north yard and see if any
   historical failure fits better per yard.
4. **Thresholds sit in small gaps.** Battery: 12.24 V failed, 12.25 V survived. The snow cut-off (7.5 cm) is my choice
   inside a wide 4.8–9.8 cm gap. 17 failures in total; all accuracy is in-sample.
5. **Night window.** Jan 15 no-starts happened at 00:09, before that night's coldest hour; the 18:00→08:00 low fits
   best, but the true rule may use a different window.
6. **-19 °C is at the edge of history.** The coldest night last winter was -20.2 °C (trucks at 12.28 V started), so
   the voltage threshold holds at -19 °C, but there is no evidence below that.

## Run it on my machine

```bash
git pull
```
```bash
python -m unittest discover -s tests -t .
```
```bash
python -m stormtwin evidence
```
```bash
python -m stormtwin whatif
```
```bash
python -m stormtwin whatif --forecast config/forecast.json
```
```bash
python -m stormtwin whatif --forecast config/forecast.json --fix T-109:battery T-110:battery T-116:battery
```
Optional refresh from the API / weather (needs internet; `load` needs `FLEET_API_KEY`):
```bash
python -m stormtwin load
```
```bash
python -m stormtwin weather
```

## How it works (in my words)

This system first loads the data from the API and env canada weather, then combines the various data into more useful per-truck metrics that can be reported at any given time (last recorded battery voltage, PTO hours since last service, etc.). It applies 2 rules found in historical data and gives recommendations on what to fix before callout, what trucks to hold back, and what trucks are near next maintenance.
