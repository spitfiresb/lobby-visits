# Architecture

The Front Desk is one Python process. Flask serves both the JSON API and the HTML pages. The data lives in an in-memory SQLite database built from the two CSV files every time the server starts.

```
 Browser (HTML pages + app.js)          curl
            │                             │
            └──────────── HTTP ───────────┘
                          │
              ┌───────────▼────────────┐
              │  app.py  (Flask)       │
              │  routes + checks:      │
              │  session  → 401        │
              │  admin    → 403        │
              │  input    → 400        │
              └───────────┬────────────┘
                          │ calls with the user's role
              ┌───────────▼────────────┐       ┌──────────┐
              │  db.py                 │       │ auth.py  │
              │  all SQL queries       │◄──────┤ signup,  │
              │  role-based columns    │       │ login,   │
              └───────────┬────────────┘       │ sessions │
                          │                    └──────────┘
              ┌───────────▼────────────┐
              │  SQLite (in memory)    │
              │  visits                │
              │  allowed_users         │
              │  accounts              │
              └───────────▲────────────┘
                          │ loaded + cleaned at startup
              visits.csv, allowed_users.csv
```

## Files

| File | Responsibility |
|---|---|
| `app.py` | Every route, the session/admin/input checks, serving the HTML pages. Start here to see the whole API. |
| `db.py` | Loads and cleans the CSVs into SQLite at startup. Holds every SQL query. |
| `auth.py` | Signup (allowlist check), login, password hashing, the session store. |
| `static/` | The pages: `login.html`, `signup.html`, `visits.html`, `visit.html`, `admin-users.html`, `404.html`. Each page's own code is a short `<script>` at the bottom of its HTML. Shared by them: `app.js` (API calls, the nav, the sign-in redirect, escaping, formatting), `style.css` (the whole look, light and dark), and `pickers.js` (our own dropdown and calendar for the filters, used only by `visits.html`). |
| `requirements.txt` | `flask`, the only dependency. |
| `README.md` | How to run it, test logins, curl examples, the endpoint list. |
| `ARCHITECTURE.md` | This file: how the pieces fit together and why. |

## Data layer (`db.py`)

**At startup:**
1. Read `visits.csv` and `allowed_users.csv`.
2. Clean them. The CSVs themselves are never edited.
   - **Untidy allowlist emails.** Two admins' emails have capital letters or spaces around them, so `normalize_email()` trims and lowercases every email, from the file and from what a person types. Otherwise those two couldn't sign up.
   - **Double sign-ins.** 58 rows at the end of the export repeat an earlier sign-in by the same visitor, for the same host and type, seconds later (a double tap on the iPad). A repeat within 5 minutes (`DUPLICATE_WINDOW`) is dropped and the first sign-in kept: 2,011 rows become 1,953 visits.
   - **An outage.** There are no rows at all for Mon 10 – Thu 13 Aug. `find_missing_weekdays()` finds the gap so the stats don't count those days as quiet ones.
   - **Missing sign-outs.** 45% of visits have no sign-out time. That's normal visitor behavior, spread evenly across the data, so it's stored as `NULL` and no stat depends on visit length.
3. Insert them into three tables:
   - `visits`: one row per visit.
   - `allowed_users`: email, name, role.
   - `accounts`: created at signup, with the email and password hash.

