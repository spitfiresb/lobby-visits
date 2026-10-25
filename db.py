"""Data layer: reads the two CSVs at startup, cleans them, and loads them into
an in-memory SQLite database. All SQL lives in this file.

The CSV files themselves are never modified.
"""

import csv
import sqlite3
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent

VISIT_TYPES = ("guest", "interview", "contractor", "vendor")
ROLES = ("admin", "viewer")
PAGE_SIZE = 50

# The access rule lives here. A viewer's SELECT only ever names these
# columns, so visitor name, email and company (and who hosted them) never
# leave the database for a viewer. Nothing is removed from results afterwards.
ADMIN_COLUMNS = (
    "visit_id", "visit_date", "signed_in_at", "signed_out_at",
    "visitor_name", "visitor_email", "visitor_company", "visit_type",
    "host_name", "host_email", "host_team", "pre_registered",
)
VIEWER_COLUMNS = (
    "visit_id", "visit_date", "signed_in_at", "signed_out_at",
    "visit_type", "host_team", "pre_registered",
)

# What an admin's search looks in. All admin-only columns: see list_visits in
# app.py for why a viewer can't search.
SEARCH_COLUMNS = ("visitor_name", "visitor_email", "visitor_company", "host_name")

# A second sign-in by the same visitor, for the same host and visit type,
# within this window is a double sign-in on the lobby iPad, not a real second
# visit. Every duplicate in the export is under 2 minutes apart; genuine
# repeat visits on the same day are an hour or more apart.
DUPLICATE_WINDOW = timedelta(minutes=5)

# One shared connection. Flask serves requests on several threads, so the only
# write after startup (creating an account) takes this lock.
conn = sqlite3.connect(":memory:", check_same_thread=False)
conn.row_factory = sqlite3.Row
write_lock = threading.Lock()

# Filled by load(): the weekdays with no visits at all (the iPad wasn't
# recording), the first and last day the export covers, and the host teams.
missing_days = []
export_dates = {"first": None, "last": None}
host_teams = []


def normalize_email(email):
    """The allowlist has mixed-case and space-padded emails, so every email we
    compare (from the file or typed by a person) goes through this first."""
    return (email or "").strip().lower()


