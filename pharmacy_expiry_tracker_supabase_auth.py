import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
from dateutil import parser # Although parser is imported, it's not explicitly used in the current version. Keeping for consistency.
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
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stDateInput>div>div>input {
        background-color: white;
        color: black;
    }
    /* Style for buttons to make them more prominent */
    .stButton>button {
        background-color: #007bff; /* Primary blue */
        color: white;
        border: none;
        padding: 10px 20px;
        border-radius: 5px;
        cursor: pointer;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #0056b3; /* Darker blue on hover */
    }
    </style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="Naija Pharmacy Expiry Tracker", layout="centered")

# ====== Initialize Supabase Client ======
# @st.cache_resource ensures the Supabase client is initialized only once per app session,
# even across Streamlit reruns. This improves performance and manages connection state.
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"] # Get Supabase URL from Streamlit secrets
    key = st.secrets["SUPABASE_KEY"] # Get Supabase Public Key from Streamlit secrets
    return create_client(url, key)

# Initialize Supabase client and user session state variables if they don't exist.
# This happens on the very first load or if the session state is cleared.
if "supabase" not in st.session_state:
    st.session_state.supabase = init_supabase()
if "user" not in st.session_state:
    st.session_state.user = None

# Create a local 'supabase' variable for convenience, referencing the session-managed client.
supabase = st.session_state.supabase

# ====== Helper Functions ======
# Function to classify product status based on days to expiry
def classify_status(days):
    if days < 0:
        return "🔴 EXPIRED"
    elif days < 30: # Less than 30 days
        return "🟠 URGENT"
    elif days < 90: # Less than 90 days (but 30 or more)
        return "🟡 WARNING"
    else: # 90 days or more
        return "🟢 SAFE"

# @st.cache_data caches the results of this function for 300 seconds (5 minutes).
# This prevents re-fetching data from Supabase unnecessarily on every rerun, improving responsiveness.
@st.cache_data(ttl=300)
def get_all_products(uid):
    try:
        # Fetch data from 'expiry_tracker' table where 'user_id' matches the current logged-in user's ID.
        # This relies on Row Level Security (RLS) policies set in Supabase to restrict data access.
        res = st.session_state.supabase.table("expiry_tracker").select("*").eq("user_id", uid).execute()
        df = pd.DataFrame(res.data) # Convert fetched data to a Pandas DataFrame
        
        if not df.empty:
            # Convert expiry_date column to datetime objects for calculations
            df["expiry_date"] = pd.to_datetime(df["expiry_date"])
            # Calculate days remaining until expiry
            df["days_to_expiry"] = (df["expiry_date"] - datetime.now()).dt.days
            # Apply status classification
            df["status"] = df["days_to_expiry"].apply(classify_status)
        return df
    except Exception as e:
        st.error(f"Error fetching data: {e}. Please ensure your database is accessible and RLS is correctly configured.")
        return pd.DataFrame()

# Function to generate a CSV from the DataFrame for download
def generate_csv(df):
    output = io.StringIO()
    # Select specific columns for the CSV export
    df[["product_name", "quantity", "expiry_date", "status"]].to_csv(output, index=False)
    return output.getvalue()

# ====== Auth Section ======
st.markdown('<h1 class="main-header">💊 Naija Pharmacy Expiry Tracker</h1>', unsafe_allow_html=True)

# Check if a user is NOT logged in
if not st.session_state.user:
    st.subheader("Login or Sign Up")
    # Radio buttons for choosing authentication option
    auth_choice = st.radio("Choose an option", ["Login", "Sign Up"])
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    # Sign Up Logic
    if auth_choice == "Sign Up":
        if st.button("Sign Up"):
            if not email or not password:
                st.warning("Please enter both email and password.")
            else:
                try:
                    # Attempt to sign up the user
                    auth_response = supabase.auth.sign_up({"email": email, "password": password})
                    user = auth_response.user # Access user object directly from the response

                    if user:
                        st.success("Sign-up successful! Please check your email for confirmation.")
                    else:
                        # Attempt to get a more specific error message from the response object
                        # The Supabase client's error format can vary, so we try a few common ways.
                        error_detail = "Unknown error during sign-up."
                        if hasattr(auth_response, 'json') and callable(auth_response.json):
                            response_json = auth_response.json()
                            error_detail = response_json.get('error_description', response_json.get('msg', error_detail))
                        elif isinstance(auth_response, dict):
                             error_detail = auth_response.get('error_description', auth_response.get('msg', error_detail))
                        st.error(f"Sign-up failed: {error_detail}")
                except Exception as e:
                    st.error(f"Sign-up failed: {str(e)}. Please check your network and Supabase configuration.")

    # Login Logic
    if auth_choice == "Login":
        if st.button("Login"):
            if not email or not password:
                st.warning("Please enter both email and password.")
            else:
                try:
                    # Attempt to sign in the user
                    auth_response = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    user = auth_response.user    # Access user object directly
                    session = auth_response.session # Access session object directly
                    
                    if user and session:
                        st.session_state.user = user # Store the user object in session state
                        access_token = session.access_token # Get the access token from the session object
                        
                        # --- FIX FOR "dict object has no attribute 'headers'" ---
                        # Re-initialize the Supabase client in session_state with the access_token.
                        # This token is crucial for Row Level Security (RLS) in Supabase,
                        # allowing the client to make authenticated requests.
                        st.session_state.supabase = create_client(
                            st.secrets["SUPABASE_URL"],
                            st.secrets["SUPABASE_KEY"],
                            options={"headers": {"Authorization": f"Bearer {access_token}"}}
                        )
                        st.success("Logged in successfully!")
                        st.rerun() # Rerun the app to display the main application content for the logged-in user
                    else:
                        st.error("Login failed: Invalid credentials or server response. Please try again.")
                except Exception as e:
                    # Catch any exceptions during the login process (e.g., network issues, invalid API response)
                    st.error(f"Login failed: {str(e)}. Please check your credentials and network connection.")

