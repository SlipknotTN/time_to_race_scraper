# Time to Race — Calendar Scraper

Scraper script that fetches F1 and MotoGP season calendars from official APIs and produces
normalized JSON files with every session converted to UTC. The output is suitable for
building race calendars, reminders, or any app that needs accurate session start/end times.

## Features

- **Formula 1**: fetches the full race calendar (free practice, qualifying, sprint, race) from the Ergast-compatible Jolpi API.
- **MotoGP**: fetches race events and all session types (practice, qualifying, sprint, warmup, race) from the official MotoGP API.
- **UTC normalization**: every session start/end is converted to UTC using the circuit's local timezone (MotoGP), so consumers never have to deal with venue-local times.
- **Idempotent merge**: already-fetched calendars are diffed against new data by round; events are classified as *added*, *unchanged*, or *modified*, and existing data is preserved where possible.
- **Run logs**: each sync writes a timestamped log file summarizing changes.

## Requirements

- Python 3.9+ (for the standard library `zoneinfo`; on older systems, install the `tzdata` and `backports.zoneinfo` packages).

No third-party dependencies are required.

## Usage

```bash
python3 fetch_calendar.py
```

This fetches both calendars and writes:

| File | Contents |
| --- | --- |
| `calendars/formula1_2026.json` | F1 race calendar for 2026 |
| `calendars/motogp_2026.json` | MotoGP race calendar for 2026 |
| `logs/<series>_<timestamp>.log` | Sync summary (added / unchanged / modified events) |

The script exits with a non-zero status if fetching a calendar fails.

## Output format

Both calendars use the same JSON structure: a top-level array of events, each containing
a list of sessions with ISO-8601 UTC timestamps.

```json
[
  {
    "round": 1,
    "name": "Australian Grand Prix",
    "circuit": "Albert Park Grand Prix Circuit",
    "location": "Melbourne, Australia",
    "sessions": [
      {
        "name": "Race",
        "start": "2026-03-08T04:00:00+00:00",
        "end": "2026-03-08T06:00:00+00:00"
      }
    ]
  }
]
```

MotoGP events additionally include a `short_name` field (e.g. `"THA"`, `"BRA"`).

Session durations that are not provided by the source APIs are estimated from typical
values (e.g. 1 hour for practice/qualifying, 30 minutes for a sprint, 2 hours for an F1
race) to produce the `end` timestamp.

## Data sources

- F1: `https://api.jolpi.ca/ergast/f1/2026.json`
- MotoGP: `https://api.motogp.pulselive.com/motogp/v1/results/` (seasons, events, sessions)

## License

MIT — see [LICENSE](LICENSE).
