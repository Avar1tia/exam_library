import os
from pathlib import Path

from flask import Flask
from flask_login import LoginManager
from sqlalchemy import event
from sqlalchemy.engine import Engine

from .models import User, db

login_manager = LoginManager()


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(connection, _record):
    if connection.__class__.__module__.startswith("sqlite3"):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_app(test_config=None):
    app = Flask(__name__)
    base_dir = Path(__file__).resolve().parent.parent
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "exam-library-secret-key"),
        SQLALCHEMY_DATABASE_URI=os.getenv(
            "DATABASE_URL",
            f"sqlite:///{base_dir / 'library.sqlite'}",
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=base_dir / "uploads",
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = (
        "Для выполнения данного действия необходимо пройти процедуру аутентификации"
    )
    login_manager.login_message_category = "warning"

    from .auth import bp as auth_bp
    from .books import bp as books_bp
    from .stats import bp as stats_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(books_bp)
    app.register_blueprint(stats_bp)

    @app.context_processor
    def inject_helpers():
        from .rights import can

        return {"can": can}

    return app


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
