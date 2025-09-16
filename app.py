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
import re

---------------------------

Snowflake connection helper

---------------------------

def get_connection(): return snowflake.connector.connect( user=st.secrets["SNOWFLAKE_USER"], password=st.secrets["SNOWFLAKE_PASSWORD"], account=st.secrets["SNOWFLAKE_ACCOUNT"], warehouse=st.secrets["SNOWFLAKE_WAREHOUSE"], database=st.secrets["SNOWFLAKE_DATABASE"], schema=st.secrets["SNOWFLAKE_SCHEMA"], )

---------------------------

Ensure tables & columns exist

---------------------------

def ensure_tables_and_columns(): try: conn = get_connection() cur = conn.cursor() # accounts cur.execute(""" CREATE TABLE IF NOT EXISTS accounts ( username VARCHAR PRIMARY KEY, password VARCHAR, role VARCHAR, loyalty_points INT DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ) """) # feedbacks cur.execute(""" CREATE TABLE IF NOT EXISTS feedbacks ( id INT AUTOINCREMENT PRIMARY KEY, item VARCHAR, feedback VARCHAR, rating INT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP ) """) # receipts cur.execute(""" CREATE TABLE IF NOT EXISTS receipts ( id INT AUTOINCREMENT PRIMARY KEY, order_id VARCHAR UNIQUE, user_id VARCHAR, items TEXT, total FLOAT, payment_method VARCHAR, details TEXT, pickup_time TIMESTAMP_NTZ, status VARCHAR, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP ) """) finally: try: cur.close() conn.commit() conn.close() except Exception: pass

Run schema ensure

try: ensure_tables_and_columns() except Exception as e: st.warning(f"Could not ensure DB schema: {e}")

---------------------------

Password utilities

---------------------------

def hash_password(password: str, salt: bytes | None = None) -> str: if salt is None: salt = secrets.token_bytes(16) hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000) return salt.hex() + "$" + hashed.hex()

def verify_password(stored: str, provided_password: str) -> bool: try: salt_hex, hash_hex = stored.split("$", 1) salt = bytes.fromhex(salt_hex) expected = hashlib.pbkdf2_hmac("sha256", provided_password.encode(), salt, 200_000) return expected.hex() == hash_hex except Exception: return False

---------------------------

DB helpers

---------------------------

def save_account(username, password, role="Non-Staff"): conn = get_connection() cur = conn.cursor() hashed = hash_password(password) try: cur.execute("INSERT INTO accounts (username, password, role) VALUES (%s, %s, %s)", (username, hashed, role)) conn.commit() finally: cur.close() conn.close()

def get_account(username): conn = get_connection() cur = conn.cursor() try: cur.execute("SELECT username, password, role, loyalty_points FROM accounts WHERE username=%s", (username,)) row = cur.fetchone() finally: cur.close() conn.close() if row: return {"username": row[0], "password": row[1], "role": row[2], "loyalty_points": int(row[3] or 0)} return None

def validate_account(username, password): acc = get_account(username) if not acc: return None if verify_password(acc["password"], password): return {"username": acc["username"], "role": acc["role"], "loyalty_points": acc["loyalty_points"]} return None

def update_loyalty_points(username, delta): conn = get_connection() cur = conn.cursor() try: cur.execute("UPDATE accounts SET loyalty_points = COALESCE(loyalty_points,0) + %s WHERE username=%s", (int(delta), username)) conn.commit() cur.execute("SELECT loyalty_points FROM accounts WHERE username=%s", (username,)) r = cur.fetchone() return int(r[0] or 0) if r else None finally: cur.close() conn.close()

def save_feedback(item, feedback, rating, username="Anon"): conn = get_connection() cur = conn.cursor() try: cur.execute("INSERT INTO feedbacks (item, feedback, rating) VALUES (%s, %s, %s)", (item, f"{username}: {feedback}", rating)) conn.commit() finally: cur.close() conn.close()

