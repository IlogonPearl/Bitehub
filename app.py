# app.py — Full compiled Canteen GenAI system (student/staff/guest)
import streamlit as st
import pandas as pd
import snowflake.connector
from groq import Groq
import random
from datetime import datetime, date, time
import matplotlib.pyplot as plt
import json

# -------------------------------------------------
#  Helper: Snowflake connection (uses st.secrets)
# -------------------------------------------------
def get_connection():
    return snowflake.connector.connect(
        user=st.secrets["SNOWFLAKE_USER"],
        password=st.secrets["SNOWFLAKE_PASSWORD"],
        account=st.secrets["SNOWFLAKE_ACCOUNT"],
        warehouse=st.secrets["SNOWFLAKE_WAREHOUSE"],
        database=st.secrets["SNOWFLAKE_DATABASE"],
        schema=st.secrets["SNOWFLAKE_SCHEMA"],
    )

# -------------------------------------------------
#  Save / Load helpers (feedback + receipts)
# -------------------------------------------------
def save_feedback(item, feedback, rating, username="Anon"):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO feedbacks (item, feedback, rating) VALUES (%s, %s, %s)",
        (item, f"{username}: {feedback}", rating),
    )
    conn.commit()
    cur.close()
    conn.close()

def load_feedbacks_df():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT item, feedback, rating, timestamp FROM feedbacks ORDER BY timestamp DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    if rows:
        return pd.DataFrame(rows, columns=["item","feedback","rating","timestamp"])
    else:
        return pd.DataFrame(columns=["item","feedback","rating","timestamp"])

# receipts.details will contain metadata string like:
# "user:{username}|pickup:{YYYY-MM-DD HH:MM}|status:pending"
def save_receipt(order_id, items, total, payment_method, details=""):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO receipts (order_id, items, total, payment_method, details) VALUES (%s, %s, %s, %s, %s)",
        (order_id, items, total, payment_method, details),
    )
    conn.commit()
    cur.close()
    conn.close()

def load_receipts_df():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT order_id, items, total, payment_method, details, timestamp FROM receipts ORDER BY timestamp DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    if rows:
        return pd.DataFrame(rows, columns=["order_id","items","total","payment_method","details","timestamp"])
    else:
        return pd.DataFrame(columns=["order_id","items","total","payment_method","details","timestamp"])

def update_receipt_status(order_id, new_status):
    # replace or add status in details string
    df = load_receipts_df()
    row = df[df["order_id"]==order_id]
    if row.empty:
        return False
    details = row.iloc[0]["details"] or ""
    # parse into dict
    parts = dict([p.split(":",1) for p in details.split("|") if ":" in p])
    parts["status"] = new_status
    new_details = "|".join([f"{k}:{v}" for k,v in parts.items()])
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE receipts SET details=%s WHERE order_id=%s", (new_details, order_id))
    conn.commit()
    cur.close()
    conn.close()
    return True

# -------------------------------------------------
#  Menu data (in-memory). Staff menu management persists nowhere here (you can persist in Snowflake)
#  We keep initial menu_data as requested.
# -------------------------------------------------
menu_data = {
    "Breakfast": {"Tapsilog": 70, "Longsilog": 65, "Hotdog Meal": 50, "Omelette": 45},
    "Lunch": {"Chicken Adobo": 90, "Pork Sinigang": 100, "Beef Caldereta": 120, "Rice": 15},
    "Snack": {"Burger": 50, "Fries": 30, "Siomai Rice": 60, "Spaghetti": 45},
    "Drinks": {"Soda": 20, "Iced Tea": 25, "Bottled Water": 15, "Coffee": 30},
    "Dessert": {"Halo-Halo": 65, "Leche Flan": 40, "Ice Cream": 35},
    "Dinner": {"Grilled Chicken": 95, "Sisig": 110, "Fried Bangus": 85, "Rice": 15},
}
# We'll track sold_out items in session_state['sold_out'] (staff can mark)
if "sold_out" not in st.session_state:
    st.session_state.sold_out = set()

