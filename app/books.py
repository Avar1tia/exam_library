import hashlib
import os
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path

import bleach
import markdown
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from .models import Book, BookView, Cover, Genre, Review, db
from .rights import can, rights_required

bp = Blueprint("books", __name__)

ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS).union(
    {"p", "br", "h1", "h2", "h3", "h4", "pre", "code", "blockquote", "ul", "ol", "li"}
)
RATINGS = [
    (5, "отлично"),
    (4, "хорошо"),
    (3, "удовлетворительно"),
    (2, "неудовлетворительно"),
    (1, "плохо"),
    (0, "ужасно"),
]


def sanitize_markdown(value):
    return bleach.clean(value, tags=ALLOWED_TAGS, strip=True)


def render_markdown(value):
    rendered = markdown.markdown(value or "", extensions=["fenced_code", "tables"])
    return bleach.clean(rendered, tags=ALLOWED_TAGS, strip=True)


def visitor_key():
    if current_user.is_authenticated:
        return f"user:{current_user.id}"
    if "visitor_key" not in session:
        session["visitor_key"] = uuid.uuid4().hex
    return f"guest:{session['visitor_key']}"


def record_view(book):
    key = visitor_key()
    start = datetime.combine(date.today(), time.min)
    count = db.session.scalar(
        db.select(func.count(BookView.id)).where(
            BookView.book_id == book.id,
            BookView.visitor_key == key,
            BookView.viewed_at >= start,
        )
    )
    if count < 10:
        db.session.add(
            BookView(
                book_id=book.id,
                user_id=current_user.id if current_user.is_authenticated else None,
                visitor_key=key,
            )
        )
        db.session.commit()


def book_form_data(book=None):
    if request.method == "POST":
        return request.form
    if not book:
        return {}
    return {
        "title": book.title,
        "short_description": book.short_description,
        "year": book.year,
        "publisher": book.publisher,
        "author": book.author,
        "pages": book.pages,
    }


def validate_book_form(require_cover):
    errors = {}
    for field in ("title", "short_description", "year", "publisher", "author", "pages"):
        if not request.form.get(field, "").strip():
            errors[field] = "Поле обязательно для заполнения."
    try:
        year = int(request.form.get("year", ""))
        if year < 1 or year > date.today().year:
            errors["year"] = "Укажите корректный год."
    except ValueError:
        errors["year"] = "Год должен быть числом."
    try:
        if int(request.form.get("pages", "")) <= 0:
            errors["pages"] = "Количество страниц должно быть больше нуля."
    except ValueError:
        errors["pages"] = "Количество страниц должно быть числом."
    if not request.form.getlist("genre_ids"):
        errors["genre_ids"] = "Выберите хотя бы один жанр."
    if require_cover and not request.files.get("cover"):
        errors["cover"] = "Загрузите обложку."
    return errors


def save_cover(book, uploaded):
    content = uploaded.read()
    digest = hashlib.md5(content).hexdigest()
    existing = db.session.scalar(db.select(Cover).filter_by(md5_hash=digest))
    if existing:
        stored_name = existing.filename
    else:
        extension = Path(uploaded.filename).suffix.lower() or ".bin"
        stored_name = f"{digest}{extension}"
        path = Path(current_app.config["UPLOAD_FOLDER"]) / stored_name
        if not path.exists():
            path.write_bytes(content)
    cover = Cover(
        filename=stored_name,
        mime_type=uploaded.mimetype or "application/octet-stream",
        md5_hash=digest,
        book=book,
    )
    db.session.add(cover)


@bp.app_template_filter("markdown")
def markdown_filter(value):
    return render_markdown(value)


@bp.route("/")
def index():
    page = request.args.get("page", 1, type=int)
    pagination = db.paginate(
        db.select(Book).order_by(Book.year.desc(), Book.id.desc()),
        page=page,
        per_page=10,
        error_out=False,
    )
    since = datetime.utcnow() - timedelta(days=90)
    popular = db.session.execute(
        db.select(Book, func.count(BookView.id).label("views_count"))
        .join(BookView)
        .where(BookView.viewed_at >= since)
        .group_by(Book.id)
        .order_by(func.count(BookView.id).desc())
        .limit(5)
    ).all()

    recent = []
    key = visitor_key()
    rows = db.session.execute(
        db.select(Book)
        .join(BookView)
        .where(BookView.visitor_key == key)
        .order_by(BookView.viewed_at.desc())
    ).scalars()
    seen = set()
    for book in rows:
        if book.id not in seen:
            recent.append(book)
            seen.add(book.id)
        if len(recent) == 5:
            break

    return render_template(
        "books/index.html",
        title="Электронная библиотека",
        pagination=pagination,
        books=pagination.items,
        popular=popular,
        recent=recent,
    )


@bp.route("/books/<int:book_id>")
def show(book_id):
    book = db.get_or_404(Book, book_id)
    record_view(book)
    own_review = None
    if current_user.is_authenticated:
        own_review = db.session.scalar(
            db.select(Review).filter_by(book_id=book.id, user_id=current_user.id)
        )
    return render_template(
        "books/show.html",
        title=book.title,
        book=book,
        own_review=own_review,
    )


