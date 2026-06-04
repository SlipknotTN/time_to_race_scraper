#!/usr/bin/env python3
"""Fetch F1 and MotoGP season calendars, producing JSON with all sessions in UTC."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError

try:
    from zoneinfo import ZoneInfo
except ImportError:
    try:
        from backports import zoneinfo as ZoneInfo
    except ImportError:
        print("zoneinfo module required (Python 3.9+ or install tzdata)", file=sys.stderr)
        sys.exit(1)


F1_API_URL = "https://api.jolpi.ca/ergast/f1/2026.json"
MOTOGP_SEASON_URL = "https://api.motogp.pulselive.com/motogp/v1/results/seasons"
MOTOGP_EVENTS_URL = "https://api.motogp.pulselive.com/motogp/v1/results/events"
MOTOGP_SESSIONS_URL = "https://api.motogp.pulselive.com/motogp/v1/results/sessions"

MOTOGP_CATEGORY_UUID = "e8c110ad-64aa-4e8e-8a86-f2f152f6a942"

USER_AGENT = "RacingCalendar/1.0"
REQUEST_TIMEOUT = 30

COUNTRY_TO_TIMEZONE = {
    "TH": "Asia/Bangkok",
    "BR": "America/Sao_Paulo",
    "US": "America/Chicago",
    "ES": "Europe/Madrid",
    "FR": "Europe/Paris",
    "IT": "Europe/Rome",
    "HU": "Europe/Budapest",
    "CZ": "Europe/Prague",
    "NL": "Europe/Amsterdam",
    "DE": "Europe/Berlin",
    "GB": "Europe/London",
    "AT": "Europe/Vienna",
    "SM": "Europe/Rome",
    "JP": "Asia/Tokyo",
    "ID": "Asia/Makassar",
    "AU": "Australia/Melbourne",
    "MY": "Asia/Kuala_Lumpur",
    "QA": "Asia/Qatar",
    "PT": "Europe/Lisbon",
}

REGION_TO_TIMEZONE = {
    "CT": "Europe/Madrid",
    "AR": "Europe/Madrid",
    "VC": "Europe/Madrid",
}


def fetch_json(url, params=None):
    full_url = url
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        full_url = f"{url}?{query}"
    req = Request(full_url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except URLError as e:
        print(f"Error fetching {full_url}: {e}", file=sys.stderr)
        return None


def parse_f1_utc(date_str, time_str=None):
    if time_str:
        combined = f"{date_str}T{time_str}"
        if combined.endswith("Z"):
            combined = combined[:-1] + "+00:00"
        elif "+" not in combined and combined.count("-") <= 2:
            combined += "+00:00"
        return datetime.fromisoformat(combined)
    else:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt


def parse_motogp_utc(date_str, country_iso, region_iso=""):
    tz_name = REGION_TO_TIMEZONE.get(region_iso) or COUNTRY_TO_TIMEZONE.get(country_iso)
    if not tz_name:
        return datetime.fromisoformat(date_str)

    dt = datetime.fromisoformat(date_str)
    local_naive = dt.replace(tzinfo=None)
    circuit_tz = ZoneInfo(tz_name)
    local_aware = local_naive.replace(tzinfo=circuit_tz)
    return local_aware.astimezone(timezone.utc)


F1_SESSION_LABELS = {
    "FirstPractice": "Free Practice 1",
    "SecondPractice": "Free Practice 2",
    "ThirdPractice": "Free Practice 3",
    "Qualifying": "Qualifying",
    "Sprint": "Sprint",
    "SprintQualifying": "Sprint Qualifying",
}

F1_SESSION_DURATIONS = {
    "FirstPractice": timedelta(hours=1),
    "SecondPractice": timedelta(hours=1),
    "ThirdPractice": timedelta(hours=1),
    "Qualifying": timedelta(hours=1),
    "Sprint": timedelta(minutes=30),
    "SprintQualifying": timedelta(hours=1),
}


def fetch_f1_calendar():
    data = fetch_json(F1_API_URL)
    if not data:
        return None

    races = data["MRData"]["RaceTable"]["Races"]
    events = []
    for race in races:
        round_num = int(race["round"])
        name = race["raceName"]
        circuit = race["Circuit"]["circuitName"]
        locality = race["Circuit"]["Location"]["locality"]
        country = race["Circuit"]["Location"]["country"]

        race_start = parse_f1_utc(race["date"], race.get("time", "00:00:00Z"))
        race_duration = timedelta(hours=2)

        sessions = [
            {
                "name": "Race",
                "start": race_start.isoformat(),
                "end": (race_start + race_duration).isoformat(),
            }
        ]

        for key, label in F1_SESSION_LABELS.items():
            if key in race:
                s_start = parse_f1_utc(race[key]["date"], race[key]["time"])
                s_dur = F1_SESSION_DURATIONS.get(key, timedelta(hours=1))
                sessions.append({
                    "name": label,
                    "start": s_start.isoformat(),
                    "end": (s_start + s_dur).isoformat(),
                })

        sessions.sort(key=lambda s: s["start"])

        events.append({
            "round": round_num,
            "name": name,
            "circuit": circuit,
            "location": f"{locality}, {country}",
            "sessions": sessions,
        })

    return events


MOTOGP_SESSION_LABELS = {
    "FP": "Free Practice",
    "PR": "Practice",
    "Q": "Qualifying",
    "SPR": "Sprint",
    "WUP": "Warmup",
    "RAC": "Race",
}

MOTOGP_SESSION_DURATIONS = {
    "FP": timedelta(hours=1),
    "PR": timedelta(hours=1),
    "Q": timedelta(minutes=50),
    "SPR": timedelta(minutes=30),
    "WUP": timedelta(minutes=30),
    "RAC": timedelta(hours=1, minutes=15),
}


def fetch_motogp_calendar():
    seasons = fetch_json(MOTOGP_SEASON_URL)
    if not seasons:
        return None

    current_season = None
    for s in seasons:
        if s["year"] == 2026:
            current_season = s
            break
    if not current_season:
        print("2026 season not found in MotoGP API", file=sys.stderr)
        return None

    season_uuid = current_season["id"]
    events_data = fetch_json(
        MOTOGP_EVENTS_URL,
        {"seasonUuid": season_uuid},
    )
    if not events_data:
        return None

    events_list = [e for e in events_data if not e.get("test", False)]
    events_list.sort(key=lambda e: e.get("date_start", ""))

    result = []
    for round_num, ev in enumerate(events_list, 1):
        ev_uuid = ev["id"]
        country_iso = ev.get("country", {}).get("iso", "")
        region_iso = ev.get("country", {}).get("region_iso", "")

        sessions_data = fetch_json(
            MOTOGP_SESSIONS_URL,
            {
                "seasonUuid": season_uuid,
                "eventUuid": ev_uuid,
                "categoryUuid": MOTOGP_CATEGORY_UUID,
            },
        )
        if not sessions_data:
            continue

        sessions = []
        for ses in sessions_data:
            s_start = parse_motogp_utc(ses["date"], country_iso, region_iso)
            stype = ses["type"]
            label = MOTOGP_SESSION_LABELS.get(stype, stype)
            s_dur = MOTOGP_SESSION_DURATIONS.get(stype, timedelta(hours=1))

            if stype == "Q" and ses.get("number") is not None:
                label = f"Qualifying {ses['number']}"
            elif stype == "FP" and ses.get("number") is not None:
                label = f"Free Practice {ses['number']}"
            elif stype == "FP" and ses.get("number") is None:
                label = "Free Practice"

            sessions.append({
                "name": label,
                "start": s_start.isoformat(),
                "end": (s_start + s_dur).isoformat(),
            })

        sessions.sort(key=lambda s: s["start"])

        circuit = ev["circuit"]["name"]
        place = ev["circuit"].get("place", "")
        country_name = ev.get("country", {}).get("name", "")
        location = f"{place}, {country_name}" if place else country_name

        result.append({
            "round": round_num,
            "name": ev.get("sponsored_name", ev["name"]),
            "short_name": ev.get("short_name", ""),
            "circuit": circuit,
            "location": location,
            "sessions": sessions,
        })

    return result


def load_json(filename):
    if not os.path.exists(filename):
        return None
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def event_checksum(event):
    return json.dumps(event, sort_keys=True, ensure_ascii=False)


def merge_events(old_events, new_events):
    if not old_events:
        return new_events, {"added": list(new_events), "unchanged": [], "modified": []}

    old_by_round = {e["round"]: e for e in old_events}
    old_checksums = {e["round"]: event_checksum(e) for e in old_events}

    added = []
    unchanged = []
    modified = []

    merged = []
    for new_ev in new_events:
        r = new_ev["round"]
        old_ev = old_by_round.get(r)
        if old_ev is None:
            added.append(new_ev)
            merged.append(new_ev)
        elif old_checksums.get(r) == event_checksum(new_ev):
            unchanged.append(old_ev)
            merged.append(old_ev)
        else:
            modified.append({"round": r, "name": new_ev["name"], "old": old_ev, "new": new_ev})
            merged.append(new_ev)

    return merged, {"added": added, "unchanged": unchanged, "modified": modified}


def write_log(log_path, series, changes, elapsed):
    lines = []
    lines.append(f"=== {series} calendar sync — {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')} ===")
    lines.append(f"Completed in {elapsed:.2f}s")

    for label, key in [("Added", "added"), ("Unchanged", "unchanged")]:
        items = changes.get(key, [])
        lines.append(f"\n{label} ({len(items)}):")
        for ev in items:
            n = ev.get("name", ev.get("event", ""))
            r = ev.get("round", "?")
            lines.append(f"  Round {r:>2}  {n}")

    modified = changes.get("modified", [])
    lines.append(f"\nModified ({len(modified)}):")
    for m in modified:
        lines.append(f"  Round {m['round']:>2}  {m['name']}")

    lines.append("")
    text = "\n".join(lines)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  Log -> {log_path}")
    return text


def sync_calendar(label, filename, fetch_fn, log_dir):
    start = datetime.now()

    print(f"\n--- {label} ---")
    print("  Fetching...")
    new_data = fetch_fn()
    if not new_data:
        print(f"  Failed to fetch {label}", file=sys.stderr)
        return False

    print("  Merging...")
    old_data = load_json(filename)
    merged, changes = merge_events(old_data, new_data)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    elapsed = (datetime.now() - start).total_seconds()
    print(f"  Saved {filename} ({len(merged)} events, {len(changes['added'])} new, "
          f"{len(changes['unchanged'])} unchanged, {len(changes['modified'])} modified)")

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_name = f"{os.path.splitext(os.path.basename(filename))[0]}_{run_ts}.log"
    log_path = os.path.join(log_dir, log_name)
    write_log(log_path, label, changes, elapsed)
    return True


def main():
    data_dir = "calendars"
    log_dir = "logs"
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    ok = True
    ok &= sync_calendar("Formula 1", os.path.join(data_dir, "formula1_2026.json"), fetch_f1_calendar, log_dir)
    ok &= sync_calendar("MotoGP", os.path.join(data_dir, "motogp_2026.json"), fetch_motogp_calendar, log_dir)

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
