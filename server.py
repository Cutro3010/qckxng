from flask import Flask, send_from_directory, redirect, url_for, session, request, jsonify
from functools import wraps
from datetime import datetime
import os
import json

app = Flask(__name__)

# Change this to a long random secret in production
app.secret_key = "change-this-to-a-random-secret-key"

MAGIC_NUMBERS_FILE = "magic_numbers.txt"
LINKS_FILE = "links.txt"
DATES_FILE = "dates.json"

# =========================================================
# FILE HELPERS
# =========================================================

def search(file_name, search_for):
    """Check whether search_for exists in a file."""

    if not os.path.exists(file_name):
        return False

    with open(file_name, "r", encoding="utf-8") as file:
        contents = file.read()

    return search_for in contents

def load_dates():
    """Load all saved dates."""

    if not os.path.exists(DATES_FILE):
        return {}

    try:
        with open(DATES_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}

def save_dates(dates):
    """Save all dates."""

    with open(DATES_FILE, "w", encoding="utf-8") as file:
        json.dump(dates, file, indent=4)

# =========================================================
# AUTHENTICATION
# =========================================================

def login_required(function):
    """Only allow logged-in users to access a route."""

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "user" not in session:
            return jsonify({
                "error": "Authentication required"
            }), 401

        return function(*args, **kwargs)

    return wrapper

# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/")
def frontend():
    return send_from_directory(".", "index.html")

@app.route("/healthcheck")
def healthcheck():
    return "Alive - Version 1"

# =========================================================
# CREATE USER LINK
# =========================================================

@app.route("/user/link/<magic_number>/<name>")
def link(name, magic_number):
    """
    Creates a connection between a magic number and a user.

    Example:

    /user/link/123456/alice
    """

    # Check that the magic number is valid
    if not search(MAGIC_NUMBERS_FILE, magic_number):
        return jsonify({
            "error": "Invalid magic number"
        }), 403

    link_value = magic_number + ">" + name

    # Avoid duplicate links
    if not search(LINKS_FILE, link_value):

        with open(LINKS_FILE, "a", encoding="utf-8") as file:
            file.write(link_value + "\n")

    return jsonify({
        "success": True,
        "message": "User link created",
        "user": name
    })

# =========================================================
# LOGIN
# =========================================================

@app.route("/user/<name>/<magic_number>")
def login(name, magic_number):
    """
    Login using the username and magic number.

    Example:

    /user/alice/123456
    """

    link_value = magic_number + ">" + name

    # Check that this exact user/magic-number combination exists
    if not search(LINKS_FILE, link_value):
        return jsonify({
            "error": "Invalid user or magic number"
        }), 403

    # Save login information in Flask session
    session["user"] = name
    session["magic_number"] = magic_number

    return redirect(
        url_for(
            "loginned",
            name=name,
            magic_number=magic_number
        )
    )

# =========================================================
# PROFILE / LOGGED-IN PAGE
# =========================================================

@app.route("/user/<name>/<magic_number>/profile")
def loginned(name, magic_number):
    """
    Page shown after successful login.
    """

    # Make sure the URL matches the logged-in session
    if session.get("user") != name:
        return jsonify({
            "error": "Unauthorized"
        }), 401

    if session.get("magic_number") != magic_number:
        return jsonify({
            "error": "Unauthorized"
        }), 401

    return jsonify({
        "logged_in": True,
        "user": name,
        "message": "Login successful"
    })

# =========================================================
# CALENDAR
# =========================================================

@app.route("/calendar")
@login_required
def calendar():
    """
    Show all upcoming dates belonging to the logged-in user.
    """

    user = session["user"]

    dates = load_dates()

    user_dates = dates.get(user, [])

    now = datetime.now()

    upcoming_dates = []

    for item in user_dates:

        try:
            date_object = datetime.fromisoformat(
                item["date"]
            )

            if date_object >= now:
                upcoming_dates.append(item)

        except (ValueError, TypeError, KeyError):
            # Ignore invalid entries
            continue

    # Sort from soonest to latest
    upcoming_dates.sort(
        key=lambda item: item["date"]
    )

    return jsonify({
        "user": user,
        "dates": upcoming_dates
    })

# =========================================================
# ADD DATE
# =========================================================

@app.route("/add_date", methods=["POST"])
@login_required
def add_date():
    """
    Add a date for the logged-in user.

    Expected JSON:

    {
        "date": "2026-12-25T18:30:00",
        "description": "Christmas dinner"
    }
    """

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "error": "Request must contain JSON"
        }), 400

    date_value = data.get("date")

    description = data.get(
        "description",
        ""
    )

    if not date_value:
        return jsonify({
            "error": "Missing 'date'"
        }), 400

    # Validate date format
    try:
        datetime.fromisoformat(date_value)

    except ValueError:
        return jsonify({
            "error": (
                "Invalid date format. "
                "Use ISO format such as "
                "2026-12-25T18:30:00"
            )
        }), 400

    dates = load_dates()

    user = session["user"]

    # Create user's list if it doesn't exist
    if user not in dates:
        dates[user] = []

    new_date = {
        "date": date_value,
        "description": description
    }

    dates[user].append(new_date)

    save_dates(dates)

    return jsonify({
        "success": True,
        "date": new_date
    }), 201

# =========================================================
# RETRIEVE ALL DATES
# =========================================================

@app.route("/retrieve_all")
@login_required
def retrieve_all():
    """
    Return every date belonging to the logged-in user.
    """

    user = session["user"]

    dates = load_dates()

    user_dates = dates.get(
        user,
        []
    )

    return jsonify({
        "user": user,
        "dates": user_dates
    })

# =========================================================
# SHOW SPECIFIC DATE
# =========================================================

@app.route("/show/<date>")
@login_required
def show_date(date):
    """
    Show all events for a specific date.

    Example:

    /show/2026-12-25
    """

    user = session["user"]

    dates = load_dates()

    user_dates = dates.get(
        user,
        []
    )

    matching_dates = []

    for item in user_dates:

        stored_date = item.get(
            "date",
            ""
        )

        # Allows:
        #
        # /show/2026-12-25
        #
        # to find:
        #
        # 2026-12-25T18:30:00

        if stored_date.startswith(date):
            matching_dates.append(item)

    if not matching_dates:
        return jsonify({
            "error": "Date not found"
        }), 404

    return jsonify({
        "user": user,
        "date": date,
        "entries": matching_dates
    })

# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
@login_required
def logout():
    """
    Log out the current user.
    """

    session.clear()

    return jsonify({
        "success": True,
        "message": "Logged out"
    })

# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":
    app.run(
        debug=True
    )
