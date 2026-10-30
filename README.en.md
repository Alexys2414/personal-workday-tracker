<p align="center">
  <img src="docs/banner.en.png" alt="Jornada: how long you've worked, how long is left, and the exact minute you can head home" width="100%">
</p>

<p align="center">
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-0f766e"></a>
  <img alt="Python 3.10 or newer" src="https://img.shields.io/badge/python-3.10%2B-0f766e">
  <img alt="Flask 3.1 bundled" src="https://img.shields.io/badge/flask-3.1%20bundled-0f766e">
  <img alt="No Node.js" src="https://img.shields.io/badge/node.js-not%20needed-b5561a">
  <img alt="No database" src="https://img.shields.io/badge/data-local%20JSON-b5561a">
  <img alt="Languages: Spanish and English" src="https://img.shields.io/badge/languages-ES%20%C2%B7%20EN-946a00">
  <img alt="Version 2.1" src="https://img.shields.io/badge/version-2.1-0f766e">
</p>

<p align="center">
  <a href="README.md">Español</a> · <b>English</b>
</p>

<p align="center">
  <a href="#quick-install-on-linux">Install</a> ·
  <a href="#using-jornada">Usage</a> ·
  <a href="#whats-new-in-jornada-21">New in 2.1</a> ·
  <a href="#keyboard-shortcuts">Shortcuts</a> ·
  <a href="#export-and-import">Export &amp; import</a> ·
  <a href="#storage-and-privacy">Privacy</a> ·
  <a href="#troubleshooting">Troubleshooting</a>
</p>

---

**Jornada** is a small web app that runs on your own computer. At a glance, it tells you how long you've worked,
how long is left and **the exact minute you can leave**, breaks included. It works offline, keeps everything in a local
JSON file and doesn't need administrator rights.

> [!IMPORTANT]
> Jornada is a **personal tool**. It is not an official time-keeping system and has no legal or employment value.
> It's for your own tracking.

## Contents