def read_csv(file_name):
    """Rows as dicts, with whitespace trimmed from every header and value."""
    with open(DATA_DIR / file_name, newline="", encoding="utf-8-sig") as f:
        return [
            {key.strip(): (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(f)
        ]


def clean_allowed_users(rows):
    users = []
    seen = set()
    for row in rows:
        email = normalize_email(row["email"])
        role = row["role"].lower()
        if role not in ROLES:
            print(f"allowed_users.csv: skipping {email}, unknown role {row['role']!r}")
            continue
        if email in seen:
            print(f"allowed_users.csv: skipping duplicate entry for {email}")
            continue
        seen.add(email)
        users.append({"email": email, "name": row["name"], "role": role})
    return users


def clean_visits(rows):
    visits = []
    for row in rows:
        if row["visit_type"] not in VISIT_TYPES:
            print(f"visits.csv: {row['visit_id']} has unknown visit type {row['visit_type']!r}")
        visits.append({
            **row,
            # Many visitors never sign out. Store that as NULL, not "".
            "signed_out_at": row["signed_out_at"] or None,
            "pre_registered": row["pre_registered"].lower() == "true",
        })
    return visits


def remove_duplicate_sign_ins(visits):
    """Drop repeat sign-ins (see DUPLICATE_WINDOW). The first sign-in is kept,
    since that's the row that has the sign-out time if there is one."""
    kept, removed = [], []
    last_sign_in = {}  # (visitor, host, type) -> time of the last kept sign-in

    for visit in sorted(visits, key=lambda v: v["signed_in_at"]):
        key = (visit["visitor_email"], visit["host_email"], visit["visit_type"])
        time = datetime.fromisoformat(visit["signed_in_at"])
        previous = last_sign_in.get(key)

        if previous is not None and time - previous <= DUPLICATE_WINDOW:
            removed.append(visit)
        else:
            kept.append(visit)
            last_sign_in[key] = time
    return kept, removed


def find_missing_weekdays(visits):
    """Weekdays between the first and last visit with no visits at all. In this
    export that's Mon 10 to Thu 13 August. Stats need this so those days aren't
    counted as quiet days."""
    dates_with_visits = {v["visit_date"] for v in visits}
    day = date.fromisoformat(min(dates_with_visits))
    last = date.fromisoformat(max(dates_with_visits))

    missing = []
    while day <= last:
        if day.weekday() < 5 and day.isoformat() not in dates_with_visits:  # Mon-Fri
            missing.append(day.isoformat())
        day += timedelta(days=1)
    return missing


def load():
    """Read, clean and load both CSVs. Call once at startup."""
    allowed_users = clean_allowed_users(read_csv("allowed_users.csv"))
    raw_visits = clean_visits(read_csv("visits.csv"))
    visits, duplicates = remove_duplicate_sign_ins(raw_visits)
    missing_days[:] = find_missing_weekdays(visits)
    export_dates["first"] = min(v["visit_date"] for v in visits)
    export_dates["last"] = max(v["visit_date"] for v in visits)
    host_teams[:] = sorted({v["host_team"] for v in visits})

    conn.executescript("""
        DROP TABLE IF EXISTS allowed_users;
        DROP TABLE IF EXISTS visits;
        DROP TABLE IF EXISTS accounts;

        CREATE TABLE allowed_users (
            email TEXT PRIMARY KEY,
            name  TEXT NOT NULL,
            role  TEXT NOT NULL
        );

        -- Created at signup. The role is not stored here: it's always read
        -- from allowed_users, so taking someone off the list ends their access.
        CREATE TABLE accounts (
            email         TEXT PRIMARY KEY REFERENCES allowed_users(email),
            password_hash TEXT NOT NULL,
            created_at    TEXT NOT NULL
        );

        CREATE TABLE visits (
            visit_id        TEXT PRIMARY KEY,
            visit_date      TEXT NOT NULL,  -- 2026-07-01
            signed_in_at    TEXT NOT NULL,  -- 2026-07-01 09:00:00
            signed_out_at   TEXT,           -- NULL if they never signed out
            visitor_name    TEXT NOT NULL,
            visitor_email   TEXT NOT NULL,
            visitor_company TEXT NOT NULL,
            visit_type      TEXT NOT NULL,
            host_name       TEXT NOT NULL,
            host_email      TEXT NOT NULL,
            host_team       TEXT NOT NULL,
            pre_registered  INTEGER NOT NULL  -- 0 or 1
        );
    """)
    conn.executemany(
        "INSERT INTO allowed_users (email, name, role) VALUES (:email, :name, :role)",
        allowed_users,
    )
    conn.executemany(
        """INSERT INTO visits VALUES (
            :visit_id, :visit_date, :signed_in_at, :signed_out_at,
            :visitor_name, :visitor_email, :visitor_company, :visit_type,
            :host_name, :host_email, :host_team, :pre_registered
        )""",
        visits,
    )
    conn.commit()

    print(
        f"Loaded {len(allowed_users)} allowed users and {len(raw_visits)} visit rows. "
        f"Removed {len(duplicates)} duplicate sign-ins, leaving {len(visits)} visits. "
        f"No data for: {', '.join(missing_days) or 'none'}."
    )


def find_allowed_user(email):
    """The allowlist entry for this email, or None if they're not on it."""
    row = conn.execute(
        "SELECT email, name, role FROM allowed_users WHERE email = ?",
        (normalize_email(email),),
    ).fetchone()
    return dict(row) if row else None


# --- Accounts -----------------------------------------------------------------

def get_account(email):
    """The account for this email, or None if they haven't signed up."""
    row = conn.execute(
        "SELECT email, password_hash FROM accounts WHERE email = ?",
        (normalize_email(email),),
    ).fetchone()
    return dict(row) if row else None


def create_account(email, password_hash):
    with write_lock:
        conn.execute(
            "INSERT INTO accounts (email, password_hash, created_at) VALUES (?, ?, ?)",
            (normalize_email(email), password_hash, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()


def list_users():
    """Everyone on the allowlist, and whether they've created an account."""
    rows = conn.execute("""
        SELECT u.email, u.name, u.role,
               a.created_at AS signed_up_at
        FROM allowed_users u
        LEFT JOIN accounts a ON a.email = u.email
        ORDER BY u.role, u.name
    """).fetchall()
    return [dict(row) for row in rows]


# --- Visits -------------------------------------------------------------------

def columns_for(role):
    return ADMIN_COLUMNS if role == "admin" else VIEWER_COLUMNS


def visit_to_dict(row):
    visit = dict(row)
    visit["pre_registered"] = bool(visit["pre_registered"])
    return visit


def build_where(filters):
    """SQL WHERE clause and its parameters for the chosen filters.
    `filters` has already been validated by app.py; any key may be missing or None."""
    conditions, params = [], []
    if filters.get("date_from"):
        conditions.append("visit_date >= ?")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        conditions.append("visit_date <= ?")
        params.append(filters["date_to"])
    if filters.get("visit_type"):
        conditions.append("visit_type = ?")
        params.append(filters["visit_type"])
    if filters.get("host_team"):
        conditions.append("host_team = ?")
        params.append(filters["host_team"])
    if filters.get("pre_registered") is not None:
        conditions.append("pre_registered = ?")
        params.append(int(filters["pre_registered"]))
    if filters.get("signed_out") is not None:
        conditions.append("signed_out_at IS NOT NULL" if filters["signed_out"] else "signed_out_at IS NULL")
    if filters.get("search"):
        # instr() rather than LIKE, so a % or _ in the search is just a character.
        matches = [f"instr(lower({column}), lower(?)) > 0" for column in SEARCH_COLUMNS]
        conditions.append("(" + " OR ".join(matches) + ")")
        params += [filters["search"]] * len(SEARCH_COLUMNS)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


def list_visits(filters, role, page=1):
    """One page of visits, newest first, plus the total matching count."""
    where, params = build_where(filters)
    columns = ", ".join(columns_for(role))

    total = conn.execute(f"SELECT COUNT(*) FROM visits {where}", params).fetchone()[0]
    total_pages = max(1, -(-total // PAGE_SIZE))  # ceiling division

    # Only fetch rows for a page that exists. app.py turns a page past the end
    # into a 400, and skipping the query means a huge page number can't
    # overflow SQLite's OFFSET.
    rows = []
    if page <= total_pages:
        rows = conn.execute(
            f"SELECT {columns} FROM visits {where} "
            "ORDER BY signed_in_at DESC LIMIT ? OFFSET ?",
            params + [PAGE_SIZE, (page - 1) * PAGE_SIZE],
        ).fetchall()

    return {
        "visits": [visit_to_dict(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "total_pages": total_pages,
    }


def get_visit(visit_id, role):
    """One visit, or None if there's no visit with that ID."""
    columns = ", ".join(columns_for(role))
    row = conn.execute(f"SELECT {columns} FROM visits WHERE visit_id = ?", (visit_id,)).fetchone()
    return visit_to_dict(row) if row else None


WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")  # date.weekday() 0-4


def recorded_days(filters):
    """The weekdays in the chosen range that we actually have data for: inside
    the export's dates, and not one of the outage days. Averages are taken
    over these days. A recorded day with no matching visits (say, no
    interviews that day) is a real zero and still counts."""
    first = max(filters.get("date_from") or export_dates["first"], export_dates["first"])
    last = min(filters.get("date_to") or export_dates["last"], export_dates["last"])

    days = []
    day = date.fromisoformat(first)
    while day <= date.fromisoformat(last):
        if day.weekday() < 5 and day.isoformat() not in missing_days:
            days.append(day)
        day += timedelta(days=1)
    return days


def get_stats(filters):
    """Headline numbers for the chosen filters. Same for both roles: counts
    contain no identity.

    Busiest day is by AVERAGE visits per recorded day, not by total. The
    10-13 Aug outage took a Monday-Thursday out of the data but no Friday, and
    the export has 14 Wednesdays but 13 of every other weekday, so totals
    compare unequal numbers of days (totals say Wednesday; averages say
    Tuesday). This is how road traffic counts handle sensor outages (the
    AASHTO method): average each weekday over the days that were recorded,
    and never fill in or zero the missing ones. See CLAUDE.md for sources.

    Busiest hour stays a plain count: the outage removed whole days, which
    lowers every hour equally, so the ranking can't change."""
    where, params = build_where(filters)

    total = conn.execute(f"SELECT COUNT(*) FROM visits {where}", params).fetchone()[0]
    visits_on = dict(conn.execute(
        f"SELECT visit_date, COUNT(*) FROM visits {where} GROUP BY visit_date", params
    ).fetchall())
    by_hour = conn.execute(
        f"""SELECT CAST(strftime('%H', signed_in_at) AS INTEGER) AS hour, COUNT(*) AS visits
            FROM visits {where} GROUP BY hour ORDER BY hour""",
        params,
    ).fetchall()

    days = recorded_days(filters)
    by_day = []
    for weekday, name in enumerate(WEEKDAY_NAMES):
        these_days = [d for d in days if d.weekday() == weekday]
        visits = sum(visits_on.get(d.isoformat(), 0) for d in these_days)
        by_day.append({
            "day": name,
            "visits": visits,
            "days_counted": len(these_days),
            # None, not 0, when there's no data for that weekday at all.
            "average_per_day": visits / len(these_days) if these_days else None,
        })

    # Always one winner. Ties on the exact average go to the higher total.
    has_data = [d for d in by_day if d["average_per_day"] is not None]
    busiest_day = max(has_data, key=lambda d: (d["average_per_day"], d["visits"]), default=None)
    busiest_hour = max(by_hour, key=lambda h: h["visits"], default=None)

    for d in by_day:  # round only after picking the winner, so rounding can't create a tie
        if d["average_per_day"] is not None:
            d["average_per_day"] = round(d["average_per_day"], 1)

    return {
        "total": total,
        "days_counted": len(days),
        "busiest_day": busiest_day["day"] if busiest_day and total else None,
        "busiest_hour": busiest_hour["hour"] if busiest_hour else None,
        "by_day_of_week": by_day,
        "by_hour": [{"hour": h["hour"], "visits": h["visits"]} for h in by_hour],
        "missing_days": missing_days_in(filters),
    }


def missing_days_in(filters):
    """The days with no data that fall inside the chosen date range, so the
    page can warn that those days aren't in the counts."""
    date_from = filters.get("date_from") or "0000-00-00"
    date_to = filters.get("date_to") or "9999-99-99"
    return [day for day in missing_days if date_from <= day <= date_to]
