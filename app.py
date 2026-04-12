import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="SmartRoute Nairobi", layout="wide")

# --- 2. DATABASE FUNCTIONS ---
def get_connection():
    """Returns a connection object to your Aiven database using st.secrets."""
    try:
        return psycopg2.connect(st.secrets["DB_URL"])
    except Exception as e:
        # We don't use st.error here because this function is called inside other logic
        return None

def force_db_setup():
    """Bypasses Aiven Web UI restrictions to create tables via Python."""
    conn = get_connection()
    if not conn:
        st.error("Could not connect to database for setup.")
        return
        
    try:
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
        st.success("✅ Success! Database tables created and Admin (admin123) added.")
    except Exception as e:
        st.error(f"❌ Force Setup Failed: {e}")
    finally:
        cur.close()
        conn.close()

def log_activity(username, action):
    conn = get_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO activity_logs (username, action) VALUES (%s, %s)", (username, action))
            conn.commit()
            cur.close()
            conn.close()
        except:
            pass

# --- 3. SESSION STATE ---
if 'logged_in' not in st.session_state:
    st.session_state.update({
        'logged_in': False, 
        'username': None, 
        'role': 'client', 
        'zip_url': "https://github.com/latest/download/model.zip"
    })

# --- 4. MAIN INTERFACE ---
def main():
    if not st.session_state.logged_in:
        st.title("🚚 Nairobi SmartRoute Login")
        
        # Connection Status Check
        test_conn = get_connection()
        if test_conn:
            st.success("Connected to Aiven Database")
            test_conn.close()
        else:
            st.warning("⚠️ Database not connected. Check your Streamlit Secrets.")

        with st.form("auth_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            mode = st.radio("Mode", ["Login", "Register"])
            submit = st.form_submit_button("Submit")
            
            if submit:
                conn = get_connection()
                if conn:
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
                            cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", 
                                        (u, generate_password_hash(p)))
                            conn.commit()
                            st.success("Registered! Switch to Login mode.")
                        except:
                            st.error("Username taken or Database error.")
                    cur.close()
                    conn.close()
        
        st.divider()
        if st.button("🛠 System: Initialize Database & Admin"):
            force_db_setup()

    else:
        # --- LOGGED IN VIEW ---
        st.sidebar.title(f"User: {st.session_state.username}")
        st.sidebar.info(f"Role: {st.session_state.role}")
        
        menu_options = ["Route Optimizer"]
        if st.session_state.role == 'admin':
            menu_options.append("Admin Panel")
            
        page = st.sidebar.radio("Navigate", menu_options)

        if page == "Route Optimizer":
            st.header("📍 Route Comparison & ETA")
            dest = st.selectbox("Destination from CBD", ["Westlands", "Kasarani", "Karen", "Mombasa Road"])
            
            # Map Visual
            m = folium.Map(location=[-1.286389, 36.817223], zoom_start=12)
            folium.Marker([-1.286389, 36.817223], popup="CBD Start", icon=folium.Icon(color='red')).add_to(m)
            st_folium(m, width=700, height=300)

            # Route Comparison Logic
            st.subheader(f"Optimal routes to {dest}")
            data = {
                "Route Type": ["Main Highway", "Bypass", "Side Streets"],
                "Distance (km)": [8.5, 12.1, 7.8],
                "ETA": ["15 mins", "18 mins", "25 mins"]
            }
            st.table(pd.DataFrame(data))

        elif page == "Admin Panel":
            st.header("🛠 Admin Controls")
            new_zip = st.text_input("Update Model ZIP URL", st.session_state.zip_url)
            if st.button("Update Model Path"):
                st.session_state.zip_url = new_zip
                st.success("Model URL updated for this session!")

            st.subheader("Interaction Logs")
            conn = get_connection()
            if conn:
                logs = pd.read_sql("SELECT * FROM activity_logs ORDER BY timestamp DESC", conn)
                st.dataframe(logs, use_container_width=True)
                conn.close()

        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

if __name__ == "__main__":
    main()
