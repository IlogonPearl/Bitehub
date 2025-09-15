import streamlit as st
import pandas as pd
import snowflake.connector
import random
from datetime import datetime

# ------------------ DB CONNECTION ------------------
def get_connection():
    return snowflake.connector.connect(
        user=st.secrets["SNOWFLAKE_USER"],
        password=st.secrets["SNOWFLAKE_PASSWORD"],
        account=st.secrets["SNOWFLAKE_ACCOUNT"],
        warehouse=st.secrets["SNOWFLAKE_WAREHOUSE"],
        database=st.secrets["SNOWFLAKE_DATABASE"],
        schema=st.secrets["SNOWFLAKE_SCHEMA"]
    )

# ------------------ LOGIN ------------------
def login(email, password):
    conn = get_connection()
    cursor = conn.cursor()

    query = f"SELECT username, role FROM users WHERE email='{email}' AND password='{password}'"
    cursor.execute(query)
    result = cursor.fetchone()
    return result if result else None

# ------------------ CREATE ACCOUNT ------------------
def create_account(username, email, password, role):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        query = f"INSERT INTO users (username, email, password, role) VALUES ('{username}', '{email}', '{password}', '{role}')"
        cursor.execute(query)
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error creating account: {e}")
        return False

# ------------------ STUDENT PORTAL ------------------
def student_portal():
    st.markdown(f"🏫 **Welcome {st.session_state['username']} to BiteHub**")

    # 1. AI Assistant (placeholder)
    st.subheader("🤖 Canteen AI Assistant")
    st.text_input("Ask something about the menu, prices, or recommendations:")

    # 2. Menu + Ordering
    st.subheader("📋 Menu & Ordering")
    menu_data = {
        "Snacks": {"Burger": 50, "Fries": 30},
        "Drinks": {"Soda": 20, "Iced Tea": 25},
        "Meals": {"Chicken Adobo": 90, "Pork Sinigang": 100}
    }

    if "cart" not in st.session_state:
        st.session_state.cart = {}

    for category, items in menu_data.items():
        with st.expander(category):
            for item, price in items.items():
                qty = st.number_input(f"{item} - ₱{price}", min_value=0, key=f"{category}_{item}")
                if qty > 0:
                    st.session_state.cart[item] = qty
                elif item in st.session_state.cart:
                    del st.session_state.cart[item]

    if st.session_state.cart:
        total = 0
        st.write("### 🛒 Your Cart")
        for item, qty in st.session_state.cart.items():
            price = next(price for cat in menu_data.values() if item in cat for item_, price in cat.items() if item_ == item)
            subtotal = qty * price
            st.write(f"{item} x {qty} = ₱{subtotal}")
            total += subtotal
        st.write(f"**Total: ₱{total}**")

        pickup_time = st.time_input("⏰ Choose Pick-Up Time")
        if st.button("Place Order"):
            order_id = f"ORD{random.randint(1000,9999)}"
            st.success(f"✅ Order placed! ID: {order_id}, Pick-Up: {pickup_time}")
            st.session_state.cart = {}

    # 3. Track Order
    st.subheader("📦 Track Orders")
    st.write("🔍 Example: Your order ORD1234 is being prepared...")

    # 4. Feedback
    st.subheader("💬 Submit Feedback")
    feedback = st.text_area("Write your feedback here...")
    if st.button("Send Feedback"):
        st.success("✅ Feedback submitted!")

    # 5. Notifications
    st.subheader("🔔 Notifications")
    st.info("📢 Your order ORD1234 is ready for pickup!")

# ------------------ STAFF PORTAL ------------------
def staff_portal():
    st.markdown(f"👨‍🍳 **Welcome {st.session_state['username']} (Staff) to BiteHub**")

    # 1. AI Assistant
    st.subheader("🤖 AI Assistant")
    st.text_input("Ask AI about sales, inventory, or suggestions:")

    # 2. Menu Management
    st.subheader("📋 Manage Menu")
    st.write("Here staff can add or edit menu items (connect to DB).")

    # 3. Feedbacks
    st.subheader("💬 Read Feedbacks")
    st.write("Show feedback table from DB here.")

    # 4. Pending Orders
    st.subheader("📦 Pending Orders")
    st.write("Show list of pending orders from DB here.")

    # 5. Sales Graph
    st.subheader("📊 Sales Report")
    sales_data = pd.DataFrame({
        "category": ["Snacks", "Drinks", "Meals"],
        "sales": [120, 250, 300]
    })
    st.bar_chart(sales_data.set_index("category"))

# ------------------ MAIN APP ------------------
def main():
    st.set_page_config(page_title="BiteHub", layout="centered")

    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    # LOGIN PAGE
    if not st.session_state["logged_in"]:
        st.title("☕ Welcome Back")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")

        if st.button("Log In"):
            user = login(email, password)
            if user:
                st.session_state["username"], st.session_state["role"] = user
                st.session_state["logged_in"] = True
                st.experimental_rerun()
            else:
                st.error("Invalid email or password")

        if st.button("Guest Account"):
            st.session_state["username"] = "Guest"
            st.session_state["role"] = "Non-Staff"
            st.session_state["logged_in"] = True
            st.experimental_rerun()

        if st.button("Create Account"):
            st.session_state["show_signup"] = True

    # SIGN UP
    elif "show_signup" in st.session_state and st.session_state["show_signup"]:
        st.title("📝 Create Account")
        username = st.text_input("Username")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        role = st.radio("Select Role", ["Non-Staff", "Staff"])

        if st.button("Sign Up"):
            if create_account(username, email, password, role):
                st.success("Account created successfully! Please log in.")
                del st.session_state["show_signup"]

        if st.button("Back to Login"):
            del st.session_state["show_signup"]

    # DASHBOARD
    else:
        if st.session_state["role"] == "Staff":
            staff_portal()
        else:
            student_portal()

        st.markdown("---")
        if st.button("Log Out"):
            st.session_state.clear()
            st.experimental_rerun()

if __name__ == "__main__":
    main()