# ====== Main App Content (Displayed when a user is logged in) ======
else: # If a user IS logged in (st.session_state.user is not None)
    # Get user details from session state.
    # Note: st.session_state.user should now consistently be a Supabase User object
    user_id = st.session_state.user.id
    user_email = st.session_state.user.email
    
    # Ensure the local 'supabase' variable refers to the RLS-aware client
    supabase = st.session_state.supabase 

    st.success(f"Welcome, {user_email} 👋")

    # Logout button
    if st.button("Logout"):
        supabase.auth.sign_out() # Perform Supabase sign out
        st.session_state.user = None # Clear user from session state
        st.session_state.supabase = init_supabase() # Re-initialize with the anonymous client
        st.cache_data.clear() # Clear all cached data (important for multi-user apps)
        st.rerun() # Rerun to display the login/signup screen

    # Add product form
    with st.form("add_product"):
        st.subheader("➕ Add New Product")
        product_name = st.text_input("Product Name")
        quantity = st.number_input("Quantity", min_value=1, step=1, value=1) # Default quantity to 1
        # Set default expiry date to 1 year from now for convenience
        default_expiry_date = datetime.now() + timedelta(days=365)
        expiry_date = st.date_input("Expiry Date", value=default_expiry_date.date())
        submitted = st.form_submit_button("Add Product")

        if submitted:
            if not product_name: # Basic validation
                st.warning("Product Name cannot be empty.")
            elif quantity <= 0:
                st.warning("Quantity must be greater than zero.")
            else:
                try:
                    data = {
                        "product_name": product_name,
                        "quantity": quantity,
                        "expiry_date": expiry_date.isoformat(), # Format date as ISO string for Supabase
                        "user_id": user_id # Link this product to the current user
                    }
                    res = supabase.table("expiry_tracker").insert(data).execute()
                    if res.data:
                        st.success(f"{product_name} added successfully!")
                        st.cache_data.clear() # Clear cache to force refresh of product list
                        st.rerun() # Rerun to show updated list immediately
                    else:
                        st.error("Failed to add product.")
                except Exception as e:
                    st.error(f"Error adding product: {e}")

    # View options and product display
    st.markdown("---")
    st.subheader("📦 Inventory")
    col1, col2, col3 = st.columns(3)

    # Fetch all products for the current user
    df = get_all_products(user_id) 

    # Buttons to filter product view. Unique keys are essential for buttons in columns.
    with col1:
        if st.button("View All", key="view_all_btn"):
            st.session_state.view = "all"
    with col2:
        if st.button("0-6 Months", key="view_6months_btn"):
            st.session_state.view = "6months"
    with col3:
        if st.button("Expired Only", key="view_expired_btn"):
            st.session_state.view = "expired"

    # Set default view if not already set
    if "view" not in st.session_state:
        st.session_state.view = "all"

    if not df.empty:
        # Apply filters based on selected view
        if st.session_state.view == "6months":
            df = df[df["days_to_expiry"] <= 180] # 180 days = 6 months
        elif st.session_state.view == "expired":
            df = df[df["days_to_expiry"] < 0]

        # Select columns to display in the DataFrame
        display_df = df[["product_name", "quantity", "expiry_date", "days_to_expiry", "status"]].copy()
        
        # Function to apply color styling based on status
        def color_status(val):
            if val == "🔴 EXPIRED":
                return 'background-color: #ffcccc' # Light red
            elif val == "🟠 URGENT":
                return 'background-color: #ffebcc' # Light orange
            elif val == "🟡 WARNING":
                return 'background-color: #ffffcc' # Light yellow
            else:
                return ''
        
        # Display the DataFrame with custom styling
        st.dataframe(display_df.style.applymap(color_status, subset=['status']))

        # Download CSV button
        st.download_button(
            "📥 Download CSV",
            data=generate_csv(df),
            file_name="nafdac_expiry_report.csv",
            mime="text/csv"
        )
    else:
        st.info("No products found in this category. Add one or change your filter!")

# ====== Footer ======
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; font-size: 0.8rem; color: #a0a0a0;">
        <p><strong>🇳🇬 NDPR Compliant | Built for Nigerian Pharmacies</strong></p>
        <p>💬 WhatsApp Alerts via <a href="https://www.twilio.com" target="_blank" style="color: #a0a0a0;">Twilio Setup</a></p>
        <p><em>Built by Atumonye James &copy; 2025</em></p>
        <p><em>Powered by Streamlit & Supabase &copy; 2025</em></p>
    </div>
    """, unsafe_allow_html=True
)