@bp.route("/books/new", methods=["GET", "POST"])
@rights_required("create_book")
def create():
    errors = {}
    if request.method == "POST":
        errors = validate_book_form(require_cover=True)
        if not errors:
            try:
                book = Book(
                    title=request.form["title"].strip(),
                    short_description=sanitize_markdown(
                        request.form["short_description"].strip()
                    ),
                    year=int(request.form["year"]),
                    publisher=request.form["publisher"].strip(),
                    author=request.form["author"].strip(),
                    pages=int(request.form["pages"]),
                )
                book.genres = list(
                    db.session.scalars(
                        db.select(Genre).where(
                            Genre.id.in_(request.form.getlist("genre_ids"))
                        )
                    )
                )
                db.session.add(book)
                db.session.flush()
                save_cover(book, request.files["cover"])
                db.session.commit()
                flash("Книга успешно добавлена.", "success")
                return redirect(url_for("books.show", book_id=book.id))
            except (SQLAlchemyError, OSError, ValueError):
                db.session.rollback()
                flash(
                    "При сохранении данных возникла ошибка. Проверьте корректность введённых данных.",
                    "danger",
                )
    genres = db.session.scalars(db.select(Genre).order_by(Genre.name)).all()
    return render_template(
        "books/form.html",
        title="Добавление книги",
        data=book_form_data(),
        genres=genres,
        selected_genres=request.form.getlist("genre_ids"),
        errors=errors,
        create=True,
    )


@bp.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
@rights_required("edit_book")
def edit(book_id):
    book = db.get_or_404(Book, book_id)
    errors = {}
    if request.method == "POST":
        errors = validate_book_form(require_cover=False)
        if not errors:
            try:
                book.title = request.form["title"].strip()
                book.short_description = sanitize_markdown(
                    request.form["short_description"].strip()
                )
                book.year = int(request.form["year"])
                book.publisher = request.form["publisher"].strip()
                book.author = request.form["author"].strip()
                book.pages = int(request.form["pages"])
                book.genres = list(
                    db.session.scalars(
                        db.select(Genre).where(
                            Genre.id.in_(request.form.getlist("genre_ids"))
                        )
                    )
                )
                db.session.commit()
                flash("Данные книги успешно обновлены.", "success")
                return redirect(url_for("books.show", book_id=book.id))
            except (SQLAlchemyError, ValueError):
                db.session.rollback()
                flash(
                    "При сохранении данных возникла ошибка. Проверьте корректность введённых данных.",
                    "danger",
                )
    genres = db.session.scalars(db.select(Genre).order_by(Genre.name)).all()
    selected = (
        request.form.getlist("genre_ids")
        if request.method == "POST"
        else [str(genre.id) for genre in book.genres]
    )
    return render_template(
        "books/form.html",
        title="Редактирование книги",
        data=book_form_data(book),
        genres=genres,
        selected_genres=selected,
        errors=errors,
        create=False,
        book=book,
    )


@bp.route("/books/<int:book_id>/delete", methods=["POST"])
@rights_required("delete_book")
def delete(book_id):
    book = db.get_or_404(Book, book_id)
    cover_path = (
        Path(current_app.config["UPLOAD_FOLDER"]) / book.cover.filename
        if book.cover
        else None
    )
    cover_hash = book.cover.md5_hash if book.cover else None
    try:
        db.session.delete(book)
        db.session.commit()
        if cover_path and cover_path.exists():
            other = db.session.scalar(db.select(Cover).filter_by(md5_hash=cover_hash))
            if not other:
                cover_path.unlink()
        flash(f"Книга «{book.title}» успешно удалена.", "success")
    except (SQLAlchemyError, OSError):
        db.session.rollback()
        flash("Не удалось удалить книгу.", "danger")
    return redirect(url_for("books.index"))


@bp.route("/books/<int:book_id>/reviews/new", methods=["GET", "POST"])
@login_required
def create_review(book_id):
    book = db.get_or_404(Book, book_id)
    if not can("review"):
        flash("У вас недостаточно прав для выполнения данного действия", "danger")
        return redirect(url_for("books.index"))
    existing = db.session.scalar(
        db.select(Review).filter_by(book_id=book.id, user_id=current_user.id)
    )
    if existing:
        flash("Вы уже оставили рецензию на эту книгу.", "warning")
        return redirect(url_for("books.show", book_id=book.id))

    if request.method == "POST":
        rating = request.form.get("rating", type=int)
        text_value = request.form.get("text", "").strip()
        if rating not in range(6) or not text_value:
            flash("Заполните оценку и текст рецензии.", "danger")
        else:
            try:
                db.session.add(
                    Review(
                        book_id=book.id,
                        user_id=current_user.id,
                        rating=rating,
                        text=sanitize_markdown(text_value),
                    )
                )
                db.session.commit()
                flash("Рецензия успешно добавлена.", "success")
                return redirect(url_for("books.show", book_id=book.id))
            except SQLAlchemyError:
                db.session.rollback()
                flash("При сохранении рецензии возникла ошибка.", "danger")

    return render_template(
        "reviews/form.html",
        title="Новая рецензия",
        book=book,
        ratings=RATINGS,
    )


@bp.route("/covers/<path:filename>")
def cover(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
