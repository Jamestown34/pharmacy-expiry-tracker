import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timedelta
from dateutil import parser
import io
import os

# Inject custom CSS with st.markdown for styling
st.markdown(
    """
    <style>
    /* Change main app background to a nice blue gradient */
    .stApp {
        background: linear-gradient(90deg, #001288, #0257a6, #93cbff);
        min-height: 100vh;
        color: white;
    }

    /* Style headers and text color */
    .css-1v3fvcr, .css-1d391kg, .css-1emrehy, .css-18e3th9 {
        color: white;
    }

    /* Style buttons */
    button[kind="primary"] {
        background-color: #001288 !important;
        color: white !important;
    }

    /* Input boxes background */
    .stTextInput>div>div>input {
        background-color: #e6f0ff;
        color: black;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Initialize Supabase client using environment variables
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# Function to add product to Supabase
def add_product(name, quantity, expiry_date, user_id):
    try:
        data = {
            "product_name": name,
            "quantity": quantity,
            "expiry_date": expiry_date,
            "user_id": user_id
        }
        supabase.table("expiry_tracker").insert(data).execute()
        return True
    except:
        return False

# Function to get all products for the logged-in user
def get_all_products(user_id):
    response = supabase.table("expiry_tracker").select("*").eq("user_id", user_id).execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["expiry_date"] = pd.to_datetime(df["expiry_date"])
        df["days_to_expiry"] = (df["expiry_date"] - datetime.now()).dt.days
        df["status"] = df["days_to_expiry"].apply(
            lambda x: "Urgent: <1 month" if x < 30 else "Warning: 1-3 months" if x < 90 else "Safe: >3 months"
        )
    return df

# Function to get products expiring within 6 months for the logged-in user
def get_expiring_products(user_id):
    six_months = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")
    response = supabase.table("expiry_tracker").select("*").eq("user_id", user_id).lte("expiry_date", six_months).execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["expiry_date"] = pd.to_datetime(df["expiry_date"])
        df["days_to_expiry"] = (df["expiry_date"] - datetime.now()).dt.days
        df["status"] = df["days_to_expiry"].apply(
            lambda x: "Urgent: <1 month" if x < 30 else "Warning: 1-3 months" if x < 90 else "Safe: >3 months"
        )
    return df

# Function to generate CSV for NAFDAC
def generate_csv(df):
    output = io.StringIO()
    df[["product_name", "quantity", "expiry_date", "status"]].to_csv(output, index=False)
    return output.getvalue()

# Streamlit app
st.set_page_config(page_title="Naija Pharmacy Expiry Tracker", layout="centered")
st.title("Naija Pharmacy Expiry Tracker")
st.write("Track drug expiry dates for your pharmacy.")

# Session state for user authentication
if "user" not in st.session_state:
    st.session_state.user = None

# Login/Signup form
if not st.session_state.user:
    st.subheader("Login or Sign Up")
    auth_choice = st.radio("Choose an option", ["Login", "Sign Up"])
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if auth_choice == "Sign Up":
        if st.button("Sign Up"):
            try:
                user = supabase.auth.sign_up({"email": email, "password": password})
                st.success("Sign-up successful! Please log in.")
            except Exception as e:
                st.error(f"Sign-up failed: {str(e)}")

    if auth_choice == "Login":
        if st.button("Login"):
            try:
                user = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.user = user.user
                st.success("Logged in successfully!")
                st.experimental_rerun()  # Refresh to show main app
            except Exception as e:
                st.error(f"Login failed: {str(e)}")
else:
    # Main app for logged-in user
    user_id = st.session_state.user.id
    st.write(f"Welcome, {st.session_state.user.email}!")

    # Input form
    with st.form("add_product_form"):
        st.write("Add New Product")
        product_name = st.text_input("Product Name (e.g., Paracetamol 500mg)")
        quantity = st.number_input("Quantity", min_value=1, step=1)
        expiry_date = st.text_input("Expiry Date (YYYY-MM-DD)")
        submit_button = st.form_submit_button("Add Product")

        if submit_button:
            try:
                # Validate date format
                parser.parse(expiry_date)
                if add_product(product_name, quantity, expiry_date, user_id):
                    st.success(f"Added {product_name} with expiry {expiry_date}!")
                else:
                    st.error("Failed to add product. Check Supabase connection.")
            except:
                st.error("Invalid date format. Use YYYY-MM-DD.")

    # Filter buttons
    st.write("View Expiry Dates")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("0-6 Months Expiry"):
            df = get_expiring_products(user_id)
            if df.empty:
                st.write("No products expiring within 6 months.")
            else:
                st.dataframe(df[["product_name", "quantity", "expiry_date", "status"]])
                st.download_button(
                    label="Download NAFDAC Report (CSV)",
                    data=generate_csv(df),
                    file_name="nafdac_expiry_report.csv",
                    mime="text/csv"
                )

    with col2:
        if st.button("All Products"):
            df = get_all_products(user_id)
            if df.empty:
                st.write("No products in inventory.")
            else:
                st.dataframe(df[["product_name", "quantity", "expiry_date", "status"]])
                st.download_button(
                    label="Download NAFDAC Report (CSV)",
                    data=generate_csv(df),
                    file_name="nafdac_expiry_report.csv",
                    mime="text/csv"
                )

    with col3:
        if st.button("Sort by Expiry"):
            df = get_all_products(user_id)
            if not df.empty:
                df = df.sort_values(by="expiry_date")
                st.dataframe(df[["product_name", "quantity", "expiry_date", "status"]])
                st.download_button(
                    label="Download NAFDAC Report (CSV)",
                    data=generate_csv(df),
                    file_name="nafdac_expiry_report.csv",
                    mime="text/csv"
                )

    # Logout button
    if st.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.experimental_rerun()

# Footer
st.write("Set up WhatsApp alerts for near-expiry drugs at: [Twilio Setup](https://www.twilio.com)")
st.write("Data encrypted for NDPR compliance")
