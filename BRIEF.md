# Storm Twin: build the what-if engine for a snowplow fleet

**You have 2 hours 10 minutes to build (1:05 to 3:15). Not finishing is normal. What you get right matters more than how much you build.**

## The situation

Credit Valley Township is a fictional township near Brampton, Ontario. It runs **30 snowplows** from **two yards**
and clears **40 plow routes**. Every truck carries a telematics device.

It is **Tuesday, December 15, 2026, 7:00 p.m.** A winter storm arrives overnight. Before the township commits trucks and
drivers, it wants to ask **"what happens if…?"** and get an answer it can act on.

Your job: build an **MVP what-if engine** (a "digital twin" of the winter fleet) for **one** of these people.

| Persona | The decision they make tonight | The kind of question they ask |
|---|---|---|
| **Dispatcher** | Which truck and driver take which route, in what order | When will each route be finished? Which roads miss the provincial standard? What if we lose a truck? |
| **Maintenance lead** | Which trucks go out, which get fixed first | Which trucks won't start in this cold? Which will lose their plow hydraulics mid-storm? |
| **Driver experience lead** | What each driver is told and who gets coached | Who is most at risk tonight, how risky, and why? |

You pick one persona. You can change your mind until the 1:45 snapshot, then it is locked.

## What we give you

- **One fleet API** (your key is on your slip). Vehicles, devices, drivers, routes, telematics (status readings, faults,
  exceptions, trips, duty status), work orders and the dispatch history for last winter, plus this season so far.
  The docs are in `API_DOCS.md`.
- **Tonight's weather bulletin** (`TONIGHT_BULLETIN.md`) and, at 2:15, **a forecast update**.
- **The replay format** (`REPLAY_FORMAT.md`) and a **starter repo** (`starter/`).

## What you find yourself

- Where the township is (the yards are at 43.792, -79.741 and 43.684, -79.672).
- **Historical weather** for last winter. It is not in the API. Use any public source (Environment Canada's historical
  climate data is free).
- **Sunrise and sunset** times, if you think they matter.
- **Which data matters**, which what-ifs are worth answering, your approach, your libraries.

## The catch

The fleet behaves according to a few **simple rules we don't tell you**. Your system has to find them in the data,
which is real-world messy. At **3:15** you freeze your code. Then we release **one real night from last winter that is
not in the API** and your frozen code predicts what happened. We score it against what actually happened.

## Ontario minimum maintenance standards for snow (O. Reg. 239/02)

| Road class | Depth that triggers clearing | Clear within |
|---|---|---|
| 1 | 2.5 cm | 4 hours |
| 2 | 5 cm | 6 hours |
| 3 | 8 cm | 12 hours |
| 4 | 8 cm | 16 hours |
| 5 | 10 cm | 24 hours |

For this exercise, **a route meets the standard if it is fully cleared within its class's hours of the callout.**

## What "done" looks like

- **L1**: your system loads the API data and runs the replay from a single command, offline.
- **L2**: it answers at least one useful what-if about tonight for your persona.
- **L3**: it answers more what-ifs and handles the 2:15 forecast update without code changes.

## How you are scored (100 points, bar is 70)

| Area | Points | What we look at |
|---|---|---|
| Judgement | 30 | Opening form (10), red-pen round (10), your persona decisions (10) |
| Systems thinking | 25 | Hidden rules you found, with numbers (15); is it a proper system: load / replay / what-if, config not hard-coded, runs from your README (10) |
| Execution | 25 | Replay accuracy (15); process: commits, snapshots, AI log (10) |
| Defence | 20 | Your 8 minutes: demo, a live what-if card, questions |

A pretty UI scores **0**. The output must be something your persona could act on tonight.
