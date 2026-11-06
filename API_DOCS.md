# Fleet API

**Base URL:** `https://storm-hackathon.vercel.app/api/v1`
**Auth:** send your key in the `X-Api-Key` header. Keys are personal; we revoke them after today.

History: **2025-12-01 to 2026-01-23** (last winter), then **2026-11-01 to now**
(this season). "Now" is **2026-12-15T19:00:00** local time.

## Calling it

```
GET https://storm-hackathon.vercel.app/api/v1/<Entity>?resultsLimit=1000&fromDate=...&toDate=...&<filter>=...
X-Api-Key: <your key>
```

Every list response looks like:

```json
{ "data": [ ... ], "count": 1000, "next": "eyJvIjoxMDAwfQ" }
```

- `resultsLimit`: page size, default 200, max 1000.
- `next`: pass it back as `cursor=<next>` to get the next page. `null` means you have everything.
- `fromDate` / `toDate`: inclusive / exclusive, compared as text against the entity's time field (see the table).
  Use the same format as that field.
- Other filters (exact match): `deviceId`, `diagnosticId`, `ruleId`, `driverId`, `vehicleName`, `routeId`, `calloutId`,
  `type`, `status`, `yard`, `planDate`.
- `GET https://storm-hackathon.vercel.app/api/v1` (no entity) lists the entities.
- Errors: `401` bad key, `404` unknown entity, `400` bad parameter.

```bash
curl -H "X-Api-Key: $FLEET_API_KEY" "https://storm-hackathon.vercel.app/api/v1/StatusData?resultsLimit=5"
```

```python
import os, requests
r = requests.get("https://storm-hackathon.vercel.app/api/v1/Trip", headers={"X-Api-Key": os.environ["FLEET_API_KEY"]},
                 params={"resultsLimit": 1000})
page = r.json(); rows = page["data"]; cursor = page["next"]
```

## Entities

| Entity | Rows | Time field (for fromDate/toDate) | What it is |
|---|---|---|---|
| `Yard` | 2 | | The two yards, with coordinates |
| `Vehicle` | 30 | | Trucks: name (e.g. T-101), home yard, body type (tandem / single axle) |
| `Device` | 30 | | Telematics devices: id, serial, current vehicle name, firmware |
| `DeviceAssignment` | 32 | `activeFrom` (UTC) | Which device was in which vehicle, when. Devices can be moved between vehicles |
| `Driver` | 48 | | Drivers: id, name, home yard, hire date |
| `Route` | 40 | | Plow routes: road class, yard, tandem required, length (km), waypoints `[lat, lon]` |
| `StatusData` | 8,260 | `dateTime` (UTC) | Daily evening readings per device: battery resting voltage, engine hours, PTO hours, odometer |
| `FaultData` | 346 | `dateTime` (UTC) | Fault codes per device, with the vendor's default severity |
| `ExceptionEvent` | 2,277 | `activeFrom` (UTC) | Rule breaks per device and driver: harsh braking, speeding, idling. With location |
| `Trip` | 446 | `start` (UTC) | Trips per device and driver |
| `DutyStatusLog` | 640 | `dateTime` (UTC) | Drivers going on and off duty |
| `Callout` | 11 | `calloutLocal` (local) | Every storm callout last winter (from the township's dispatch system) |
| `DispatchAssignment` | 446 | `startLocal` (local) | Which truck and driver cleared which route, in what order, start/end, status |
| `DispatchPlan` | 30 | | Tonight's plan: truck, driver, ordered routes (made at 4 p.m. with every truck) |
| `WorkOrder` | 132 | `openedLocal` (local) | The shop's work orders: services, repairs, road calls, inspections |

### Field notes

- **Time zones.** Telematics entities (`StatusData`, `FaultData`, `ExceptionEvent`, `Trip`, `DutyStatusLog`,
  `DeviceAssignment`) use ISO 8601 **UTC** (`...Z`). The township's own systems (`Callout`, `DispatchAssignment`,
  `DispatchPlan`, `WorkOrder`) store **local wall-clock time** with no offset, as their staff typed or recorded it.
- **Telematics is keyed by device**, not by truck. The dispatch and shop systems use truck names.
- **StatusData** `diagnostic.id` values: `DiagnosticBatteryRestingVoltageId` (volts),
  `DiagnosticEngineHoursId` (hours, cumulative), `DiagnosticPtoHoursId` (hours the plow/spreader hydraulics ran,
  cumulative), `DiagnosticOdometerId` (km, cumulative).
- **ExceptionEvent** `rule.id` values: `RuleHarshBrakingId`, `RuleSpeedingId` (details: `speed`, `speedUnit`,
  `postedLimit`), `RuleIdlingId` (details: `ptoEngaged`). `driver.id` is `UnknownDriverId` when the driver did not log in.
- **DispatchAssignment** `status`: `COMPLETED`, `BROKEN_DOWN` (truck failed part way; `fractionOfRoute` = share done),
  `REASSIGNED` (another truck finished it or took it over; `reassignedFrom` = the failed truck).
- **WorkOrder** `type`: `ROAD_CALL` (with `reason`), `BATTERY_REPLACED`, `HYDRAULIC_SERVICE`, `HYDRAULIC_REPAIR`,
  `PM_INSPECTION`. `meterReadings` is whatever the mechanic wrote down, and is sometimes empty.
- There is **no weather** in this API.

The data is real-world messy on purpose. Treat everything as evidence, not truth.
