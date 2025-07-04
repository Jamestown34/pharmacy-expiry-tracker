import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
from dateutil import parser
import io

# ====== Styling ======
st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #001288, #0257a6, #93cbff);
        color: white;
        min-height: 100vh;
    }
    .main-header {
        text-align: center;
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 1rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    .stTextInput>div>div>input, .stNumberInput>div>div>input {
        background-color: white;
        color: black;
    }
    </style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="Naija Pharmacy Expiry Tracker", layout="centered")

# ====== Initialize Supabase Client ======
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

if "supabase" not in st.session_state:
    st.session_state.supabase = init_supabase()
if "user" not in st.session_state:
    st.session_state.user = None

supabase = st.session_state.supabase

# ====== Helper Functions ======
def classify_status(days):
    if days < 0:
        return "🔴 EXPIRED"
    elif days < 30:
        return "🟠 URGENT"
    elif days < 90:
        return "🟡 WARNING"
    else:
        return "🟢 SAFE"

@st.cache_data(ttl=300)
def get_all_products(uid):
    try:
        # Ensure the supabase client has the correct auth token for RLS
        # This will use the RLS-aware client stored in session_state after login
        res = st.session_state.supabase.table("expiry_tracker").select("*").eq("user_id", uid).execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            df["expiry_date"] = pd.to_datetime(df["expiry_date"])
            df["days_to_expiry"] = (df["expiry_date"] - datetime.now()).dt.days
            df["status"] = df["days_to_expiry"].apply(classify_status)
        return df
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return pd.DataFrame()

def generate_csv(df):
    output = io.StringIO()
    df[["product_name", "quantity", "expiry_date", "status"]].to_csv(output, index=False)
    return output.getvalue()

# ====== Auth Section ======
st.markdown('<h1 class="main-header">💊 Naija Pharmacy Expiry Tracker</h1>', unsafe_allow_html=True)

if not st.session_state.user:
    st.subheader("Login or Sign Up")
    option = st.radio("Choose an option:", ["Login", "Sign Up"])
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if option == "Sign Up":
        if st.button("Sign Up"):
            try:
                response = supabase.auth.sign_up({"email": email, "password": password})
                if response.user:
                    st.success("Account created! Check your email to confirm.")
                else:
                    st.error(f"Sign-up failed: {response.json().get('error_description', response.json().get('msg', 'Unknown error'))}")
            except Exception as e:
                st.error(f"Sign-up failed: {e}")

    if option == "Login":
        if st.button("Login"):
            try:
                auth = supabase.auth.sign_in_with_password({"email": email, "password": password})
                if auth.user:
                    st.session_state.user = auth.user
                    access_token = auth.session.access_token
                    # CORRECTED: Create RLS-aware client with proper options structure
                    st.session_state.supabase = create_client(
                        st.secrets["SUPABASE_URL"],
                        st.secrets["SUPABASE_KEY"],
                        options={"headers": {"Authorization": f"Bearer {access_token}"}}
                    )
                    st.rerun()
                else:
                    st.error("Login failed. Check your credentials.")
            except Exception as e:
                st.error(f"Login failed: {e}")

# ====== Main App ======
else:
    user = st.session_state.user
    # Ensure 'supabase' variable always refers to the session_state client
    supabase = st.session_state.supabase 
    user_id = user.id

    st.success(f"Welcome, {user.email} 👋")

    # Logout button
    if st.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.session_state.supabase = init_supabase() # Re-initialize with anonymous client
        st.cache_data.clear() # Clear cached data for the previous user
        st.rerun()

    # Add product form
    with st.form("add_product"):
        st.subheader("➕ Add New Product")
        product_name = st.text_input("Product Name")
        quantity = st.number_input("Quantity", min_value=1, step=1)
        expiry_date = st.date_input("Expiry Date")
        submitted = st.form_submit_button("Add Product")

        if submitted:
            try:
                data = {
                    "product_name": product_name,
                    "quantity": quantity,
                    "expiry_date": expiry_date.isoformat(),
                    "user_id": user_id
                }
                res = supabase.table("expiry_tracker").insert(data).execute()
                if res.data:
                    st.success(f"{product_name} added!")
                    st.cache_data.clear() # Clear cache to refresh product list
                    st.rerun()
                else:
                    st.error("Failed to add product.")
            except Exception as e:
                st.error(f"Error: {e}")

    # View options
    st.markdown("---")
    st.subheader("📦 Inventory")
    col1, col2, col3 = st.columns(3)

    df = get_all_products(user_id) # This helper function now uses st.session_state.supabase

    with col1:
        if st.button("View All"):
            st.session_state.view = "all"

    with col2:
        if st.button("0-6 Months"):
            st.session_state.view = "6months"

    with col3:
        if st.button("Expired Only"):
            st.session_state.view = "expired"

    if "view" not in st.session_state:
        st.session_state.view = "all"

    if not df.empty:
        if st.session_state.view == "6months":
            df = df[df["days_to_expiry"] <= 180]
        elif st.session_state.view == "expired":
            df = df[df["days_to_expiry"] < 0]

        # Display relevant columns
        display_df = df[["product_name", "quantity", "expiry_date", "days_to_expiry", "status"]].copy()
        # Custom styling for the status column
        def color_status(val):
            if val == "🔴 EXPIRED":
                return 'background-color: #ffcccc' # Light red
            elif val == "🟠 URGENT":
                return 'background-color: #ffebcc' # Light orange
            elif val == "🟡 WARNING":
                return 'background-color: #ffffcc' # Light yellow
            else:
                return ''
        
        st.dataframe(display_df.style.applymap(color_status, subset=['status']))

        st.download_button(
            "📥 Download CSV",
            data=generate_csv(df),
            file_name="nafdac_expiry_report.csv",
            mime="text/csv"
        )
    else:
        st.info("No products found. Add one to get started!")

# ====== Footer ======
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center;">
        <p><strong>🇳🇬 NDPR Compliant | Built for Nigerian Pharmacies</strong></p>
        <p>💬 WhatsApp Alerts via <a href="https://www.twilio.com" target="_blank">Twilio Setup</a></p>
        <p><em>Powered by Streamlit & Supabase</em></p>
    </div>
    """, unsafe_allow_html=True
)