1. [Screenshots and demo](#screenshots-and-demo)
2. [Main features](#main-features)
3. [Requirements](#requirements)
4. [Quick install on Linux](#quick-install-on-linux)
5. [Quick install on Windows](#quick-install-on-windows)
6. [Create a desktop shortcut](#create-a-desktop-shortcut)
7. [Using Jornada](#using-jornada)
8. [What's new in Jornada 2.1](#whats-new-in-jornada-21)
   [Backups](#1-backup-and-restore) ·
   [Compact mode](#2-floating-compact-mode) ·
   [Alerts](#3-smart-alerts) ·
   [Simulator](#4-leaving-time-simulator) ·
   [Holidays](#5-holidays-vacation-and-absences) ·
   [Statistics](#6-advanced-statistics) ·
   [Weekly target](#7-weekly-target-and-simulated-compensation) ·
   [Personalisation](#8-visual-personalisation)
9. [Standard and short-day schedules](#standard-and-short-day-schedules)
10. [Keyboard shortcuts](#keyboard-shortcuts)
11. [Export and import](#export-and-import)
12. [Languages and themes](#languages-and-themes)
13. [Storage and privacy](#storage-and-privacy)
14. [Browser limitations](#browser-limitations)
15. [Project structure](#project-structure)
16. [Development and tests](#development-and-tests)
17. [Troubleshooting](#troubleshooting)
18. [Roadmap](#roadmap)
19. [Contributing](#contributing)
20. [License](#license)

## Screenshots and demo

<p align="center">
  <img src="docs/screenshots/dashboard-en.png" alt="Main dashboard in English: countdown, leaving time and clock-in action" width="860">
</p>

<p align="center">
  <img src="docs/demo.gif" alt="Demo: start day, break, back to work and day complete" width="760"><br>
  <sub>Start day → break → back to work → day complete (real recording, fictitious data, Spanish interface).</sub>
</p>

<table>
  <tr>
    <td width="50%"><img src="docs/screenshots/dashboard-light.png" alt="Dashboard in light mode"><br><sub><b>Light mode</b>: working, with the expected leaving time.</sub></td>
    <td width="50%"><img src="docs/screenshots/dashboard-dark.png" alt="Dashboard in dark mode"><br><sub><b>Dark mode</b>: the same states, tuned for the evening.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/simulator.png" alt="Workday simulator comparing current and simulated day"><br><sub><b>Simulator</b> (2.1): try breaks and leaving times without touching your records.</sub></td>
    <td><img src="docs/screenshots/stats.png" alt="Advanced statistics: activity map, averages, balance and weekly comparison"><br><sub><b>Statistics</b> (2.1): activity, averages, trend and weeks.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/weekly.png" alt="Weekly target card and upcoming days off"><br><sub><b>This week</b> (2.1): weekly target, closed balance and upcoming holidays.</sub></td>
    <td><img src="docs/screenshots/calendar-settings.png" alt="Holiday, vacation and day-type settings"><br><sub><b>Holidays and vacation</b> (2.1): recurring dates, ranges, import and rules.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/alerts.png" alt="Alert settings"><br><sub><b>Alerts</b> (2.1): countdown, day complete and breaks.</sub></td>
    <td><img src="docs/screenshots/backup.png" alt="Backups in Settings, Data"><br><sub><b>Backups</b> (2.1): everything in a single JSON file.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/accents.png" alt="Coral accent in light mode and violet with compact density in dark mode"><br><sub><b>Personalisation</b> (2.1): accents, density and animations.</sub></td>
    <td align="center"><img src="docs/screenshots/compact.png" alt="Compact view: state, countdown, exit and main action" width="280"><br><sub><b>Compact mode</b> (2.1): a widget to keep beside your work.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/calendar.png" alt="Monthly calendar, day details and week view"><br><sub><b>History</b>: calendar, day details with notes and week view.</sub></td>
    <td><img src="docs/screenshots/shortcuts.png" alt="Keyboard shortcut editor waiting for a combination"><br><sub><b>Shortcuts</b>: assign any combination, game-controls style.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/settings.png" alt="Schedule settings"><br><sub><b>Settings</b>: schedules, usual week and summer hours.</sub></td>
    <td><img src="docs/screenshots/import.png" alt="CSV import preview with duplicates"><br><sub><b>Import</b>: a preview before anything is saved.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/report.png" alt="Printable A4 report"><br><sub><b>PDF report</b>: ready to print on A4.</sub></td>
    <td align="center"><img src="docs/screenshots/mobile.png" alt="Mobile view with the clock-in button at the bottom" width="230"><br><sub><b>Mobile</b>: the main action sits within thumb reach.</sub></td>
  </tr>
</table>

<sub>All screenshots show the real app with fictitious data. Apart from the first one, they show the Spanish interface.</sub>

## Main features

| | |
|---|---|
| ⏱️ **Live countdown** | Time left updates every second. It's calculated from saved timestamps, so it stays exact even if you close the browser or the computer sleeps. |
| 🏁 **Exact leaving time** | Includes any mandatory break still to take. It also shows when you'd leave without it, and with your optional break. |
| ☕ **Multiple breaks** | During a break, work time freezes and a second timer runs. You're warned if the minimum break is missing. |
| 🎉 **Day complete** | A subtle celebration when you hit your target; keep working and overtime starts counting. |
| ⚖️ **Flexible balance** | Time over and under per day, week, month and all time. It warns but never blocks. |
| 🗓️ **Schedules** | Standard hours, short Friday and summer hours by date, plus a manual schedule for any single day. |
| 📝 **Notes** | One note per day and one per break. They never change any calculation. |
| ⌨️ **Custom shortcuts** | Any key combination for the main actions, with conflict detection. |
| 📤 **CSV and PDF** | Export full history, a week, a month or a date range. Printable A4 report. |
| 📥 **Safe import** | Preview, duplicate handling and a backup before saving. |
| 🌍 **Spanish and English** | Switches instantly, no page reload. |
| 🌗 **Light and dark** | Light, dark or system theme; layouts adapted to desktop, tablet and phone. |
| ♿ **Accessible** | Full keyboard navigation with visible focus, touch-friendly buttons and support for `prefers-reduced-motion`. |
| 💾 **Full backups** *(2.1)* | One JSON with days, settings and holidays; validated restore with an automatic copy first. |
| 🪟 **Compact mode** *(2.1)* | A 360 px widget in the same tab, a separate window or floating on top (where the browser supports it). |
| 🔔 **Alerts** *(2.1)* | At 30, 15, 5, 1 min or your own; day complete and breaks. In-app, desktop or sound. |
| 🧪 **Simulator** *(2.1)* | "What if I rest 20 min more?", "what if I leave at 17:00?"… never touching your records. |
| 🏖️ **Holidays and vacation** *(2.1)* | Holidays (also yearly), vacation ranges, leave, sick leave and absences; you decide how each type counts. |
| 📊 **Statistics** *(2.1)* | Activity map, balance trend, averages and weekly comparison, in SVG with data tables. |
| 🎯 **Weekly target** *(2.1)* | From your schedules or custom, with an informational compensation simulation. |
| 🎨 **Personalisation** *(2.1)* | Five accents, comfortable or compact density, reduced/normal/expressive animations and optional cards. |

## Requirements

- **Python 3.10 or newer.** It's the only thing you need. Flask and its dependencies are already bundled in
  the [`vendor/`](vendor/) folder.
- A modern browser: Firefox, Chrome, Edge or Safari.

You do **not** need `pip`, `npm`, Node.js, Docker, a database, an internet connection or administrator rights.

> [!NOTE]
> Jornada is not a standalone executable: it can't run without Python. If your computer doesn't have it,
> see [how to get it without admin rights](#python-isnt-found).

## Quick install on Linux

**Option A: with Git**

```bash
git clone https://github.com/<your-username>/jornada.git
cd jornada
./iniciar.sh
```

**Option B: downloading the ZIP**

1. On GitHub, click **Code → Download ZIP**.
2. Unzip it inside your home folder, for example `~/jornada`.
3. Open a terminal in that folder and run `./iniciar.sh`.

Your browser opens `http://127.0.0.1:8765`. For a desktop icon, see
[Create a desktop shortcut](#create-a-desktop-shortcut).

## Quick install on Windows

1. Download the project, with `git clone` or as a ZIP, and unzip it in your user folder.
2. Double-click **`iniciar.bat`**.
3. A console opens (that's the server), along with Jornada in your browser.

If the launcher can't find Python, it explains alternatives that **don't need admin rights**.
See also [Python isn't found](#python-isnt-found).

## Create a desktop shortcut

On **Linux**, once and without `sudo`:

```bash
./instalar-escritorio.sh
```

This creates:

- `~/.local/share/applications/jornada.desktop`: Jornada shows up in your applications menu.
- `~/Desktop/Jornada.desktop` (or your localized desktop folder): the desktop icon.
- `Jornada.desktop` inside the project, to start it from your file manager.

If your desktop marks the icon as "untrusted", allow it once:

| Desktop | What to do |
|---|---|
| GNOME / Ubuntu | Right-click the icon → **Allow Launching**. |
| KDE Plasma | On first double-click, choose **Execute** and "Do not ask again". |
| XFCE | **Mark executable** or **Launch anyway**. |
| Cinnamon / MATE | Properties → Permissions → **Allow executing file as program**. |

If you move the project folder, run the script again. To remove the shortcuts, run
`./instalar-escritorio.sh --quitar`; your data isn't touched.

On **Windows**, create a shortcut to `iniciar.bat` (right-click → *Send to → Desktop*).

## Using Jornada

### Open and quit

- **Open:** double-click the icon, `iniciar.sh` or `iniciar.bat`. If Jornada is already running, only the
  browser opens; a second instance is never created.
- **Quit completely:** the **⏻** button, top right → *Quit Jornada*. It stops the server and frees the port.
  Closing just the tab does not stop the server.
- **Auto-quit:** if nobody uses it for 12 hours, it closes itself. Change that with `JORNADA_IDLE_HOURS`;
  with `0` it never closes.

### An example day

With standard hours: 8 h 30 min of work and a 1 h mandatory break.

| Time | What you do | What Jornada shows |
|---|---|---|
| **07:53** | Press **Start day** | Expected clock-out **17:23** (07:53 + 8 h 30 min + 1 h break). |
| **12:00** | Check the dashboard | Worked **4 h 07 min**; **4 h 23 min** left; leaving at **17:23**. |
| **14:50** | **Start break** | Work time freezes; a second timer measures the break. |
| **15:49** | **End break** (59 min) | Before the break: 6 h 57 min. **1 h 33 min** left: you can leave at **17:22**. **1 min** of mandatory break is still missing; take it and you leave at **17:23**. |
| **17:22** | — | **Day complete! You can head home.** From here on it counts as overtime. |
| **17:45** | **Finish day** | Worked **8 h 53 min**: day balance **+23 min**. |

The balance accumulates without forcing you to make it up. With +25, −15, +40 and −10 minutes over four days,
the week's balance is **+40 min**. You can check it in the **Balance** section (today, week, month and all time)
and in the calendar, where each day shows its hours and its overtime or shortfall.

### Fixing entries

- **Edit** opens the day editor: clock-in, clock-out, breaks, schedule, target and notes.
  Clock-out and breaks are validated: no clock-out before clock-in, no overlapping breaks and no future times.
- **Add day** records a day you forgot to clock.
- **Resume day** undoes an accidental "Finish": the gap counts as a break.

### Notes

- **Day note:** the 📝 icon in the "Today" card, or "Add note" in any day's details.
- **Break note:** the 📝 icon next to each break, in the timeline or in the day's details.
- There are quick suggestions, such as "Team meeting" or "Doctor's appointment". Notes show subtly in the calendar and are included in exports.
  **They never change any time calculation.**

## What's new in Jornada 2.1

Eight new features, all optional and grouped in *Settings* or their own views so the dashboard stays clean.
None of them changes how existing days are calculated, and nothing needs installing.

### 1. Backup and restore

*Settings → Data → Backups.*

- **Download full backup** creates `jornada-backup-YYYY-MM-DD.json` with **everything**: days, breaks, notes, schedules,
  usual week, summer periods, holidays and absences, language, theme, accent, density, animations, visible cards,
  shortcuts, weekly target, alerts and day-type rules.
- **Restore a backup…**: pick the file and Jornada **parses and validates all of it** (format, version, structure, every date and
  time, every setting and a SHA-256 checksum). It shows what you have now and what you'll have afterwards, and warns that your
  current data **will be replaced**. You must tick a box and confirm.
- Before writing, Jornada saves a copy of the current data in `data/backups/pre-restauracion-…/`. The three files are written
  **as a single operation**: if something fails halfway, the files already replaced get their previous content back.
  You never end up with settings from one backup and records from another.
- Files over 10 MB, invalid JSON, non-Jornada files, backups from a newer version, unexpected keys, inconsistent data and hand-edited
  backups (checksum mismatch) are rejected, and nothing is written.
- If the data changes between the preview and the confirmation (for example, you clock in from another window), you're asked to start again.

<details>
<summary><b>File format (schema version 1)</b></summary>

```json
{
  "format": "jornada-backup",
  "schema_version": 1,
  "app_version": "2.1.0",
  "created_at": "2026-10-30T18:05:00+01:00",
  "checksum": "sha256:…",
  "counts": { "days": 120, "calendar_days": 14, "recurring": 9, "…": "…" },
  "data": {
    "records":  { "version": 1, "days": { "2026-10-29": { "clock_in": "…", "breaks": [ … ] } } },
    "settings": { "version": 3, "profiles": { … }, "accent": "teal", "notifications": { … } },
    "calendar": { "version": 1, "days": { "2026-12-08": { "type": "holiday", "label": "…" } }, "recurring": { "12-25": { "label": "Christmas" } } }
  }
}
```

- `checksum` is the SHA-256 of `data` serialised canonically (sorted keys, no spaces). It's optional on restore,
  but if present it must match.
- Future versions can read this schema and migrate it. This version rejects a `schema_version` greater than 1.
- Backups from 2.0 (version 2 settings, no `calendar`) are accepted and migrated on restore.
</details>

### 2. Floating compact mode

The **Compact mode** button (a window with a small box inside) in the top bar:

| Option | What it does |
|---|---|
| **Compact view here** | This tab shows only the widget (`/compact`). The ↗ button goes back to the full app. |
| **Open in a separate window** | A small browser window (~380 × 460) to keep beside your work. |
| **Keep on top** | Only shown if the browser supports the [Document Picture-in-Picture API](https://developer.mozilla.org/docs/Web/API/Document_Picture-in-Picture_API) (desktop Chrome and Edge 116+). The window floats above the others. |

The widget shows the state, countdown, leaving time, percentage done and the main action.

- **Sync:** the dashboard and the widget notify each other through `BroadcastChannel` (falling back to `localStorage`)
  and ask the server for the state every 30 s. The countdown is calculated locally, with no requests every second.
- **No duplicates:** each action carries the state its window expected. If another window has already changed the day,
  the server rejects it and the window refreshes.

> [!NOTE]
> "Keep on top" depends on the browser. Firefox and Safari don't offer it, so a normal window is used instead,
> and the OS won't keep it above other windows.

### 3. Smart alerts

*Settings → Alerts.*

- **Before finishing:** at 30, 15, 5 and 1 min (each one on/off) or any interval of your own (up to 8).
- **Day complete.**
- **Breaks (optional):** a reminder about the pending mandatory break after X hours of work, minimum break completed,
  and configured break exceeded.
- **How:** an in-app message, a desktop notification and a subtle sound (generated on the fly, no audio files).
  Desktop permission is **only requested when you turn that option on**. The sound only plays after you've interacted
  with the page, as browsers require.
- **No repeats:** each alert is recorded per day and shared across tabs and windows. Reloading doesn't repeat it,
  and if its moment has already passed when you open Jornada, you don't get a late alert. If you edit the day and more time is
  left again, the alert re-arms.

> [!IMPORTANT]
> Alerts are calculated in the browser. **They only work while Jornada is running and open** in some tab or window.
> They're not guaranteed with the server or browser closed or the computer asleep. There's no background process.

### 4. Leaving-time simulator

The **Simulate workday** button (wand icon) in the "Today" card, or <kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>S</kbd>.

- Adjust clock-in, target hours, break taken and extra break (sliders), use of the optional break and a desired exit.
  Results update instantly.
- Shortcuts for the usual questions: "What if I rest 20 min more?", "what if I leave at 17:00 / 18:30?",
  "what about the optional break?" and, for tomorrow, "what if I start at 07:45?".
- **Current vs simulated:** exit, time worked, breaks and balance, each with its difference and a visual bar.
- It uses **exactly the same calculation** as the dashboard (`core.compute_day`) on a copy of the day. It **never writes to
  `records.json`**; tests check that no file changes.

### 5. Holidays, vacation and absences

*Settings → Calendar*, or **Day type** in the details of any calendar day.

- **Types:** holiday, vacation, day off, leave, sick leave and custom absence (with a name).
- **Holidays:** create, edit and delete them, either on one date or **every year** on the same date.
  You can import them from JSON (`[{"date": "2026-12-08", "label": "…"}]`) or CSV (`date;name;recurring`, with dates
  `2026-12-08`, `08/12/2026` or `12-25` for every year). Jornada **ships no official calendars**: you add your own holidays,
  with no dependency on any API.
- **Vacation ranges:** pick from and to. Before confirming, you see how many days will be marked.
  Only your working days are marked, and holidays are kept.
- **How each type counts:** you decide, in *Settings → Calendar*:
  - **No target** (default): creates no deficit and lowers the weekly target.
  - **Keeps target:** if you don't work, it counts as a deficit.
- **Existing records:** marking a day that already has records **never changes its times**. Jornada asks:
  - **Just mark:** the label is shown and the day is unchanged.
  - **Apply rules:** its target becomes the type's, with a copy saved first in `data/backups/`.
- Working on a holiday counts entirely as extra time.
- **In the calendar**, each state can also be told apart without colour:

| State | Looks like |
|---|---|
| No record | Empty cell |
| Non-working | Dashed border |
| Holiday, vacation or other absence | Diagonal hatching + type icon (flag, suitcase, palm…) |
| Incomplete day | Red with the shortfall (−0:25) |
| Completed | Green with the surplus (+0:35) |

### 6. Advanced statistics

The **Advanced statistics** button in the *Balance* section. It opens a dedicated view so the dashboard stays light.

- **Monthly activity:** a heatmap of completed, incomplete and in-progress days, days off, non-working days and days without records.
- **Balance trend:** a line of the cumulative balance by **week** (12) or **month** (12).
- **Averages:** average clock-in and clock-out, effective work and break, plus the longest and shortest days.
  They only use days with records; clock-out, work and breaks only use closed days. Available for the month or all time.
- **Weekly comparison:** target vs hours done over the last 8 weeks, with the balance on top.
- A day **still open** is never read as a deficit: it only adds its extra time.
- Accessible: each chart has a description, a legend and a **Show data** button with the equivalent table. Hovering a point, bar or day shows its details.
  Charts are hand-drawn SVG, no libraries.

### 7. Weekly target and simulated compensation

The **This week** card on the dashboard and *Settings → Schedule → Weekly target*.

- **From my schedules** (default): the sum of each day's target. With the default schedules,
  4 × 8 h 30 min + 7 h = **41 h**. It uses your real values, short Friday, summer hours and holidays.
- **Custom:** any figure; holidays and vacation subtract their day.
- The card separates **progress** (hours done against the target: remaining and extra) from the **closed balance**
  (the sum of finished days). A day in progress is never shown as a deficit.
- **Simulated compensation** (can be turned off): "You're +0:45: what if you leave earlier?". Pick minutes and a day to see
  when you'd leave, that day's balance and how the week would end up. **It's informational only**: nothing is saved and
  Jornada applies no compensation rules.

### 8. Visual personalisation

*Settings → Appearance.* Changes preview instantly and are undone if you cancel.

- **Theme:** light, dark or follow the system.
- **Accent:** teal, blue, violet, coral or amber. Each one's contrast is checked (≥ 4.5:1) in both themes.
  With coral and amber, breaks switch to blue (and, with amber, "day complete" to teal) so states stay distinct.
- **Density:** comfortable or compact. It changes spacing and sizes; no information is hidden.
  (It's unrelated to *compact mode*, the floating window.)
- **Animations:** reduced, normal or expressive, the last adding a staggered entrance and a slightly bigger celebration.
  If your system asks for **less motion**, that always wins, whatever you choose.
- **Dashboard cards:** show or hide quick stats, running balance, weekly summary, upcoming holidays and history.
  The countdown, expected exit and clock buttons can't be hidden.

## Standard and short-day schedules

| Schedule | Default (editable in *Settings → Schedule*) |
|---|---|
| Standard hours | 08:00–18:00 · 8 h 30 min · 60 min break + 30 optional |
| Short Friday | 08:00–15:00 · 7 h |
| Summer hours | 08:00–15:00 · 7 h · applied by date, for example 1 July to 31 August |

- Each weekday has its own schedule, working-day flag and work mode (office or remote).
- **Priority:** a schedule picked by hand for a day > summer period > usual week.
- Every day **keeps the schedule and target it had**, so changing settings never rewrites the past.
- 7 h worked on a 7 h day gives a balance of 0, never a shortfall.

## Keyboard shortcuts

*Settings → Shortcuts.* Click **Assign key**, then press the combination you want.

| Action | Default |
|---|---|
| Start day | <kbd>Alt</kbd> + <kbd>Shift</kbd> + <kbd>I</kbd> |
| Start break | <kbd>Alt</kbd> + <kbd>Shift</kbd> + <kbd>D</kbd> |
| End break | <kbd>Alt</kbd> + <kbd>Shift</kbd> + <kbd>V</kbd> |
| Finish day | <kbd>Alt</kbd> + <kbd>Shift</kbd> + <kbd>F</kbd> |
| Open calendar | <kbd>Alt</kbd> + <kbd>Shift</kbd> + <kbd>C</kbd> |
| Open statistics | <kbd>Alt</kbd> + <kbd>Shift</kbd> + <kbd>B</kbd> |
| Open settings | <kbd>Alt</kbd> + <kbd>Shift</kbd> + <kbd>A</kbd> |
| Toggle light/dark theme | <kbd>Alt</kbd> + <kbd>Shift</kbd> + <kbd>T</kbd> |
| Edit today | <kbd>Alt</kbd> + <kbd>Shift</kbd> + <kbd>E</kbd> |
| Simulate workday *(2.1)* | <kbd>Alt</kbd> + <kbd>Shift</kbd> + <kbd>S</kbd> |

The defaults follow the Spanish action names (I = *Iniciar*, D = *Descanso*…); reassign them to whatever suits you.

- **Duplicates:** Jornada detects them and won't assign them.
- **Reserved shortcuts:** it warns about combinations usually owned by the browser or OS (for example <kbd>Ctrl</kbd>+<kbd>T</kbd>).
- **Managing them:** you can remove a binding or restore the defaults.
- **When they work:** only while the Jornada tab is focused, never while you're typing in a field or with a window open.
- **What they do:** only actions valid at that moment; for example, "End break" does nothing unless you're on a break.
- **Physical keys:** keys are identified by position (`KeyboardEvent.code`), so they work the same on any keyboard layout.
- **No global shortcuts:** nothing is installed at system level.

## Export and import

From **History → Export or import**, or *Settings → Data*.
To save **everything** (settings and holidays too) in one file, use the [full backup](#1-backup-and-restore).

### Export

- **What:** full history, this week, the selected month or a date range.
- **CSV:** works with Excel and LibreOffice (UTF-8, semicolon-separated). One column per field: date, work mode,
  schedule, clock-in, clock-out, time worked, target, balance, notes and every break with its note.
- **PDF report:** opens a page ready to print or *Save as PDF* on A4, with a table of days and a period
  summary (worked, target, breaks, time over and under).

### Import

1. Pick or drop a CSV. It can be one exported by Jornada, even after re-saving it in Excel.
2. Jornada validates the **whole** file (dates, times, breaks and structure) and shows a preview: new, already existing and with errors.
3. For dates that already exist, choose to **skip them** or **overwrite only the ones you tick**. Overwriting asks for confirmation.
4. On confirmation, **a backup** is saved in `data/backups/` and the changes are written in a single step.

If anything changes between the preview and the confirmation, the import stops without writing anything.
Exporting and re-importing keeps all relevant data; automated tests check this.

## Languages and themes

- **Language:** Spanish (default) or English, from the 🌐 button in the top bar or in *Settings → Appearance*.
  It switches instantly, without reloading, and is saved.
- **Theme:** light, dark or system (the ☀️/🌙 button or *Settings → Appearance*).
- **Formats:** 24 h or 12 h clock, and durations as `02:34:18` or `2 h 34 min`.

Strings live in [`static/i18n/`](static/i18n/). To add a language, copy `es.json` under a new name,
translate it and add its code to `LANGUAGES` in [`i18n.py`](i18n.py).

## Storage and privacy

- 🏠 **Everything stays on your computer**, in the `data/` folder. No accounts, no external database, no cloud sync.
- 🔒 **Localhost only:** the server listens on `127.0.0.1` and rejects requests that use any other host name.
- 📴 **Offline:** no CDN is used; the font and icons are bundled.
- 💾 **Safe saving:** every change is written instantly and atomically (temporary file, `fsync` and `os.replace`).
  The previous version is kept as `*.json.bak`.

| File | Contents |
|---|---|
| `data/records.json` | Your days: entries, breaks, notes, schedule and target for each day |
| `data/settings.json` | Schedules, week, summer hours, shortcuts, language, appearance, alerts, weekly target and day-type rules |
| `data/calendar.json` *(2.1)* | Holidays (one-off and recurring), vacation and absences |
| `data/backups/` | Automatic copies: before importing, restoring, applying a day type to existing days and migrating settings |

Holidays have their own file because they're data that grows over the years, not settings. The new preferences
extend `settings.json` instead of adding more files.

**Migration to 2.1:** on first launch, `settings.json` goes from version 2 to 3. A copy is saved first in
`data/backups/pre-migracion-ajustes-v2-…/`. Only **new** keys are added, with their defaults; no existing setting is
overwritten. `records.json` keeps its format: days created on a marked date include the optional `day_type` field.

> [!WARNING]
> **Never commit `data/` to any repository.** The project's `.gitignore` already excludes it, along with the generated
> shortcut, which contains paths from your computer.

## Browser limitations

Jornada only uses standard browser features. Some depend on the browser and the OS, so they aren't presented as guaranteed:

| Feature | Depends on |
|---|---|
| Desktop notifications | You granting permission to `127.0.0.1` and the system's notification service. |
| Alert sound | You having interacted with the page (autoplay policy). |
| Alerts in general | Jornada running and open in some tab; browsers throttle background tabs, so an alert may arrive a few seconds late. |
| Keeping the widget on top | Document Picture-in-Picture (desktop Chrome and Edge). Elsewhere, a normal window. |
| Separate window | The browser not blocking the pop-up for `127.0.0.1`. |
| Sync between windows | `BroadcastChannel`, or `localStorage` if missing; plus a server check every 30 s. |

## Project structure

```text
jornada/
├── app.py                 Flask server (127.0.0.1 only), API, lifecycle and port handling
├── core.py                Calculations, schedules, day types, validation and notes (no Flask)
├── insights.py            Simulator, weekly target, compensation and statistics (2.1, pure)
├── daymarks.py            Vacation ranges and holiday import (2.1, pure)
├── backup.py              Full-backup format and validation (2.1)
├── csvio.py               CSV export and import
├── i18n.py                Server-side translations (same JSON files as the browser)
├── storage.py             JSON with atomic writes, recovery and all-or-nothing multi-file writes
├── templates/
│   ├── index.html         Interface (served already translated)
│   ├── compact.html       Compact view /compact (2.1)
│   ├── _icons.html        Shared SVG icons
│   └── report.html        Printable A4 report
├── static/
│   ├── css/style.css      Visual system: tokens, accents, density, states, responsive and motion
│   ├── js/                common.js · app.js · notify.js · calendar.js · insights.js · compact.js ·
│   │                      i18n.js · shortcuts.js · datatools.js (no frameworks)
│   ├── i18n/              es.json · en.json
│   ├── fonts/             Plus Jakarta Sans (OFL)
│   └── img/               Icon
├── vendor/                Flask and dependencies (pure Python, with their licenses)
├── tests/                 Automated tests
├── iniciar.sh · iniciar.bat · instalar-escritorio.sh
└── docs/                  Banner, screenshots and demo
```

Principles: durations are calculated in UTC from saved timestamps, never with an in-memory counter.
Times are read in `Europe/Madrid`, daylight-saving changes included. The interface is HTML, CSS and JavaScript with no dependencies.

## Development and tests

```bash
python3 -m unittest -v        # 179 tests
python3 app.py --open         # manual start
python3 app.py --port 9000    # different preferred port (or PORT=9000)
WORKTIME_DATA_DIR=/tmp/test python3 app.py   # test data in another folder
```

The tests cover:

- **Calculations:** the 07:53 example, daylight saving, schedules and priorities.
- **Validation, notes and preferences.**
- **Export and import:** round trip, duplicates, files re-saved in Excel and formula protection.
- **Translations:** the same keys in both languages and no key used without a translation.
- **Real launches:** second instance, busy port and clean shutdown.
- **Versions:** every element the interface uses exists in the page, and an instance left open during an update never mixes versions.
- **Backups (2.1):** full export, exact round trip, corrupted or tampered files, future versions, old 2.0 backups,
  changes between preview and confirmation, and a **failure halfway through writing** without data loss.
- **Simulator (2.1):** it matches the dashboard's leaving time to the second; breaks, short days, overtime, early exit,
  and that it **modifies no file**.
- **Holidays and vacation (2.1):** recurring dates, ranges, holidays during summer hours, non-working days, configurable rules
  and untouched historical records.
- **Statistics and weekly target (2.1):** exact averages, incomplete weeks, open days, empty months, cumulative balance,
  vacation weeks and compensation.
- **Personalisation, alerts and compact mode (2.1):** persistence, accent contrast, reduced motion, no duplicated actions
  across windows, and the alert planner **run in headless Chrome** (no Node.js).
- **Real browser (2.1):** if Chrome or Chromium is available, the dashboard, simulator, statistics, settings and compact view are
  loaded with fictitious data and checked for JavaScript errors. Otherwise these tests are skipped.

## Troubleshooting

<details>
<summary><b>Python isn't found</b></summary>

- **Linux:** nearly every distribution ships `python3`. Without admin rights you can unzip a portable Python into
  `./python/`, so that `python/bin/python3` exists.
- **Windows:** use the python.org installer with *Customize installation* and leave *Install for all users* unticked
  (it installs for your user only). Alternatively, unzip the *Windows embeddable package* into a `python\` folder inside the project.
- If your company blocks all of these, the only option is to ask your IT department for Python.
</details>

<details>
<summary><b>Port 8765 is busy</b></summary>

Jornada automatically tries 8766, 8767… up to 8784, without touching the program that's using the port.
You can also pick another one with `--port`.
</details>

<details>
<summary><b>Double-click does nothing on Linux</b></summary>

Allow the icon (see the [shortcut](#create-a-desktop-shortcut) table), and run `./instalar-escritorio.sh` again
if you moved the folder. When started without a terminal, messages go to `data/jornada.log`.
</details>

<details>
<summary><b>I updated Jornada while it was open</b></summary>

Jornada notices and shows a banner: "Jornada has been updated". Quit it with **⏻** and open it again to run the new
server version. The page is always served consistently with the installed files, so versions never get mixed.
</details>

<details>
<summary><b>Desktop notifications don't show up</b></summary>

Check that the option is on in *Settings → Alerts*. If the browser blocked them, allow them for `127.0.0.1` in the site settings
(the padlock or info icon next to the address). Jornada must be open in some tab. Use **Test alert** to check.
</details>

<details>
<summary><b>The "Keep on top" option is missing</b></summary>

Your browser doesn't support Document Picture-in-Picture. Use "Open in a separate window": a normal, small window.
</details>

<details>
<summary><b>A backup can't be restored</b></summary>

Jornada explains why: it isn't JSON, isn't a Jornada backup, comes from a newer version, is damaged or was edited by hand.
Nothing was changed. If it's from a future version, update Jornada.
</details>

<details>
<summary><b>A shortcut does nothing</b></summary>

Check that the Jornada tab is focused, that you aren't typing in a field and that no window is open.
If Jornada warned you that the combination is reserved, the browser may be keeping it: pick another one.
</details>

<details>
<summary><b>Excel shows odd characters when opening the CSV</b></summary>

The CSV is UTF-8 with a BOM, which Excel recognizes. If you use *Data → From Text*, choose UTF-8 and the ";" separator.
Jornada can also import files that Excel re-saved with commas or in Windows-1252.
</details>

## Roadmap

Ideas that might come later; none of these exist yet:

- More languages (Catalan, Galician, Basque, Portuguese…), with no code changes.
- A standalone executable for computers without Python.
- Periodic automatic backups to a folder of your choice.

Available since 2.1: break reminder, weekly targets and a balance trend chart.

## Contributing

Contributions are welcome. Keep to the project's spirit: **small, local and with nothing extra to install**.

1. Open an issue describing the change.
2. Run `python3 -m unittest` before sending a pull request, and add tests for anything new.
3. Every visible string goes in `static/i18n/es.json` and `en.json`, with the same keys.
4. Never include real data in examples, screenshots or tests.

## License

Jornada's code is released under the [MIT](LICENSE) license. Third-party components keep their own licenses:

- Flask, Werkzeug, Jinja2, MarkupSafe, itsdangerous, Click and Blinker: BSD-3-Clause.
- tzdata: Apache-2.0.
- Plus Jakarta Sans: SIL OFL 1.1.

The license texts are in `vendor/*.dist-info/` and `static/fonts/`.
