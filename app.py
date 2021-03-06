import json
import os.path
import uuid
from threading import Lock

from flask import Flask, flash, g, redirect, request, session, render_template
from db import init_app, get_db
import functools
from secret import app_key


app = Flask(__name__)
app.config.from_mapping(
    SECRET_KEY=app_key,
    DATABASE="db.sqlite",
)
init_app(app)
lock = Lock()

# create example dataset
if os.path.exists("dataset.json"):
    app.logger.info("Dataset found, skipping example dataset creation.")
else:
    d = []

    for i in range(1000):
        d.append({
            "text": f"test {i}",
            "label": None,
        })

    with open("dataset.json", "w") as f:
        json.dump(d, f)

    app.logger.info("Example dataset created at dataset.json.")


def login_required(view):
    """View decorator that redirects anonymous users to the login page."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect("/login")
        return view(**kwargs)
    return wrapped_view


@app.before_request
def load_logged_in_user():
    """If a user id is stored in the session, load the user object from
    the database into ``g.user``."""
    user_id = session.get("user_id")

    if user_id is None:
        g.user = None
    else:
        g.user = (
            get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        )


def logout():
    """Clear the current session, including the stored user id."""
    session.clear()
    return redirect("/login")


def update_dataset(label):
    lock.acquire()
    with open("dataset.json", "r+") as f:
        dataset = json.load(f)
        dataset[session["start_id"]]["label"] = label
        f.seek(0)  # otherwise it will append a complete copy of the dataset
        json.dump(dataset, f)
        f.truncate()  # fix if the updated file is smaller than the original

        app.logger.info(f"User {session['user_id']} "
                        f"rated {label} "
                        f"text {dataset[session['start_id']]['text']}")
    lock.release()


@app.route("/", methods=("GET", "POST"))
@login_required
def label():
    user_id = session.get('user_id')
    users_count = len(get_db().execute("SELECT * FROM users").fetchall())
    user_to_label_ratio = 1 / users_count
    go_back = False

    if request.method == "POST":
        if "logout" in request.form:
            return logout()

        elif "toxic" in request.form:
            update_dataset(label=True)

        elif "nontoxic" in request.form:
            update_dataset(label=False)

        elif "unknown" in request.form:
            update_dataset(label="/")

        elif "goback" in request.form:
            if "entry_id" in session:
                session["entry_id"] -= 1
                go_back = True

    start = 0
    text = ""
    done = False

    with open("dataset.json", "r") as f:
        dataset = json.load(f)
        dataset_len = len(dataset)
        dataset_lower_limit = int(dataset_len * (user_id - 1) * user_to_label_ratio)
        dataset_upper_limit = int(dataset_len * user_id * user_to_label_ratio)
        dataset_to_label = dataset[dataset_lower_limit:dataset_upper_limit]

        # if the user has already started labeling, resume from the next unlabeled entry
        if "entry_id" in session and \
                dataset_lower_limit <= (session["entry_id"] + dataset_lower_limit) <= dataset_upper_limit:
            start = session["entry_id"]

        # can't use enumerate to start from an offset https://stackoverflow.com/posts/14736201/timeline#comment_82284617
        for i in range(start, dataset_len):
            entry = dataset_to_label[i]
            if "text" in entry:
                if go_back or ("label" not in entry or entry["label"] is None):
                    text = entry["text"]
                    session["entry_id"] = i
                    session["start_id"] = i + dataset_lower_limit
                    app.logger.debug(f"entry_id: {session['entry_id']}, start_id: {session['start_id']}, entry: {entry}")
                    break
        else:
            done = True

    labeled = len([True for entry in dataset if entry["label"] is not None])
    return render_template("label.html", text=text, done=done, labeled=labeled, total=len(dataset))


@app.route("/login", methods=("GET", "POST"))
def login():
    """Log in a registered user by adding the user id to the session."""
    if request.method == "POST":
        username = request.form["username"]
        error = None
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user is None:
            error = "Incorrect username."
            app.logger.warning(f"Failed login attempt by user {username}.")

        if error is None:
            # store the user id in a new session and return to the index
            session.clear()
            session["user_id"] = user["id"]
            app.logger.info(f"Successful login attempt by user {username}.")
            return redirect("/")

        flash(error)

    return render_template("login.html")


@app.route("/manageusers", methods=("GET", "POST"))
def manage_users():
    """Add and remove users."""
    def render_and_return():
        users = {row['id']: row['username'] for row in get_db().execute("SELECT * FROM users").fetchall()}
        return render_template("manageusers.html", users=users)

    if request.method == "GET":
        if session.get("user_id") != 1:
            flash("Unauthorized to manage users.")
            return redirect("/")

    elif request.method == "POST":
        if "cancel" in request.form:
            return redirect("/")

        elif "logout" in request.form:
            return logout()

        else:
            error = None
            if "newusername" in request.form:
                username = uuid.uuid4().hex
                get_db().execute(
                    "INSERT INTO users (username) VALUES (?)", (username,)
                )
                get_db().commit()
                flash(f"Added user {username}???")
            else:
                username = request.form["delusername"]
                user = get_db().execute(
                    "SELECT * FROM users WHERE username = ?", (username,)
                ).fetchone()

                if user is None:
                    error = f"Non-existing username: {username}."

                if user['id'] == 1:
                    error = "?????? Cannot delete admin user. ??????"

                if error is None:
                    get_db().execute(
                        "DELETE FROM users WHERE username = ?", (username,)
                    )
                    get_db().commit()
                    flash(f"Deleted user {username}.")

            if error is None:
                return render_and_return()

        flash(error)

    return render_and_return()


@app.route("/stats", methods=("GET", "POST"))
def see_stats():
    """See labeling completion statistics."""

    if request.method == "POST":
        if "logout" in request.form:
            return logout()

    if session.get("user_id") != 1:
        flash("Unauthorized to see stats.")
        return redirect("/")

    with open("dataset.json", "r") as f:
        dataset = json.load(f)

    labeled = []
    for i, entry in enumerate(dataset):
        if "label" in entry and entry["label"] is not None:
            labeled.append({
                "index": i,
                "label": entry["label"],
            })

    users_count = len(get_db().execute("SELECT * FROM users").fetchall())
    user_to_label_ratio = 1 / users_count
    dataset_len = len(dataset)
    users_assignments = []
    for user_id in range(1, users_count + 1):
        dataset_lower_limit = int(dataset_len * (user_id - 1) * user_to_label_ratio)
        dataset_upper_limit = int(dataset_len * user_id * user_to_label_ratio)
        users_assignments.append(f"{user_id}: [{dataset_lower_limit}:{dataset_upper_limit}) "
                                 f"({len([e for e in dataset[dataset_lower_limit:dataset_upper_limit] if e['label'] in (True, False, '/')]) / (dataset_upper_limit - dataset_lower_limit) * 100:.2f} %)")

    if len(labeled) == 0:
        stats = {
            "Completion": "0 %",
            "Labeled Toxic": "N/A",
            "Labeled Non-toxic": "N/A",
            "Labeled Unknown": "N/A",
            "Usable (labeled toxic + labeled non-toxic)": 0,
        }
    else:
        stats = {
            "Completion": f'{len(labeled) / len(dataset) * 100:.3f} %',
            "Labeled Toxic": f'{len([e for e in labeled if e["label"] is True]) / len(labeled) * 100:.3f} %',
            "Labeled Non-toxic": f'{len([e for e in labeled if e["label"] is False]) / len(labeled) * 100:.3f} %',
            "Labeled Unknown": f'{len([e for e in labeled if e["label"] == "/"]) / len(labeled) * 100:.3f} %',
            "Usable (labeled toxic + labeled non-toxic)": len([
                e for e in labeled if e["label"] is True or e["label"] is False
            ]),
        }

    stats["Users' Assignments"] = " - ".join(users_assignments)
    stats["Labeled IDs"] = [e["index"] for e in labeled]

    return render_template("stats.html", stats=stats)
