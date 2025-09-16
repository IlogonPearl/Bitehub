import os import base64 import streamlit as st import pandas as pd import snowflake.connector from groq import Groq import random from datetime import datetime, date

-------------------------------------------------

Snowflake connection

-------------------------------------------------

def get_connection(): return snowflake.connector.connect( user=st.secrets["SNOWFLAKE_USER"], password=st.secrets["SNOWFLAKE_PASSWORD"], account=st.secrets["SNOWFLAKE_ACCOUNT"], warehouse=st.secrets["SNOWFLAKE_WAREHOUSE"], database=st.secrets["SNOWFLAKE_DATABASE"], schema=st.secrets["SNOWFLAKE_SCHEMA"], )

-------------------------------------------------

Feedback + Receipts helpers

-------------------------------------------------

def save_feedback(item, feedback, rating, username="Anon"): conn = get_connection() cur = conn.cursor() cur.execute( "INSERT INTO feedbacks (item, feedback, rating) VALUES (%s, %s, %s)", (item, f"{username}: {feedback}", rating), ) conn.commit() cur.close() conn.close()

def load_feedbacks_df(): conn = get_connection() cur = conn.cursor() cur.execute("SELECT item, feedback, rating, timestamp FROM feedbacks ORDER BY timestamp DESC") rows = cur.fetchall() cur.close() conn.close() if rows: return pd.DataFrame(rows, columns=["item","feedback","rating","timestamp"]) return pd.DataFrame(columns=["item","feedback","rating","timestamp"])

def save_receipt(order_id, items, total, payment_method, details=""): conn = get_connection() cur = conn.cursor() cur.execute( "INSERT INTO receipts (order_id, items, total, payment_method, details) VALUES (%s, %s, %s, %s, %s)", (order_id, items, total, payment_method, details), ) conn.commit() cur.close() conn.close()

def load_receipts_df(): conn = get_connection() cur = conn.cursor() cur.execute("SELECT order_id, items, total, payment_method, details, timestamp FROM receipts ORDER BY timestamp DESC") rows = cur.fetchall() cur.close() conn.close() if rows: return pd.DataFrame(rows, columns=["order_id","items","total","payment_method","details","timestamp"]) return pd.DataFrame(columns=["order_id","items","total","payment_method","details","timestamp"])

-------------------------------------------------

Menu data

-------------------------------------------------

menu_data = { "Breakfast": {"Tapsilog": 70, "Longsilog": 65, "Hotdog Meal": 50, "Omelette": 45}, "Lunch": {"Chicken Adobo": 90, "Pork Sinigang": 100, "Beef Caldereta": 120, "Rice": 15}, "Snack": {"Burger": 50, "Fries": 30, "Siomai Rice": 60, "Spaghetti": 45}, "Drinks": {"Soda": 20, "Iced Tea": 25, "Bottled Water": 15, "Coffee": 30}, "Dessert": {"Halo-Halo": 65, "Leche Flan": 40, "Ice Cream": 35}, "Dinner": {"Grilled Chicken": 95, "Sisig": 110, "Fried Bangus": 85, "Rice": 15}, }

if "sold_out" not in st.session_state: st.session_state.sold_out = set()

-------------------------------------------------

Groq client

-------------------------------------------------

client = Groq(api_key=st.secrets["GROQ_API_KEY"])

-------------------------------------------------

Session setup

-------------------------------------------------

if "page" not in st.session_state: st.session_state.page = "login" if "user" not in st.session_state: st.session_state.user = None if "cart" not in st.session_state: st.session_state.cart = {} if "points" not in st.session_state: st.session_state.points = 0 if "notifications" not in st.session_state: st.session_state.notifications = []

-------------------------------------------------

Config + CSS + Background

-------------------------------------------------

st.set_page_config(page_title="BiteHub Canteen GenAI", layout="wide")

st.markdown("""

<style>
div.stButton > button {
    margin: 8px;
    width: 170px;
    height: 44px;
    font-size: 15px;
    border-radius: 8px;
}
h1, h2, h3 { color: #222; }
</style>""", unsafe_allow_html=True)

def set_background(image_path): try: with open(image_path, "rb") as f: data = f.read() img_b64 = base64.b64encode(data).decode() css = f""" <style> .stApp {{ background-image: url("data:image/jpg;base64,{img_b64}"); background-size: cover; background-position: center; }} </style> """ st.markdown(css, unsafe_allow_html=True) except Exception: st.warning("Background image not found (can.jpg)")

if os.path.exists("can.jpg"): set_background("can.jpg")

-------------------------------------------------

Pages: Login / Signup / Guest / Main

-------------------------------------------------

if st.session_state.page == "login": st.markdown("<h2>☕ BiteHub — Login</h2>", unsafe_allow_html=True) username = st.text_input("Username", placeholder="Enter username", key="login_username") password = st.text_input("Password", type="password", placeholder="Enter password", key="login_password")

col1, col2, col3 = st.columns(3)
with col1:
    if st.button("Log In", key="btn_login"):
        if username and password:
            st.session_state.user = {"username": username, "role": "Non-Staff"}
            st.session_state.page = "main"
        else:
            st.error("Please enter both username and password.")
with col2:
    if st.button("Guest Account", key="btn_guest"):
        st.session_state.user = {"username": "Guest", "role": "Non-Staff"}
        st.session_state.page = "main"
with col3:
    if st.button("Create Account", key="btn_create_acc"):
        st.session_state.page = "signup"

elif st.session_state.page == "signup": st.markdown("<h2>✍️ Create Account</h2>", unsafe_allow_html=True) new_username = st.text_input("New Username", key="signup_username") new_pass = st.text_input("New Password", type="password", key="signup_password") new_role = st.selectbox("Role", ["Non-Staff", "Staff"], key="signup_role")

