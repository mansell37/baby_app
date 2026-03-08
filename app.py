"""
Baby Shopping List Web App - Flask backend.
Shared shopping list and to-dos with SQLite.
Optional shared-password auth when SHARED_PASSWORD env is set.
"""
import json
import os
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, render_template_string

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
DB_PATH = Path(__file__).parent / "baby_list.db"

SHARED_PASSWORD = os.environ.get("SHARED_PASSWORD", "").strip()
REQUIRE_AUTH = bool(SHARED_PASSWORD)


def _auth_ok():
    if not REQUIRE_AUTH:
        return True
    return session.get("authenticated") is True


@app.before_request
def require_auth():
    if _auth_ok():
        return None
    # Allow login and logout
    if request.path == "/login":
        return None
    if request.path == "/logout" and request.method == "POST":
        return None
    # Require auth for everything else
    if request.path.startswith("/api/"):
        return jsonify({"error": "Login required"}), 401
    if request.path == "/logout":
        return redirect(url_for("login"))
    return redirect(url_for("login"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS shopping_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL DEFAULT 0,
            qty INTEGER NOT NULL DEFAULT 1,
            link TEXT,
            shipping_estimate TEXT,
            price_updated_at TEXT,
            acquired INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0
        );
    """)
    # Migrations for existing DBs
    for col, sql in [
        ("acquired", "ALTER TABLE shopping_items ADD COLUMN acquired INTEGER NOT NULL DEFAULT 0"),
        ("shipping_estimate", "ALTER TABLE shopping_items ADD COLUMN shipping_estimate TEXT"),
        ("price_updated_at", "ALTER TABLE shopping_items ADD COLUMN price_updated_at TEXT"),
    ]:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass
    conn.close()


def _extract_price_from_html(html, url):
    """Try to find a product price in HTML. Returns float or None."""
    # Prefer meta tags (Open Graph / product)
    meta_price = re.search(
        r'<meta[^>]+(?:property|name)=["\'](?:product:price:amount|og:price:amount|price)["\'][^>]+content=["\']([\d.]+)["\']',
        html,
        re.I,
    )
    if meta_price:
        try:
            return float(meta_price.group(1))
        except ValueError:
            pass
    meta_content = re.search(
        r'<meta[^>]+content=["\']([\d.,]+)["\'][^>]+(?:property|name)=["\'](?:product:price:amount|og:price:amount)["\']',
        html,
        re.I,
    )
    if meta_content:
        try:
            return float(meta_content.group(1).replace(",", ""))
        except ValueError:
            pass
    # JSON-LD Product / Offer price
    ld = re.search(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([^<]+)</script>',
        html,
        re.I | re.DOTALL,
    )
    if ld:
        try:
            data = json.loads(ld.group(1))
            if isinstance(data, dict):
                if "offers" in data and isinstance(data["offers"], dict):
                    p = data["offers"].get("price")
                    if p is not None:
                        return float(p)
                if "price" in data:
                    return float(data["price"])
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        if "offers" in item and isinstance(item["offers"], dict):
                            p = item["offers"].get("price")
                            if p is not None:
                                return float(p)
                        if "price" in item:
                            return float(item["price"])
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    # Fallback: first $ amount that looks like a price (avoid tiny numbers like 0.99 from scripts)
    dollar = re.search(r'\$\s*([\d,]+(?:\.\d{2})?)', html[:80000])
    if dollar:
        try:
            return float(dollar.group(1).replace(",", ""))
        except ValueError:
            pass
    return None


@app.route("/api/fetch-price", methods=["GET"])
def fetch_price():
    url = (request.args.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return jsonify({"error": "Invalid URL"}), 400
    try:
        r = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ShoppingList/1.0)"},
        )
        r.raise_for_status()
    except requests.RequestException as e:
        return jsonify({"error": "Could not fetch URL", "detail": str(e)}), 422
    price = _extract_price_from_html(r.text, url)
    if price is None:
        return jsonify({"error": "Could not find a price on this page"}), 422
    return jsonify({"price": round(price, 2), "currency": "AUD"})


# ----- Shopping items API -----

@app.route("/api/items", methods=["GET"])
def list_items():
    acquired = request.args.get("acquired", "").lower() == "true"
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, price, qty, link, shipping_estimate, price_updated_at, acquired FROM shopping_items WHERE acquired = ? ORDER BY id",
        (1 if acquired else 0,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/items", methods=["POST"])
def add_item():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    price = float(data.get("price") or 0)
    qty = int(data.get("qty") or 1)
    link = (data.get("link") or "").strip() or None
    shipping_estimate = (data.get("shipping_estimate") or "").strip() or None
    price_updated_at = (data.get("price_updated_at") or "").strip() or None
    if not name:
        return jsonify({"error": "Name is required"}), 400
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO shopping_items (name, price, qty, link, shipping_estimate, price_updated_at, acquired) VALUES (?, ?, ?, ?, ?, ?, 0)",
        (name, price, qty, link, shipping_estimate, price_updated_at),
    )
    conn.commit()
    row = conn.execute("SELECT id, name, price, qty, link, shipping_estimate, price_updated_at, acquired FROM shopping_items WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return jsonify(dict(row)), 201


@app.route("/api/items/<int:item_id>", methods=["PUT"])
def update_item(item_id):
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    price = data.get("price")
    qty = data.get("qty")
    link = data.get("link")
    shipping_estimate = data.get("shipping_estimate")
    price_updated_at = data.get("price_updated_at")
    if "link" in data:
        link = (data["link"] or "").strip() or None
    if "shipping_estimate" in data:
        shipping_estimate = (data["shipping_estimate"] or "").strip() or None
    if "price_updated_at" in data:
        price_updated_at = (data["price_updated_at"] or "").strip() or None
    conn = get_db()
    row = conn.execute("SELECT id, name, price, qty, link, shipping_estimate, price_updated_at, acquired FROM shopping_items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    row = dict(row)
    if name:
        row["name"] = name
    if price is not None:
        row["price"] = float(price)
    if qty is not None:
        row["qty"] = int(qty)
    if "link" in data:
        row["link"] = link
    if "shipping_estimate" in data:
        row["shipping_estimate"] = shipping_estimate
    if "price_updated_at" in data:
        row["price_updated_at"] = price_updated_at
    conn.execute(
        "UPDATE shopping_items SET name = ?, price = ?, qty = ?, link = ?, shipping_estimate = ?, price_updated_at = ? WHERE id = ?",
        (row["name"], row["price"], row["qty"], row["link"], row["shipping_estimate"], row["price_updated_at"], item_id),
    )
    conn.commit()
    updated = conn.execute("SELECT id, name, price, qty, link, shipping_estimate, price_updated_at, acquired FROM shopping_items WHERE id = ?", (item_id,)).fetchone()
    conn.close()
    return jsonify(dict(updated))


@app.route("/api/items/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    conn = get_db()
    conn.execute("DELETE FROM shopping_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return "", 204


# ----- Todos API -----

@app.route("/api/todos", methods=["GET"])
def list_todos():
    conn = get_db()
    rows = conn.execute("SELECT id, title, done FROM todos ORDER BY id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/todos", methods=["POST"])
def add_todo():
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400
    conn = get_db()
    cur = conn.execute("INSERT INTO todos (title, done) VALUES (?, 0)", (title,))
    conn.commit()
    row = conn.execute("SELECT id, title, done FROM todos WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return jsonify(dict(row)), 201


@app.route("/api/todos/<int:todo_id>", methods=["PATCH"])
def update_todo(todo_id):
    data = request.get_json() or {}
    conn = get_db()
    row = conn.execute("SELECT id, title, done FROM todos WHERE id = ?", (todo_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    if "done" in data:
        done = 1 if data["done"] else 0
        conn.execute("UPDATE todos SET done = ? WHERE id = ?", (done, todo_id))
    if "title" in data and data["title"] is not None:
        title = (data["title"] or "").strip()
        conn.execute("UPDATE todos SET title = ? WHERE id = ?", (title, todo_id))
    conn.commit()
    row = conn.execute("SELECT id, title, done FROM todos WHERE id = ?", (todo_id,)).fetchone()
    conn.close()
    return jsonify(dict(row))


@app.route("/api/todos/<int:todo_id>", methods=["DELETE"])
def delete_todo(todo_id):
    conn = get_db()
    conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/items/<int:item_id>/acquired", methods=["PATCH"])
def set_item_acquired(item_id):
    data = request.get_json() or {}
    acquired = 1 if data.get("acquired", True) else 0
    conn = get_db()
    conn.execute("UPDATE shopping_items SET acquired = ? WHERE id = ?", (acquired, item_id))
    conn.commit()
    row = conn.execute("SELECT id, name, price, qty, link, shipping_estimate, price_updated_at, acquired FROM shopping_items WHERE id = ?", (item_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


@app.route("/api/items/refresh-prices", methods=["POST"])
def refresh_all_prices():
    """Fetch current price from each item's link and update. Sets price_updated_at."""
    from datetime import datetime
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, link FROM shopping_items WHERE acquired = 0 AND link IS NOT NULL AND link != ''"
    ).fetchall()
    updated = 0
    failed = 0
    now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    for row in rows:
        item_id, name, link = row["id"], row["name"], (row["link"] or "").strip()
        if not link:
            continue
        try:
            r = requests.get(
                link,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0 (compatible; ShoppingList/1.0)"},
            )
            r.raise_for_status()
            price = _extract_price_from_html(r.text, link)
            if price is not None:
                conn.execute(
                    "UPDATE shopping_items SET price = ?, price_updated_at = ? WHERE id = ?",
                    (round(price, 2), now_iso, item_id),
                )
                updated += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    conn.commit()
    conn.close()
    return jsonify({
        "updated": updated,
        "failed": failed,
        "prices_as_of": now_iso,
    })


