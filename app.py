import json
import os.path
from logging.config import dictConfig
import uuid

from flask import Flask, flash, g, redirect, request, session, url_for, render_template, logging
from db import init_app, get_db
import functools


app = Flask(__name__)
app.config.from_mapping(
    SECRET_KEY="changeme",
    DATABASE="db.sqlite",
)
init_app(app)

logger = logging.create_logger(app)

# logger
dictConfig({
    'version': 1,
    'root': {
        'level': 'INFO',
    }
})

# create example dataset
if not os.path.exists("dataset.json"):
    d = []

    for i in range(1000):
        d.append({
            "comment": f"test {i}",
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


def update_dataset(label: bool):
    with open("dataset.json", "r+") as f:
        dataset = json.load(f)
        dataset[session["start_id"]]["label"] = label
        f.seek(0)  # otherwise it will append a complete copy of the dataset
        json.dump(dataset, f)
        f.truncate()  # fix if the updated file is smaller than the original

        app.logger.info(f"User {session['user_id']} "
                        f"rated {'toxic' if label else 'non-toxic'} "
                        f"comment {dataset[session['start_id']]['comment']}")


@app.route("/", methods=("GET", "POST"))
@login_required
def label():
    user_id = session.get('user_id')
    users_count = len(get_db().execute("SELECT * FROM users").fetchall())
    user_to_label_ratio = 1 / users_count
    go_back = False

    if request.method == "POST":
        if "logout" in request.form:
            """Clear the current session, including the stored user id."""
            session.clear()
            return redirect("/login")

        elif "toxic" in request.form:
            update_dataset(label=True)

        elif "nontoxic" in request.form:
            update_dataset(label=False)

        elif "goback" in request.form:
            if "entry_id" in session:
                session["entry_id"] -= 1
                go_back = True

    start = 0
    comment = ""
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
            if "comment" in entry:
                if go_back or ("label" not in entry or entry["label"] is None):
                    comment = entry["comment"]
                    session["entry_id"] = i
                    session["start_id"] = i + dataset_lower_limit
                    app.logger.debug(f"entry_id: {session['entry_id']}, start_id: {session['start_id']}, entry: {entry}")
                    break
        else:
            ...  # TODO: render template saying "nice job"

    return render_template("label.html", comment=comment)


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
    if request.method == "POST":
        if "cancel" in request.form:
            return redirect("/")
        else:
            error = None
            if session["user_id"] == 1:
                if "newusername" in request.form:
                    username = uuid.uuid4().hex
                    get_db().execute(
                        "INSERT INTO users (username) VALUES (?)", (username,)
                    )
                    get_db().commit()
                    flash(f"Added user {username} - ⚠️ COPY IT NOW ⚠️")
                else:
                    username = request.form["delusername"]
                    user = get_db().execute(
                        "SELECT * FROM users WHERE username = ?", (username,)
                    ).fetchone()

                    if user is None:
                        error = f"Non-existing username: {username}."

                    if error is None:
                        get_db().execute(
                            "DELETE FROM users WHERE username = ?", (username,)
                        )
                        get_db().commit()
                        flash(f"Deleted user {username}.")

                if error is None:
                    return render_template("manageusers.html")

            else:
                error = "Unauthorized to manage users."

        flash(error)

    return render_template("manageusers.html")
