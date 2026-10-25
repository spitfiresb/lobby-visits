"""The Front Desk: every route lives in this file.

Every /api/ request goes through the same checks, in this order:
  1. Signed in?        no  -> 401   (load_user, runs before every request)
  2. Allowed here?     no  -> 403   (admin-only routes)
  3. Input makes sense? no -> 400   (parse_filters, parse_page)
  4. Query db.py with the user's role -> 200 JSON
"""

from datetime import datetime

from flask import Flask, g, jsonify, redirect, request

import auth
import db

SESSION_COOKIE = "session"

app = Flask(__name__)
app.json.sort_keys = False  # keep fields in the order db.py selects them

db.load()


# --- Errors -------------------------------------------------------------------

class InputError(Exception):
    """Bad query input. Becomes a 400 with a message the person can act on."""


def error(status, message):
    return jsonify(error=message), status


@app.errorhandler(InputError)
def handle_input_error(e):
    return error(400, str(e))


@app.errorhandler(auth.AuthError)
def handle_auth_error(e):
    return error(e.status, e.message)


@app.errorhandler(404)
def handle_not_found(e):
    # curl and fetch() get JSON. A person in a browser gets a real page.
    if request.path.startswith(("/api/", "/auth/")):
        return error(404, f"There's nothing at {request.path}.")
    return app.send_static_file("404.html"), 404


@app.errorhandler(405)
def handle_wrong_method(e):
    return error(405, f"{request.method} isn't supported on {request.path}.")


@app.errorhandler(500)
def handle_server_error(e):
    return error(500, "Something went wrong on our side. Try again.")


# --- Check 1: the session ----------------------------------------------------

@app.before_request
def load_user():
    """Runs before every request, so no /api/ route can forget the check."""
    g.user = auth.user_for_token(request.cookies.get(SESSION_COOKIE))
    if request.path.startswith("/api/") and g.user is None:
        return error(401, "You're not signed in. Sign in with POST /auth/login first.")


# --- Check 3: input ----------------------------------------------------------

def parse_date(name):
    value = request.args.get(name, "").strip()
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise InputError(f"'{name}' must be a date like 2026-08-01, but got '{value}'.")
    # strptime also accepts "2026-8-1", but the database compares dates as
    # text, so always pass on the zero-padded form: "2026-08-01".
    return parsed.date().isoformat()


def parse_filters():
    """The date range and visit type from the query string, validated."""
    date_from = parse_date("from")
    date_to = parse_date("to")
    if date_from and date_to and date_to < date_from:
        raise InputError(
            f"The end date ({date_to}) is before the start date ({date_from}). "
            "Pick an end date on or after the start date."
        )

    visit_type = request.args.get("type", "").strip().lower() or None
    if visit_type and visit_type not in db.VISIT_TYPES:
        raise InputError(
            f"'{visit_type}' isn't a visit type. Use one of: {', '.join(db.VISIT_TYPES)}."
        )

    return {"date_from": date_from, "date_to": date_to, "visit_type": visit_type}


def parse_yes_no(name):
    value = request.args.get(name, "").strip().lower()
    if not value:
        return None
    if value not in ("yes", "no"):
        raise InputError(f"'{name}' must be yes or no, but got '{value}'.")
    return value == "yes"


def parse_list_filters():
    """Filters for the visit list only, on top of parse_filters(): host team,
    pre-registered, signed out, and a search. The stats ignore these."""
    team = request.args.get("team", "").strip()
    host_team = next((t for t in db.host_teams if t.lower() == team.lower()), None)
    if team and host_team is None:
        raise InputError(f"'{team}' isn't a host team. Use one of: {', '.join(db.host_teams)}.")

    return {
        "host_team": host_team,
        "pre_registered": parse_yes_no("pre_registered"),
        "signed_out": parse_yes_no("signed_out"),
        "search": request.args.get("q", "").strip() or None,
    }


def parse_page():
    value = request.args.get("page", "1").strip()
    # isdecimal(), not isdigit(): isdigit() also accepts "²", which int() can't read.
    if not value.isdecimal() or int(value) < 1:
        raise InputError(f"'page' must be a whole number from 1 up, but got '{value}'.")
    return int(value)


# --- Auth routes --------------------------------------------------------------

def form_data():
    """Email and password from JSON (curl, fetch) or a plain HTML form post.
    Anything that isn't text (a number, a list) counts as missing, so odd
    input gets the normal "enter your email" answer rather than a crash."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = request.form
    email = data.get("email")
    password = data.get("password")
    return {
        "email": email if isinstance(email, str) else "",
        "password": password if isinstance(password, str) else "",
    }


def signed_in_response(user, token, status=200):
    response = jsonify(user)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="Lax")
    return response, status


@app.post("/auth/signup")
def signup():
    data = form_data()
    user = auth.signup(data.get("email"), data.get("password"))
    token = auth.login(data.get("email"), data.get("password"))  # sign them straight in
    return signed_in_response(user, token, status=201)


@app.post("/auth/login")
def login():
    data = form_data()
    token = auth.login(data.get("email"), data.get("password"))
    return signed_in_response(auth.user_for_token(token), token)


@app.post("/auth/logout")
def logout():
    auth.logout(request.cookies.get(SESSION_COOKIE))
    response = jsonify(signed_out=True)
    response.delete_cookie(SESSION_COOKIE)
    return response


# --- API routes ---------------------------------------------------------------

@app.get("/api/me")
def me():
    return jsonify({**g.user, "can_see_visitor_identity": g.user["role"] == "admin"})


@app.get("/api/visits")
def list_visits():
    # Check 2: search matches visitor names and emails, so a viewer could use
    # it to find out whether someone visited ("any results for Jane Doe?").
    if request.args.get("q", "").strip() and g.user["role"] != "admin":
        return error(403, "Only admins can search visits.")

    filters = {**parse_filters(), **parse_list_filters()}
    page = parse_page()
    result = db.list_visits(filters, g.user["role"], page)
    if page > result["total_pages"]:
        raise InputError(
            f"Page {page} doesn't exist. These filters have {result['total_pages']} page(s)."
        )
    return jsonify(result)


@app.get("/api/visits/<visit_id>")
def get_visit(visit_id):
    visit = db.get_visit(visit_id, g.user["role"])
    if visit is None:
        return error(404, f"There's no visit with ID '{visit_id}'.")
    return jsonify(visit)


@app.get("/api/stats")
def stats():
    return jsonify(db.get_stats(parse_filters()))


@app.get("/api/users")
def list_users():
    # Check 2: admin only. The page hides its link from viewers, but this is
    # the check that actually keeps them out.
    if g.user["role"] != "admin":
        return error(403, "Only admins can see the user list.")
    return jsonify(users=db.list_users())


# --- Pages --------------------------------------------------------------------
# Each URL has its own HTML file, so refreshing any page keeps you on it. The
# files contain no data: they fetch it from /api/ and the API applies the rules.

@app.get("/")
def home():
    return redirect("/visits")


@app.get("/login")
def login_page():
    return app.send_static_file("login.html")


@app.get("/signup")
def signup_page():
    return app.send_static_file("signup.html")


@app.get("/visits")
def visits_page():
    return app.send_static_file("visits.html")


@app.get("/visits/<visit_id>")
def visit_page(visit_id):
    return app.send_static_file("visit.html")


@app.get("/admin/users")
def admin_users_page():
    return app.send_static_file("admin-users.html")


if __name__ == "__main__":
    app.run(port=5000)
