import os 
import base64 
import streamlit as st 
import pandas as pd 
import snowflake.connector 
from groq import Groq 
import random 
from datetime import datetime, date, time 
import matplotlib.pyplot as plt

-------------------------------------------------

Helper: Snowflake connection (uses st.secrets)

-------------------------------------------------

def get_connection(): return snowflake.connector.connect( user=st.secrets["SNOWFLAKE_USER"], password=st.secrets["SNOWFLAKE_PASSWORD"], account=st.secrets["SNOWFLAKE_ACCOUNT"], warehouse=st.secrets["SNOWFLAKE_WAREHOUSE"], database=st.secrets["SNOWFLAKE_DATABASE"], schema=st.secrets["SNOWFLAKE_SCHEMA"], )

-------------------------------------------------

Save / Load helpers (feedback + receipts)

-------------------------------------------------

def save_feedback(item, feedback, rating, username="Anon"): conn = get_connection() cur = conn.cursor() cur.execute( "INSERT INTO feedbacks (item, feedback, rating) VALUES (%s, %s, %s)", (item, f"{username}: {feedback}", rating), ) conn.commit() cur.close() conn.close()

def load_feedbacks_df(): conn = get_connection() cur = conn.cursor() cur.execute("SELECT item, feedback, rating, timestamp FROM feedbacks ORDER BY timestamp DESC") rows = cur.fetchall() cur.close() conn.close() if rows: return pd.DataFrame(rows, columns=["item","feedback","rating","timestamp"]) else: return pd.DataFrame(columns=["item","feedback","rating","timestamp"])

def save_receipt(order_id, items, total, payment_method, details=""): conn = get_connection() cur = conn.cursor() cur.execute( "INSERT INTO receipts (order_id, items, total, payment_method, details) VALUES (%s, %s, %s, %s, %s)", (order_id, items, total, payment_method, details), ) conn.commit() cur.close() conn.close()

def load_receipts_df(): conn = get_connection() cur = conn.cursor() cur.execute("SELECT order_id, items, total, payment_method, details, timestamp FROM receipts ORDER BY timestamp DESC") rows = cur.fetchall() cur.close() conn.close() if rows: return pd.DataFrame(rows, columns=["order_id","items","total","payment_method","details","timestamp"]) else: return pd.DataFrame(columns=["order_id","items","total","payment_method","details","timestamp"])

def update_receipt_status(order_id, new_status): df = load_receipts_df() row = df[df["order_id"]==order_id] if row.empty: return False details = row.iloc[0]["details"] or "" parts = dict([p.split(":",1) for p in details.split("|") if ":" in p]) parts["status"] = new_status new_details = "|".join([f"{k}:{v}" for k,v in parts.items()]) conn = get_connection() cur = conn.cursor() cur.execute("UPDATE receipts SET details=%s WHERE order_id=%s", (new_details, order_id)) conn.commit() cur.close() conn.close() return True

-------------------------------------------------

Menu data (in-memory)

-------------------------------------------------

menu_data = { "Breakfast": {"Tapsilog": 70, "Longsilog": 65, "Hotdog Meal": 50, "Omelette": 45}, "Lunch": {"Chicken Adobo": 90, "Pork Sinigang": 100, "Beef Caldereta": 120, "Rice": 15}, "Snack": {"Burger": 50, "Fries": 30, "Siomai Rice": 60, "Spaghetti": 45}, "Drinks": {"Soda": 20, "Iced Tea": 25, "Bottled Water": 15, "Coffee": 30}, "Dessert": {"Halo-Halo": 65, "Leche Flan": 40, "Ice Cream": 35}, "Dinner": {"Grilled Chicken": 95, "Sisig": 110, "Fried Bangus": 85, "Rice": 15}, } if "sold_out" not in st.session_state: st.session_state.sold_out = set()

-------------------------------------------------

Groq client (AI)

-------------------------------------------------

client = Groq(api_key=st.secrets["GROQ_API_KEY"])

-------------------------------------------------

Session setup

-------------------------------------------------

if "page" not in st.session_state: st.session_state.page = "login" if "user" not in st.session_state: st.session_state.user = None if "cart" not in st.session_state: st.session_state.cart = {} if "points" not in st.session_state: st.session_state.points = 0 if "notifications" not in st.session_state: st.session_state.notifications = []

-------------------------------------------------

CSS + Background