def load_feedbacks_df(): conn = get_connection() cur = conn.cursor() try: cur.execute("SELECT item, feedback, rating, timestamp FROM feedbacks ORDER BY timestamp DESC") rows = cur.fetchall() finally: cur.close() conn.close() if rows: return pd.DataFrame(rows, columns=["item", "feedback", "rating", "timestamp"]) return pd.DataFrame(columns=["item", "feedback", "rating", "timestamp"])

def save_receipt(order_id, items, total, payment_method, details="", pickup_time=None, status="Pending", user_id=None): conn = get_connection() cur = conn.cursor() try: cur.execute("INSERT INTO receipts (order_id, user_id, items, total, payment_method, details, pickup_time, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (order_id, user_id, items, float(total), payment_method, details, pickup_time, status)) conn.commit() finally: cur.close() conn.close()

def load_receipts_df(): conn = get_connection() cur = conn.cursor() try: cur.execute("SELECT order_id, user_id, items, total, payment_method, details, pickup_time, status, timestamp FROM receipts ORDER BY timestamp DESC") rows = cur.fetchall() finally: cur.close() conn.close() if rows: return pd.DataFrame(rows, columns=["order_id", "user_id", "items", "total", "payment_method", "details", "pickup_time", "status", "timestamp"]) return pd.DataFrame(columns=["order_id", "user_id", "items", "total", "payment_method", "details", "pickup_time", "status", "timestamp"])

def set_receipt_status(order_id, new_status): conn = get_connection() cur = conn.cursor() try: cur.execute("UPDATE receipts SET status=%s WHERE order_id=%s", (new_status, order_id)) conn.commit() finally: cur.close() conn.close() return True

#--------------------------

Menu data

#---------------------------

menu_data = { "Breakfast": {"Tapsilog": 70, "Longsilog": 65, "Hotdog Meal": 50, "Omelette": 45}, "Lunch": {"Chicken Adobo": 90, "Pork Sinigang": 100, "Beef Caldereta": 120, "Rice": 15}, "Snack": {"Burger": 50, "Fries": 30, "Siomai Rice": 60, "Spaghetti": 45}, "Drinks": {"Soda": 20, "Iced Tea": 25, "Bottled Water": 15, "Coffee": 30}, "Dessert": {"Halo-Halo": 65, "Leche Flan": 40, "Ice Cream": 35}, "Dinner": {"Grilled Chicken": 95, "Sisig": 110, "Fried Bangus": 85, "Rice": 15}, } if "sold_out" not in st.session_state: st.session_state.sold_out = set()

#---------------------------

Groq client

#---------------------------

try: client = Groq(api_key=st.secrets["GROQ_API_KEY"]) except Exception: client = None

#---------------------------

Session state init

#---------------------------

if "page" not in st.session_state: st.session_state.page = "login" if "user" not in st.session_state: st.session_state.user = None if "cart" not in st.session_state: st.session_state.cart = {} if "loyalty_points" not in st.session_state: st.session_state.loyalty_points = 0 if "notifications" not in st.session_state: st.session_state.notifications = []

#---------------------------

UI setup

#---------------------------

st.set_page_config(page_title="BiteHub Canteen GenAI", layout="wide") st.markdown("""

<style>
header[data-testid="stHeader"] { display: none; }
div.stButton > button { width:180px; height:44px; margin:8px; font-size:15px; border-radius:8px; }
.center-buttons { text-align:center; }
.login-card { background:rgba(255,255,255,0.95); padding:20px; border-radius:10px; max-width:720px; margin:12px auto; box-shadow:0 6px 20px rgba(0,0,0,0.25); }
[data-testid="stAppViewContainer"] > section:first-child { padding-top:6px; }
</style>""", unsafe_allow_html=True)

Main app pages (login/signup/etc.) would continue here

Replace all references of st.session_state.points with st.session_state.loyalty_points

Replace update_points() calls with update_loyalty_points()

Apply discounts and display balances using loyalty_points


#Main app pages (login/signup/etc.) would continue here

Replace all references of st.session_state.points with st.session_state.loyalty_points

#Replace update_points() calls with update_loyalty_points()

#Apply discounts and display balances using loyalty_points



# background image loader (optional)
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
# AI wrapper
# ---------------------------
def run_ai(question, extra_context=""):
    if not client:
        return "⚠️ AI unavailable (no Groq client configured)."
    if not question:
        return "Please ask a question."
    menu_text = ", ".join([f"{item} ({price})" for cat in menu_data.values() for item, price in cat.items()])
    context = f"MENU: {menu_text}\n{extra_context}"
    prompt = f"You are an assistant for a canteen. Context: {context}\nUser question: {question}"
    try:
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role":"user","content":prompt}],
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"⚠️ AI unavailable: {e}"

# ---------------------------
# Password validator
# ---------------------------
def password_valid_rules(pw: str):
    # symbol check: any non-alphanumeric and non-space character
    rules = {
        "length": len(pw) >= 12,
        "upper": bool(re.search(r"[A-Z]", pw)),
        "lower": bool(re.search(r"[a-z]", pw)),
        "digit": bool(re.search(r"[0-9]", pw)),
        "symbol": bool(re.search(r"[^\w\s]", pw))  # improved symbol detection
    }
    return rules

# ---------------------------
# Pages: Login / Signup / Main
# ---------------------------
if st.session_state.page == "login":
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown("<h2>☕ BiteHub — Login</h2>", unsafe_allow_html=True)

    username = st.text_input("Username", placeholder="Enter username", key="login_username")
    password = st.text_input("Password", type="password", placeholder="Enter password", key="login_password")

    st.markdown('<div class="center-buttons">', unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,1,1])
    with col1:
        if st.button("Log In", key="login_btn"):
            try:
                user = validate_account(username, password)
            except Exception as e:
                st.error(f"Login error (DB): {e}")
                user = None
            if user:
                st.session_state.user = user
                st.session_state.page = "main"
                st.success(f"Welcome, {user['username']}!")
            else:
                st.error("❌ Invalid username or password. Please try again or create an account.")
    with col2:
        if st.button("Guest Account", key="guest_btn"):
            # Set guest user (no points, limited features)
            st.session_state.user = {"username": "Guest", "role": "Non-Staff", "points": 0}
            st.session_state.page = "main"
            st.success("Signed in as Guest")
    with col3:
        if st.button("Create Account", key="goto_signup"):
            st.session_state.page = "signup"
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

