# Bosch eBike Flow — Home Assistant integration

A Home Assistant custom integration (distributed through HACS) for the
reverse-engineered Bosch eBike Flow cloud API. The code is in
`custom_components/bosch_ebike/`; `api/` is a small synchronous `requests`
client, run in HA's executor by the coordinators in `coordinator.py`.

## Checks

Run all of these before committing; CI runs the same set, plus hassfest,
HACS validation, and zizmor.

```bash
uv sync --locked --extra dev
uv run ruff check custom_components/ tests/
uv run ruff format --check custom_components/ tests/
uv run codespell custom_components/ tests/ README.md
uv run mypy custom_components/
uv run pytest tests/
uvx zizmor --offline .github/
```

## Commits

Follow Zulip's commit discipline:

- Each commit is one coherent, minimal change, and passes every check above
  on its own. Split unrelated changes, and refactors from behavior changes.
- Subject: `area: Imperative summary.` — e.g. `sensors: Add range sensor.`,
  `auth: ...`, `coordinator: ...`, `ci: ...`.
- The body explains why: what was wrong, and why this is the fix.
- Fix a mistake in an unpushed commit by amending or rebasing it, not with
  a follow-up commit.

## Compatibility

- `hacs.json` sets the minimum Home Assistant version (currently 2026.3,
  the first on Python 3.14). The code may use anything that version and its
  Python support, and nothing newer.
- The dev environment pins exactly that Home Assistant version, so the tests
  run against the oldest supported release. `homeassistant` and
  `pytest-homeassistant-custom-component` (which pins an exact
  `homeassistant`) are excluded from Dependabot; when raising the minimum,
  bump `hacs.json`, `pyproject.toml`, and both packages in `uv.lock`
  together.
- Never list `requests` (or any other package Home Assistant itself
  depends on) in `manifest.json`; hassfest rejects it.

## The Bosch API

There is no documentation; behavior was established by observation, and by
other projects that use the same API. Things that are easy to get wrong:

- Login uses the Flow app's own Keycloak client (`one-bike-app`), so the
  redirect goes to the app's URL scheme, which is why the user pastes the
  code from the browser's devtools. Keycloak answers a dead refresh token
  with `invalid_grant`; that, and only that, should trigger reauth.
- `/v1/state-of-charge/{id}` and theft-detection's `latest-locations` return
  404 when there is simply no data (bike offline, no location yet). That is
  not an error.
- `/v1/activity` ignores every per-bike filter parameter tried (`bikeId`,
  `bike-id`, `filter[bikeId]`); filter client-side. Sort is
  `sort=-startTime`.
- `reachableRange` (in the SoC response) lines up with the profile's
  `driveUnit.driveUnitAssistModes`, minus the `"0"` (OFF) mode. Riders can
  reconfigure their modes, and older profile responses do not list them.
  Display names for mode IDs come from a ride's `assistModeUsage`.
- `/v1/bike-profile` wraps each bike in JSON:API `data[].attributes`;
  `/v2/bike-profile` is flat. We use v2.
- Bosch also has an official EU Data Act API (`api.bosch-ebike.com`), with a
  different, user-registered client. It has no state of charge or live
  location, and its tokens do not work against this API (nor ours against
  it).

## Test fixtures

`tests/fixtures/` holds real API responses, with identifying values (IDs,
serial numbers, dates) replaced. When the API changes shape, refresh them
from live data rather than guessing. From the Home Assistant config
directory of an installation that has the integration set up:

```bash
TOKEN=$(jq -r '.data.entries[] | select(.domain=="bosch_ebike") | .data.token.access_token' \
  .storage/core.config_entries)
curl -s -H "Authorization: Bearer $TOKEN" \
  https://obc-rider-profile.prod.connected-biking.cloud/v2/bike-profile/
```

The access token is a credential: never commit it, or paste it anywhere.
