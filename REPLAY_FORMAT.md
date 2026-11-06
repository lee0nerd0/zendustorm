# Replay format

At **3:15** you freeze. Then you get **one input file for your persona**: a real night from last winter that is **not in
the API**. Your frozen code turns it into an output file. We score the output against what really happened.

## The contract

1. Before 3:15, put **one line** in `REPLAY_COMMAND` at the root of your repo, using `{input}` and `{output}`:

   ```
   python -m stormtwin replay --input {input} --output {output}
   ```

2. At 3:15: push, then submit your **freeze commit ID** (`git rev-parse HEAD`).
3. Then you get your persona's password. Download your input, save it as `replay/input.json`, run your command, and
   commit **only** `replay/input.json` and `replay/output.json`.
4. Afterwards we re-run your frozen commit on the same input, **offline**, in a clean container. Same output = valid.

The input contains that night's weather (so everyone uses the same numbers) and, for maintenance, the records from
the day before the storm. Everything else your system needs must already be in your committed `data/`.

All times are **local** (America/Toronto), format `YYYY-MM-DDTHH:MM:SS`.

## Dispatcher

**Input** (`dispatch_input.json`): `callout_local`, `weather` (`daily`, `hourly`), and `trucks`: for each truck its `yard`,
`tandem`, `driver` and the ordered `sequence` of routes it actually ran that night. Each sequence item has `route` and
`fraction` (1.0 = the whole route). Items can also have:
- `broken_at_local` + `fraction_done`: the truck broke down on this route at that time.
- `reassigned_from` + `available_after_local`: this piece was handed to this truck after another truck broke down.

`breakdowns` lists the breakdowns. `routes_to_predict` lists every route.

**Output:** the time each route was **fully** cleared.

```json
{"persona": "dispatch", "route_finish": {"R-01": "YYYY-MM-DDTHH:MM:SS", "R-02": "..."}}
```

A route is right if you are within **12 minutes or 4% of the time since callout**, whichever is larger.

## Maintenance lead

**Input** (`maintenance_input.json`): `night`, `callout_local`, `weather`, `trucks` (every truck), and
`records_since_your_data_ends`: API-format `StatusData`, `FaultData` and `WorkOrder` rows for the day before the storm.

**Output:** for every truck, one of `ok`, `no_start`, `hydraulic`.

```json
{"persona": "maintenance", "trucks": {"T-101": "ok", "T-102": "no_start", "T-103": "hydraulic"}}
```

Real failures are worth the most; false alarms cost points.

## Driver experience lead

**Input** (`driver_input.json`): `weather` and `shifts`: `driver`, `truck`, `start_local`, `end_local`, and the `routes`
they drove (`route`, `fraction`).

**Output:** the number of **harsh-braking events** each driver will have on that shift.

```json
{"persona": "driver", "harsh_brakes": {"D-01": 4, "D-02": 11}}
```

Right if within **1 event or 10%**, whichever is larger.

## Scoring

Every item counts. A few items in each night are **hard events** (the ones a shortcut gets wrong) and count
3x. The replay is 15 of your 100 points.
