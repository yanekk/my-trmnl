# T12 — Weather-source resilience: hold last-good + in-cycle retries

**Phase:** 4 (enhancement, post-deploy) · **Depends on:** T05, T08 · **Weight:** medium-light

Owner-added amendment (2026-09-07), agreed after the owner saw the weather box flick to
"niedostępne" for one refresh when Open-Meteo returned a transient 503. Requirements settled with
the owner this session; the decisions are recorded in DESIGN §2.6 and §Decisions.

## Goal

The weather box blanks to "niedostępne" the moment a single weather fetch fails, even though a
good reading was in hand two minutes earlier. Open-Meteo is a free, no-account service and returns
the odd 503, so this happens often enough to catch the eye. A few-minutes-old temperature is still
useful and not misleading (unlike a bus time), so weather should ride out a brief outage: retry the
fetch a few times within the cycle, and if it still fails, keep showing the last good reading for a
while rather than blanking. This is weather only — buses and calendar keep blanking immediately,
because a wrong bus time is worse than an honest gap (DESIGN §2.6).

## Design sections this implements

DESIGN §2.6 (the weather source now holds its last good reading for up to ~30 minutes across a
brief outage, with in-cycle retries, instead of blanking on the first failure; buses and calendar
are unchanged). No change to the boundary: the hold and the retry live in the composition root, and
the pure core still only turns `WeatherData` into a view or a `Failure` into "niedostępne"
(DESIGN §3.1).

## Files

- `trmnl/server/loop.py` — add a `WeatherCache` (in-memory, no disk), mirroring `VehicleCache`:
  it wraps `weather.fetch_weather`, retries on failure with a fixed backoff, and holds the last
  successful `WeatherData` with the `now` it was fetched at. Wire it into `Deps` and
  `_fetch_weather`, and construct it in `main`. New module constants for the backoff schedule and
  the hold window. No change to the pure core, the renderer, or any golden.
- `trmnl/adapters/weather.py` — unchanged. `fetch_weather` stays a single-request, stateless
  function; the retry and the hold are the composition root's, because the hold is state that must
  persist across cycles and only a held object can carry it (the adapter is called fresh each
  cycle). Keeping retry beside the hold also keeps the adapter free of sleeps.
- `tests/server/test_loop.py` — the cases below. An injected fake sleep, so no test really waits.

## Interface

```python
# trmnl/server/loop.py — module constants
WEATHER_RETRY_BACKOFF_S: tuple[int, ...] = (5, 10, 15)  # waits between attempts; 4 attempts total
WEATHER_HOLD = timedelta(minutes=30)                     # how long a last-good reading is shown

class WeatherCache:
    """The weather source with a brief last-good hold and in-cycle retries (T12).
    In-memory only — a restart during an outage has nothing to hold, so weather is
    "niedostępne" until the first success (accepted)."""

    def __init__(self, *, sleep: Callable[[float], None] = _time.sleep) -> None: ...

    def fetch(
        self, cfg: Config, now: datetime, client: httpx.Client
    ) -> WeatherData | Failure: ...
        # Attempt weather.fetch_weather; on a Failure, sleep the next backoff and retry,
        # for at most len(BACKOFF)+1 attempts. On any success: store (data, now), return it.
        # On failure after every attempt: return the held WeatherData if one exists and
        # now - its_fetch_time <= WEATHER_HOLD, else return the last Failure.

# Deps gains an optional weather cache; None keeps the old single-fetch path (existing
# loop tests pass None and are unaffected).
class Deps:
    def __init__(self, ..., weather: "WeatherCache | None" = None): ...

def _fetch_weather(cfg, now, deps):
    if deps.weather is None:
        return weather.fetch_weather(cfg.lat, cfg.lon, now, deps.http)
    return deps.weather.fetch(cfg, now, deps.http)
```

- **The backoff schedule is the hard cap.** It is finite — at most four attempts and 30s of
  waiting — so a flaky service can never stall the board indefinitely (owner's "hard cap").
  Worst case is ~30s of backoff plus up to four 10s request timeouts (~70s) only if every attempt
  hits the full timeout; a fast 5xx that recovers on the first retry costs ~5s. The cycle cadence
  is 120s, so even the worst case stays inside one interval.
- **The age check takes `now` as an argument, never a clock read** (DESIGN §3.1), so the 30-minute
  window is testable with fixed times. The hold measures age from the last *successful* fetch, not
  from the first, so a reading refreshed at t keeps for 30 minutes past t.
- **Any `Failure` triggers a retry** — network error, non-200, or unparseable body alike. A schema
  change (unparseable) would burn the retry schedule and then be held for 30 minutes before
  blanking; that is rare and acceptable, and simpler than classifying failures.
- **The image is still published fresh every cycle.** A held reading substitutes a normal
  `WeatherData`, so `assemble` draws an ordinary weather region — this is distinct from the
  last-good *image* path (a render/write failure), which is unchanged.

## Tests

- [ ] Success on the first attempt: `fetch` returns the data, calls the injected sleep zero times,
      and stores the reading (a later all-failing cycle then holds it).
- [ ] Failure then success on a later attempt: the backoff sleeps are called in order (5, then 10…)
      up to the successful attempt, and the returned data is the successful one.
- [ ] Always-failing fetch calls `weather.fetch_weather` exactly four times and calls sleep exactly
      with 5, 10, 15 — the hard cap; it never loops further.
- [ ] All attempts fail with a held reading younger than 30 minutes → `fetch` returns the held
      `WeatherData` (so the region renders normally), not a `Failure`.
- [ ] All attempts fail with a held reading older than 30 minutes → `fetch` returns a `Failure`
      (→ "niedostępne").
- [ ] All attempts fail with nothing ever held (cold start / restart mid-outage) → `Failure`.
- [ ] The hold age is measured from the last success: a reading stored at t1 is still held at
      t1+29min even if the first success was long before (the timestamp advances on each success).
- [ ] Buses and calendar are unaffected: a cycle where weather holds still shows a bus/calendar
      `Failure` as "niedostępne" (the weather exception does not leak to the other sources).
- [ ] No test performs a real sleep (the fake sleep records its calls); the suite stays quiet.

## Done when

- [ ] On a weather fetch failure the loop retries up to three times (5/10/15s) that cycle, and a
      last good reading younger than 30 minutes is shown in place of "niedostępne" — all proven
      from fixtures with an injected clock and sleep, no real waiting.
- [ ] A held reading older than 30 minutes, or none ever recorded, falls back to "niedostępne";
      buses and calendar still blank immediately on their own failures, unchanged.
- [ ] The suite is green and quiet on the Mac and on the Pi 3.9 (`--ignore=tests/render`), because
      this is loop/composition-root code (no external-data parsing change, but run the Pi anyway
      per the CLAUDE.md deploy note since it touches the running service path).

## Needs a person

The behaviour is fully testable here with fixtures, a fixed clock and a fake sleep — nothing about
the retry, the hold or the age window needs the device. The only real-world confirmation is
opportunistic and not required to close the task: next time the owner happens to catch Open-Meteo
returning an error, the weather box should stay put (showing the last reading) rather than flicking
to "niedostępne". Fold that into the next on-device glance and record it dated in FINDINGS if seen;
do not hold the task open for it, since it cannot be forced on demand.
