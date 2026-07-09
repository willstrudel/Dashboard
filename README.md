# Dashboard

A personal, single-file dashboard — clock, weather, calendar, projects, hobbies, shortcuts, and notes. No build step, no dependencies to install, no backend. Open `dashboard.html` in a browser and it works.

## Running it

Just open `dashboard.html` directly in any modern browser (double-click the file, or `File > Open`). No server required.

## What's in it

| Panel | What it does |
|---|---|
| **Clock** | Live time in US Eastern (EST/EDT, handled automatically) |
| **Weather** | Current conditions + 7-day forecast for Roswell, GA, via the free [Open-Meteo](https://open-meteo.com) API (no API key needed) |
| **Calendar** | Click a day to add an event. Local only for now — see note below. |
| **Projects** | A checkable list of personal projects |
| **Hobbies** | A simple tag list |
| **Shortcuts** | Link cards to local docs/sites — supports `https://` and `file://` paths |
| **Notes** | Freeform text, autosaves as you type |

## How data is saved

Everything you add (calendar events, projects, hobbies, shortcuts, notes) is saved in the browser's `localStorage`, scoped to that file on that machine/browser. That means:

- Data persists across reopens **as long as** you keep using the same file, in the same browser, on the same device.
- Moving the file, opening it in a different browser, or clearing browser data will reset it.
- There's currently no sync between devices.

## Known limitations / next steps

- **No live iPhone/iCloud calendar sync.** A static local file can't reach out to iCloud or Google Calendar without hitting CORS restrictions and needing credentials — that requires a small backend. Planned path: a Google Calendar feed or CalDAV integration once this becomes a hosted service.
- **No cross-device sync.** Also a backend/database problem, same as above.
- **Weather location is hardcoded** to Roswell, GA (lat/lon in the script) — easy to change by editing `WX_LAT` / `WX_LON` in `dashboard.html`.

## Editing

It's one file — HTML, CSS, and JS all inline in `dashboard.html`. No build tools, no package.json. Open it in any editor (or point Claude Code at it) and edit directly.
