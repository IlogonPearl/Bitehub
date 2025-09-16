# app.py - BiteHub (compiled) with Snowflake-safe schema upgrades (preserve data)
import os
import base64
import streamlit as st
import pandas as pd
import snowflake.connector
from groq import Groq
import random
from datetime import datetime, date, time
import matplotlib.pyplot as plt
import hashlib
import secrets
import time as time_mod

# ---------------------------
# Helper: Snowflake connection
# ---------------------------
def get_connection():
    return snowflake.connector.connect(
        user=st.secrets["SNOWFLAKE_USER"],
        password=st.secrets["SNOWFLAKE_PASSWORD"],
        account=st.secrets["SNOWFLAKE_ACCOUNT"],
        warehouse=st.secrets["SNOWFLAKE_WAREHOUSE"],
        database=st.secrets["SNOWFLAKE_DATABASE"],
        schema=st.secrets["SNOWFLAKE_SCHEMA"],
    )

# ---------------------------
# Ensure tables & columns exist (safe, preserve data)
# ---------------------------
def ensure_tables_and_columns():
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Create accounts table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                username VARCHAR PRIMARY KEY,
                password VARCHAR,
                role VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Create feedbacks table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS feedbacks (
                id INT AUTOINCREMENT PRIMARY KEY,
                item VARCHAR,
                feedback VARCHAR,
                rating INT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Create receipts table if not exists (keep minimal columns; we'll add missing ones later)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS receipts (
                id INT AUTOINCREMENT PRIMARY KEY,
                order_id VARCHAR UNIQUE,
                user_id VARCHAR,
                items TEXT,
                total FLOAT,
                payment_method VARCHAR,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # helper to check if column exists
        def column_exists(table_name, column_name):
            cur.execute(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_catalog = %s AND table_schema = %s AND table_name = %s AND column_name = %s
                """,
                (st.secrets["SNOWFLAKE_DATABASE"], st.secrets["SNOWFLAKE_SCHEMA"], table_name.upper(), column_name.upper()),
            )
            cnt = cur.fetchone()[0]
            return cnt > 0

        # Add pickup_time column if missing
        if not column_exists("receipts", "pickup_time"):
            cur.execute("ALTER TABLE receipts ADD COLUMN pickup_time TIMESTAMP_NTZ")
        # Add status column if missing (default 'Pending')
        if not column_exists("receipts", "status"):
            # Add column
            cur.execute("ALTER TABLE receipts ADD COLUMN status VARCHAR")
            # Set default pending for existing nulls
            cur.execute("UPDATE receipts SET status='Pending' WHERE status IS NULL")
    finally:
        cur.close()
        conn.commit()
        conn.close()

# Run the ensure step early (safe, idempotent)
try:
    ensure_tables_and_columns()
except Exception as e:
    # If DB creds missing in st.secrets or connection fails, show warning but keep app running for dev/testing
    st.warning(f"Could not ensure DB schema (will continue in limited/local mode): {e}")

# ---------------------------
# Password hashing (PBKDF2)
# ---------------------------
def hash_password(password: str, salt: bytes | None = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex() + "$" + hashed.hex()

def verify_password(stored: str, provided_password: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = hashlib.pbkdf2_hmac("sha256", provided_password.encode(), salt, 200_000)
        return expected.hex() == hash_hex
    except Exception:
        return False

# ---------------------------
# DB helpers: accounts, feedbacks, receipts
# ---------------------------
def save_account(username, password, role="Non-Staff"):
    conn = get_connection()
    cur = conn.cursor()
    hashed = hash_password(password)
    try:
        cur.execute(
            "INSERT INTO accounts (username, password, role) VALUES (%s, %s, %s)",
            (username, hashed, role),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

def get_account(username):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT username, password, role FROM accounts WHERE username=%s", (username,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if row:
        return {"username": row[0], "password": row[1], "role": row[2]}
    return None

def validate_account(username, password):
    acc = get_account(username)
    if not acc:
        return None
    if verify_password(acc["password"], password):
        return {"username": acc["username"], "role": acc["role"]}
    return None

def save_feedback(item, feedback, rating, username="Anon"):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO feedbacks (item, feedback, rating) VALUES (%s, %s, %s)",
            (item, f"{username}: {feedback}", rating),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

def load_feedbacks_df():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT item, feedback, rating, timestamp FROM feedbacks ORDER BY timestamp DESC")
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    if rows:
        return pd.DataFrame(rows, columns=["item", "feedback", "rating", "timestamp"])
    return pd.DataFrame(columns=["item", "feedback", "rating", "timestamp"])

def save_receipt(order_id, items, total, payment_method, details="", pickup_time=None, status="Pending"):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO receipts (order_id, items, total, payment_method, details, pickup_time, status) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (order_id, items, total, payment_method, details, pickup_time, status),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

def load_receipts_df():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT order_id, items, total, payment_method, details, pickup_time, status, timestamp FROM receipts ORDER BY timestamp DESC")
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    if rows:
        return pd.DataFrame(rows, columns=["order_id", "items", "total", "payment_method", "details", "pickup_time", "status", "timestamp"])
    return pd.DataFrame(columns=["order_id", "items", "total", "payment_method", "details", "pickup_time", "status", "timestamp"])

def set_receipt_status(order_id, new_status):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE receipts SET status=%s WHERE order_id=%s", (new_status, order_id))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return True

# ---------------------------
# Static menu (kept in memory for demo)
# ---------------------------
menu_data = {
    "Breakfast": {"Tapsilog": 70, "Longsilog": 65, "Hotdog Meal": 50, "Omelette": 45},
    "Lunch": {"Chicken Adobo": 90, "Pork Sinigang": 100, "Beef Caldereta": 120, "Rice": 15},
    "Snack": {"Burger": 50, "Fries": 30, "Siomai Rice": 60, "Spaghetti": 45},
    "Drinks": {"Soda": 20, "Iced Tea": 25, "Bottled Water": 15, "Coffee": 30},
    "Dessert": {"Halo-Halo": 65, "Leche Flan": 40, "Ice Cream": 35},
    "Dinner": {"Grilled Chicken": 95, "Sisig": 110, "Fried Bangus": 85, "Rice": 15},
}
if "sold_out" not in st.session_state:
    st.session_state.sold_out = set()

# ---------------------------
# Groq client
# ---------------------------
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# ---------------------------
# Session initialization
# ---------------------------
if "page" not in st.session_state:
    st.session_state.page = "login"
if "user" not in st.session_state:
    st.session_state.user = None
if "cart" not in st.session_state:
    st.session_state.cart = {}
if "points" not in st.session_state:
    st.session_state.points = 0
if "notifications" not in st.session_state:
    st.session_state.notifications = []

# ---------------------------
# UI setup + background
# ---------------------------
st.set_page_config(page_title="BiteHub Canteen GenAI", layout="wide")

st.markdown(
    """
<style>
div.stButton > button {
    display: inline-block;
    margin: 8px;
    width: 170px;
    height: 44px;
    font-size: 15px;
    border-radius: 8px;
}
.center-buttons { text-align:center; }
h1,h2,h3 { color:#222; }
</style>
""",
    unsafe_allow_html=True,
)

def set_background(image_path):
    try:
        with open(image_path, "rb") as f:
            data = f.read()
        img_b64 = base64.b64encode(data).decode()
        css = f"""
        <style>
        .stApp {{
            background-image: url("data:image/jpg;base64,{img_b64}");
            background-size: cover;
            background-position: center;
        }}
        </style>
        """
        st.markdown(css, unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"Could not load background: {e}")

if os.path.exists("can.jpg"):
    set_background("can.jpg")

# ---------------------------
# Main pages: Login / Signup / Main
# ---------------------------

if st.session_state.page == "login":
    st.markdown("<h2>☕ BiteHub — Login</h2>", unsafe_allow_html=True)
    username = st.text_input("Username", placeholder="Enter username", key="login_username")
    password = st.text_input("Password", type="password", placeholder="Enter password", key="login_password")

    st.markdown('<div class="center-buttons">', unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,1,1])
    with col1:
        if st.button("Log In", key="login_btn"):
            user = validate_account(username, password)
            if user:
                st.session_state.user = user
                st.session_state.page = "main"
                st.success(f"Welcome, {username}!")
            else:
                st.error("❌ Invalid username or password. Please try again or create an account.")
    with col2:
        if st.button("Guest Account", key="guest_btn"):
            st.session_state.user = {"username": "Guest", "role": "Non-Staff"}
            st.session_state.page = "main"
            st.success("Signed in as Guest")
    with col3:
        if st.button("Create Account", key="goto_signup"):
            st.session_state.page = "signup"
    st.markdown("</div>", unsafe_allow_html=True)

elif st.session_state.page == "signup":
    st.markdown("<h2>✍️ Create Account</h2>", unsafe_allow_html=True)
    new_username = st.text_input("New Username", key="signup_username")
    new_pass = st.text_input("New Password", type="password", key="signup_password")
    new_role = st.selectbox("Role", ["Non-Staff", "Staff"], key="signup_role")
    if st.button("Register", key="register_btn"):
        if new_username and new_pass:
            # check if already exists
            if get_account(new_username):
                st.error("Username already exists. Choose another.")
            else:
                try:
                    save_account(new_username, new_pass, new_role)
                    st.success(f"✅ Account created for {new_username}. Please log in.")
                    st.session_state.page = "login"
                except Exception as e:
                    st.error(f"Could not create account: {e}")
        else:
            st.error("Please fill all fields.")
    if st.button("Back to Login", key="back_login"):
        st.session_state.page = "login"

# ---------------------------
# MAIN Portal (Student / Staff)
# ---------------------------
elif st.session_state.page == "main":
    user = st.session_state.user or {"username": "Guest", "role": "Non-Staff"}
    st.title(f"🏫 Welcome {user['username']} to BiteHub")

    # AI helper
    def run_ai(question, extra_context=""):
        if not question:
            return "Please ask something."
        menu_text = ", ".join([f"{item} ({price})" for cat in menu_data.values() for item, price in cat.items()])
        context = f"MENU: {menu_text}\n{extra_context}"
        prompt = f"You are a canteen assistant. Context: {context}\nUser question: {question}"
        try:
            resp = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role":"user","content":prompt}],
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"⚠️ AI unavailable: {e}"

    # Non-Staff view
    if user["role"] == "Non-Staff":
        if user["username"] == "Guest":
            st.warning("🔓 You're using Guest. Create an account and enjoy promotions like Loyalty points, Surprise Promos.")

        st.subheader("🤖 Canteen AI Assistant")
        q = st.text_input("Ask about menu, budget, feedback, or sales:", key="ai_query")
        if st.button("Ask AI", key="ai_button"):
            with st.spinner("Asking AI..."):
                st.info(run_ai(q))

        st.divider()
        colA, colB = st.columns([2,1])

        # Menu & ordering
        with colA:
            st.subheader("📋 Menu")
            for cat, items in menu_data.items():
                with st.expander(cat):
                    for item_name, price in items.items():
                        if item_name in st.session_state.sold_out:
                            st.write(f"~~{item_name}~~ — Sold out")
                            continue
                        cols = st.columns([1,1,1])
                        qty_key = f"qty_{cat}_{item_name}"
                        qty = cols[0].number_input(f"{item_name} (₱{price})", min_value=0, value=0, step=1, key=qty_key)
                        if cols[1].button("Add", key=f"add_{cat}_{item_name}") and qty>0:
                            st.session_state.cart[item_name] = st.session_state.cart.get(item_name,0) + qty
                            st.success(f"Added {qty} x {item_name}")

            # cart summary
            if st.session_state.cart:
                st.subheader("🛒 Your Cart")
                total = 0
                for it, qtt in st.session_state.cart.items():
                    price = next((p for cat in menu_data.values() for n,p in cat.items() if n==it), 0)
                    st.write(f"{it} x {qtt} = ₱{price*qtt}")
                    total += price*qtt

                st.write(f"**Subtotal: ₱{total}**")
                st.write(f"🔖 Points: {st.session_state.points} pts (100 pts = ₱1)")

                max_discount = st.session_state.points // 100
                use_points = st.checkbox(f"Apply points (max ₱{max_discount})", key="use_points")
                discount = 0
                if use_points and max_discount>0:
                    discount = st.number_input("Discount amount (₱)", min_value=0, max_value=max_discount, value=0, key="discount_pesos")
                final_total = max(0, total - discount)
                st.write(f"**Total after discount: ₱{final_total}**")

                pickup_date = st.date_input("Pickup date", value=date.today(), key="pickup_date")
                pickup_time = st.time_input("Pickup time", value=datetime.now().time(), key="pickup_time")
                payment_method = st.radio("Payment Method", ["Cash","Card","E-Wallet"], key="payment_method")

                if st.button("Place Order", key="place_order"):
                    order_id = f"ORD{random.randint(10000,99999)}"
                    items_str = ", ".join([f"{k}x{v}" for k,v in st.session_state.cart.items()])
                    pickup_dt = datetime.combine(pickup_date, pickup_time)
                    details = f"user:{user['username']}|notes:pickup scheduled"
                    try:
                        save_receipt(order_id, items_str, final_total, payment_method, details, pickup_time=pickup_dt, status="Pending")
                        st.session_state.points += int(final_total)
                        if discount>0:
                            st.session_state.points -= discount * 100
                        st.success(f"✅ Order placed! Order ID: {order_id} | Total: ₱{final_total}")
                        st.session_state.notifications.append(f"Order {order_id} placed for pickup {pickup_dt.strftime('%Y-%m-%d %H:%M')}")
                        st.session_state.cart = {}
                    except Exception as e:
                        st.error(f"Error saving order: {e}")

        # Feedback & notifications
        with colB:
            st.subheader("✍️ Give Feedback")
            fb_item = st.selectbox("Select Item:", ["(select)"] + [i for cat in menu_data.values() for i in cat.keys()], key="fb_item")
            rating = st.slider("Rate this item (1-5):", 1,5,3, key="fb_rating")
            fb_text = st.text_area("Your Feedback:", key="fb_text")
            if st.button("Submit Feedback", key="submit_fb"):
                if fb_item != "(select)" and fb_text.strip():
                    try:
                        save_feedback(fb_item, fb_text.strip(), rating, username=user["username"])
                        st.success("✅ Feedback submitted!")
                    except Exception as e:
                        st.error(f"Failed to save feedback: {e}")
                else:
                    st.warning("Choose an item and write feedback.")

            st.markdown("---")
            st.subheader("🔔 Notifications")
            if st.session_state.notifications:
                for n in st.session_state.notifications[-5:]:
                    st.info(n)
            else:
                st.info("No notifications yet.")

        st.divider()
        st.subheader("📦 Your Recent Orders")
        try:
            receipts_df = load_receipts_df()
            if not receipts_df.empty:
                receipts_df["user"] = receipts_df["details"].fillna("").apply(lambda d: dict([p.split(":",1) for p in d.split("|") if ":" in p]).get("user",""))
                my = receipts_df[receipts_df["user"]==user["username"]]
                if not my.empty:
                    st.dataframe(my[["order_id","items","total","payment_method","pickup_time","status","timestamp","details"]])
                else:
                    st.info("No previous orders found.")
            else:
                st.info("No receipts recorded yet.")
        except Exception as e:
            st.error(f"Could not load receipts: {e}")

        if st.button("Log Out", key="logout_btn"):
            st.session_state.page = "login"
            st.session_state.user = None
# -------------------------------------------------
    # Staff Portal
    # -------------------------------------------------
    elif user["role"] == "Staff":
        st.success("👨‍🍳 Staff Portal")

        st.subheader("🤖 Staff AI Assistant")
        staff_q = st.text_input("Ask Staff AI")
        if st.button("Ask Staff AI"):
            sales = load_receipts_df().head(20).to_dict()
            fb = load_feedbacks_df().head(20).to_dict()
            st.info(run_ai(staff_q, f"Sales: {sales}\nFeedback: {fb}"))

        st.subheader("📋 Manage Menu")
        cat = st.selectbox("Category", list(menu_data.keys()))
        item = st.text_input("Item")
        price = st.number_input("Price", 0.0, 999.0, 10.0)
        if st.button("Add/Update"):
            menu_data[cat][item] = price
            st.success(f"{item} updated in {cat}")

        sel = st.selectbox("Select Item", ["(none)"] + [i for c in menu_data.values() for i in c.keys()])
        if sel != "(none)":
            if st.button("Sold Out"):
                st.session_state.sold_out.add(sel)
            if st.button("Available"):
                st.session_state.sold_out.discard(sel)
            if st.button("Remove"):
                for c in menu_data:
                    menu_data[c].pop(sel, None)

        st.subheader("📝 Feedbacks")
        fb = load_feedbacks_df()
        st.dataframe(fb)

        st.subheader("📦 Pending Orders")

try:
    receipts_df = load_receipts_df()
    if not receipts_df.empty:
        # Parse details into dictionary
        receipts_df["parsed"] = receipts_df["details"].fillna("").apply(
            lambda d: dict([p.split(":", 1) for p in d.split("|") if ":" in p])
        )
        receipts_df["user"] = receipts_df["parsed"].apply(lambda p: p.get("user", ""))
        receipts_df["status"] = receipts_df["parsed"].apply(lambda p: p.get("status", "unknown"))
        receipts_df["pickup"] = receipts_df["parsed"].apply(lambda p: p.get("pickup", ""))

        # Filter pending
        pending = receipts_df[receipts_df["status"] == "pending"]

        if not pending.empty:
            for i, row in pending.iterrows():
                st.write(f"**Order {row['order_id']}** — {row['items']} | Pickup: {row['pickup']} | By {row['user']}")
                if st.button(f"Mark Ready — {row['order_id']}", key=f"ready_{row['order_id']}"):
                    success = update_receipt_status(row["order_id"], "ready for pickup")
                    if success:
                        st.success(f"✅ Order {row['order_id']} marked as Ready for Pickup")
                    else:
                        st.error("⚠️ Could not update order status.")
        else:
            st.info("No pending orders.")
    else:
        st.info("No receipts yet.")
except Exception as e:
    st.error(f"Could not load pending orders: {e}")