elif st.session_state.page == "signup":
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown("<h2>✍️ Create Account</h2>", unsafe_allow_html=True)

    new_username = st.text_input("New Username", key="signup_username")
    new_pass = st.text_input("New Password", type="password", key="signup_password")
    new_role = st.selectbox("Role", ["Non-Staff", "Staff"], key="signup_role")

    # live validation
    rules = password_valid_rules(new_pass)
    st.markdown("**Password rules:** (all must be green to enable Register)")
    st.write(f"- Minimum 12 chars: {'✅' if rules['length'] else '❌'}")
    st.write(f"- Uppercase letter: {'✅' if rules['upper'] else '❌'}")
    st.write(f"- Lowercase letter: {'✅' if rules['lower'] else '❌'}")
    st.write(f"- Number: {'✅' if rules['digit'] else '❌'}")
    st.write(f"- Symbol: {'✅' if rules['symbol'] else '❌'}")

    if st.button("Register", key="register_btn"):
        if not new_username or not new_pass:
            st.error("Please fill all fields.")
        elif not all(rules.values()):
            st.error("Password does not meet requirements.")
        else:
            try:
                if get_account(new_username):
                    st.error("Username already exists.")
                else:
                    save_account(new_username, new_pass, new_role)
                    st.success(f"✅ Account created for {new_username}. Please log in.")
                    st.session_state.page = "login"
            except Exception as e:
                st.error(f"Could not create account: {e}")

    if st.button("Back to Login", key="back_login"):
        st.session_state.page = "login"
    st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------
