import os
import base64
import streamlit as st
import pandas as pd
import snowflake.connector
from groq import Groq
import random
from datetime import datetime, date, time
import matplotlib.pyplot as plt

# -------------------------------------------------
# Helper: Snowflake connection (uses st.secrets)
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
# Feedback + Receipts
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
        return pd.DataFrame(rows, columns=["item", "feedback", "rating", "timestamp"])
    else:
        return pd.DataFrame(columns=["item", "feedback", "rating", "timestamp"])

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
        return pd.DataFrame(rows, columns=["order_id", "items", "total", "payment_method", "details", "timestamp"])
    else:
        return pd.DataFrame(columns=["order_id", "items", "total", "payment_method", "details", "timestamp"])

def update_receipt_status(order_id, new_status):
    df = load_receipts_df()
    row = df[df["order_id"] == order_id]
    if row.empty:
        return False
    details = row.iloc[0]["details"] or ""
    parts = dict([p.split(":", 1) for p in details.split("|") if ":" in p])
    parts["status"] = new_status
    new_details = "|".join([f"{k}:{v}" for k, v in parts.items()])
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE receipts SET details=%s WHERE order_id=%s", (new_details, order_id))
    conn.commit()
    cur.close()
    conn.close()
    return True

# -------------------------------------------------
# Accounts (Login / Signup)
# -------------------------------------------------
def save_account(username, password, role="Non-Staff"):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO accounts (username, password, role) VALUES (%s, %s, %s)",
        (username, password, role),
    )
    conn.commit()
    cur.close()
    conn.close()

def validate_account(username, password):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT username, role FROM accounts WHERE username=%s AND password=%s",
        (username, password),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return {"username": row[0], "role": row[1]}
    return None

# -------------------------------------------------
# Static Menu Data
# -------------------------------------------------
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

# -------------------------------------------------
# Groq client (AI)
# -------------------------------------------------
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# -------------------------------------------------
# Session State Initialization
# -------------------------------------------------
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

# -------------------------------------------------
# Page Setup
# -------------------------------------------------
st.set_page_config(page_title="BiteHub Canteen GenAI", layout="wide")

# Background Image
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
        st.error(f"Could not load background: {e}")

if os.path.exists("can.jpg"):
    set_background("can.jpg")

# -------------------------------------------------
# LOGIN / SIGNUP / GUEST
# -------------------------------------------------
if st.session_state.page == "login":
    st.markdown("<h2>☕ BiteHub — Login</h2>", unsafe_allow_html=True)
    username = st.text_input("Username", placeholder="Enter username")
    password = st.text_input("Password", type="password", placeholder="Enter password")

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("Log In"):
            user = validate_account(username, password)
            if user:
                st.session_state.user = user
                st.session_state.page = "main"
                st.success(f"Welcome, {username}!")
            else:
                st.error("❌ Invalid username or password. Please try again or create an account.")
    with col2:
        if st.button("Guest Account"):
            st.session_state.user = {"username": "Guest", "role": "Non-Staff"}
            st.session_state.page = "main"
            st.success("Signed in as Guest")
    with col3:
        if st.button("Create Account"):
            st.session_state.page = "signup"

elif st.session_state.page == "signup":
    st.markdown("<h2>✍️ Create Account</h2>", unsafe_allow_html=True)
    new_username = st.text_input("New Username")
    new_pass = st.text_input("New Password", type="password")
    new_role = st.selectbox("Role", ["Non-Staff", "Staff"])
    if st.button("Register"):
        if new_username and new_pass:
            try:
                save_account(new_username, new_pass, new_role)
                st.success(f"✅ Account created for {new_username} as {new_role}. Please log in.")
                st.session_state.page = "login"
            except Exception as e:
                st.error(f"⚠️ Could not create account: {e}")
        else:
            st.error("Please fill all fields.")
    if st.button("Back to Login"):
        st.session_state.page = "login"

# -------------------------------------------------
# MAIN APP (students + staff)
# -------------------------------------------------
elif st.session_state.page == "main":
    user = st.session_state.user or {"username": "Guest", "role": "Non-Staff"}
    st.title(f"🏫 Welcome {user['username']} to BiteHub")

    # AI Helper
    def run_ai(question, extra_context=""):
        if not question:
            return "Please ask something."
        menu_text = ", ".join([f"{item} ({price})" for cat in menu_data.values() for item, price in cat.items()])
        context = f"MENU: {menu_text}\n{extra_context}"
        prompt = f"You are a canteen assistant. Context: {context}\nUser question: {question}"
        try:
            resp = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"⚠️ AI unavailable: {e}"

    # Non-Staff Portal
    if user["role"] == "Non-Staff":
        # (unchanged code for menu, cart, feedback, orders, etc.)
        ...
    # Staff Portal
    elif user["role"] == "Staff":
        # (unchanged staff portal code)
        ...
