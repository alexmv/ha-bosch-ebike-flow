# Bosch eBike Flow — Home Assistant Integration

Custom [Home Assistant](https://www.home-assistant.io/) integration for [Bosch eBike Flow](https://www.bosch-ebike.com/en/products/ebike-flow-app) bikes. Exposes battery state, ride statistics, odometer, and GPS location as HA entities.

## Features

- **Battery** — State of charge (%)
- **Odometer** — Total distance from the drive unit
- **Battery stats** — Capacity (Wh), charge cycles, lifetime energy delivered
- **Motor hours** — Total powered-on time
- **Last ride** — Distance, duration, avg/max speed, avg power, calories, CO2 saved, elevation gain, rider energy share, timestamp
- **GPS location** — Device tracker for bikes with a Bosch Connected Module (BCM)

## Installation

### HACS (recommended)

1. Open HACS in your HA instance
2. Go to **Integrations** → three-dot menu → **Custom repositories**
3. Add this repository URL, category **Integration**
4. Search for "Bosch eBike Flow" and install
5. Restart Home Assistant

### Manual

Copy `custom_components/bosch_ebike/` into your HA `config/custom_components/` directory and restart.

## Setup

1. Go to **Settings → Integrations → Add Integration → Bosch eBike Flow**
2. Open Developer Tools (**F12**), go to the **Network** tab, and enable **Preserve log**
3. Click the login link to sign in with your Bosch / SingleKey ID account
4. After logging in, the browser will fail to open the redirect — this is expected
5. In the Network tab, find the **302** redirect request (to a URL containing `login-actions`)
6. Click it → **Response Headers** → copy the `Location` value (starts with `onebikeapp-android://`, contains `code=`)
7. Paste the full URL (or just the code value) into the HA form
8. The integration discovers your bikes and creates entities automatically

## Entities

Each bike appears as an HA device with these sensors:

| Sensor                   | Unit      | Source              |
| ------------------------ | --------- | ------------------- |
| Battery                  | %         | State of charge API |
| Odometer                 | m         | Drive unit profile  |
| Battery Capacity         | Wh        | Battery profile     |
| Charge Cycles            | —         | Battery profile     |
| Motor Hours              | h         | Drive unit profile  |
| Battery Energy Delivered | Wh        | Battery profile     |
| Last Ride Distance       | m         | Activity API        |
| Last Ride Duration       | s         | Activity API        |
| Last Ride Avg Speed      | km/h      | Activity API        |
| Last Ride Max Speed      | km/h      | Activity API        |
| Last Ride Avg Power      | W         | Activity API        |
| Last Ride Calories       | kcal      | Activity API        |
| Last Ride CO2 Saved      | g         | Activity API        |
| Last Ride Rider Energy   | %         | Activity API        |
| Last Ride Elevation Gain | m         | Activity API        |
| Last Ride Time           | timestamp | Activity API        |

Bikes with a BCM (Connected Module) also get a **device tracker** entity with GPS coordinates.

## Polling Intervals

- Bike data (profile, battery, rides): every 5 minutes
- GPS location: every 30 minutes

## Development

```bash
uv sync --extra dev
uv run pytest tests/ -v
uv run ruff check custom_components/ tests/
uv run ruff format custom_components/ tests/
```

## License

MIT
