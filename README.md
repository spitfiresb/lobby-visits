# The Front Desk

A small internal web app for Brightline's workplace team. It shows lobby visits (who came in, when, and when the lobby is busiest) from the sign-in iPad's export. Only people on an allowlist can use it. Admins see who visited; viewers see how busy the building is, never a visitor's identity.

One Python process: a Flask JSON API plus plain HTML pages, with the data loaded from `visits.csv` and `allowed_users.csv` into SQLite at startup.

## Run it

Needs Python 3.9 or newer (tested on 3.12).

```bash
pip install -r requirements.txt
python app.py
```

Then open <http://localhost:5000>. Signing in takes you to the visits list.

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