# -------------------------------------------------
#  Groq client (AI)
# -------------------------------------------------
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# -------------------------------------------------
#  Session setup
# -------------------------------------------------
if "page" not in st.session_state:
    st.session_state.page = "login"
if "user" not in st.session_state:
    st.session_state.user = None
if "cart" not in st.session_state:
    st.session_state.cart = {}            # item -> qty
if "points" not in st.session_state:
    st.session_state.points = 0          # loyalty points in-session
if "notifications" not in st.session_state:
    st.session_state.notifications = []  # simple notification list

# -------------------------------------------------
#  CSS for buttons + centered login + background if file present
# -------------------------------------------------
st.set_page_config(page_title="BiteHub Canteen GenAI", layout="wide")

st.markdown("""
<style>
div.stButton > button {
    display: inline-block;
    margin: 8px;
    width: 170px;
    height: 44px;
    font-size: 15px;
    border-radius: 8px;
}
.center-buttons {
    text-align: center;
}
h1, h2, h3 { color: #222; }
</style>
""", unsafe_allow_html=True)

# Load background safely for Streamlit Cloud
image_path = "can.jpg"  # must be in the same directory as app.py
if os.path.exists(image_path):
    set_background(image_path)
else:
    st.warning("Background image not found. Please upload can.jpg in your project folder.")
    with open(_image_path, "rb") as f:
        import base64
        img_b64 = base64.b64encode(f.read()).decode()
    st.markdown(f"""
    <style>
    .stApp {{
        background-image: url("data:image/jpg;base64,{img_b64}");
        background-size: cover;
        background-position: center;
    }}
    </style>""", unsafe_allow_html=True)

# -------------------------------------------------
#  UI: LOGIN / SIGNUP / GUEST
# -------------------------------------------------
if st.session_state.page == "login":
    st.markdown("<h2>☕ BiteHub — Login</h2>", unsafe_allow_html=True)
    username = st.text_input("Username", placeholder="Enter username")
    password = st.text_input("Password", type="password", placeholder="Enter password")

    st.markdown('<div class="center-buttons">', unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,1,1])
    with col1:
        if st.button("Log In"):
            if username and password:
                # NOTE: currently not checking Snowflake users; this is local session login.
                # If you have a users table in Snowflake, replace this behavior with a query.
                st.session_state.user = {"username": username, "role": "Non-Staff"}
                st.session_state.page = "main"
                st.success(f"Welcome, {username}!")
            else:
                st.error("Please enter both username and password.")
    with col2:
        if st.button("Guest Account"):
            st.session_state.user = {"username": "Guest", "role": "Non-Staff"}
            st.session_state.page = "main"
            st.success("Signed in as Guest")
    with col3:
        if st.button("Create Account"):
            st.session_state.page = "signup"
    st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.page == "signup":
    st.markdown("<h2>✍️ Create Account</h2>", unsafe_allow_html=True)
    new_username = st.text_input("New Username")
    new_pass = st.text_input("New Password", type="password")
    new_role = st.selectbox("Role", ["Non-Staff", "Staff"])
    if st.button("Register"):
        # NOTE: registration not persisted to Snowflake here (you may add a users table and persist)
        st.success(f"Account created for {new_username} as {new_role}. Please log in.")
        st.session_state.page = "login"
    if st.button("Back to Login"):
        st.session_state.page = "login"

