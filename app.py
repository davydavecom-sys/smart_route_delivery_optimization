import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="SmartRoute Nairobi", layout="wide", page_icon="🚚")

# Initialize Session State
if 'logged_in' not in st.session_state:
    st.session_state.update({
        'logged_in': False, 
        'username': None, 
        'role': 'client', 
        'zip_url': "https://github.com/example/model.zip"
    })

# --- 2. DATABASE UTILITIES ---
def get_connection():
    try:
        return psycopg2.connect(st.secrets["DB_URL"])
    except Exception as e:
        return None

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

def force_db_setup():
    conn = get_connection()
    if not conn:
        st.error("Connection failed. Check Secrets.")
        return
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, role TEXT DEFAULT 'client')")
        cur.execute("CREATE TABLE IF NOT EXISTS activity_logs (id SERIAL PRIMARY KEY, username TEXT, action TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        # Default Admin
        admin_pw = generate_password_hash("nairobi2026")
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES ('admin123', %s, 'admin') ON CONFLICT DO NOTHING", (admin_pw,))
        conn.commit()
        st.success("Database Initialized! Admin: admin123 | Pass: nairobi2026")
    except Exception as e:
        st.error(f"Setup Error: {e}")
    finally:
        conn.close()

# --- 3. UI SECTIONS ---

def login_page():
    st.title("🚚 Nairobi SmartRoute")
    st.subheader("Login or Register to access the Optimizer")
    
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Log In"):
                conn = get_connection()
                if conn:
                    cur = conn.cursor(cursor_factory=RealDictCursor)
                    cur.execute("SELECT * FROM users WHERE username = %s", (u,))
                    user = cur.fetchone()
                    if user and check_password_hash(user['password_hash'], p):
                        st.session_state.logged_in = True
                        st.session_state.username = user['username']
                        st.session_state.role = user['role']
                        log_activity(u, "Logged In")
                        st.rerun()
                    else:
                        st.error("Invalid Username or Password")
                    conn.close()

    with tab2:
        with st.form("reg_form"):
            new_u = st.text_input("New Username")
            new_p = st.text_input("New Password", type="password")
            if st.form_submit_button("Register Account"):
                conn = get_connection()
                if conn:
                    try:
                        cur = conn.cursor()
                        cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (new_u, generate_password_hash(new_p)))
                        conn.commit()
                        st.success("Account created! Please switch to Login tab.")
                    except:
                        st.error("Username already exists.")
                    conn.close()

    st.divider()
    with st.expander("System Administration"):
        if st.button("Initialize Database Tables"):
            force_db_setup()

def main_dashboard():
    # Sidebar Navigation
    st.sidebar.title(f"Welcome, {st.session_state.username}")
    nav = ["Route Optimizer"]
    if st.session_state.role == 'admin':
        nav.append("Admin Console")
    
    choice = st.sidebar.radio("Navigation", nav)
    
    if st.sidebar.button("Log Out"):
        st.session_state.logged_in = False
        st.rerun()

    # PAGE 1: ROUTE OPTIMIZER
    if choice == "Route Optimizer":
        st.header("📍 Route Analysis & Comparison")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            origin = st.text_input("Origin", "Nairobi CBD", disabled=True)
            destination = st.selectbox("Destination", ["Westlands", "Kasarani", "Karen", "Mombasa Road", "Upper Hill"])
            analyze = st.button("Analyze Best Routes")
            
        with col2:
            m = folium.Map(location=[-1.286389, 36.817223], zoom_start=12)
            folium.Marker([-1.286389, 36.817223], popup="Start: CBD").add_to(m)
            st_folium(m, width="100%", height=300, key="nairobi_map")

        if analyze:
            log_activity(st.session_state.username, f"Analyzed route to {destination}")
            st.subheader(f"Comparisons for {destination}")
            # Mock data based on your project requirements
            results = pd.DataFrame({
                "Route Option": ["Fastest (Highway)", "Shortest (Local)", "Eco (Bypass)"],
                "Distance (km)": [8.4, 6.2, 11.5],
                "Est. Time (ETA)": ["18 mins", "28 mins", "22 mins"],
                "Traffic Density": ["Heavy", "Moderate", "Light"]
            })
            st.table(results)

    # PAGE 2: ADMIN CONSOLE
    elif choice == "Admin Console":
        st.header("🛠 Administrator Dashboard")
        
        # Zipfile / Model Management
        st.subheader("Project Model Management")
        new_url = st.text_input("Update Model ZIP URL", st.session_state.zip_url)
        if st.button("Apply New Model URL"):
            st.session_state.zip_url = new_url
            log_activity(st.session_state.username, f"Changed ZIP URL to {new_url}")
            st.success("Model path updated successfully.")

        # Interaction Logs
        st.subheader("Website Interaction History")
        conn = get_connection()
        if conn:
            logs_df = pd.read_sql("SELECT * FROM activity_logs ORDER BY timestamp DESC", conn)
            st.dataframe(logs_df, use_container_width=True)
            conn.close()

# --- 4. APP ROUTING ---
if st.session_state.logged_in:
    main_dashboard()
else:
    login_page()
