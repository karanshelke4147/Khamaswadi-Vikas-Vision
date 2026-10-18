from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import sqlite3, secrets, csv, io, os
from pathlib import Path
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent
DB = BASE / "khamaswadi.db"
UPLOAD_DIR = BASE / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

# Security settings
app.secret_key = os.environ.get("SECRET_KEY", "change-this-before-online-deployment")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

WARDS = [f"वॉर्ड {i}" for i in range(1, 6)]

CATEGORIES = [
    "पाणी",
    "रस्ता",
    "स्ट्रीट लाईट",
    "स्वच्छता",
    "गटार / ड्रेनेज",
    "आरोग्य",
    "शिक्षण",
    "शेती",
    "सार्वजनिक सुविधा",
    "युवक",
    "महिला",
    "इतर"
]

STATUSES = [
    "नवीन",
    "तपासणी सुरू",
    "काम सुरू",
    "पूर्ण",
    "सध्या शक्य नाही"
]

PRIORITIES = [
    "सामान्य",
    "महत्त्वाची",
    "तातडीची"
]

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def get_db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = get_db()

    con.execute("""
        CREATE TABLE IF NOT EXISTS issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            ward TEXT NOT NULL,
            category TEXT NOT NULL,
            location TEXT NOT NULL,
            description TEXT NOT NULL,
            priority TEXT NOT NULL,
            duration TEXT,
            photo_url TEXT,
            name_optional TEXT,
            phone_optional TEXT,
            status TEXT NOT NULL,
            assigned_person TEXT,
            expected_completion_date TEXT,
            action_taken TEXT,
            internal_note TEXT,
            last_updated TEXT NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0,
            archived_at TEXT
        )
    """)

    # Safe migration for older V2 databases
    cols = {
        row["name"]
        for row in con.execute("PRAGMA table_info(issues)").fetchall()
    }

    if "archived" not in cols:
        con.execute(
            "ALTER TABLE issues ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
        )

    if "archived_at" not in cols:
        con.execute(
            "ALTER TABLE issues ADD COLUMN archived_at TEXT"
        )

    con.execute("""
        CREATE TABLE IF NOT EXISTS public_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id TEXT NOT NULL,
            update_text TEXT NOT NULL,
            update_date TEXT NOT NULL
        )
    """)

    con.commit()
    con.close()


def backup_database_bytes():
    # SQLite online backup so the backup remains consistent
    # even while the database is open.
    source = sqlite3.connect(DB)
    memory = sqlite3.connect(":memory:")

    source.backup(memory)

    source.close()

    data = io.BytesIO()

    for line in memory.iterdump():
        data.write((line + "\n").encode("utf-8"))

    memory.close()

    return data.getvalue()


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))

        return fn(*args, **kwargs)

    return wrapper


def make_issue_id(con):
    row = con.execute(
        "SELECT COALESCE(MAX(id), 0) + 1 AS n FROM issues"
    ).fetchone()

    return f"KHV-{row['n']:04d}"


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


@app.context_processor
def shared():
    return {
        "wards": WARDS,
        "categories": CATEGORIES,
        "statuses": STATUSES,
        "priorities": PRIORITIES
    }


# Initialize / migrate database when app starts
init_db()


# ---------------------------------------------------------
# PUBLIC HOME
# ---------------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


# ---------------------------------------------------------
# PUBLIC FEEDBACK
# ---------------------------------------------------------

