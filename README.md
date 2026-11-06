# Storm Twin – <your name>

Persona: Maintenance lead

## Run it (a judge must be able to do this from a fresh clone)

```bash
# 1. install: Python 3.10+, standard library only (see requirements.txt). Nothing to pip install.

# 2. load: download the fleet API into data/raw/ (needs the key in an env var, never in git)
export FLEET_API_KEY=<your key>
python -m stormtwin load                       # all entities (~13k rows, ~25 requests)
python -m stormtwin load --only WorkOrder      # re-fetch a subset
#    -> data/raw/<Entity>.json + data/raw/_manifest.json (row counts, sha256, warnings)
#    Settings (URL, page size, timeouts, retries) are in config/settings.json.

# 2b. weather: Environment Canada hourly + daily obs (TORONTO INTL A) -> data/weather/ (no key)
python -m stormtwin weather
#    -> daily.json, hourly.json, callout_nights.json (low before / around each callout), raw/*.csv

# 3. replay: works offline from data/ (command is in REPLAY_COMMAND)
python -m stormtwin replay --input replay/input.json --output replay/output.json

# 4. what-if: answer a question about tonight                          [next step]
#    python -m stormtwin whatif --low -19 ...

# tests (offline, mock API)
python -m unittest discover -s tests -t . -v
```

## How it works (5 lines max)

## What I'd do next
