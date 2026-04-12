import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="SmartRoute Nairobi", layout="wide")

# --- 2. DATABASE REPAIR (FORCING WRITE ACCESS) ---
def force_db_setup():
    """Bypasses Aiven Web UI restrictions to create tables via Python."""
    try:
        conn = psycopg2.connect(st.secrets["DB_URL"])
        cur = conn.cursor()
        
        # Create Users Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'client'
            );
        """)
        
        # Create Activity Logs Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id SERIAL PRIMARY KEY,
                username TEXT,
                action TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create a Default Admin Account
        admin_user = "admin123"
        admin_pass = generate_password_hash("nairobi2026")
        cur.execute("""
            INSERT INTO users (username, password_hash, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (username) DO NOTHING;
        """, (admin_user, admin_pass, 'admin'))
        
        conn.commit()
        cur.close()
        conn.close()
        st.success("✅ Success! Database tables created and Admin (admin123) added.")
    except Exception as e:
        st.error(f"❌ Force Setup Failed: {e}")

# --- 3. CORE LOGIC ---
def get_connection():
    return psycopg2.connect(st.secrets["DB_URL"])

def log_activity(username, action):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO activity_logs (username, action) VALUES (%s, %s)", (username, action))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

# --- 4. INTERFACE ---
if 'logged_in' not in st.session_state:
    st.session_state.update({'logged_in': False, 'username': None, 'role': 'client', 'zip_url': ""})

def main():
    if not st.session_state.logged_in:
        st.title("🚚 Nairobi SmartRoute Login")
        
        with st.form("auth_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            mode = st.radio("Mode", ["Login", "Register"])
            submit = st.form_submit_button("Submit")
            
            if submit:
                conn = get_connection()
                cur = conn.cursor(cursor_factory=RealDictCursor)
                if mode == "Login":
                    cur.execute("SELECT * FROM users WHERE username = %s", (u,))
                    user = cur.fetchone()
                    if user and check_password_hash(user['password_hash'], p):
                        st.session_state.logged_in = True
                        st.session_state.username = user['username']
                        st.session_state.role = user['role']
                        log_activity(u, "Logged In")
                        st.rerun()
                    else:
                        st.error("Invalid credentials")
                else:
                    try:
                        cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (u, generate_password_hash(p)))
                        conn.commit()
                        st.success("Registered! Switch to Login mode.")
                    except:
                        st.error("Username taken.")
                conn.close()
        
        st.divider()
        if st.button("🛠 System: Initialize Database & Admin"):
            force_db_setup()

    else:
        # LOGGED IN VIEW
        st.sidebar.title(f"User: {st.session_state.username} ({st.session_state.role})")
        page = st.sidebar.radio("Go to", ["Route Optimizer", "Admin Panel"]) if st.session_state.role == 'admin' else ["Route Optimizer"]

        if "Route Optimizer" in page:
            st.header("📍 Route Comparison & ETA")
            dest = st.selectbox("Destination from CBD", ["Westlands", "Kasarani", "Karen", "Mombasa Road"])
            
            # Map Logic
            m = folium.Map(location=[-1.286389, 36.817223], zoom_start=12) # Nairobi CBD
            folium.Marker([-1.286389, 36.817223], popup="CBD Start", icon=folium.Icon(color='red')).add_to(m)
            st_folium(m, width=700, height=300)

            # Data Comparison Table
            data = {
                "Route Type": ["Main Highway", "Bypass", "Side Streets"],
                "Distance (km)": [8.5, 12.1, 7.8],
                "ETA": ["15 mins", "18 mins", "25 mins"]
            }
            st.table(pd.DataFrame(data))

        elif "Admin Panel" in page:
            st.header("🛠 Admin Controls")
            new_zip = st.text_input("Update Model ZIP URL", st.session_state.zip_url)
            if st.button("Update Model Path"):
                st.session_state.zip_url = new_zip
                st.success("Updated!")

            st.subheader("Interaction Logs")
            conn = get_connection()
            logs = pd.read_sql("SELECT * FROM activity_logs ORDER BY timestamp DESC", conn)
            st.dataframe(logs)
            conn.close()

        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

main()
