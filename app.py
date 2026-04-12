import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Smart Route City Solution", layout="wide", page_icon="🚚")

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

# --- 3. LOCATION DATA ---
# Expanded Nairobi points
locations = {
    "Nairobi CBD": [-1.286389, 36.817223],
    "Westlands": [-1.2646, 36.8045],
    "Kasarani": [-1.2217, 36.8967],
    "Karen": [-1.3201, 36.7045],
    "Mombasa Road": [-1.3410, 36.9020],
    "Upper Hill": [-1.2990, 36.8070],
    "Runda": [-1.2133, 36.7971],
    "Industrial Area": [-1.3094, 36.8431],
    "Langata": [-1.3323, 36.7583],
    "Dagoretti": [-1.2882, 36.7144],
    "Roysambu": [-1.2189, 36.8837],
    "Starehe": [-1.2721, 36.8375],
    "Kilimani": [-1.2900, 36.7840],
    "Eastleigh": [-1.2740, 36.8520],
    "Gigiri": [-1.2333, 36.8056],
    "South C": [-1.3200, 36.8300],
    "Embaksai": [-1.3167, 36.9167],
    "Madaraka": [-1.3040, 36.8200]
}
location_list = sorted(list(locations.keys()))

# --- 4. UI SECTIONS ---

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
    st.sidebar.title(f"Welcome, {st.session_state.username}")
    nav = ["Route Optimizer"]
    if st.session_state.role == 'admin':
        nav.append("Admin Console")
    
    choice = st.sidebar.radio("Navigation", nav)
    
    if st.sidebar.button("Log Out"):
        st.session_state.logged_in = False
        st.rerun()

    if choice == "Route Optimizer":
        st.header("📍 Route Analysis & Comparison")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.markdown("### Search Locations")
            # Suggestion-based search boxes
            origin = st.selectbox("Type or Select Origin", location_list, index=0)
            destination = st.selectbox("Type or Select Destination", location_list, index=1)
            analyze = st.button("Calculate Optimal Routes")
            
        with col2:
            start_coords = locations[origin]
            dest_coords = locations[destination]

            # Center map between points
            avg_lat = (start_coords[0] + dest_coords[0]) / 2
            avg_lon = (start_coords[1] + dest_coords[1]) / 2
            m = folium.Map(location=[avg_lat, avg_lon], zoom_start=13)

            folium.Marker(start_coords, popup=f"Pickup: {origin}", icon=folium.Icon(color='red', icon='play')).add_to(m)
            folium.Marker(dest_coords, popup=f"Dropoff: {destination}", icon=folium.Icon(color='green', icon='stop')).add_to(m)

            if origin != destination:
                folium.PolyLine([start_coords, dest_coords], color="blue", weight=4, opacity=0.7, dash_array='5').add_to(m)

            st_folium(m, width="100%", height=400, key=f"map_{origin}_{destination}")

        if analyze:
            if origin == destination:
                st.warning("Origin and Destination cannot be the same.")
            else:
                log_activity(st.session_state.username, f"Route Search: {origin} to {destination}")
                st.subheader(f"Comparison: {origin} to {destination}")
                results = pd.DataFrame({
                    "Strategy": ["AI Optimized", "Shortest Path", "Traffic Avoidance"],
                    "Distance (km)": [8.4, 6.2, 10.5],
                    "ETA": ["18 mins", "27 mins", "22 mins"],
                    "Fuel Cost (Est)": ["KES 120", "KES 150", "KES 140"]
                })
                st.table(results)

    elif choice == "Admin Console":
        st.header("🛠 Administrator Dashboard")
        st.subheader("Project Model Management")
        new_url = st.text_input("Update Model ZIP URL", st.session_state.zip_url)
        if st.button("Apply New Model URL"):
            st.session_state.zip_url = new_url
            log_activity(st.session_state.username, f"Admin updated ZIP to {new_url}")
            st.success("Model path updated.")

        st.subheader("Interaction Logs")
        conn = get_connection()
        if conn:
            logs_df = pd.read_sql("SELECT * FROM activity_logs ORDER BY timestamp DESC", conn)
            st.dataframe(logs_df, use_container_width=True)
            conn.close()

# --- 5. APP ROUTING ---
if st.session_state.logged_in:
    main_dashboard()
else:
    login_page()
