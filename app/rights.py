from functools import wraps

from flask import flash, redirect, request, url_for
from flask_login import current_user


RIGHTS = {
    "admin": {"create_book", "edit_book", "delete_book", "review", "statistics"},
    "moderator": {"edit_book", "review"},
    "user": {"review"},
}


def can(action):
    return (
        current_user.is_authenticated
        and action in RIGHTS.get(current_user.role_name, set())
    )


def rights_required(action):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                flash(
                    "Для выполнения данного действия необходимо пройти процедуру аутентификации",
                    "warning",
                )
                return redirect(url_for("auth.login", next=request.url))
            if not can(action):
                flash(
                    "У вас недостаточно прав для выполнения данного действия",
                    "danger",
                )
                return redirect(url_for("books.index"))
            return view(*args, **kwargs)

        return wrapped

    return decorator