# -------------------------------------------------
#  MAIN APP — role-based
# -------------------------------------------------
elif st.session_state.page == "main":
    user = st.session_state.user or {"username":"Guest","role":"Non-Staff"}
    st.title(f"🏫 Welcome {user['username']} to BiteHub")

    # common top-level AI Assistant box (keeps the genai)
    def run_ai(question, extra_context=""):
        if not question:
            st.warning("Type a question for the AI.")
            return
        menu_text = ", ".join([f"{item} ({price})" for cat in menu_data.values() for item, price in cat.items()])
        context = f"MENU: {menu_text}\n{extra_context}"
        prompt = f"You are a friendly canteen assistant. Context: {context}\nUser question: {question}"
        try:
            resp = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role":"user","content":prompt}],
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"⚠️ AI unavailable: {e}"

    # Non-Staff / Student portal
    if user["role"] == "Non-Staff":
        # guest banner
        if user["username"] == "Guest":
            st.warning("🔓 Unlock rewards! Create an account to enjoy full benefits: Loyalty points, special discounts, and priority promos")

        # 1) AI Assistant
        st.markdown("### 🤖 Canteen AI Assistant")
        q = st.text_input("Ask about menu, budget, or feedback:")
        if st.button("Ask AI"):
            with st.spinner("Asking AI..."):
                ans = run_ai(q)
                st.success(ans)

        st.divider()

        # 2) Menu + Ordering (left) and Feedback (right)
        colA, colB = st.columns([2,1])

        with colA:
            st.subheader("📋 Menu")
            # collapsible categories with quantity input
            for cat, items in menu_data.items():
                with st.expander(cat, expanded=False):
                    for item_name, price in items.items():
                        soldout = item_name in st.session_state.sold_out
                        if soldout:
                            st.write(f"~~{item_name}~~ — Sold out")
                            continue
                        # each item has a small row: qty input + add button
                        cols = st.columns([1,1,1])
                        qty_key = f"qty_{cat}_{item_name}"
                        qty = cols[0].number_input(f"{item_name} (₱{price})", min_value=0, value=0, step=1, key=qty_key)
                        add_btn = cols[1].button("Add", key=f"add_{cat}_{item_name}")
                        if add_btn and qty>0:
                            # update cart
                            st.session_state.cart[item_name] = st.session_state.cart.get(item_name,0) + qty
                            st.success(f"Added {qty} x {item_name} to cart")
                        # show price
                        cols[2].write("")

            # show cart summary & checkout
            if st.session_state.cart:
                st.markdown("#### 🛒 Your Cart")
                total = 0
                for it, qtt in st.session_state.cart.items():
                    # find price
                    price = next((price for cat in menu_data.values() for name, price in cat.items() if name==it), 0)
                    st.write(f"{it} x{qtt} = ₱{price*qtt}")
                    total += price*qtt

                # loyalty points discount calculation
                st.write(f"**Subtotal: ₱{total}**")
                st.write(f"🔖 Points: {st.session_state.points} pts (100 pts = ₱1 discount)")
                max_discount_pesos = st.session_state.points // 100
                use_points = st.checkbox(f"Apply points for discount (max ₱{max_discount_pesos})")
                discount = 0
                if use_points and max_discount_pesos>0:
                    apply_amount = st.number_input("How many pesos to discount (integer):", min_value=0, max_value=max_discount_pesos, value=0)
                    discount = apply_amount
                final_total = max(0, total - discount)
                st.write(f"**Total after discount: ₱{final_total}**")

                # pickup date/time
                st.write("Choose pickup date and time:")
                pickup_date = st.date_input("Pickup date", value=date.today())
                pickup_time = st.time_input("Pickup time", value=datetime.now().time())

                payment_method = st.radio("Payment method:", ["Cash", "Card", "E-Wallet"])
                if payment_method == "Card":
                    card = st.text_input("Card number")
                    exp = st.text_input("Expiry (MM/YY)")
                elif payment_method == "E-Wallet":
                    wallet = st.selectbox("Wallet", ["GCash","Maya","QR Scan"])

                if st.button("Place Order"):
                    # create order id and details string
                    order_id = f"ORD{random.randint(10000,99999)}"
                    items_str = ", ".join([f"{k}x{v}" for k,v in st.session_state.cart.items()])
                    pickup_dt = f"{pickup_date.isoformat()} {pickup_time.strftime('%H:%M')}"
                    details = f"user:{user['username']}|pickup:{pickup_dt}|status:pending"
                    try:
                        save_receipt(order_id, items_str, final_total, payment_method, details)
                        # earn points: 1 point per ₱1 spent (you can change)
                        earned = int(final_total)
                        st.session_state.points += earned
                        # if apply points, deduct used points
                        if use_points and discount>0:
                            st.session_state.points -= discount*100
                        st.success(f"✅ Order placed: {order_id}. Earned {earned} pts. Current pts: {st.session_state.points}")
                        # notification stub for student
                        st.session_state.notifications.append(f"Order {order_id} placed for pickup {pickup_dt}")
                        st.session_state.cart = {}  # clear cart
                    except Exception as e:
                        st.error(f"Error saving order: {e}")

        with colB:
            st.subheader("✍️ Feedback (anonymous shown)")
            fb_item = st.selectbox("Item for feedback", ["(select)"] + [i for cat in menu_data.values() for i in cat.keys()])
            fb_rating = st.slider("Rate (1-5)", 1,5,3)
            fb_text = st.text_area("Feedback text")
            if st.button("Submit Feedback"):
                if fb_item and fb_text:
                    try:
                        save_feedback(fb_item, fb_text, fb_rating, username=user["username"])
                        st.success("✅ Feedback submitted!")
                    except Exception as e:
                        st.error(f"Failed to save feedback: {e}")
                else:
                    st.warning("Choose item and write feedback.")

            st.markdown("---")
            st.subheader("🔔 Notifications")
            if st.session_state.notifications:
                for n in st.session_state.notifications[-5:]:
                    st.info(n)
            else:
                st.info("No notifications yet.")

        st.divider()

        # quick view of recent receipts (own orders)
        st.subheader("📦 Your Recent Orders")
        try:
            receipts = load_receipts_df()
            if not receipts.empty:
                # filter by user
                def get_user_from_details(details):
                    if not details: return ""
                    parts = dict([p.split(":",1) for p in details.split("|") if ":" in p])
                    return parts.get("user","")
                receipts["user"] = receipts["details"].fillna("").apply(get_user_from_details)
                my = receipts[receipts["user"]==user["username"]]
                if not my.empty:
                    st.dataframe(my[["order_id","items","total","details","timestamp"]])
                else:
                    st.info("No previous orders found.")
            else:
                st.info("No receipts recorded yet.")
        except Exception as e:
            st.error(f"Could not load receipts: {e}")

        # logout button at bottom
        st.markdown("---")
        if st.button("Log Out"):
            st.session_state.page = "login"
            st.session_state.user = None

    # Staff portal
    elif user["role"] == "Staff":
        st.success("👨‍🍳 Staff Portal Access Granted")

        # AI assistant for staff: can analyze sales & feedbacks (uses Groq)
        st.subheader("🤖 Staff AI Assistant")
        staff_q = st.text_input("Ask AI (e.g. suggest dishes based on recent feedback/sales)")
        if st.button("Ask Staff AI"):
            # prepare context
            try:
                sales_df = load_receipts_df()
                fb_df = load_feedbacks_df()
                sales_summary = sales_df.head(50).to_dict() if not sales_df.empty else "No sales"
                fb_summary = fb_df.head(50).to_dict() if not fb_df.empty else "No feedback"
                extra_context = f"Sales: {sales_summary}\nFeedback: {fb_summary}"
                with st.spinner("Running staff AI..."):
                    ans = run_ai(staff_q, extra_context=extra_context)
                    st.success(ans)
            except Exception as e:
                st.error(f"AI failed: {e}")

        st.divider()

        # Menu management
        st.subheader("📋 Manage Menu")
        m_col1, m_col2 = st.columns(2)
        with m_col1:
            new_cat = st.selectbox("Category to edit/add", list(menu_data.keys()))
            new_item = st.text_input("Item name")
            new_price = st.number_input("Price", min_value=0.0, value=10.0)
            if st.button("Add / Update Item"):
                # add to menu_data in-memory
                if new_cat not in menu_data:
                    menu_data[new_cat] = {}
                menu_data[new_cat][new_item] = new_price
                st.success(f"Added/Updated {new_item} in {new_cat} at ₱{new_price}")
        with m_col2:
            # list items to mark sold out or remove
            all_items = [i for cat in menu_data.values() for i in cat.keys()]
            sel_item = st.selectbox("Select item to mark sold-out / remove", ["(none)"]+all_items)
            if sel_item != "(none)":
                if st.button("Mark Sold Out"):
                    st.session_state.sold_out.add(sel_item)
                    st.success(f"{sel_item} marked sold out.")
                if st.button("Mark Available"):
                    st.session_state.sold_out.discard(sel_item)
                    st.success(f"{sel_item} marked available.")
                if st.button("Remove Item"):
                    # remove globally
                    for cat in list(menu_data.keys()):
                        if sel_item in menu_data[cat]:
                            del menu_data[cat][sel_item]
                    st.success(f"{sel_item} removed from menu.")

        st.divider()

        # Feedbacks list
        st.subheader("📝 Feedbacks")
        try:
            fb_df = load_feedbacks_df()
            if not fb_df.empty:
                st.dataframe(fb_df)
            else:
                st.info("No feedback yet.")
        except Exception as e:
            st.error(f"Could not load feedbacks: {e}")

        st.divider()

        # Pending orders + mark ready
        st.subheader("📦 Pending Orders")
        try:
            receipts = load_receipts_df()
            if not receipts.empty:
                # parse details and show useful columns
                def parse_details(details):
                    parts = dict([p.split(":",1) for p in (details or "").split("|") if ":" in p])
                    return parts.get("user",""), parts.get("pickup",""), parts.get("status","pending")
                receipts[["user","pickup","status"]] = receipts["details"].fillna("").apply(
                    lambda d: pd.Series(parse_details(d))
                )
                pending = receipts[receipts["status"]=="pending"]
                if not pending.empty:
                    st.dataframe(pending[["order_id","user","items","total","pickup","timestamp"]])
                    order_to_update = st.text_input("Order ID to mark ready")
                    if st.button("Mark Ready"):
                        if order_to_update:
                            ok = update_receipt_status(order_to_update, "ready")
                            if ok:
                                st.success(f"Marked {order_to_update} ready. A notification will be available to user.")
                                # For demo: push notification to session (can't reach user's session in different browser)
                                st.session_state.notifications.append(f"Order {order_to_update} is ready.")
                            else:
                                st.error("Order ID not found.")
                else:
                    st.info("No pending orders.")
            else:
                st.info("No receipts recorded yet.")
        except Exception as e:
            st.error(f"Could not load receipts: {e}")

        st.divider()

        # Sales report by category (compact)
        st.subheader("📊 Sales Report (by category)")
        try:
            receipts = load_receipts_df()
            if not receipts.empty:
                # expand 'items' strings like "Burgerx2, Ricex1" into rows
                rows = []
                for _, r in receipts.iterrows():
                    items_part = r["items"]
                    for ent in items_part.split(","):
                        ent = ent.strip()
                        if not ent: continue
                        if "x" in ent:
                            nm, q = ent.split("x")
                            q = int(q)
                        else:
                            nm, q = ent, 1
                        nm = nm.strip()
                        # map item to category
                        cat = next((catname for catname,d in menu_data.items() if nm in d), "Other")
                        rows.append({"category":cat, "qty": q, "total": float(r["total"])})
                if rows:
                    df = pd.DataFrame(rows)
                    cat_sales = df.groupby("category")["qty"].sum().sort_values(ascending=False)
                    fig, ax = plt.subplots(figsize=(5,2.5))
                    cat_sales.plot(kind="bar", ax=ax)
                    ax.set_ylabel("Qty sold")
                    st.pyplot(fig)
                else:
                    st.info("No itemized sales to show.")
            else:
                st.info("No receipts recorded yet.")
        except Exception as e:
            st.error(f"Sales report error: {e}")

        st.markdown("---")
        if st.button("Log Out"):
            st.session_state.page = "login"
            st.session_state.user = None

    else:
        st.error("Unknown role. Please log out and log in again.")

# end of app