if st.button("Register", key="btn_register"):
    st.success(f"Account created for {new_username} as {new_role}. Please log in.")
    st.session_state.page = "login"
if st.button("Back to Login", key="btn_back_login"):
    st.session_state.page = "login"

elif st.session_state.page == "main": user = st.session_state.user or {"username":"Guest","role":"Non-Staff"} st.title(f"🏫 Welcome {user['username']} to BiteHub")

def run_ai(question, extra_context=""):
    if not question:
        return "Please type a question."
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

if user["role"] == "Non-Staff":
    if user["username"] == "Guest":
        st.warning("🔓 Unlock rewards! Create an account to enjoy loyalty points and promos.")

    st.subheader("🤖 Canteen AI Assistant")
    q = st.text_input("Ask about menu, budget, or feedback:", key="ask_ai")
    if st.button("Ask AI", key="btn_ask_ai"):
        st.info(run_ai(q))

    st.subheader("📋 Menu")
    for cat, items in menu_data.items():
        with st.expander(cat):
            for item_name, price in items.items():
                if item_name in st.session_state.sold_out:
                    st.write(f"~~{item_name}~~ — Sold out")
                    continue
                cols = st.columns([1,1,1])
                qty = cols[0].number_input(f"{item_name} (₱{price})", min_value=0, value=0, step=1, key=f"qty_{cat}_{item_name}")
                if cols[1].button("Add", key=f"add_{cat}_{item_name}") and qty>0:
                    st.session_state.cart[item_name] = st.session_state.cart.get(item_name,0) + qty
                    st.success(f"Added {qty} x {item_name} to cart")

    if st.session_state.cart:
        st.subheader("🛒 Your Cart")
        total = 0
        for it, qtt in st.session_state.cart.items():
            price = next((p for cat in menu_data.values() for n, p in cat.items() if n==it), 0)
            st.write(f"{it} x{qtt} = ₱{price*qtt}")
            total += price*qtt

        st.write(f"Subtotal: ₱{total}")
        st.write(f"Points: {st.session_state.points}")

        max_discount_pesos = st.session_state.points // 100
        use_points = st.checkbox(f"Apply points (max ₱{max_discount_pesos})", key="apply_points")
        discount = 0
        if use_points and max_discount_pesos>0:
            discount = st.number_input("How many pesos to discount:", min_value=0, max_value=max_discount_pesos, value=0, key="discount_input")

        final_total = max(0, total - discount)
        st.write(f"Total after discount: ₱{final_total}")

        pickup_date = st.date_input("Pickup date", value=date.today(), key="pickup_date")
        pickup_time = st.time_input("Pickup time", value=datetime.now().time(), key="pickup_time")

        payment_method = st.radio("Payment method", ["Cash", "Card", "E-Wallet"], key="pay_method")

        if st.button("Place Order", key="btn_place_order"):
            order_id = f"ORD{random.randint(10000,99999)}"
            items_str = ", ".join([f"{k}x{v}" for k,v in st.session_state.cart.items()])
            pickup_dt = f"{pickup_date.isoformat()} {pickup_time.strftime('%H:%M')}"
            details = f"user:{user['username']}|pickup:{pickup_dt}|status:pending"
            try:
                save_receipt(order_id, items_str, final_total, payment_method, details)
                st.session_state.points += int(final_total)
                if use_points and discount>0:
                    st.session_state.points -= discount*100
                st.success(f"✅ Order placed: {order_id}")
                st.session_state.cart = {}
            except Exception as e:
                st.error(f"Error saving order: {e}")

    st.subheader("✍️ Feedback")
    fb_item = st.selectbox("Item", ["(select)"]+[i for cat in menu_data.values() for i in cat.keys()], key="fb_item")
    fb_rating = st.slider("Rate (1-5)", 1,5,3, key="fb_rate")
    fb_text = st.text_area("Feedback text", key="fb_text")
    if st.button("Submit Feedback", key="btn_fb"):
        if fb_item != "(select)" and fb_text:
            try:
                save_feedback(fb_item, fb_text, fb_rating, username=user["username"])
                st.success("Feedback submitted!")
            except Exception as e:
                st.error(f"Failed to save feedback: {e}")

    st.subheader("📦 Your Orders")
    try:
        df = load_receipts_df()
        if not df.empty:
            def get_user(details):
                parts = dict([p.split(":",1) for p in details.split("|") if ":" in p])
                return parts.get("user","")
            df["user"] = df["details"].fillna("").apply(get_user)
            my = df[df["user"]==user["username"]]
            if not my.empty:
                st.dataframe(my)
            else:
                st.info("No orders yet.")
        else:
            st.info("No receipts recorded.")
    except Exception as e:
        st.error(f"Error loading receipts: {e}")

    if st.button("Log Out", key="btn_logout"):
        st.session_state.page = "login"
        st.session_state.user = None

elif user["role"] == "Staff":
    st.success("👨‍🍳 Staff Portal")

    st.subheader("🤖 Staff AI Assistant")
    staff_q = st.text_input("Ask AI:", key="staff_ai")
    if st.button("Ask Staff AI", key="btn_staff_ai"):
        sales_df = load_receipts_df()
        fb_df = load_feedbacks_df()
        extra_context = f"Sales: {sales_df.to_dict() if not sales_df.empty else 'No sales'}\nFeedback: {fb_df.to_dict() if not fb_df.empty else 'No feedback'}"
        st.info(run_ai(staff_q, extra_context=extra_context))

    st.subheader("📝 Feedbacks")
    fb_df = load_feedbacks_df()
    if not fb_df.empty:
        st.dataframe(fb_df)
    else:
        st.info("No feedback yet.")