-------------------------------------------------

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
</style>""", unsafe_allow_html=True)

def set_background(image_path): try: with open(image_path, "rb") as f: data = f.read() img_b64 = base64.b64encode(data).decode() css = f""" <style> .stApp {{ background-image: url("data:image/jpg;base64,{img_b64}"); background-size: cover; background-position: center; }} </style> """ st.markdown(css, unsafe_allow_html=True) except Exception as e: st.error(f"Could not load background: {e}")

if os.path.exists("can.jpg"): set_background("can.jpg")

-------------------------------------------------

LOGIN / SIGNUP / GUEST

-------------------------------------------------

if st.session_state.page == "login": st.markdown("<h2>☕ BiteHub — Login</h2>", unsafe_allow_html=True) username = st.text_input("Username", placeholder="Enter username") password = st.text_input("Password", type="password", placeholder="Enter password")

st.markdown('<div class="center-buttons">', unsafe_allow_html=True)
col1, col2, col3 = st.columns([1,1,1])
with col1:
    if st.button("Log In"):
        if username and password:
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

elif st.session_state.page == "signup": st.markdown("<h2>✍️ Create Account</h2>", unsafe_allow_html=True) new_username = st.text_input("New Username") new_pass = st.text_input("New Password", type="password") new_role = st.selectbox("Role", ["Non-Staff", "Staff"]) if st.button("Register"): st.success(f"Account created for {new_username} as {new_role}. Please log in.") st.session_state.page = "login" if st.button("Back to Login"): st.session_state.page = "login"

-------------------------------------------------

MAIN APP (Students + Staff)

-------------------------------------------------

elif st.session_state.page == "main": user = st.session_state.user or {"username":"Guest","role":"Non-Staff"} st.title(f"🏫 Welcome {user['username']} to BiteHub")

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

# Non-Staff portal
if user["role"] == "Non-Staff":
    if user["username"] == "Guest":
        st.warning("🔓 Unlock rewards! Create an account to enjoy Loyalty points, discounts, and promos.")

    st.subheader("🤖 Canteen AI Assistant")
    q = st.text_input("Ask about menu, budget, or feedback:")
    if st.button("Ask AI"):
        st.success(run_ai(q))

    st.divider()
    colA, colB = st.columns([2,1])

    # Menu + Ordering
    with colA:
        st.subheader("📋 Menu")
        for cat, items in menu_data.items():
            with st.expander(cat):
                for item_name, price in items.items():
                    if item_name in st.session_state.sold_out:
                        st.write(f"~~{item_name}~~ — Sold out")
                        continue
                    cols = st.columns([1,1,1])
                    qty = cols[0].number_input(f"{item_name} (₱{price})", 0, 10, 0, key=f"qty_{cat}_{item_name}")
                    if cols[1].button("Add", key=f"add_{cat}_{item_name}") and qty>0:
                        st.session_state.cart[item_name] = st.session_state.cart.get(item_name,0) + qty
                        st.success(f"Added {qty} x {item_name}")

        if st.session_state.cart:
            st.subheader("🛒 Your Cart")
            total = sum(
                qty * next(price for cat in menu_data.values() for name, price in cat.items() if name==item)
                for item, qty in st.session_state.cart.items()
            )
            st.write(f"Subtotal: ₱{total}")
            st.write(f"Points: {st.session_state.points}")
            discount = 0
            max_disc = st.session_state.points // 100
            if st.checkbox(f"Use points (max ₱{max_disc})") and max_disc>0:
                discount = st.number_input("Discount (₱):", 0, max_disc, 0)
            final_total = max(0, total-discount)
            st.write(f"Total after discount: ₱{final_total}")

            pickup_date = st.date_input("Pickup date", value=date.today())
            pickup_time = st.time_input("Pickup time", value=datetime.now().time())
            pay = st.radio("Payment", ["Cash","Card","E-Wallet"])

            if st.button("Place Order"):
                oid = f"ORD{random.randint(10000,99999)}"
                items_str = ", ".join([f"{k}x{v}" for k,v in st.session_state.cart.items()])
                details = f"user:{user['username']}|pickup:{pickup_date} {pickup_time}|status:pending"
                save_receipt(oid, items_str, final_total, pay, details)
                st.session_state.points += final_total
                if discount>0:
                    st.session_state.points -= discount*100
                st.session_state.notifications.append(f"Order {oid} placed!")
                st.session_state.cart = {}
                st.success(f"✅ Order {oid} placed!")

    # Feedback + Notifications
    with colB:
        st.subheader("✍️ Feedback")
        fb_item = st.selectbox("Item", ["(select)"]+[i for cat in menu_data.values() for i in cat.keys()])
        fb_text = st.text_area("Feedback")
        fb_rating = st.slider("Rating", 1,5,3)
        if st.button("Submit Feedback") and fb_item != "(select)":
            save_feedback(fb_item, fb_text, fb_rating, user["username"])
            st.success("Feedback submitted!")

        st.subheader("🔔 Notifications")
        for n in st.session_state.notifications[-5:]:
            st.info(n)

    st.divider()
    st.subheader("📦 Your Orders")
    rec = load_receipts_df()
    if not rec.empty:
        rec["user"] = rec["details"].fillna("").apply(lambda d: dict([p.split(":",1) for p in d.split("|") if ":" in p]).get("user",""))
        mine = rec[rec["user"]==user["username"]]
        st.dataframe(mine)

    if st.button("Log Out"):
        st.session_state.page = "login"
        st.session_state.user = None

# Staff Portal
elif user["role"] == "Staff":
    st.success("👨‍🍳 Staff Portal")

    st.subheader("🤖 Staff AI Assistant")
    sq = st.text_input("Ask AI")
    if st.button("Ask Staff AI"):
        sales = load_receipts_df().head(20).to_dict()
        fb = load_feedbacks_df().head(20).to_dict()
        st.success(run_ai(sq, f"Sales: {sales}\nFeedback: {fb}"))

    st.subheader("📋 Manage Menu")
    cat = st.selectbox("Category", list(menu_data.keys()))
    item = st.text_input("Item")
    price = st.number_input("Price", 0.0, 999.0, 10.0)
    if st.button("Add/Update"):
        menu_data[cat][item] = price
        st.success(f"{item} updated in {cat}")

    sel = st.selectbox("Select Item", ["(none)"]+[i for c in menu_data.values() for i in c.keys()])
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

    st.subheader("📊 Sales")
    rec = load_receipts_df()
    st.dataframe(rec)

    if st.button("Log Out"):
        st.session_state.page = "login"
        st.session_state.user = None