**Queries:**
- `list_visits(filters, role, page)`: filtered (see below), newest first, 50 per page. Returns `visits`, `total`, `page`, `page_size`, `total_pages`. It only runs the row query for a page that exists, so a huge page number can't overflow SQLite's `OFFSET`.
- `get_visit(visit_id, role)`: one visit, or `None`.
- `get_stats(filters)`: `total`, `busiest_day`, `busiest_hour`, `days_counted`, `by_day_of_week` (Mon–Fri, each with `visits`, `days_counted`, `average_per_day`), `by_hour` (plain counts), and `missing_days` (the outage days inside the chosen range, so the page can warn about them).
  - **Busiest day is by average visits per recorded day**, not by total. A recorded day is a weekday inside the export's dates that isn't an outage day. Totals compare unequal numbers of days: the outage took out a Monday–Thursday but no Friday, and the export has 14 Wednesdays but 13 of every other weekday. Averaging each weekday over the days that were actually recorded, without filling in the missing ones, is how road traffic counts handle sensor outages (the AASHTO method in the US [FHWA Traffic Monitoring Guide](https://www.fhwa.dot.gov/policyinformation/tmguide/tmg_2022/appendix-l.cfm)). `recorded_days(filters)` lists those days.
  - A weekday with no recorded days gets `average_per_day: null`, not 0. With no visits in range, `busiest_day` and `busiest_hour` are `null`.
- `list_users()`: the allowlist plus `signed_up_at` (null if they haven't).
- `find_allowed_user(email)`, `get_account(email)`, `create_account(email, hash)`: used by `auth.py`. `create_account` returns `False` if the email already has an account (two signups at the same moment can both pass `auth.py`'s check; the table's unique email stops the second, which gets a 409).

**One connection, one lock.** Flask serves requests on several threads, and they all share one SQLite connection. Two threads must never use it at the same time: they'd share its prepared statements and read each other's results (seen as random 500s, and as signed-in people answered with "not signed in"). So after startup every query goes through `query(sql, params)`, which holds `db.lock`, and `create_account` holds it too. Each query takes well under a millisecond, so the lock costs nothing noticeable here.

**Filled in at startup** and read elsewhere: `missing_days` (the outage weekdays), `export_dates` (first and last day in the export) and `host_teams` (the 8 teams, used to validate `?team=`).

**Filters.** `filters` is `{date_from, date_to, visit_type}`, already validated by `app.py`. The list also takes `{host_team, pre_registered, signed_out, search}` (`parse_list_filters()`), which the stats ignore. `build_where()` turns whichever are set into one parameterized `WHERE` clause. Search uses `instr()` over `SEARCH_COLUMNS` (visitor name, email, company, host name), so `%` and `_` are plain characters.

**Role rule:** there are two fixed column lists, `ADMIN_COLUMNS` and `VIEWER_COLUMNS`. A viewer's `SELECT` never includes visitor name, email or company, or the host's name or email, so those values never leave the database for a viewer. Nothing is hidden or removed afterwards.

## API layer (`app.py`)

Every data request passes the same checks, in this order:

```
1. Session check   no or invalid cookie        → 401 {"error": "..."}
                   (one before_request hook for every /api/ path)
2. Role check      viewer on /api/users,       → 403 {"error": "..."}
                   viewer sending ?q= (search)
3. Validate input  bad date, end < start,      → 400 {"error": "<what to fix>"}
                   unknown type or team, a yes/no filter that isn't yes or no,
                   bad or past-the-end page
4. Query           db function called with the user's role → 200 JSON
```

| Method | Path | Who | Returns |
|---|---|---|---|
| POST | `/auth/signup` | anyone | Creates an account if the email is on the allowlist and signs you in: 201. 400 for a missing email or a password under 8 characters, 403 if not on the list, 409 if already signed up |
| POST | `/auth/login` | anyone | Sets the session cookie. 401, with one message, for a wrong email or a wrong password |
| POST | `/auth/logout` | signed in | Clears the session |
| GET | `/api/me` | signed in | Email, name, role, `can_see_visitor_identity` |
| GET | `/api/visits?from=&to=&type=&team=&pre_registered=yes\|no&signed_out=yes\|no&q=&page=` | signed in | Paged visit rows. Identity fields only for admin. `q` (search) is admin only: a viewer gets 403, since searching names would reveal who visited |
| GET | `/api/visits/<id>` | signed in | One visit. Identity fields only for admin |
| GET | `/api/stats?from=&to=&type=` | signed in | Busiest day (by average per recorded day) and hour, per-weekday totals and averages, counts by hour, and `missing_days` in the range |
| GET | `/api/users` | admin | The allowlist and signup status |

Signup and login accept JSON (curl, `fetch`) or a plain form post. Every error, including 404 and 405, is `{"error": "..."}`. Unknown `/api/` paths get 401 when signed out, so they don't reveal which routes exist.

**Sessions:** at login the server creates a random token, stores `token → email` in a Python dict, and sends it as an HttpOnly, SameSite=Lax cookie. This works in the browser and with curl (`-c` / `-b cookies.txt`). The role is looked up from the allowlist on every request, so taking someone off the list ends their access at once.

**Nothing survives a restart.** Accounts live in the in-memory database and sessions in a dict, so a restarted server has no accounts: everyone signs up again. That's deliberate for a prototype, so every fresh start behaves the same way, and the README says so.

## Pages

| URL | File | Who |
|---|---|---|
| `/login`, `/signup` | `login.html`, `signup.html` | anyone |
| `/visits` | `visits.html` | admin, viewer |
| `/visits/<id>` | `visit.html` | admin, viewer |
| `/admin/users` | `admin-users.html` | admin |
| anything else | `404.html` (status 404). Unknown `/api/` and `/auth/` paths get a JSON 404 instead | anyone |

- **Refresh works everywhere.** Flask maps each URL to its own HTML file. `/` redirects to `/visits`.
- **Filters live in the URL.** `/visits?from=2026-08-01&to=2026-08-31&type=interview` passes the same query string to `/api/visits` and `/api/stats`, so a shared link opens already filtered. The filter form is a plain GET form. The list's own filters (search, team, pre-registered, signed out) sit above the table, belong to the same form via `form="filters"`, and apply as you change them: the page rewrites the URL with `history.replaceState` and reloads only the list. "View" links carry the query string along, so "back" on a visit returns to the same filtered list.
- **Our own pickers.** `pickers.js` swaps the filter form's `<select>`s and date `<input>`s for its own dropdown and calendar. Each hides the real control, which still holds the value, so the form submits exactly what it did before. The dropdown fires a `change` event like a real `<select>`. An unknown `?type=` in the URL shows an empty dropdown and the API's 400 message.
- **Search is admin only.** The search box is only drawn for admins. A viewer who pastes a search link gets the API's 403 message on the page.
- **Page guards:** on load, `app.js` calls `/api/me`.
  - A 401 sends you to `/login?next=<this page>`, and you return there after signing in. `nextPage()` resolves `next` with the browser's URL parser and only follows it if it stays on this site, so `//evil`, `/\evil` and tab or newline tricks all land on `/visits`.
  - A viewer on `/admin/users` sees "you don't have access" on that same URL (no redirect, so no loop).
  - The nav only shows links the user's role can open, and marks the current one.
- **Display:** the viewer list shows a grey "Visitor" where a name would be; the visit page's heading is the visit type ("Interview visit"), with a grey line saying visitor details are only shown to admins. Values from the CSV are escaped (`esc()`) before going into HTML.
- **States:** "Loading…" while fetching, "No visits match these filters" when the dates and type match nothing, a "No visits match." row in the table when only the list filters do (the table dims while the list reloads), the API's own message in a red box for a 400 or 404, and a yellow warning when the range includes outage days. If no recorded days fall in the range at all, it says "No data was recorded for these dates" instead of "No visits".

## Where security lives

| Layer | Role |
|---|---|
| API (`app.py` + `db.py`) | **The real control.** Session check, admin check, and a role-specific `SELECT` that never fetches identity columns for a viewer. |
| API search rule (`app.py`) | A viewer can't search (`?q=` → 403). Search matches visitor names and emails, so letting a viewer search would let them learn who visited without ever seeing a name. |
| Pages (`app.js`) | **A courtesy.** Redirects, "no access" messages and a hidden search box, so people don't hit dead ends. Removing them would not expose any data. Two things here do matter: every CSV value is escaped before it goes into HTML (`esc()`), and `nextPage()` won't send anyone off-site after login. |

## Look

All in `style.css`: warm off-white or off-black (never pure white or black), hairlines, rounded `.panel` boxes, one dark button, grey tags for visit types and roles. Dark mode follows the computer's setting: every color is a CSS variable, and one `@media (prefers-color-scheme: dark)` block swaps them. System fonts only, nothing loaded from outside. Small animations (bars grow in, popovers fade and slide, the View link's underline draws in on hover) are switched off for people who ask for reduced motion.
