import streamlit as st
import os
import base64
import pandas as pd
import snowflake.connector
from groq import Groq
import random
from datetime import datetime
import matplotlib.pyplot as plt

# =========================================================
# BACKGROUND IMAGE
# =========================================================
def set_background(image_file):
    with open(image_file, "rb") as f:
        data = f.read()
    encoded = base64.b64encode(data).decode()
    css = f"""
    <style>
    .stApp {{
        background-image: url("data:image/jpg;base64,{encoded}");
        background-size: cover;
        background-position: center;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# ✅ load background
image_path = os.path.join(os.path.dirname(__file__), "can.jpg")
if os.path.exists(image_path):
    set_background(image_path)

# =========================================================
# SNOWFLAKE CONNECTION
# =========================================================
def get_connection():
    return snowflake.connector.connect(
        user=st.secrets["SNOWFLAKE_USER"],
        password=st.secrets["SNOWFLAKE_PASSWORD"],
        account=st.secrets["SNOWFLAKE_ACCOUNT"],
        warehouse=st.secrets["SNOWFLAKE_WAREHOUSE"],
        database=st.secrets["SNOWFLAKE_DATABASE"],
        schema=st.secrets["SNOWFLAKE_SCHEMA"],
    )

# ----------------- SAVE FEEDBACK -----------------
def save_feedback(item, feedback, rating):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO feedbacks (item, feedback, rating) VALUES (%s, %s, %s)",
        (item, feedback, rating),
    )
    conn.commit()
    cur.close()
    conn.close()

# ----------------- LOAD FEEDBACK -----------------
def load_feedbacks():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT item, feedback, rating, timestamp FROM feedbacks ORDER BY timestamp DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return pd.DataFrame(rows, columns=["item", "feedback", "rating", "timestamp"]) \
        if rows else pd.DataFrame(columns=["item", "feedback", "rating", "timestamp"])

# ----------------- SAVE RECEIPT -----------------
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

# ----------------- LOAD SALES -----------------
def load_sales():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT items, total, payment_method, timestamp FROM receipts")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return pd.DataFrame(rows, columns=["items", "total", "payment_method", "timestamp"]) \
        if rows else pd.DataFrame(columns=["items", "total", "payment_method", "timestamp"])

# =========================================================
# MENU DATA
# =========================================================
menu_data = {
    "Breakfast": {"Tapsilog": 70, "Longsilog": 65, "Hotdog Meal": 50, "Omelette": 45},
    "Lunch": {"Chicken Adobo": 90, "Pork Sinigang": 100, "Beef Caldereta": 120, "Rice": 15},
    "Snack": {"Burger": 50, "Fries": 30, "Siomai Rice": 60, "Spaghetti": 45},
    "Drinks": {"Soda": 20, "Iced Tea": 25, "Bottled Water": 15, "Coffee": 30},
    "Dessert": {"Halo-Halo": 65, "Leche Flan": 40, "Ice Cream": 35},
    "Dinner": {"Grilled Chicken": 95, "Sisig": 110, "Fried Bangus": 85, "Rice": 15},
}

# =========================================================
# GROQ AI CLIENT
# =========================================================
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# =========================================================

# ====================================
# CSS for styling
# ====================================
st.markdown("""
    <style>
    div.stButton > button {
        display: inline-block;
        margin: 10px;         /* space between buttons */
        width: 180px;
        height: 50px;
        font-size: 18px;
        border-radius: 8px;
    }
    .center-buttons {
        text-align: center;
    }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# LOGIN & SIGNUP SYSTEM
# =========================================================
if "page" not in st.session_state:
    st.session_state.page = "login"

# =========================
# =========================
import streamlit as st

st.set_page_config(page_title="Cafe Login", layout="centered")

# ====================================
# Login form UI
# ====================================
st.markdown("<div class='login-card'>", unsafe_allow_html=True)
st.markdown("<h2>☕ Welcome Back</h2>", unsafe_allow_html=True)



email = st.text_input("Email", placeholder="Enter your email")
password = st.text_input("Password", type="password", placeholder="Enter your password")
#CSS styling
st.markdown("""
<style>
            div.stButton > button {
                display: inline-block;
                margin: 10px;         /* space between buttons */
                width: 180px;
                height: 50px;
                font-size: 18px;
                border-radius: 8px;
            }
            .center-buttons {
                text-align: center;
            }
            </style>
            """, unsafe_allow_html=True)
st.markdown('<div class="center-buttons">', unsafe_allow_html=True)


col1, col2, col3 = st.columns(3)

# --- Button 1: Log In ---
with col1:
    if st.button("Log In", key="login_btn"):
        if email and password:
            st.session_state.page = "main"
            st.session_state.user = email
            st.success(f"✅ Logged in as {email}")
        else:
            st.error("⚠️ Please enter both email and password.")

# --- Button 2: Guest Account ---
with col2:
    if st.button("Guest Account", key="guest_btn"):
        st.session_state.page = "main"
        st.session_state.user = "Guest"
        st.info("Logged in as Guest")

# --- Button 3: Create Account ---
with col3:
    if st.button("Create Account", key="create_btn"):
        st.session_state.page = "signup"
