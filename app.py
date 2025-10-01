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

# ---------------------------
# PAGE CONFIG
# ---------------------------
page_bg_img = f"""
<style>

.st-emotion-cache-1yiq2ps{{

        background-image: url("can.jpg");
        background-size: cover;
        background-repeat: no-repeat;
        background-attachment: fixed;
    
}}
</style>
"""
    st.markdown(page_bg_img, unsafe_allow_html=True)

# ---------------------------
# DB CONNECTION
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
# DB INITIALIZATION
# ---------------------------
def ensure_tables_and_columns():
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                username VARCHAR PRIMARY KEY,
                password VARCHAR,
                role VARCHAR,
                loyalty_points INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS feedbacks (
                id INT AUTOINCREMENT PRIMARY KEY,
                item VARCHAR,
                feedback VARCHAR,
                rating INT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS receipts (
                id INT AUTOINCREMENT PRIMARY KEY,
                order_id VARCHAR UNIQUE,
                user_id VARCHAR,
                items TEXT,
                total FLOAT,
                payment_method VARCHAR,
                details TEXT,
                pickup_time TIMESTAMP_NTZ,
                status VARCHAR,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    finally:
        try:
            cur.close()
            conn.commit()
            conn.close()
        except:
            pass

try:
    ensure_tables_and_columns()
except Exception as e:
    st.warning(f"⚠️ Could not ensure DB schema: {e}")

# ---------------------------
# AUTH HELPERS
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
    except:
        return False

def save_account(username: str, password: str, role: str = "Non-Staff"):
    conn = get_connection()
    cur = conn.cursor()
    hashed = hash_password(password)
    cur.execute("INSERT INTO accounts (username, password, role) VALUES (%s, %s, %s)", (username, hashed, role))
    conn.commit()
    cur.close(); conn.close()

def get_account(username: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT username, password, role, loyalty_points FROM accounts WHERE username=%s", (username,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if row:
        return {"username": row[0], "password": row[1], "role": row[2], "loyalty_points": int(row[3] or 0)}
    return None

def validate_account(username: str, password: str):
    acc = get_account(username)
    if acc and verify_password(acc["password"], password):
        return {"username": acc["username"], "role": acc["role"], "loyalty_points": acc["loyalty_points"]}
    return None

# ---------------------------
# SESSION STATE INIT
# ---------------------------
if "page" not in st.session_state:
    st.session_state.page = "login"
if "user" not in st.session_state:
    st.session_state.user = None

# ---------------------------
# LOGIN PAGE
# ---------------------------
if st.session_state.page == "login":
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown("<h2>☕ BiteHub — Login</h2>", unsafe_allow_html=True)

    username = st.text_input("Username", placeholder="Enter username")
    password = st.text_input("Password", type="password", placeholder="Enter password")

    col1, col2, col3 = st.columns([1,1,1])
    with col1:
        if st.button("Log In"):
            user = validate_account(username, password)
            if user:
                st.session_state.user = user
                st.session_state.page = "main"
                st.success(f"Welcome, {user['username']}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with col2:
        if st.button("Guest Account"):
            st.session_state.user = {"username": "Guest", "role": "Non-Staff", "loyalty_points": 0}
            st.session_state.page = "main"
            st.success("Signed in as Guest")
            st.rerun()

    with col3:
        if st.button("Create Account"):
            st.session_state.page = "signup"
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# SIGNUP PAGE
# ---------------------------
elif st.session_state.page == "signup":
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown("<h2>✍️ Create Account</h2>", unsafe_allow_html=True)

    new_username = st.text_input("New Username")
    new_pass = st.text_input("New Password", type="password")
    new_role = st.selectbox("Role", ["Non-Staff", "Staff"])

    if st.button("Register"):
        if get_account(new_username):
            st.error("Username already exists.")
        else:
            save_account(new_username, new_pass, new_role)
            st.success(f"✅ Account created for {new_username}. Please log in.")
            st.session_state.page = "login"
            st.rerun()

    if st.button("Back to Login"):
        st.session_state.page = "login"
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# MAIN PORTAL
# ---------------------------

elif st.session_state.page == "main":
    user = st.session_state.user or {"username": "Guest", "role": "Non-Staff", "loyalty_points",0}
    st.title(f"🏫 Welcome {user['username']} to BiteHub")
    st.write("Main portal goes here... (menus, orders, staff, etc.)")
    
    if "loyalty_points" not in user:
        user["loyalty_points"] = user.get("loyalty_points", 0)

    # Guest banner above AI assistant (only one message)
    if user["username"] == "Guest":
        st.warning("🔓 You're on a Guest session. Create an account to enjoy loyalty points, promos, and feedback posting.")

    st.title(f"🏫 Welcome {user['username']} to BiteHub")

    # COMMON: AI assistant area for all roles
    st.markdown("### 🤖 Canteen AI Assistant")
    q = st.text_input("Ask about menu, budget, feedback, or ordering:", key="ai_query_main")
    if st.button("Ask AI", key="ai_button_main"):
        extra = ""
        try:
            sales_df = load_receipts_df()
            feedback_df = load_feedbacks_df()
            extra = f"SALES_SUMMARY: {sales_df.head(10).to_dict() if not sales_df.empty else 'No sales'}\nFEEDBACK_SUMMARY: {feedback_df.head(10).to_dict() if not feedback_df.empty else 'No feedback'}"
        except Exception:
            extra = "DB context unavailable."
        with st.spinner("Asking AI..."):
            st.info(run_ai(q, extra))

    st.divider()

    # Non-Staff (includes Guest)
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
                            st.session_state.cart[item_name] = st.session_state.cart.get(item_name, 0) + qty
                            st.success(f"Added {qty} x {item_name}")

            # cart summary & checkout
            if st.session_state.cart:
                st.subheader("🛒 Your Cart")
                total = 0
                for it, qtt in st.session_state.cart.items():
                    price = next((p for cat in menu_data.values() for n,p in cat.items() if n == it), 0)
                    st.write(f"{it} x {qtt} = ₱{price*qtt}")
                    total += price*qtt

                st.write(f"**Subtotal: ₱{total}**")

                # loyalty points display for logged-in users
                user_points = 0
                if not is_guest:
                    try:
                        db_acc = get_account(user["username"])
                        user_points = db_acc.get("loyalty_points", 0) if db_acc else 0
                    except Exception:
                        user_points = st.session_state.loyalty_points
                    st.write(f"🔖 Points available: {user_points} pts (100 pts = ₱1)")

                # Tiered discounts (only for logged in users)
                discount = 0
                applied_points = 0
                if not is_guest:
                    tier_options = []
                    if user_points >= 500:
                        tier_options.append(("Use 500 pts → ₱10 discount", 10, 500))
                    if user_points >= 200:
                        tier_options.append(("Use 200 pts → ₱3 discount", 3, 200))
                    if user_points >= 100:
                        tier_options.append(("Use 100 pts → ₱1 discount", 1, 100))
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

                payment_method = st.radio("Payment Method", ["Cash", "Card", "E-Wallet"], key="pmethod")
                payment_details = ""
                if payment_method == "Card":
                    payment_details = st.text_input("Card Number (mock)", key="card_num")
                elif payment_method == "E-Wallet":
                    payment_details = st.selectbox("E-Wallet", ["GCash", "Maya", "QR Scan"], key="ewallet_type")

                if st.button("Place Order", key="place_order_nonstaff"):
                    order_id = f"ORD{random.randint(10000,99999)}"
                    items_str = ", ".join([f"{k}x{v}" for k,v in st.session_state.cart.items()])
                    pickup_dt = datetime.combine(pickup_date, pickup_time)
                    details = f"user:{user['username']}|notes:pickup scheduled"
                    try:
                        save_receipt(order_id, items_str, final_total, payment_method, details, pickup_time=pickup_dt, status="Pending", user_id=user['username'] if not is_guest else None)
                        # update loyalty points for non-guest
                        if not is_guest:
                            earned = int(total)
                            try:
                                update_loyalty_points(user['username'], earned)
                                if applied_points > 0:
                                    update_loyalty_points(user['username'], -applied_points)
                            except Exception:
                                # if DB unavailable, update session fallback
                                st.session_state.loyalty_points = st.session_state.loyalty_points + earned - applied_points
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
                rating = st.slider("Rate this item (1-5):", 1, 5, 3, key="fb_rating")
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
                # filter by user_id if not guest
                if not is_guest:
                    my = receipts_df[receipts_df["user_id"] == user["username"]]
                else:
                    my = receipts_df
                if not my.empty:
                    st.dataframe(my[["order_id","items","total","payment_method","pickup_time","status","timestamp"]])
                else:
                    st.info("No previous orders found.")
            else:
                st.info("No receipts recorded yet.")
        except Exception as e:
            st.error(f"Could not load receipts: {e}")

        # logout button
        if st.button("Log Out", key="logout_nonstaff"):
            st.session_state.page = "login"
            st.session_state.user = None

    # ---------------------------
    # STAFF PORTAL
    # ---------------------------
    elif user["role"] == "Staff":
        st.title("🛠️ BiteHub Staff Portal")
        choice = st.sidebar.radio("Staff Menu", ["Dashboard", "Pending Orders", "Manage Menu", "AI Assistant", "Feedback Review", "Sales Report"])

        if choice == "Dashboard":
            st.subheader("📊 Staff Dashboard")
            st.info("Overview: pending orders, quick sales, and recent feedback.")
            try:
                receipts = load_receipts_df()
                fb = load_feedbacks_df()
                st.metric("Total Orders", len(receipts))
                st.metric("Feedbacks", len(fb))
                pending = receipts[receipts["status"].str.lower() == "pending"] if not receipts.empty else pd.DataFrame()
                st.metric("Pending Orders", len(pending))
            except Exception as e:
                st.error(f"Could not load quick stats: {e}")

        elif choice == "Pending Orders":
            st.subheader("📦 Pending Orders")
            try:
                receipts_df = load_receipts_df()
                if not receipts_df.empty:
                    pending = receipts_df[receipts_df["status"].str.lower() == "pending"]
                    if not pending.empty:
                        for _, row in pending.iterrows():
                            st.write(f"Order {row['order_id']}: {row['items']} — ₱{row['total']} | Pickup: {row['pickup_time']} | By: {row['user_id']}")
                            if st.button(f"Mark Ready {row['order_id']}", key=f"ready_{row['order_id']}"):
                                set_receipt_status(row['order_id'], "Ready for Pickup")
                                st.success(f"Order {row['order_id']} marked ready")
                                st.rerun()
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
                    sums = receipts_df.groupby("payment_method")["total"].sum()
                    st.bar_chart(sums)
                else:
                    st.info("No sales yet.")
            except Exception as e:
                st.error(f"Could not load sales: {e}")

        # staff logout
        if st.button("Log Out", key="logout_staff"):
            st.session_state.page = "login"
            st.session_state.user = None