# ----- Summary -----

@app.route("/api/summary", methods=["GET"])
def summary():
    conn = get_db()
    # Only count and sum items not yet acquired (to-buy list)
    row = conn.execute(
        "SELECT COALESCE(SUM(price * qty), 0) AS total, COUNT(*) AS item_count FROM shopping_items WHERE acquired = 0"
    ).fetchone()
    total = row["total"]
    item_count = row["item_count"]
    todo_count = conn.execute("SELECT COUNT(*) AS c FROM todos WHERE done = 0").fetchone()["c"]
    conn.close()
    return jsonify({"total": total, "item_count": item_count, "todos_left": todo_count})


# ----- Login (when SHARED_PASSWORD is set) -----

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Login – Hannah and Matts Shopping List</title>
<style>
  body { font-family: system-ui, sans-serif; background: #f8f6f4; margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
  .box { background: #fff; padding: 2rem; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); max-width: 320px; width: 100%; }
  h1 { margin: 0 0 1rem 0; font-size: 1.25rem; color: #2c2c2c; }
  input { width: 100%; padding: 0.6rem; font-size: 1rem; border: 1px solid #e2ddd8; border-radius: 8px; box-sizing: border-box; margin-bottom: 1rem; }
  button { width: 100%; padding: 0.6rem; font-size: 1rem; background: #6b8f71; color: #fff; border: none; border-radius: 8px; cursor: pointer; }
  button:hover { background: #5a7a5f; }
  .error { color: #b85450; font-size: 0.9rem; margin-bottom: 0.5rem; }
</style>
</head>
<body>
  <div class="box">
    <h1>Hannah and Matts Shopping List</h1>
    <p style="color:#5c5c5c; margin:0 0 1rem 0;">Enter the shared password to continue.</p>
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <form method="post" action="/login">
      <input type="password" name="password" placeholder="Password" required autofocus />
      <button type="submit">Log in</button>
    </form>
  </div>
</body>
</html>"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if _auth_ok():
            return redirect(url_for("index"))
        return render_template_string(LOGIN_HTML)
    # POST
    password = (request.form.get("password") or "").strip()
    if password == SHARED_PASSWORD:
        session["authenticated"] = True
        return redirect(request.args.get("next") or url_for("index"))
    return render_template_string(LOGIN_HTML, error="Wrong password. Try again."), 401


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("authenticated", None)
    return redirect(url_for("login"))


# ----- Serve frontend -----

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def static_file(path):
    return send_from_directory(app.static_folder, path)


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=(port == 5000))
