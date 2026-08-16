# Dashboard

A personal dashboard — clock, weather, calendar, projects, hobbies, shortcuts, notes, live Bluetooth device battery levels, and a separate Library page for tracking epubs staged for Kindle. No build step, no framework.

## Running it

Open **http://127.0.0.1:8420/dashboard.html** in a browser — not the file directly.

The Bluetooth battery panel reads `battery.json` at runtime, and Chrome/Edge block that kind of local-file read when the page is opened via `file://`. So the dashboard is served over a tiny local Python HTTP server (`server.py`, bound to `127.0.0.1` only — never reachable from the network) instead. It starts automatically at login — see "How the Bluetooth panel stays live" below for how.

If you only care about clock/weather/calendar/etc. and not Bluetooth, opening the file directly still works fine for those panels.

## What's in it

| Panel | What it does |
|---|---|
| **Clock** | Live time in US Eastern (EST/EDT, handled automatically). Has a brighter lavender corner glow as its signature accent. |
| **Weather** | Current conditions + 7-day forecast, via the free [Open-Meteo](https://open-meteo.com) API (no API key needed). City dropdown (Roswell / Summerville / Duluth, GA — choice saved to `localStorage`), severe weather alert banner from the National Weather Service, and a click-through hourly forecast modal per day. See "Weather details" below. Refreshes every 5 minutes in the browser; low temps are shown in lavender. |
| **Calendar** | Click a day to add an event. Optionally syncs in read-only events from your iPhone/iCloud calendar — see "Calendar sync" below. Hovering a day shows a lavender tint; today stays solid green. |
| **Bluetooth + Shortcuts** | Share one column next to the Calendar (a flex stack), together matching the Calendar's height — Bluetooth sizes to its content and Shortcuts grows to fill the rest, so there's no dead space. On narrow screens, where everything stacks into one column, Bluetooth breaks out of this pairing and moves up to sit right under the clock, above Weather — see "Responsive layout" below. |
| **Bluetooth** | Battery % for paired Bluetooth devices, refreshed every 30s in the browser (re-reads `battery.json`; doesn't refresh the underlying data — see the ⟳ button below for that). Currently tracks 2 devices (keyboard + mouse) — see `battery.json`. Battery percentage text is lavender. A ⟳ button next to the device count triggers an on-demand poll. |
| **Shortcuts** | Link cards to local docs/sites — supports `https://` and `file://` paths. Drag and drop a card onto another to reorder (order saved to `localStorage`); hover state is lavender. |
| **Hobbies** | A simple tag list. Tag pill borders are lavender. |
| **Notes** | Freeform text, autosaves as you type. Focus border is lavender. |
| **Projects** | A checkable list of personal projects. Checkbox accent color is lavender. |

**Greeting** (top left) changes by time of day, computed in Eastern time: Good morning (12:00am–11:59am), Good afternoon (12:00pm–5:00pm), Good evening (5:01pm–9:59pm), Good night (10:00pm–11:59pm). Re-checks every 30s so it flips live if the tab is left open across a boundary.

**Color scheme**: mint green (`--accent`, `#6ee7b7`) is the primary accent (buttons, "today", drag targets, battery-good). Lavender (`--lavender`, `#c4b5fd`) is a secondary accent — each card above has one lavender-colored element, and the Clock card additionally has a lavender corner glow.

**Favicon**: an inline SVG (data URI, no separate file) — a mint-green ◆ diamond on a dark panel background, matching the topbar brand mark.

**FOUC fix**: `<meta name="color-scheme" content="dark">` plus a non-render-blocking Google Fonts load (`media="print" onload="this.media='all'"` trick) prevent a flash of the browser's default light background when this loads as a new-tab homepage before fonts/network are ready.

## Responsive layout

Two breakpoints, both in `dashboard.html`'s `<style>` block:

- **≤980px** — the 12-column grid becomes 6 columns and every panel spans the full row, so everything stacks into one column. Stacking order is controlled with CSS `order` on each panel: Clock, **Bluetooth**, Weather, Calendar, Shortcuts, Hobbies, Notes, Projects. Bluetooth and Shortcuts normally share one grid cell (`.panel-stack`, a flex column) so they can match the Calendar's height side-by-side on wide screens; at this breakpoint `.panel-stack` switches to `display:contents`, which dissolves the wrapper so its two children become independent grid items and can be reordered separately — that's how Bluetooth ends up above Weather while Shortcuts stays put after Calendar.
- **≤600px** — grid drops to a single explicit column, panel padding shrinks, and the top bar switches from a row to a stacked column.

If you need to change the stacking order again, edit the `order` values in the `@media (max-width:980px)` block right after the `.panel-stack` CSS rules (search for `panel-bluetooth`) — that block must stay *after* the base `.panel-stack{display:flex;...}` rule in the file, or the cascade will silently prefer the flex rule over `display:contents` at narrow widths.

## Weather details

- **Cities**: a dropdown in the Weather panel header switches between Roswell, Summerville, and Duluth, GA. The selection persists in `localStorage` (`dash:wx-city`) and drives both the Open-Meteo forecast and the NWS alert lookup below. Lat/lon per city live in `WX_CITIES` in `dashboard.html` — add more by adding entries there.
- **Severe weather alerts**: pulled from the National Weather Service's free, no-key `api.weather.gov/alerts/active` endpoint (US-only, which is fine — all three cities are in Georgia). Active alerts render as a banner above the forecast, colored red for Extreme/Severe and amber for lower severities. Each alert has a ✕ to dismiss it for the current browser tab/session (`sessionStorage`); it reappears next time the alert is still active in a new session.
- **Hourly forecast modal**: click any day card to open a modal with an hour-by-hour breakdown (condition, precipitation chance, temperature) for that day, sourced from Open-Meteo's hourly data (already included in the same forecast request, no extra API call). Close with the ✕, a click outside the modal, or Escape.
- **Why not Weather.com/IBM?** The Weather Company API is enterprise/paid-only now — no free public tier — so Open-Meteo (forecast) + NWS (alerts) covers the same ground for free.

## Calendar sync (iCloud, Google/Gmail, or any ICS feed)

Read-only, one-way: events from each connected calendar show up on the dashboard; nothing created here pushes back to the source. Multiple calendars can be connected at once (e.g. iCloud + Gmail together) — their events merge into the same calendar grid and Upcoming list, each tagged with its source label.

**Setup — iCloud:**
1. On your iPhone (or icloud.com): Calendar app → tap the calendar's name → turn on **Public Calendar** → **Share Link** → copy the link (starts with `webcal://`).
2. In the dashboard, click **⚙ Sync calendars** in the Calendar panel header. Enter a label (e.g. "iCloud"), then paste the link when prompted.

**Setup — Google/Gmail:**
1. On calendar.google.com: **Settings** → pick the calendar under "Settings for my calendars" → **Integrate calendar** → copy the **Secret address in iCal format**.
2. In the dashboard, click **⚙ Sync calendars**, label it (e.g. "Gmail"), and paste that link when prompted.
3. Google explicitly calls this a *secret* address — anyone with the link can read that calendar, so treat it like a password. (iCloud's "public" link is functionally similar — unguessable but unauthenticated — just less bluntly named.)

Repeat "⚙ Sync calendars" for each additional calendar you want pulled in. `server.py` appends to the saved list (re-adding the same link updates its label instead of duplicating it).

**How it works:** the browser can't fetch iCloud's or Google's servers directly (CORS), so `server.py` does the fetch server-side via `GET /api/calendar-events`, which reads every configured calendar, fetches + parses each feed, and hands the dashboard merged, source-tagged JSON. `POST /api/ical-config` is what the "⚙ Sync calendars" button calls to append a calendar. Each feed is cached in memory per-URL for 15 minutes so page loads don't hit iCloud/Google every time; the dashboard itself re-polls `/api/calendar-events` every 15 minutes.

The ICS parser is hand-rolled (no external pip dependency, matching this project's no-build-tools philosophy) and lives in `server.py`. It handles one-off events, all-day events, and a pragmatic subset of recurrence (`RRULE`: DAILY/WEEKLY/MONTHLY/YEARLY, `INTERVAL`, `COUNT`, `UNTIL`, `BYDAY` for weekly) — enough for typical personal-calendar events. It only resolves events down to a *date*, not a time of day, since that's all the dashboard's calendar UI tracks.

Synced events show as a lavender dot on the calendar grid (vs. amber for events you added locally) and appear in the Upcoming list tagged with their source label (e.g. **iCloud**, **Gmail**), without a remove button since they're read-only. If a feed becomes unreachable or `server.py` isn't running, the sync note under the calendar explains what's wrong — per-calendar, if one source fails but another is fine.

**Config file:** all connected calendars live in `ical-config.json` — `{"calendars": [{"label": "iCloud", "url": "webcal://..."}, {"label": "Gmail", "url": "https://calendar.google.com/calendar/ical/.../basic.ics"}]}` — gitignored since it holds effectively-private links. (An older single-`{"url": ...}` shape from before multi-calendar support still loads fine; `server.py` migrates it in memory on read.)

## Library (epub tracking)

A separate page, `library.html` (linked from "Library" in the dashboard topbar), for cataloging the epubs staged for Kindle transfer. Deliberately breaks from the dashboard's dark/teal theme — an old-fashioned reading-room look (deep maroon walls, mahogany bookcases, brass plaques, dentil crown molding), scoped entirely to this one file.

**Three bookcases:** Reading and Read sit side by side and show real face-out cover art; Collection underneath holds the entire library sorted A–Z as a classic row of spines (chunked across multiple shelf boards once it outgrows one row). Reading status (Want to Read / Reading / Read) and per-book notes are set from a click-through detail modal and saved to `localStorage` (`lib:` prefix) — separate from the dashboard's own `dash:` keys.

**How scanning works:** `server.py`'s `GET /api/library-scan` reads the folder path from `library-config.json` (`{"epub_folder": "..."}`, gitignored — machine-specific) and walks it recursively (books are organized into series/genre subfolders, not left flat). Each `.epub` is just a zip file — title/author come from the OPF package document's `dc:title`/`dc:creator`, and the cover image is pulled straight out of the manifest (EPUB2 `<meta name="cover">` or EPUB3 `properties="cover-image"`) and returned as a base64 data URI. Results are cached in memory per-file by mtime, so a rescan only re-parses epubs that actually changed. The "Folder…" button in the Library topbar reads/writes that config via `GET`/`POST /api/library-config` without needing to hand-edit the file. There's no auto-refresh interval — only an initial scan on page load and the manual "Rescan" button — since a personal epub collection doesn't change on its own, and periodic background rebuilds are exactly what caused the dashboard's own layout-jump issue (see the Weather panel history).

**Spine color-matching:** each spine (and each cover's fallback tile, if a book has no embedded cover) is colored from the book's *actual* cover art, not an arbitrary palette. Pillow (already installed on this machine — the one non-stdlib dependency in this project) decodes the cover, quantizes it to a small palette, and picks the most common color cluster that isn't near-black/near-white/near-gray (a flat pixel average blends everything into mud; the single largest cluster is usually just background or a shadow vignette). Degrades quietly to a hash-based palette if Pillow isn't available.

**Security notes**, since this endpoint parses files that could in principle come from anywhere: epub XML (container.xml/OPF) is parsed with any DOCTYPE declaration rejected outright, closing off "billion laughs" entity-expansion bombs without needing the `defusedxml` dependency. Cover art is rendered via DOM APIs (`createElement('img')` + `.src =`), not string-templated `innerHTML`, so a crafted cover value can't be interpreted as markup. All state-changing `POST` endpoints on `server.py` (library folder, calendar sync) now reject cross-origin requests (`Origin` header must match `127.0.0.1:8420` when present), and the calendar-sync fetch only allows `http`/`https` URLs — both closing real CSRF/SSRF gaps flagged by an automated review, not just library-specific hardening.

## How the Bluetooth panel stays live

Pieces, all in this folder:

- **`server.py`** — the local web server, replacing the stock `python -m http.server`. Serves this folder at `http://127.0.0.1:8420` (static files, same as before) and adds one route: `POST /api/poll-bluetooth`, which runs `check-bluetooth-battery.ps1` synchronously and returns `{"ok": true}` when it's done. This is what the Bluetooth panel's ⟳ button calls.
- **`check-bluetooth-battery.ps1`** — queries Windows' PnP device battery property for paired Bluetooth/media devices and writes the result to `battery.json`. Also checks whether `server.py` is running and (re)starts it if not (used to start the stock `http.server`; now starts `server.py` so the poll route stays available regardless of what launched it).
- **`start-dashboard-server.ps1`** — just the server-start half of the script above, with no Bluetooth polling. Runs at login (see below) so the dashboard is reachable without waiting on any scheduled task.

Both scripts launch `server.py` hidden (no console window) via `Start-Process -WindowStyle Hidden python.exe server.py`. **Must use `python.exe`, not `pythonw.exe`** — pythonw has no stdout/stderr, and the base `http.server` request logging throws on every request under pythonw, silently dropping the connection before a response is sent (`server.py` silences that logging itself, but the launch commands still use `python.exe` for consistency).

**Starts automatically at login** via a shortcut in the Startup folder (`shell:startup` → `Dashboard Server.lnk`), which runs `start-dashboard-server.ps1` hidden. Task Scheduler's "At log on" trigger is blocked by policy on this machine, so this uses the Startup folder instead — same mechanism already used for Ollama. Not a true "on power-on" start (it fires at user login, not before), but that's the practical equivalent here.

**Manual poll button**: the Bluetooth panel has a ⟳ button next to the device count. Clicking it calls `POST /api/poll-bluetooth`, waits for the script to finish, then refreshes the panel — useful now that the scheduled watchdog (below) is disabled and `battery.json` doesn't update on its own.

A Windows Scheduled Task, **"MAGI Bluetooth Battery Check"**, used to run `check-bluetooth-battery.ps1` every 2 minutes while logged in, doubling as both the auto-refresh for `battery.json` and the server watchdog.

To check the task: `schtasks /query /tn "MAGI Bluetooth Battery Check" /v /fo list`

> **Currently disabled (2026-07-21).** Suspected of interfering with Will's Bluetooth mouse/keyboard — paused to test. See `decisions/log.md` in the MAGI root for the full note. While disabled: `battery.json` only updates when the ⟳ button is clicked, and the server has no watchdog if it dies mid-session (login-time start still covers reboots). Re-enable auto-refresh with `schtasks /change /tn "MAGI Bluetooth Battery Check" /enable`.

## How data is saved

Everything you add (calendar events, projects, hobbies, shortcuts, notes) is saved in the browser's `localStorage`, scoped to that file on that machine/browser. That means:

- Data persists across reopens **as long as** you keep using the same file, in the same browser, on the same device.
- Moving the file, opening it in a different browser, or clearing browser data will reset it.
- There's currently no sync between devices.

## Known limitations / next steps

- **Calendar sync is one-way and read-only.** See "Calendar sync" above. Events created on the dashboard don't push back to iCloud/Google — that would need CalDAV (iCloud) or OAuth + the Calendar API (Google) instead of a plain ICS feed, a possible future upgrade.
- **No cross-device sync for locally-added events/notes/etc.** Still a `localStorage`/backend problem — unrelated to the calendar sync above, which is server-fetched and not affected by this.
- **Weather cities are hardcoded** to Roswell/Summerville/Duluth, GA (lat/lon in `WX_CITIES` in `dashboard.html`) — add more cities by adding entries there.
- **Bluetooth panel only shows devices Windows already reports a battery level for.** Some devices (especially headsets designed around a manufacturer app) never expose that property to Windows and won't appear.
- **`battery.json` doesn't auto-refresh while the scheduled watchdog task is disabled** (see above) — it only updates when the ⟳ button is clicked. The server itself still starts automatically at login.
- **Library reading status/notes are `localStorage`-only**, same cross-device caveat as the rest of the dashboard — see "How data is saved" above. Spine color-matching needs Pillow (already installed here); without it, spines fall back to a hash-based palette instead of the book's real cover color.

## Editing

`dashboard.html` is HTML/CSS/JS in one file. `check-bluetooth-battery.ps1` reads Bluetooth battery data; `server.py` serves the dashboard and exposes the on-demand poll route; `start-dashboard-server.ps1` is the login-time launcher for `server.py`. No build tools, no package.json — open any of them in any editor (or point Claude Code at them) and edit directly.

## Files

| File | Purpose |
|---|---|
| `dashboard.html` | The whole UI — markup, styles, and JS in one file. |
| `library.html` | The Library page — markup, styles (maroon/mahogany theme, scoped to this file), and JS in one file. |
| `server.py` | Local static file server (127.0.0.1:8420) plus `POST /api/poll-bluetooth`, `GET /api/calendar-events`, `POST`/`GET /api/ical-config`, `POST /api/ical-config/remove`, `GET /api/library-scan`, and `POST`/`GET /api/library-config`. |
| `check-bluetooth-battery.ps1` | Reads Bluetooth/media device battery levels from Windows, writes `battery.json`, and starts `server.py` if it isn't already running. |
| `start-dashboard-server.ps1` | Starts `server.py` if it isn't running — no Bluetooth polling. Run at login via the Startup folder shortcut. |
| `battery.json` | Generated data file the dashboard's Bluetooth panel reads. Not meant to be hand-edited. Gitignored — runtime data, not source. |
| `ical-config.json` | Holds connected calendar feeds (`{"calendars": [{"label", "url"}, ...]}`), written by the "⚙ Sync calendars" button. Gitignored — these are effectively-private links. |
| `library-config.json` | Holds the configured epub folder (`{"epub_folder": "..."}`), written by the Library page's "Folder…" button. Gitignored — a machine-specific path. |
| `bluetooth-battery-session-2026-07-20.html` | Dated working notes from building the Bluetooth panel — a session artifact, not part of the running app. |
