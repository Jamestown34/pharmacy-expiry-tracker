import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
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
        return "\ud83d\udd34 EXPIRED"
    elif days < 30:
        return "\ud83d\udfe0 URGENT"
    elif days < 90:
        return "\ud83d\udfe1 WARNING"
    else:
        return "\ud83d\udfe2 SAFE"

@st.cache_data(ttl=300)
def get_all_products(uid):
    try:
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
    cleaned_df = df.copy()
    cleaned_df["status"] = cleaned_df["status"].replace({
        "\ud83d\udd34 EXPIRED": "EXPIRED",
        "\ud83d\udfe0 URGENT": "URGENT",
        "\ud83d\udfe1 WARNING": "WARNING",
        "\ud83d\udfe2 SAFE": "SAFE"
    })
    output = io.StringIO()
    cleaned_df[["product_name", "quantity", "expiry_date", "status"]].to_csv(output, index=False)
    return output.getvalue()

# ====== Auth Section ======
st.markdown('<h1 class="main-header">&#128138; Naija Pharmacy Expiry Tracker</h1>', unsafe_allow_html=True)

if not st.session_state.user:
    st.subheader("Login or Sign Up")
    auth_choice = st.radio("Choose an option", ["Login", "Sign Up"])
    name = ""
    if auth_choice == "Sign Up":
        name = st.text_input("Pharmacy / Business Name")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if auth_choice == "Sign Up":
        if st.button("Sign Up"):
            try:
                auth_response = supabase.auth.sign_up({
                    "email": email,
                    "password": password,
                    "options": {"data": {"name": name}}
                })
                user = auth_response.user
                if user:
                    st.success("Sign-up successful! Please check your email for confirmation.")
                else:
                    st.error("Sign-up failed: Invalid response from server.")
            except Exception as e:
                st.error(f"Sign-up failed: {str(e)}")

    if auth_choice == "Login":
        if st.button("Login"):
            try:
                auth_response = supabase.auth.sign_in_with_password({"email": email, "password": password})
                user = auth_response.user
                session = auth_response.session
                if user and session:
                    st.session_state.user = user
                    supabase.auth.set_session(
                        access_token=session.access_token,
                        refresh_token=session.refresh_token
                    )
                    st.success("Logged in successfully!")
                    st.rerun()
                else:
                    st.error("Login failed: Invalid response from server.")
            except Exception as e:
                st.error(f"Login failed: {str(e)}")

else:
    user_id = st.session_state.user.id
    user_name = st.session_state.user.user_metadata.get("name", st.session_state.user.email)
   st.success(f"Welcome, {user_name}")

    if st.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.session_state.supabase = init_supabase()
        st.cache_data.clear()
        st.rerun()

    df = get_all_products(user_id)
    if not df.empty:
        counts = df["status"].value_counts().to_dict()
        with st.container():
            st.subheader("\ud83d\udcca Expiry Summary")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("\ud83d\udd34 Expired", counts.get("\ud83d\udd34 EXPIRED", 0))
            col2.metric("\ud83d\udfe0 Urgent", counts.get("\ud83d\udfe0 URGENT", 0))
            col3.metric("\ud83d\udfe1 Warning", counts.get("\ud83d\udfe1 WARNING", 0))
            col4.metric("\ud83d\udfe2 Safe", counts.get("\ud83d\udfe2 SAFE", 0))

    if "show_inventory" not in st.session_state:
        st.session_state.show_inventory = False

    if st.button("\ud83d\uddc2\ufe0f Check Inventory"):
        st.session_state.show_inventory = not st.session_state.show_inventory

    if st.session_state.show_inventory:
        st.markdown("---")
        st.subheader("\ud83d\udce6 Inventory")

        with st.expander("\ud83d\udd0d Filter Products", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                search_term = st.text_input("Search by Product Name").strip().lower()
            with col2:
                view_option = st.selectbox("View", ["All", "0-6 Months", "Expired Only"])

        if not df.empty:
            if search_term:
                df = df[df["product_name"].str.lower().str.contains(search_term)]
            if view_option == "0-6 Months":
                df = df[df["days_to_expiry"] <= 180]
            elif view_option == "Expired Only":
                df = df[df["days_to_expiry"] < 0]

            display_df = df[["product_name", "quantity", "expiry_date", "days_to_expiry", "status"]].copy()

            def color_status(val):
                if val == "\ud83d\udd34 EXPIRED":
                    return 'background-color: #ffcccc'
                elif val == "\ud83d\udfe0 URGENT":
                    return 'background-color: #ffebcc'
                elif val == "\ud83d\udfe1 WARNING":
                    return 'background-color: #ffffcc'
                else:
                    return ''

            st.dataframe(display_df.style.applymap(color_status, subset=['status']))

            st.download_button(
                "\ud83d\udcc5 Download CSV",
                data=generate_csv(df),
                file_name="nafdac_expiry_report.csv",
                mime="text/csv"
            )

            st.markdown("### \u270f\ufe0f Update or Delete Products")
            for _, row in df.iterrows():
                with st.expander(f"{row['product_name']} (Qty: {row['quantity']}, Status: {row['status']})"):
                    new_qty = st.number_input(
                        f"Update quantity for {row['product_name']}",
                        min_value=0,
                        value=int(row['quantity']),
                        step=1,
                        key=f"qty_{row['id']}"
                    )
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(f"Update Quantity", key=f"update_{row['id']}"):
                            try:
                                supabase.table("expiry_tracker").update({"quantity": new_qty}).eq("id", row["id"]).execute()
                                st.success("Quantity updated.")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error updating: {e}")
                    with col2:
                        if st.button(f"Delete Product", key=f"delete_{row['id']}"):
                            try:
                                supabase.table("expiry_tracker").delete().eq("id", row["id"]).execute()
                                st.warning("Product deleted.")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error deleting: {e}")
        else:
            st.info("No products found. Add one to get started!")

    with st.form("add_product"):
        st.subheader("\u2795 Add New Product")
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
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Failed to add product.")
            except Exception as e:
                st.error(f"Error: {e}")

# ====== Footer ======
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center;">
        <p><strong>&#127475;&#127466; NDPR Compliant | Built for Nigerian Pharmacies & Medcine Stores</strong></p>
        <p>&#128172; WhatsApp Alerts via <a href="https://www.twilio.com" target="_blank">Twilio Setup</a></p>
        <p><em>Built by Atumonye James © 2025</em></p>
        <p><em>Powered by Streamlit & Supabase</em></p>
    </div>
    """, unsafe_allow_html=True
)