@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    error = None

    if request.method == "POST":
        f = request.form

        required = [
            "ward",
            "category",
            "location",
            "description",
            "priority"
        ]

        if any(not f.get(k, "").strip() for k in required):
            error = "कृपया आवश्यक माहिती पूर्ण भरा."

        elif (
            f["ward"] not in WARDS
            or f["category"] not in CATEGORIES
            or f["priority"] not in PRIORITIES
        ):
            error = "कृपया दिलेल्या पर्यायांमधून योग्य माहिती निवडा."

        else:
            photo_url = ""

            photo = request.files.get("photo")

            if photo and photo.filename:
                if not allowed_file(photo.filename):
                    error = (
                        "फक्त JPG, JPEG, PNG किंवा WEBP "
                        "फोटो स्वीकारला जातो."
                    )

                else:
                    filename = (
                        f"{secrets.token_hex(8)}_"
                        f"{secure_filename(photo.filename)}"
                    )

                    photo.save(UPLOAD_DIR / filename)

                    photo_url = f"/static/uploads/{filename}"

            if not error:
                con = get_db()

                now = datetime.now().strftime("%Y-%m-%d %H:%M")

                issue_id = make_issue_id(con)

                con.execute(
                    """
                    INSERT INTO issues
                    (
                        issue_id,
                        created_at,
                        ward,
                        category,
                        location,
                        description,
                        priority,
                        duration,
                        photo_url,
                        name_optional,
                        phone_optional,
                        status,
                        last_updated
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        issue_id,
                        now,
                        f["ward"],
                        f["category"],
                        f["location"].strip(),
                        f["description"].strip(),
                        f["priority"],
                        f.get("duration", ""),
                        photo_url,
                        f.get("name", "").strip(),
                        f.get("phone", "").strip(),
                        "नवीन",
                        now
                    )
                )

                con.commit()
                con.close()

                return render_template(
                    "success.html",
                    issue_id=issue_id
                )

    return render_template(
        "feedback.html",
        error=error
    )


# ---------------------------------------------------------
# PUBLIC STATUS CHECK
# ---------------------------------------------------------

@app.route("/status", methods=["GET", "POST"])
def status():
    result = None
    updates = []
    error = None

    if request.method == "POST":
        issue_id = request.form.get(
            "issue_id",
            ""
        ).strip().upper()

        con = get_db()

        result = con.execute(
            """
            SELECT
                issue_id,
                created_at,
                ward,
                category,
                location,
                description,
                priority,
                status,
                last_updated,
                photo_url
            FROM issues
            WHERE issue_id=?
            """,
            (issue_id,)
        ).fetchone()

        if result:
            updates = con.execute(
                """
                SELECT
                    update_text,
                    update_date
                FROM public_updates
                WHERE issue_id=?
                ORDER BY id DESC
                """,
                (issue_id,)
            ).fetchall()

        else:
            error = "हा संदर्भ क्रमांक सापडला नाही."

        con.close()

    return render_template(
        "status.html",
        result=result,
        updates=updates,
        error=error
    )


# ---------------------------------------------------------
# ADMIN LOGIN
# ---------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":

        admin_username = os.getenv(
            "ADMIN_USERNAME",
            "admin"
        )

        admin_password = os.getenv(
            "ADMIN_PASSWORD"
        )

        username = request.form.get(
            "username",
            ""
        )

        password = request.form.get(
            "password",
            ""
        )

        if (
            admin_password
            and username == admin_username
            and password == admin_password
        ):
            session["admin"] = True

            return redirect(
                url_for("dashboard")
            )

        error = "Username किंवा Password चुकीचा आहे."

    return render_template(
        "login.html",
        error=error
    )


# ---------------------------------------------------------
# ADMIN LOGOUT
# ---------------------------------------------------------

@app.route("/admin/logout")
def logout():
    session.pop("admin", None)

    return redirect(
        url_for("login")
    )


# ---------------------------------------------------------
# ADMIN DASHBOARD
# ---------------------------------------------------------

@app.route("/admin")
@admin_required
def dashboard():
    con = get_db()

    show_archived = request.args.get(
        "archived",
        "0"
    ) == "1"

    if show_archived:
        rows = con.execute(
            """
            SELECT *
            FROM issues
            WHERE archived=1
            ORDER BY id DESC
            """
        ).fetchall()

    else:
        rows = con.execute(
            """
            SELECT *
            FROM issues
            WHERE archived=0
            ORDER BY id DESC
            """
        ).fetchall()

    archived_count = con.execute(
        """
        SELECT COUNT(*) AS n
        FROM issues
        WHERE archived=1
        """
    ).fetchone()["n"]

    con.close()

    total = len(rows)

    resolved = sum(
        r["status"] == "पूर्ण"
        for r in rows
    )

    urgent = sum(
        r["priority"] == "तातडीची"
        for r in rows
    )

    open_count = total - resolved

    ward_counts = {
        w: sum(r["ward"] == w for r in rows)
        for w in WARDS
    }

    category_counts = {
        c: sum(r["category"] == c for r in rows)
        for c in CATEGORIES
    }

    status_counts = {
        s: sum(r["status"] == s for r in rows)
        for s in STATUSES
    }

    priority_counts = {
        p: sum(r["priority"] == p for r in rows)
        for p in PRIORITIES
    }

    resolution_pct = (
        round((resolved / total) * 100, 1)
        if total
        else 0
    )

    return render_template(
        "dashboard.html",
        rows=rows,
        total=total,
        resolved=resolved,
        urgent=urgent,
        open_count=open_count,
        ward_counts=ward_counts,
        category_counts=category_counts,
        status_counts=status_counts,
        priority_counts=priority_counts,
        resolution_pct=resolution_pct,
        archived_count=archived_count,
        show_archived=show_archived
    )


# ---------------------------------------------------------
# ADMIN ISSUE DETAIL
# ---------------------------------------------------------

@app.route("/admin/issue/<int:issue_id>")
@admin_required
def issue_detail(issue_id):
    con = get_db()

    issue = con.execute(
        """
        SELECT *
        FROM issues
        WHERE id=?
        """,
        (issue_id,)
    ).fetchone()

    updates = []

    if issue:
        updates = con.execute(
            """
            SELECT *
            FROM public_updates
            WHERE issue_id=?
            ORDER BY id DESC
            """,
            (issue["issue_id"],)
        ).fetchall()

    con.close()

    if not issue:
        return "Issue not found", 404

    return render_template(
        "issue_detail.html",
        issue=issue,
        updates=updates
    )


# ---------------------------------------------------------
# ADMIN UPDATE ISSUE
# ---------------------------------------------------------

@app.route(
    "/admin/update/<int:issue_id>",
    methods=["POST"]
)
@admin_required
def update_issue(issue_id):
    f = request.form

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M"
    )

    con = get_db()

    con.execute(
        """
        UPDATE issues
        SET
            status=?,
            assigned_person=?,
            expected_completion_date=?,
            action_taken=?,
            internal_note=?,
            last_updated=?
        WHERE id=?
        """,
        (
            f.get("status", "नवीन"),
            f.get("assigned_person", "").strip(),
            f.get("expected_completion_date", ""),
            f.get("action_taken", "").strip(),
            f.get("internal_note", "").strip(),
            now,
            issue_id
        )
    )

    public_update = f.get(
        "public_update",
        ""
    ).strip()

    if public_update:

        row = con.execute(
            """
            SELECT issue_id
            FROM issues
            WHERE id=?
            """,
            (issue_id,)
        ).fetchone()

        if row:
            con.execute(
                """
                INSERT INTO public_updates
                (
                    issue_id,
                    update_text,
                    update_date
                )
                VALUES (?, ?, ?)
                """,
                (
                    row["issue_id"],
                    public_update,
                    now
                )
            )

    con.commit()
    con.close()

    return redirect(
        url_for(
            "issue_detail",
            issue_id=issue_id,
            saved=1
        )
    )


# ---------------------------------------------------------
# ARCHIVE / RESTORE
# ---------------------------------------------------------

@app.route(
    "/admin/issue/<int:issue_id>/archive",
    methods=["POST"]
)
@admin_required
def archive_issue(issue_id):
    con = get_db()

    issue = con.execute(
        """
        SELECT issue_id, archived
        FROM issues
        WHERE id=?
        """,
        (issue_id,)
    ).fetchone()

    if not issue:
        con.close()

        return "Issue not found", 404

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M"
    )

    if issue["archived"]:

        con.execute(
            """
            UPDATE issues
            SET
                archived=0,
                archived_at=NULL,
                last_updated=?
            WHERE id=?
            """,
            (now, issue_id)
        )

    else:

        con.execute(
            """
            UPDATE issues
            SET
                archived=1,
                archived_at=?,
                last_updated=?
            WHERE id=?
            """,
            (now, now, issue_id)
        )

    con.commit()
    con.close()

    return redirect(
        url_for(
            "issue_detail",
            issue_id=issue_id,
            changed=1
        )
    )


# ---------------------------------------------------------
# DELETE ISSUE
# ---------------------------------------------------------

@app.route(
    "/admin/issue/<int:issue_id>/delete",
    methods=["POST"]
)
@admin_required
def delete_issue(issue_id):
    con = get_db()

    issue = con.execute(
        """
        SELECT issue_id, photo_url
        FROM issues
        WHERE id=?
        """,
        (issue_id,)
    ).fetchone()

    if not issue:
        con.close()

        return "Issue not found", 404

    con.execute(
        """
        DELETE FROM public_updates
        WHERE issue_id=?
        """,
        (issue["issue_id"],)
    )

    con.execute(
        """
        DELETE FROM issues
        WHERE id=?
        """,
        (issue_id,)
    )

    con.commit()
    con.close()

    if issue["photo_url"]:

        filename = Path(
            issue["photo_url"]
        ).name

        photo_path = (
            UPLOAD_DIR / filename
        )

        try:
            photo_path.unlink(
                missing_ok=True
            )
        except OSError:
            pass

    return redirect(
        url_for(
            "dashboard",
            deleted=1
        )
    )


# ---------------------------------------------------------
# DATABASE BACKUP
# ---------------------------------------------------------

@app.route("/admin/backup")
@admin_required
def backup_database():

    data = backup_database_bytes()

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    return send_file(
        io.BytesIO(data),
        mimetype="application/sql",
        as_attachment=True,
        download_name=(
            f"khamaswadi_backup_{stamp}.sql"
        )
    )


# ---------------------------------------------------------
# EXPORT CSV
# ---------------------------------------------------------

@app.route("/admin/export")
@admin_required
def export_csv():

    con = get_db()

    rows = con.execute(
        """
        SELECT *
        FROM issues
        ORDER BY id DESC
        """
    ).fetchall()

    con.close()

    out = io.StringIO(
        newline=""
    )

    out.write("\ufeff")

    writer = csv.writer(out)

    writer.writerow([
        "Issue ID",
        "Created",
        "Ward",
        "Category",
        "Location",
        "Description",
        "Priority",
        "Status",
        "Assigned Person",
        "Expected Date",
        "Action Taken",
        "Last Updated",
        "Archived"
    ])

    for r in rows:

        writer.writerow([
            r["issue_id"],
            r["created_at"],
            r["ward"],
            r["category"],
            r["location"],
            r["description"],
            r["priority"],
            r["status"],
            r["assigned_person"],
            r["expected_completion_date"],
            r["action_taken"],
            r["last_updated"],
            "होय" if r["archived"] else "नाही"
        ])

    return send_file(
        io.BytesIO(
            out.getvalue().encode(
                "utf-8-sig"
            )
        ),
        mimetype="text/csv",
        as_attachment=True,
        download_name="khamaswadi_issues.csv"
    )


# ---------------------------------------------------------
# API
# ---------------------------------------------------------

@app.route("/api/issues")
@admin_required
def api_issues():

    con = get_db()

    rows = con.execute(
        """
        SELECT *
        FROM issues
        ORDER BY id DESC
        """
    ).fetchall()

    con.close()

    return jsonify([
        dict(r)
        for r in rows
    ])


# ---------------------------------------------------------
# PWA MANIFEST
# ---------------------------------------------------------

@app.route("/manifest.json")
def manifest():

    return send_file(
        BASE / "static" / "manifest.json",
        mimetype="application/manifest+json"
    )


# ---------------------------------------------------------
# SERVICE WORKER
# ---------------------------------------------------------

@app.route("/sw.js")
def sw():

    return send_file(
        BASE / "static" / "sw.js",
        mimetype="application/javascript"
    )


# ---------------------------------------------------------
# RUN APP
# ---------------------------------------------------------

if __name__ == "__main__":

    init_db()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )