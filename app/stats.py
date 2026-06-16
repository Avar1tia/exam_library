import csv
import io
from datetime import date, datetime, time, timedelta

from flask import Blueprint, Response, render_template, request
from sqlalchemy import func

from .models import Book, BookView, User, db
from .rights import rights_required

bp = Blueprint("stats", __name__, url_prefix="/statistics")


class SimplePagination:
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = max((total + per_page - 1) // per_page, 1)

    def iter_pages(self):
        return range(1, self.pages + 1)


def parse_date(value, end=False):
    if not value:
        return None
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    return datetime.combine(parsed, time.max if end else time.min)


def journal_query():
    return (
        db.select(BookView)
        .order_by(BookView.viewed_at.desc())
    )


def views_query(date_from=None, date_to=None):
    query = (
        db.select(Book.title.label("book_title"), func.count(BookView.id).label("views_count"))
        .join(BookView)
        .where(BookView.user_id.is_not(None))
        .group_by(Book.id)
        .order_by(func.count(BookView.id).desc())
    )
    if date_from:
        query = query.where(BookView.viewed_at >= date_from)
    if date_to:
        query = query.where(BookView.viewed_at <= date_to)
    return query


@bp.route("/")
@rights_required("statistics")
def index():
    tab = request.args.get("tab", "journal")
    page = request.args.get("page", 1, type=int)
    raw_from = request.args.get("date_from", "")
    raw_to = request.args.get("date_to", "")
    date_from = parse_date(raw_from)
    date_to = parse_date(raw_to, end=True)
    if tab == "views":
        rows = [
            {"book_title": row.book_title, "views_count": row.views_count}
            for row in db.session.execute(views_query(date_from, date_to)).all()
        ]
        start = (page - 1) * 10
        pagination = SimplePagination(
            rows[start:start + 10],
            page,
            10,
            len(rows),
        )
    else:
        pagination = db.paginate(
            journal_query(), page=page, per_page=10, error_out=False
        )
    return render_template(
        "statistics/index.html",
        title="Статистика",
        tab=tab,
        pagination=pagination,
        date_from=raw_from,
        date_to=raw_to,
    )


def csv_response(filename, headers, rows):
    stream = io.StringIO()
    stream.write("\ufeff")
    writer = csv.writer(stream, delimiter=";")
    writer.writerow(headers)
    writer.writerows(rows)
    return Response(
        stream.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@bp.route("/journal.csv")
@rights_required("statistics")
def journal_csv():
    views = db.session.scalars(journal_query()).all()
    rows = [
        (
            view.user.full_name if view.user else "Неаутентифицированный пользователь",
            view.book.title,
            view.viewed_at.strftime("%d.%m.%Y %H:%M:%S"),
        )
        for view in views
    ]
    filename = f"visit_journal_{date.today().isoformat()}.csv"
    return csv_response(filename, ["Пользователь", "Книга", "Дата"], rows)


@bp.route("/views.csv")
@rights_required("statistics")
def views_csv():
    raw_from = request.args.get("date_from", "")
    raw_to = request.args.get("date_to", "")
    rows = db.session.execute(
        views_query(parse_date(raw_from), parse_date(raw_to, end=True))
    ).all()
    filename = f"book_views_{date.today().isoformat()}.csv"
    return csv_response(
        filename,
        ["Книга", "Количество просмотров"],
        [(row.book_title, row.views_count) for row in rows],
    )
