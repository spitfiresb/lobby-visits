# The Front Desk

A small internal web app for Brightline's workplace team. It shows lobby visits (who came in, when, and when the lobby gets busy) from the sign-in iPad's export.

The visit data is a list of real people's names and emails, so access is the point of the app:

- **Admins** (3 people) see everything, including each visitor's name, email and company, and who hosted them.
- **Viewers** (5 people) see how busy the building is: counts, dates, host teams and visit types. **Never a visitor's identity.**
- **Nobody else** can sign up.

These rules are enforced by the API. A viewer can't reach a visitor's name through the pages, by editing a URL, through a filter, or with curl.

It's one Python process: a Flask JSON API plus plain HTML pages, with `visits.csv` and `allowed_users.csv` loaded into SQLite at startup.

## Contents

- [Run it](#run-it)
- [Test logins](#test-logins)
- [Try it with curl](#try-it-with-curl)
- [API](#api)
- [Pages](#pages)
- [How access is enforced](#how-access-is-enforced)
- [About the data](#about-the-data)
- [Project layout](#project-layout)
- [What's simplified](#whats-simplified)

## Run it

Needs Python 3.9 or newer (tested on 3.12).

```bash
pip install -r requirements.txt
python app.py
```

Then open <http://localhost:5000>. Signing in takes you to the visits list.

At startup the server prints what it loaded and cleaned:

```
Loaded 8 allowed users and 2011 visit rows. Removed 58 duplicate sign-ins, leaving 1953 visits. No data for: 2026-08-10, 2026-08-11, 2026-08-12, 2026-08-13.
```

## Test logins

Nobody is pre-registered: everyone on the allowlist creates their own account. So for each role, **sign up once** at <http://localhost:5000/signup> with the email and password below, then use the same details to sign in.

| Role | Name | Email | Password |
|---|---|---|---|
| Admin | Dana Whitfield | `dana.whitfield@brightline.example` | `admin-pass-1` |
| Viewer | Sam Ferreira | `sam.ferreira@brightline.example` | `viewer-pass-1` |

- Signing up also signs you in.
- **Accounts are kept in memory, so they reset when the server restarts.** After a restart, sign up again with the same details.
- Any of the 8 people in `allowed_users.csv` can sign up (with any password of 8+ characters). Email matching ignores case and spaces. Any other email is refused.
- To try both roles side by side, use a normal window for one and a private window for the other.

## Try it with curl

These use a cookie file to stay signed in, the same way a browser does. Run them in a Unix-style shell: macOS or Linux, or Git Bash on Windows. Windows PowerShell's `curl` is a different command.

**1. Sign up both test users.** Skip this if you already signed up on the page; you'd get "You already have an account".

```bash
curl -s -X POST localhost:5000/auth/signup -H "Content-Type: application/json" -d '{"email":"dana.whitfield@brightline.example","password":"admin-pass-1"}'
curl -s -X POST localhost:5000/auth/signup -H "Content-Type: application/json" -d '{"email":"sam.ferreira@brightline.example","password":"viewer-pass-1"}'
```

**2. Log in.** `-c` saves the session cookie to a file, one file per person:

```bash
curl -s -c admin.txt -X POST localhost:5000/auth/login -H "Content-Type: application/json" -d '{"email":"dana.whitfield@brightline.example","password":"admin-pass-1"}'
curl -s -c viewer.txt -X POST localhost:5000/auth/login -H "Content-Type: application/json" -d '{"email":"sam.ferreira@brightline.example","password":"viewer-pass-1"}'
```

```json
{"email":"sam.ferreira@brightline.example","name":"Sam Ferreira","role":"viewer"}
```

**3. A filtered visits call: interviews in August.** `-b` sends the saved cookie:

```bash
curl -s -b viewer.txt "localhost:5000/api/visits?from=2026-08-01&to=2026-08-31&type=interview"
```

The same call as each role. There are 115 matching visits, 50 per page, newest first:

<table>
<tr><th>Admin (<code>-b admin.txt</code>)</th><th>Viewer (<code>-b viewer.txt</code>)</th></tr>
<tr><td>

```json
{
  "visits": [
    {
      "visit_id": "V001211",
      "visit_date": "2026-08-31",
      "signed_in_at": "2026-08-31 09:53:00",
      "signed_out_at": null,
      "visitor_name": "Clara Ferreira",
      "visitor_email": "cferreira@pacificfreig.example",
      "visitor_company": "Pacific Freight",
      "visit_type": "interview",
      "host_name": "Kenji Osei",
      "host_email": "kenji.osei@brightline.example",
      "host_team": "Facilities",
      "pre_registered": false
    },
    ...
  ],
  "total": 115,
  "page": 1,
  "page_size": 50,
  "total_pages": 3
}
```

</td><td>

```json
{
  "visits": [
    {
      "visit_id": "V001211",
      "visit_date": "2026-08-31",
      "signed_in_at": "2026-08-31 09:53:00",
      "signed_out_at": null,
      "visit_type": "interview",
      "host_team": "Facilities",
      "pre_registered": false
    },
    ...
  ],
  "total": 115,
  "page": 1,
  "page_size": 50,
  "total_pages": 3
}
```

</td></tr>
</table>

The viewer's rows don't hide the identity fields or set them to `null`. The fields aren't in the response at all.

**4. Check it yourself.** Search the viewer's raw response for a visitor's name. It prints `0`:

```bash
curl -s -b viewer.txt "localhost:5000/api/visits?type=interview" | grep -c "Felix Fischer"
```

## API

All responses are JSON. Every `/api/` endpoint needs a session cookie; the `/auth/` ones don't.

### Auth

| Method | Path | Body | Does |
|---|---|---|---|
| POST | `/auth/signup` | `{"email", "password"}` | Creates an account if the email is on the allowlist, and signs you in. **201** |
| POST | `/auth/login` | `{"email", "password"}` | Starts a session: sets an HttpOnly `session` cookie. **200** |
| POST | `/auth/logout` | | Ends the session |

Signup and login also accept a plain HTML form post.

### Data

| Method | Path | Who | Returns |
|---|---|---|---|
| GET | `/api/me` | signed in | `email`, `name`, `role` and `can_see_visitor_identity` |
| GET | `/api/visits` | signed in | One page of visits (filters below), newest first: `visits`, `total`, `page`, `page_size` (50), `total_pages`. Identity fields only for admins |
| GET | `/api/visits/<visit_id>` | signed in | One visit, e.g. `/api/visits/V000004`. Identity fields only for admins |
| GET | `/api/stats` | signed in | The headline numbers for the same date and type filters (see below) |
| GET | `/api/users` | **admin** | The allowlist, with `signed_up_at` for each person (`null` if they haven't signed up) |

### Filters

`/api/visits` and `/api/stats` both take:

| Parameter | Example | |
|---|---|---|
| `from=` | `from=2026-08-01` | First day, inclusive |
| `to=` | `to=2026-08-31` | Last day, inclusive |
| `type=` | `type=interview` | `guest`, `interview`, `contractor` or `vendor` |

`/api/visits` also takes:

| Parameter | Example | |
|---|---|---|
| `page=` | `page=2` | Which page of 50 |
| `team=` | `team=Engineering` | The host's team: Engineering, Executive, Facilities, Finance, Legal, Marketing, Recruiting or Sales |
| `pre_registered=` | `pre_registered=yes` | `yes` or `no` |
| `signed_out=` | `signed_out=no` | `yes` or `no`: whether the visitor signed out |
| `q=` | `q=pacific` | **Admins only.** Searches visitor name, email, company and host name |

All filtering, counting and paging happen on the server.

### Stats

`/api/stats?from=2026-08-01&to=2026-08-31` returns (trimmed):

```json
{
  "total": 494,
  "days_counted": 17,
  "busiest_day": "Wednesday",
  "busiest_hour": 9,
  "by_day_of_week": [
    {"day": "Monday", "visits": 97, "days_counted": 4, "average_per_day": 24.2},
    {"day": "Tuesday", "visits": 109, "days_counted": 3, "average_per_day": 36.3},
    ...
  ],
  "by_hour": [{"hour": 9, "visits": 182}, {"hour": 10, "visits": 58}, ...],
  "missing_days": ["2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13"]
}
```

- **`busiest_day` is by average visits per recorded day, not by total.** See [the outage](#about-the-data) for why.
- **`days_counted`** is the number of weekdays in the range that have data.
- **`missing_days`** lists the outage days inside the range, so the page can warn about them. A weekday with no recorded days gets `average_per_day: null`, not 0.

### Errors

Every error has the same shape, `{"error": "<a message a person can act on>"}`:

| Status | When | Example message |
|---|---|---|
| **400** | Bad input: a malformed date, an end date before the start, an unknown type or team, a yes/no filter that isn't yes or no, a bad page or one past the end, a missing email, a password under 8 characters | `The end date (2026-08-01) is before the start date (2026-08-31). Pick an end date on or after the start date.` |
| **401** | No valid session, or a wrong email or password at login | `You're not signed in. Sign in with POST /auth/login first.` |
| **403** | A viewer on an admin-only endpoint, a viewer searching, or a signup from an email not on the allowlist | `Only admins can see the user list.` |
| **404** | An unknown visit or path | `There's no visit with ID 'V999999'.` |
| **405** | The wrong method, like `GET /auth/login` | `GET isn't supported on /auth/login.` |
| **409** | Signing up twice | `You already have an account. Sign in instead.` |

Login gives the same message for a wrong email and a wrong password, so it can't be used to find out who has an account. When you're signed out, an unknown `/api/` path gets 401, not 404, so it doesn't reveal which routes exist.

## Pages

| URL | Who | What's on it |
|---|---|---|
| `/login`, `/signup` | anyone | Sign in, or create an account if you're on the allowlist |
| `/visits` | both | The headline numbers (total visits, busiest day and hour), counts by day and by hour, and the visit list with filters. Admins also get a search box |
| `/visits/<visit_id>` | both | One visit. An admin sees the person; a viewer sees the visit type as the heading, and the date, times, host team and pre-registration |
| `/admin/users` | admins | The allowlist, and who has signed up |
| anything else | anyone | A real "page not found" page (status 404) |

- **Every page has its own URL**, so refreshing any page, including a single visit, keeps you there.
- **Filters live in the URL.** <http://localhost:5000/visits?from=2026-08-01&to=2026-08-31&type=interview> opens already filtered, so a pasted link shows the same list. Opening a visit keeps the filters, so going back returns to the same list.
- **Not signed in?** You're sent to `/login` and brought back to the page you wanted afterwards.
- **A viewer on an admin page** sees "You don't have access to this page". The nav never offers them that link.
- **Where a viewer would see a name**, the list shows a grey "Visitor".
- **Plain words on screen:** "Didn't sign out" rather than a blank or `null`, and a warning when the dates include days with no data.

## How access is enforced

| Layer | Its job |
|---|---|
| **The API** (`app.py` + `db.py`) | **The real control.** One check runs before every `/api/` request and returns 401 without a valid session. Admin-only routes return 403 to a viewer. A viewer's database query only ever selects the columns a viewer may see (`VIEWER_COLUMNS` in `db.py`), so identity values never leave the database for them. Nothing is removed from results afterwards. |
| **Search** (`app.py`) | A viewer sending `q=` gets 403. Search matches visitor names and emails, so otherwise a viewer could learn whether someone visited ("any results for Jane Doe?") without ever seeing a name. |
| **The pages** (`static/app.js`) | **A courtesy**, not security. Redirects, "no access" messages and hiding links and the search box from viewers keep people out of dead ends. Removing them wouldn't expose any data. |

Some other details:
- A person's role is read from the allowlist on every request, so taking someone off the list ends their access straight away.
- Values from the CSV are escaped before they go into a page.
- After login, the page only returns you to an address on this site, so a crafted sign-in link can't send someone elsewhere.

## About the data

The export has problems that would quietly skew the numbers or lock people out. The app handles each one when it loads. **The CSV files themselves are never changed.**

| Problem | What it would have caused | What the app does |
|---|---|---|
| **Untidy emails in the allowlist.** `Marcus.Vitale@Brightline.example` has capitals; ` ines.reyes@brightline.example ` has spaces around it. | Two of the three admins couldn't sign up. | Trims and lowercases emails, both from the file and whatever a person types. |
| **58 duplicate sign-ins** (V001954–V002011). Each repeats an earlier sign-in by the same visitor, for the same host and visit type, 11–95 seconds later: a double tap on the iPad. | Every count about 3% too high; people listed twice. | Keeps the first sign-in and drops any repeat within 5 minutes. 2,011 rows become 1,953 visits. Three genuine same-day repeat visits (an hour or more apart) are kept. |
| **No data for Mon 10 – Thu 13 August.** Four weekdays have no rows at all, while Friday the 14th has 20. The iPad wasn't recording. | Raw totals compare unequal numbers of days: those four days are missing from Monday–Thursday but not Friday, and the range also has 14 Wednesdays but 13 of every other weekday. Totals say Wednesday is busiest (509 visits); the fair comparison says Tuesday. | Picks the busiest day by **average visits per recorded day**: Tuesday, 39.6 a day, just ahead of Wednesday's 39.2. Missing days are left out, never counted as zero or filled in. The pages warn when the dates include them. |
| **45% of visits have no sign-out time** (870 of 1,953), spread evenly across months, types and hours. | Visitors simply leave without signing out. Nothing here depends on visit length, so no number is affected. | Stores it as empty, and the pages say "Didn't sign out". |

The busiest-day method is the one US road agencies use when roadside traffic counters go offline: average each day of the week over the days that were actually recorded, and don't invent the missing ones. See [AASHTO's method in the FHWA Traffic Monitoring Guide](https://www.fhwa.dot.gov/policyinformation/tmguide/tmg_2022/appendix-l.cfm). Days lost to an equipment fault don't bias the averages; they just leave fewer days behind them. Tuesday and Wednesday are within day-to-day noise of each other. The clear pattern is that midweek is busy, and Mondays and Fridays are quiet.

## Project layout

```
app.py            Every route, and the checks each request goes through. Start here.
db.py             Loads and cleans the CSVs into SQLite at startup. Every SQL query.
auth.py           Signup (the allowlist check), login, password hashing, sessions.
static/           The pages. Each page's own code is a short script at the bottom.
  login.html, signup.html, visits.html, visit.html, admin-users.html, 404.html
  app.js          Shared by every page: API calls, the nav, sign-in redirects, escaping.
  pickers.js      The dropdown and calendar used by the filters.
  style.css       The look.
visits.csv        Three months of lobby sign-ins, one row per visit.
allowed_users.csv The 8 people who may use the app, and their roles.
requirements.txt  flask, the only dependency.
```

The only dependency is Flask. SQLite and password hashing come with Python and Flask.

## What's simplified

This is a prototype that runs on your own machine.

- **Accounts and sessions live in memory.** A restart forgets every account, so everyone signs up again.
- **Signing up doesn't verify the email.** Anyone who knows an allowlisted address can register as that person, if they get there first.
- **No HTTPS, password reset, rate limiting or two-factor sign-in.**

Passwords are stored hashed (werkzeug's salted hashing, which comes with Flask), never in plain text.
