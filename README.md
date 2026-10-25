# The Front Desk

A small internal web app for Brightline's workplace team. It shows lobby visits (who came in, when, and when the lobby gets busy) from the sign-in iPad's export.

- **Admins** (3 people) see everything, including each visitor's name, email and company, and who hosted them.
- **Viewers** (5 people) see how busy the building is: counts, dates, host teams and visit types. **Never a visitor's identity.**
- **Nobody else** can sign up.

These rules are enforced by the API, not just the pages. It's one Python process: a Flask JSON API plus plain HTML pages, with `visits.csv` and `allowed_users.csv` loaded into SQLite at startup.

## Run it

Needs Python 3.9 or newer (tested on 3.12).

```bash
pip install -r requirements.txt
python app.py
```

Then open <http://localhost:5000>.

## Test logins

Nobody is pre-registered, so for each role **sign up once** at <http://localhost:5000/signup> with the details below, then sign in with them.

| Role | Name | Email | Password |
|---|---|---|---|
| Admin | Dana Whitfield | `dana.whitfield@brightline.example` | `admin-pass-1` |
| Viewer | Sam Ferreira | `sam.ferreira@brightline.example` | `viewer-pass-1` |

- **Accounts are kept in memory, so they reset when the server restarts.** After a restart, sign up again.
- Any of the 8 people in `allowed_users.csv` can sign up. Email matching ignores case and spaces. Any other email is refused.
- To use both roles at once, use a normal window for one and a private window for the other.

## Try it with curl

Run these in macOS/Linux or Git Bash (Windows PowerShell's `curl` is a different command). They keep the session in a cookie file, like a browser does.

**1. Sign up.** Skip this if you already signed up on the page.

```bash
curl -s -X POST localhost:5000/auth/signup -H "Content-Type: application/json" -d '{"email":"sam.ferreira@brightline.example","password":"viewer-pass-1"}'
```

**2. Log in.** `-c` saves the session cookie:

```bash
curl -s -c cookies.txt -X POST localhost:5000/auth/login -H "Content-Type: application/json" -d '{"email":"sam.ferreira@brightline.example","password":"viewer-pass-1"}'
```

**3. A filtered visits call: interviews in August.** `-b` sends the cookie:

```bash
curl -s -b cookies.txt "localhost:5000/api/visits?from=2026-08-01&to=2026-08-31&type=interview"
```

This returns 115 visits, 50 per page. A viewer's rows don't contain the identity fields at all. They aren't hidden or set to `null`:

```json
{"visit_id": "V001211", "visit_date": "2026-08-31", "signed_in_at": "2026-08-31 09:53:00", "signed_out_at": null, "visit_type": "interview", "host_team": "Facilities", "pre_registered": false}
```

As the admin, the same rows also include `visitor_name`, `visitor_email`, `visitor_company`, `host_name` and `host_email`.

**4. Check it yourself.** Search the viewer's raw response for the name of a visitor who is on that page. It prints `0`:

```bash
curl -s -b cookies.txt "localhost:5000/api/visits?from=2026-08-01&to=2026-08-31&type=interview" | grep -c "Hannah Okafor"
```

Signed in as the admin, the same command prints `1`.

## API

All responses are JSON. Every `/api/` endpoint needs a session cookie; the `/auth/` ones don't.

| Method | Path | Who | Does |
|---|---|---|---|
| POST | `/auth/signup` | anyone | `{"email", "password"}`. Creates an account if the email is on the allowlist, and signs you in |
| POST | `/auth/login` | anyone | `{"email", "password"}`. Starts a session (an HttpOnly cookie) |
| POST | `/auth/logout` | anyone | Ends the session |
| GET | `/api/me` | signed in | Your email, name and role |
| GET | `/api/visits` | signed in | One page of visits, newest first, with `total` and `total_pages`. Identity fields only for admins |
| GET | `/api/visits/<visit_id>` | signed in | One visit, e.g. `/api/visits/V000004`. Identity fields only for admins |
| GET | `/api/stats` | signed in | Total visits, busiest day and hour, and counts by day of week and by hour |
| GET | `/api/users` | admin | The allowlist, and who has signed up |

**Filters.** All filtering, counting and paging happen on the server.

| Parameter | Works on | |
|---|---|---|
| `from=2026-08-01`, `to=2026-08-31` | visits, stats | Date range, inclusive |
| `type=interview` | visits, stats | `guest`, `interview`, `contractor` or `vendor` |
| `page=2` | visits | Which page of 50 |
| `team=Engineering`, `pre_registered=yes`, `signed_out=no` | visits | Host team, and two yes/no filters |
| `q=pacific` | visits | Search by visitor, company or host. **Admins only** |

The busiest day is picked by average visits per recorded day, not by total. A four-day outage in August left Monday to Thursday with fewer recorded days than Friday, so totals would compare unequal numbers of days.

**Errors** are always `{"error": "<a message a person can act on>"}`:

| Status | When |
|---|---|
| 400 | Bad input: a malformed date, an end date before the start, an unknown type or team, a yes/no filter that isn't yes or no, a bad page |
| 401 | Not signed in, or a wrong email or password |
| 403 | A viewer on an admin-only endpoint or searching, or a signup from an email not on the allowlist |
| 404 | An unknown visit or path |
| 409 | Signing up twice |

## Pages

| URL | Who | What's on it |
|---|---|---|
| `/login`, `/signup` | anyone | Sign in, or create an account |
| `/visits` | both | Headline numbers (total, busiest day and hour), counts by day and hour, and the filtered visit list |
| `/visits/<visit_id>` | both | One visit. An admin sees the person; a viewer sees the visit without anyone's identity |
| `/admin/users` | admins | The allowlist, and who has signed up. A viewer sees "You don't have access" |
| anything else | anyone | A "page not found" page |

Every page has its own URL and survives a refresh. Filters live in the URL, so a pasted link opens already filtered. If you're not signed in, you're sent to sign in and then brought back.

## How access is enforced

- **The API is the real control.** One check runs before every `/api/` request (no session: 401), and admin-only routes refuse viewers (403).
- **A viewer's database query never selects identity columns** (`VIEWER_COLUMNS` in `db.py`), so names and emails never leave the database for them. Search is admin-only for the same reason: otherwise a viewer could learn whether someone visited.
- **The pages are a courtesy.** Redirects, "no access" messages, and hiding links from viewers keep people out of dead ends. Removing them wouldn't expose any data.

## Project layout

```
app.py            Every route, and the checks each request goes through. Start here.
db.py             Loads and cleans the CSVs into SQLite at startup. Every SQL query.
auth.py           Signup (the allowlist check), login, password hashing, sessions.
static/           The pages, plus shared app.js (API calls, nav, escaping),
                  pickers.js (filter dropdowns and calendar) and style.css.
visits.csv        Three months of lobby sign-ins. Never modified; cleaned on load.
allowed_users.csv The 8 people who may use the app, and their roles.
requirements.txt  flask, the only dependency.
ARCHITECTURE.md   How the pieces fit together, and why.
```
