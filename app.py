import streamlit as st
import pandas as pd
import folium
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from streamlit_folium import st_folium
from streamlit_js_eval import streamlit_js_eval
from werkzeug.security import generate_password_hash, check_password_hash

# --- 1. CONFIGURATION & BOUNDS ---
NAIROBI_BOUNDS = {"lat_min": -1.45, "lat_max": -1.15, "lon_min": 36.60, "lon_max": 37.10}

if 'logged_in' not in st.session_state:
    st.session_state.update({
        'logged_in': False, 'user': None, 'role': 'client',
        'origin_coords': [-1.286389, 36.817223]
    })

st.set_page_config(page_title="Nairobi SmartRoute Pro", layout="wide", page_icon="🚚")

# --- 2. DATABASE & AUTH UTILS ---
def get_connection():
    try:
        return psycopg2.connect(st.secrets["DB_URL"])
    except:
        st.error("Database connection failed. Check your DB_URL secret.")
        return None

def init_db():
    """Ensure tables exist on startup."""
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE,
                password_hash TEXT,
                role TEXT DEFAULT 'client'
            )
        """)
        # Optional: Auto-create your admin if it doesn't exist
        admin_hash = generate_password_hash("nairobi2026")
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", 
                    ("admin123", admin_hash, "admin"))
        conn.commit()
        cur.close()
        conn.close()

init_db()

# --- 3. ROUTING ENGINE ---
def fetch_global_route(coords_list):
    api_key = st.secrets.get("ORS_API_KEY")
    if not api_key: return None, None
    formatted = [[c[1], c[0]] for c in coords_list]
    url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
    try:
        r = requests.post(url, json={"coordinates": formatted}, 
                          headers={'Authorization': api_key, 'Content-Type': 'application/json'}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return [[p[1], p[0]] for p in data['features'][0]['geometry']['coordinates']], data['features'][0]['properties']['summary']
    except: pass
    return None, None

# --- 4. AUTHENTICATION UI ---
def auth_page():
    st.title("🚚 Nairobi SmartRoute AI")
    tab1, tab2 = st.tabs(["Login", "Register New User"])
    
    with tab1:
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Enter Dashboard"):
                conn = get_connection()
                if conn:
                    cur = conn.cursor(cursor_factory=RealDictCursor)
                    cur.execute("SELECT * FROM users WHERE username = %s", (u,))
                    user = cur.fetchone()
                    if user and check_password_hash(user['password_hash'], p):
                        st.session_state.update({'logged_in': True, 'user': u, 'role': user['role']})
                        st.rerun()
                    else: st.error("Invalid credentials.")
                    conn.close()

    with tab2:
        with st.form("register_form"):
            new_u = st.text_input("Choose Username")
            new_p = st.text_input("Choose Password", type="password")
            new_r = st.selectbox("Account Type", ["client", "admin"], help="Client is standard driver access.")
            if st.form_submit_button("Create Account"):
                if len(new_u) < 3 or len(new_p) < 4:
                    st.warning("Username/Password too short.")
                else:
                    conn = get_connection()
                    if conn:
                        try:
                            cur = conn.cursor()
                            hashed = generate_password_hash(new_p)
                            cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)", 
                                        (new_u, hashed, new_r))
                            conn.commit()
                            st.success("Registration successful! Please switch to the Login tab.")
                        except: st.error("Username already exists.")
                        finally: conn.close()

# --- 5. DASHBOARD ---
def main_dashboard():
    st.sidebar.title(f"User: {st.session_state.user}")
    st.sidebar.caption(f"Access: {st.session_state.role}")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    # GPS Logic
    loc_data = streamlit_js_eval(js_expressions="navigator.geolocation.getCurrentPosition(pos => {return [pos.coords.latitude, pos.coords.longitude]}, err => {return 'FAILED'})", target_id='get_loc', key="GPS_FETCH")
    if loc_data == "FAILED": st.sidebar.error("Failed to get location.")
    elif loc_data and (NAIROBI_BOUNDS["lat_min"] <= loc_data[0] <= NAIROBI_BOUNDS["lat_max"]):
        st.session_state.origin_coords = loc_data

    # Locations
    locations = {
        "📍 Current GPS": st.session_state.origin_coords,
        "Nairobi CBD": [-1.286389, 36.817223], "Westlands": [-1.2646, 36.8045], 
        "Karen": [-1.3201, 36.7045], "JKIA Airport": [-1.3321, 36.9212],
        "Kasarani": [-1.2217, 36.8967], "Industrial Area": [-1.3094, 36.8431],
        "Two Rivers Mall": [-1.2133, 36.8056], "Syokimau SGR": [-1.3592, 36.9367]
    }
    
    sorted_names = sorted([k for k in locations.keys() if "GPS" not in k])
    full_list = ["📍 Current GPS"] + sorted_names

    st.header("Global Route Optimization")
    c1, c2 = st.columns([1, 2])
    with c1:
        start = st.selectbox("Start", full_list)
        stops = st.multiselect("Stops", [k for k in full_list if k != start])
        opt = st.button("🚀 Calculate Global Optimum", use_container_width=True)
    with c2:
        full_trip = [locations[start]] + [locations[s] for s in stops]
        m = folium.Map(location=locations[start], zoom_start=12)
        folium.Marker(locations[start], icon=folium.Icon(color='green')).add_to(m)
        for s in stops: folium.Marker(locations[s], icon=folium.Icon(color='blue')).add_to(m)
        if opt and len(full_trip) >= 2:
            path, stats = fetch_global_route(full_trip)
            if path:
                folium.PolyLine(path, color="#1f77b4", weight=6).add_to(m)
                st.success(f"Trip Optimized: {round(stats['duration']/60, 1)} mins")
        st_folium(m, width="100%", height=500, key="global_map")

# --- RUN ---
if st.session_state.logged_in: main_dashboard()
else: auth_page()
