import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timedelta
from dateutil import parser
import io

# ====== Style with CSS ======
st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(90deg, #001288, #0257a6, #93cbff);
        min-height: 100vh;
        color: white;
    }
    .css-1v3fvcr, .css-1d391kg, .css-1emrehy, .css-18e3th9 {
        color: white;
    }
    button[kind="primary"] {
        background-color: #001288 !important;
        color: white !important;
    }
    .stTextInput>div>div>input {
        background-color: #e6f0ff;
        color: black;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ====== Load Supabase secrets ======
supabase_url = st.secrets["SUPABASE_URL"]
supabase_key = st.secrets["SUPABASE_KEY"]

# ====== Initialize Supabase client once ======
if "supabase" not in st.session_state:
    st.session_state.supabase = create_client(supabase_url, supabase_key)
if "user" not in st.session_state:
    st.session_state.user = None

supabase = st.session_state.supabase

# ====== Page Title ======
st.set_page_config(page_title="Naija Pharmacy Expiry Tracker", layout="centered")
st.title("Naija Pharmacy Expiry Tracker")
st.write("Track drug expiry dates for your pharmacy.")

# ====== AUTH SECTION ======
if not st.session_state.user:
    st.subheader("Login or Sign Up")
    auth_choice = st.radio("Choose an option", ["Login", "Sign Up"])
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if auth_choice == "Sign Up":
        if st.button("Sign Up"):
            try:
                response = supabase.auth.sign_up({
                    "email": email,
                    "password": password
                })
                if response.get("user"):
                    st.success("Sign-up successful! Please check your email.")
                else:
                    st.error("Sign-up may have failed. Try another email.")
            except Exception as e:
                st.error(f"Sign-up failed: {str(e)}")

    if auth_choice == "Login":
        if st.button("Login"):
            try:
                user_session = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": password
                })

                access_token = user_session['session']['access_token']
                user = user_session['user']

                # Authenticated Supabase client for RLS
                st.session_state.supabase = create_client(
                    supabase_url,
                    supabase_key,
                    {
                        "global": {
                            "headers": {
                                "Authorization": f"Bearer {access_token}"
                            }
                        }
                    }
                )
                st.session_state.user = user
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {str(e)}")

else:
    # ====== MAIN APP ======
    supabase = st.session_state.supabase
    user_id = st.session_state.user["id"]
    st.write(f"Welcome, {st.session_state.user['email']}!")

    # Add product form
    with st.form("add_product_form"):
        st.write("Add New Product")
        product_name = st.text_input("Product Name (e.g., Paracetamol 500mg)")
        quantity = st.number_input("Quantity", min_value=1, step=1)
        expiry_date = st.text_input("Expiry Date (YYYY-MM-DD)")
        submit_button = st.form_submit_button("Add Product")

        if submit_button:
            try:
                parser.parse(expiry_date)
                data = {
                    "product_name": product_name,
                    "quantity": quantity,
                    "expiry_date": expiry_date,
                    "user_id": user_id
                }
                res = supabase.table("expiry_tracker").insert(data).execute()
                st.success("Product added!")
            except Exception as e:
                st.error(f"Failed to add product: {e}")

    # ====== Helper Functions ======
    def get_all_products(uid):
        res = supabase.table("expiry_tracker").select("*").eq("user_id", uid).execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            df["expiry_date"] = pd.to_datetime(df["expiry_date"])
            df["days_to_expiry"] = (df["expiry_date"] - datetime.now()).dt.days
            df["status"] = df["days_to_expiry"].apply(
                lambda x: "Urgent: <1 month" if x < 30 else "Warning: 1-3 months" if x < 90 else "Safe: >3 months"
            )
        return df

    def generate_csv(df):
        output = io.StringIO()
        df[["product_name", "quantity", "expiry_date", "status"]].to_csv(output, index=False)
        return output.getvalue()

    # ====== Buttons: View Products ======
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("0-6 Months Expiry"):
            six_months = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")
            res = supabase.table("expiry_tracker").select("*").eq("user_id", user_id).lte("expiry_date", six_months).execute()
            df = pd.DataFrame(res.data)
            if not df.empty:
                df["expiry_date"] = pd.to_datetime(df["expiry_date"])
                df["days_to_expiry"] = (df["expiry_date"] - datetime.now()).dt.days
                df["status"] = df["days_to_expiry"].apply(
                    lambda x: "Urgent: <1 month" if x < 30 else "Warning: 1-3 months" if x < 90 else "Safe: >3 months"
                )
                st.dataframe(df)
                st.download_button("Download CSV", data=generate_csv(df), file_name="nafdac_expiry_report.csv")

    with col2:
        if st.button("All Products"):
            df = get_all_products(user_id)
            if not df.empty:
                st.dataframe(df)
                st.download_button("Download CSV", data=generate_csv(df), file_name="nafdac_all_products.csv")

    with col3:
        if st.button("Sort by Expiry"):
            df = get_all_products(user_id)
            if not df.empty:
                df = df.sort_values(by="expiry_date")
                st.dataframe(df)

    # ====== Logout ======
    if st.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.session_state.supabase = create_client(supabase_url, supabase_key)
        st.rerun()

# ====== Footer ======
st.write("Set up WhatsApp alerts for near-expiry drugs at: [Twilio Setup](https://www.twilio.com)")
st.write("Data encrypted for NDPR compliance")