# ====================================
# Signup Page
# ====================================
if "page" in st.session_state and st.session_state.page == "signup":
    st.markdown("<div class='login-card'>", unsafe_allow_html=True)
    st.markdown("<h2>✍️ Create Account</h2>", unsafe_allow_html=True)

    new_email = st.text_input("New Email", key="new_email")
    new_pass = st.text_input("New Password", type="password", key="new_pass")

    if st.button("Register"):
        st.success("✅ Account created! You can now log in.")
        st.session_state.page = "login"

    if st.button("Back to Login"):
        st.session_state.page = "login"

    st.markdown("</div>", unsafe_allow_html=True)

# ====================================
# =========================================================
# MAIN APP AFTER LOGIN
# =========================================================
if st.session_state.page == "main":
    st.set_page_config(page_title="Canteen GenAI System", layout="wide")
    st.title(f"🏫 Welcome {st.session_state.user} to Canteen GenAI System")

    # ---------- AI ASSISTANT ----------
    st.markdown("### 🤖 Canteen AI Assistant")
    user_query = st.text_input("Ask me about menu, budget, feedback, or sales:")
    if st.button("Ask AI"):
        sales_df = load_sales()
        feedback_df = load_feedbacks()

        context = f"""
        MENU: {menu_data}
        SALES DATA: {sales_df.to_dict() if not sales_df.empty else "No sales"}
        FEEDBACK DATA: {feedback_df.to_dict() if not feedback_df.empty else "No feedback"}
        """

        prompt = f"""
        You are a smart AI assistant for a school canteen.
        Suggest combo meals, answer budget questions, summarize sales, share feedback.
        Context: {context}
        Question: {user_query}
        """

        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
            )
            st.success(response.choices[0].message.content)
        except Exception as e:
            st.error(f"⚠️ AI unavailable: {e}")

    st.divider()

    # ---------- PLACE ORDER ----------
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🛒 Place an Order")

        if "cart" not in st.session_state:
            st.session_state.cart = {}

        for category, items in menu_data.items():
            with st.expander(category, expanded=False):
                for item, price in items.items():
                    qty = st.number_input(f"{item} - ₱{price}", min_value=0, step=1, key=f"{category}_{item}")
                    if qty > 0:
                        st.session_state.cart[item] = qty
                    elif item in st.session_state.cart:
                        del st.session_state.cart[item]

        if st.session_state.cart:
            st.markdown("#### 🛒 Your Cart")
            total = 0
            for item, qty in st.session_state.cart.items():
                for cat, items in menu_data.items():
                    if item in items:
                        price = items[item]
                subtotal = price * qty
                total += subtotal
                st.write(f"{item} x {qty} = ₱{subtotal}")

            st.write(f"**Total: ₱{total}**")

            payment_method = st.radio("Payment Method", ["Cash", "Card", "E-Wallet"])
            details = ""

            if payment_method == "Card":
                card_num = st.text_input("Card Number")
                expiry = st.text_input("Expiry Date (MM/YY)")
                cvv = st.text_input("CVV", type="password")
                details = f"Card: {card_num}, Exp: {expiry}"
            elif payment_method == "E-Wallet":
                wallet_type = st.selectbox("Choose Wallet", ["GCash", "Maya", "QR Scan"])
                details = wallet_type

            if st.button("Place Order"):
                order_id = f"ORD{random.randint(1000,9999)}"
                items_str = ", ".join([f"{k}x{v}" for k,v in st.session_state.cart.items()])
                save_receipt(order_id, items_str, total, payment_method, details)
                st.success(f"✅ Order placed! Order ID: {order_id} | Total: ₱{total}")
                st.session_state.cart = {}

    # ---------- FEEDBACK ----------
    with col2:
        st.subheader("✍️ Give Feedback")
        feedback_item = st.selectbox("Select Item:", [i for cat in menu_data.values() for i in cat.keys()])
        rating = st.slider("Rate this item (1-5 stars):", 1, 5, 3)
        feedback_text = st.text_area("Your Feedback:")
        if st.button("Submit Feedback"):
            if feedback_text:
                save_feedback(feedback_item, feedback_text, rating)
                st.success("✅ Feedback submitted!")
            else:
                st.warning("Please write feedback before submitting.")

    # ---------- FEEDBACK RECORDS ----------
    st.subheader("📝 Feedback Records")
    feedback_df = load_feedbacks()
    if not feedback_df.empty:
        st.dataframe(feedback_df)
    else:
        st.info("No feedback available yet.")

    # ---------- SALES REPORT ----------
    st.subheader("📊 Sales Report")
    sales_df = load_sales()

    if not sales_df.empty:
        st.dataframe(sales_df)

        item_to_category = {i: cat for cat, items in menu_data.items() for i in items.keys()}

        expanded_rows = []
        for _, row in sales_df.iterrows():
            for entry in row["items"].split(","):
                entry = entry.strip()
                if "x" in entry:
                    item, qty = entry.split("x")
                    qty = int(qty)
                else:
                    item, qty = entry, 1
                expanded_rows.append({
                    "item": item.strip(),
                    "qty": qty,
                    "total": row["total"],
                    "payment_method": row["payment_method"],
                    "timestamp": row["timestamp"],
                    "category": item_to_category.get(item.strip(), "Other")
                })

        expanded_df = pd.DataFrame(expanded_rows)
        category_sales = expanded_df.groupby("category")["total"].sum()

        fig, ax = plt.subplots(figsize=(5,5))
        category_sales.plot(kind="bar", ax=ax)
        ax.set_ylabel("Total Sales (₱)")
        ax.set_title("Sales per Category")
        st.pyplot(fig)
    else:
        st.info("No sales records available yet.")