# MAIN Portal (Non-Staff and Staff)
# ---------------------------
elif st.session_state.page == "main":
    user = st.session_state.user or {"username": "Guest", "role": "Non-Staff", "points": 0}
    # ensure user dict has points
    if "points" not in user:
        user["points"] = user.get("points", 0)

    # Guest banner placed at the top (above AI)
    if user["username"] == "Guest":
        st.warning("🔓 You're on a Guest session. Create an account to enjoy loyalty points, promos, and feedback posting.")

    st.title(f"🏫 Welcome {user['username']} to BiteHub")

    # COMMON: AI assistant area for all roles (Non-Staff and Staff)
    st.markdown("### 🤖 Canteen AI Assistant")
    q = st.text_input("Ask about menu, budget, feedback, or sales:", key="ai_query_main")
    if st.button("Ask AI", key="ai_button_main"):
        extra = ""
        # provide non-sensitive context for staff or non-staff
        try:
            sales_df = load_receipts_df()
            feedback_df = load_feedbacks_df()
            extra = f"SALES_SUMMARY: {sales_df.head(10).to_dict() if not sales_df.empty else 'No sales'}\nFEEDBACK_SUMMARY: {feedback_df.head(10).to_dict() if not feedback_df.empty else 'No feedback'}"
        except Exception:
            extra = "DB context unavailable."
        with st.spinner("Asking AI..."):
            st.info(run_ai(q, extra))

    st.divider()

    # Non-Staff view (also applies to Guest with some limits)
    if user["role"] == "Non-Staff":
        is_guest = (user["username"] == "Guest")

        colA, colB = st.columns([2,1])

        # Menu & ordering (left)
        with colA:
            st.subheader("📋 Menu")
            for cat, items in menu_data.items():
                with st.expander(cat, expanded=False):
                    for item_name, price in items.items():
                        if item_name in st.session_state.sold_out:
                            st.write(f"~~{item_name}~~ — Sold out")
                            continue
                        cols = st.columns([1,1,1])
                        qty_key = f"qty_{cat}_{item_name}"
                        qty = cols[0].number_input(f"{item_name} (₱{price})", min_value=0, value=0, step=1, key=qty_key)
                        if cols[1].button("Add", key=f"add_{cat}_{item_name}") and qty > 0:
                            st.session_state.cart[item_name] = st.session_state.cart.get(item_name,0) + qty
                            st.success(f"Added {qty} x {item_name}")

            # cart summary & checkout
            if st.session_state.cart:
                st.subheader("🛒 Your Cart")
                total = 0
                for it, qtt in st.session_state.cart.items():
                    price = next((p for cat in menu_data.values() for n,p in cat.items() if n==it), 0)
                    st.write(f"{it} x {qtt} = ₱{price*qtt}")
                    total += price*qtt

                st.write(f"**Subtotal: ₱{total}**")
                # loyalty points display for non-guest accounts only
                user_points = 0
                if not is_guest:
                    try:
                        db_acc = get_account(user["username"])
                        user_points = db_acc.get("points", 0) if db_acc else 0
                    except Exception:
                        user_points = st.session_state.get("points", 0)
                    st.write(f"🔖 Points available: {user_points} pts (100 pts = ₱1)")

                # Tiered discounts
                discount = 0
                applied_points = 0
                if not is_guest:
                    # offer tier options
                    tier_options = []
                    if user_points >= 500:
                        tier_options.append(("Use 500+ pts → ₱10 discount", 10, 500))
                    if user_points >= 200:
                        tier_options.append(("Use 200 pts → ₱3 discount", 3, 200))
                    if user_points >= 100:
                        tier_options.append(("Use 100 pts → ₱1 discount", 1, 100))
                    # allow simple custom redemption up to floor(user_points/100)
                    if tier_options:
                        st.markdown("**Redeem points for preset discounts:**")
                        chosen = st.selectbox("Choose redemption (optional)", ["None"] + [t[0] for t in tier_options], key="redeem_choice")
                        if chosen != "None":
                            for label, disc_val, pts_req in tier_options:
                                if label == chosen:
                                    discount = disc_val
                                    applied_points = pts_req
                                    break

                final_total = max(0, total - discount)
                st.write(f"**Total after discount: ₱{final_total}**")

                # pickup scheduling
                pickup_date = st.date_input("Pickup date (optional)", value=date.today(), key="pickup_date")
                pickup_time = st.time_input("Pickup time (optional)", value=datetime.now().time(), key="pickup_time")

                payment_method = st.radio("Payment Method", ["Cash","Card","E-Wallet"], key="pmethod")
                payment_details = ""
                if payment_method == "Card":
                    payment_details = st.text_input("Card Number (mock)", key="card_num")
                elif payment_method == "E-Wallet":
                    payment_details = st.selectbox("E-Wallet", ["GCash", "Maya", "QR Scan"], key="ewallet_type")

                if st.button("Place Order", key="place_order_nonstaff"):
                    # save receipt
                    order_id = f"ORD{random.randint(10000,99999)}"
                    items_str = ", ".join([f"{k}x{v}" for k,v in st.session_state.cart.items()])
                    pickup_dt = datetime.combine(pickup_date, pickup_time)
                    details = f"user:{user['username']}|notes:pickup scheduled"
                    try:
                        save_receipt(order_id, items_str, final_total, payment_method, details, pickup_time=pickup_dt, status="Pending", user_id=user['username'] if not is_guest else None)
                        # update points if not guest
                        if not is_guest:
                            # earn points: int(total)
                            earned = int(total)
                            update_points(user['username'], earned)
                            # deduct redeemed pts if used
                            if applied_points > 0:
                                update_points(user['username'], -applied_points)
                        # add notification
                        st.session_state.notifications.append(f"Order {order_id} placed for pickup {pickup_dt.strftime('%Y-%m-%d %H:%M')}")
                        st.success(f"✅ Order placed! Order ID: {order_id} | Total: ₱{final_total}")
                        st.session_state.cart = {}
                    except Exception as e:
                        st.error(f"Error saving order: {e}")

        # Feedback & notifications (right column)
        with colB:
            st.subheader("✍️ Give Feedback")
            if is_guest:
                st.info("Guests cannot submit feedback. Create an account to leave comments and ratings.")
            else:
                fb_item = st.selectbox("Select Item:", ["(select)"] + [i for cat in menu_data.values() for i in cat.keys()], key="fb_item")
                rating = st.slider("Rate this item (1-5):", 1,5,3, key="fb_rating")
                fb_text = st.text_area("Your Feedback:", key="fb_text")
                if st.button("Submit Feedback", key="submit_fb_nonstaff"):
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
                for n in st.session_state.notifications[-6:]:
                    st.info(n)
            else:
                st.info("No notifications yet.")

        st.divider()
        st.subheader("📦 Order History / Track")
        try:
            receipts_df = load_receipts_df()
            if not receipts_df.empty:
                # parse details into dict and filter by user when not guest
                receipts_df["parsed"] = receipts_df["details"].fillna("").apply(lambda d: dict([p.split(":",1) for p in d.split("|") if ":" in p]))
                receipts_df["user"] = receipts_df["parsed"].apply(lambda p: p.get("user","") or p.get("user_id",""))
                my = receipts_df if is_guest else receipts_df[receipts_df["user_id"]==user["username"]]
                if not my.empty:
                    st.dataframe(my[["order_id","items","total","payment_method","pickup_time","status","timestamp"]])
                else:
                    st.info("No previous orders found.")
            else:
                st.info("No receipts recorded yet.")
        except Exception as e:
            st.error(f"Could not load receipts: {e}")

        # logout placed below content
        if st.button("Log Out", key="logout_nonstaff"):
            st.session_state.page = "login"
            st.session_state.user = None

    # STAFF PORTAL
    elif user["role"] == "Staff":
        st.title("🛠️ BiteHub Staff Portal")
        # staff should use main area, not sidebar; but we keep a compact sidebar nav
        choice = st.sidebar.radio("Staff Menu", ["Dashboard","Pending Orders","Manage Menu","AI Assistant","Feedback Review","Sales Report"])

        if choice == "Dashboard":
            st.subheader("📊 Staff Dashboard")
            st.info("Overview: pending orders, quick sales, and recent feedback.")
            # quick counts
            try:
                receipts = load_receipts_df()
                fb = load_feedbacks_df()
                st.metric("Total Orders", len(receipts))
                st.metric("Feedbacks", len(fb))
                pending = receipts[receipts["status"].str.lower()=="pending"] if not receipts.empty else pd.DataFrame()
                st.metric("Pending Orders", len(pending))
            except Exception as e:
                st.error(f"Could not load quick stats: {e}")

        elif choice == "Pending Orders":
            st.subheader("📦 Pending Orders")
            try:
                receipts_df = load_receipts_df()
                if not receipts_df.empty:
                    pending = receipts_df[receipts_df["status"].str.lower()=="pending"]
                    if not pending.empty:
                        for _, row in pending.iterrows():
                            st.write(f"Order {row['order_id']}: {row['items']} — ₱{row['total']} | Pickup: {row['pickup_time']} | By: {row['user_id']}")
                            if st.button(f"Mark Ready {row['order_id']}", key=f"ready_{row['order_id']}"):
                                set_receipt_status(row['order_id'], "Ready for Pickup")
                                st.success(f"Order {row['order_id']} marked ready")
                                st.experimental_rerun()
                    else:
                        st.info("No pending orders.")
                else:
                    st.info("No receipts yet.")
            except Exception as e:
                st.error(f"Could not load pending orders: {e}")

        elif choice == "Manage Menu":
            st.subheader("📋 Manage Menu (in-memory demo)")
            cat = st.selectbox("Category", list(menu_data.keys()))
            item = st.text_input("Item name")
            price = st.number_input("Price", min_value=0.0, step=1.0, value=10.0)
            if st.button("Add / Update Item"):
                if item:
                    menu_data[cat][item] = float(price)
                    st.success(f"{item} added/updated in {cat}")
            sel = st.selectbox("Select item to modify", ["(none)"] + [i for c in menu_data.values() for i in c.keys()])
            if sel != "(none)":
                if st.button("Mark Sold Out"):
                    st.session_state.sold_out.add(sel)
                    st.success(f"{sel} marked as Sold Out")
                if st.button("Mark Available"):
                    st.session_state.sold_out.discard(sel)
                    st.success(f"{sel} marked Available")
                if st.button("Remove Item"):
                    for c in menu_data:
                        menu_data[c].pop(sel, None)
                    st.success(f"{sel} removed")

        elif choice == "AI Assistant":
            st.subheader("🤖 Staff AI Assistant")
            staff_q = st.text_input("Ask Staff AI", key="staff_ai_q")
            if st.button("Ask Staff AI", key="staff_ai_btn"):
                # create context from latest sales & feedback
                try:
                    sales = load_receipts_df().head(50).to_dict()
                    fb = load_feedbacks_df().head(50).to_dict()
                    ctx = f"Sales: {sales}\nFeedback: {fb}"
                except Exception:
                    ctx = "DB context unavailable"
                with st.spinner("Asking AI..."):
                    st.info(run_ai(staff_q, ctx))

        elif choice == "Feedback Review":
            st.subheader("💬 Customer Feedback")
            try:
                fb_df = load_feedbacks_df()
                if not fb_df.empty:
                    st.dataframe(fb_df)
                else:
                    st.info("No feedback yet.")
            except Exception as e:
                st.error(f"Could not load feedbacks: {e}")

        elif choice == "Sales Report":
            st.subheader("📈 Sales Report")
            try:
                receipts_df = load_receipts_df()
                if not receipts_df.empty:
                    st.dataframe(receipts_df)
                    # small bar chart: sales by payment method
                    sums = receipts_df.groupby("payment_method")["total"].sum()
                    st.bar_chart(sums)
                else:
                    st.info("No sales yet.")
            except Exception as e:
                st.error(f"Could not load sales: {e}")

        # Logout bottom
        if st.button("Log Out", key="logout_staff"):
            st.session_state.page = "login"
            st.session_state.user = None





