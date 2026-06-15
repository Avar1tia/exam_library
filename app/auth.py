from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from .models import User, db

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("books.index"))

    if request.method == "POST":
        login_value = request.form.get("login", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))
        user = db.session.scalar(db.select(User).filter_by(login=login_value))
        if user and user.check_password(password):
            login_user(user, remember=remember)
            return redirect(request.args.get("next") or url_for("books.index"))
        flash(
            "Невозможно аутентифицироваться с указанными логином и паролем",
            "danger",
        )

    return render_template("login.html", title="Вход")


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(request.referrer or url_for("books.index"))
