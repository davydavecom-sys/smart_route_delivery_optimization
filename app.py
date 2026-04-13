import streamlit as st
import pandas as pd
import folium
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from streamlit_folium import st_folium
from streamlit_js_eval import streamlit_js_eval
from werkzeug.security import generate_password_hash, check_password_hash

# --- 1. SETTINGS & BOUNDS ---
NAIROBI_BOUNDS = {"lat_min": -1.45, "lat_max": -1.15, "lon_min": 36.60, "lon_max": 37.10}

if 'logged_in' not in st.session_state:
    st.session_state.update({
        'logged_in': False, 'user': None, 'role': 'client',
        'origin_coords': [-1.286389, 36.817223],
        'path_to_draw': None, 'stats_to_show': None
    })

st.set_page_config(page_title="Nairobi SmartRoute Pro", layout="wide", page_icon="🚚")

# --- 2. DATABASE UTILS ---
def get_connection():
    try: return psycopg2.connect(st.secrets["DB_URL"])
    except: return None

def init_db():
    conn = get_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, role TEXT DEFAULT 'client')")
            cur.execute("ALTER TABLE users ALTER COLUMN password_hash TYPE TEXT")
            admin_hash = generate_password_hash("nairobi2026")
            cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin') ON CONFLICT DO NOTHING", ("admin123", admin_hash))
            conn.commit()
        finally:
            conn.close()

init_db()

# --- 3. ROUTING ENGINE (FIXED ROAD LOADING) ---
def fetch_global_route(coords_list):
    api_key = st.secrets.get("ORS_API_KEY")
    if not api_key:
        st.error("API Key missing!")
        return None
    
    # ORS expects [Lon, Lat]
    formatted_coords = [[c[1], c[0]] for c in coords_list]
    
    url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
    payload = {
        "coordinates": formatted_coords,
        "alternative_routes": {"target_count": 3, "share_factor": 0.6},
        "instructions": "false" # Keep response small
    }
    
    try:
        r = requests.post(url, json=payload, headers={'Authorization': api_key}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            routes = []
            # Extract each feature (the primary and the alternatives)
            for feature in data['features']:
                # FLIP BACK to [Lat, Lon] for Folium
                raw_path = feature['geometry']['coordinates']
                flipped_path = [[p[1], p[0]] for p in raw_path]
                
                routes.append({
                    "path": flipped_path,
                    "stats": feature['properties']['summary']
                })
            return routes
        else:
            st.error(f"API Error {r.status_code}: {r.text}")
    except Exception as e:
        st.error(f"Connection Error: {e}")
    return None

# --- 4. AUTH PAGE ---
def auth_page():
    st.title("🚚 Nairobi SmartRoute AI")
    t1, t2 = st.tabs(["Login", "Sign Up"])
    with t1:
        with st.form("l"):
            u, p = st.text_input("User"), st.text_input("Pass", type="password")
            if st.form_submit_button("Login"):
                conn = get_connection()
                if conn:
                    cur = conn.cursor(cursor_factory=RealDictCursor)
                    cur.execute("SELECT * FROM users WHERE username = %s", (u,))
                    user = cur.fetchone()
                    if user and check_password_hash(user['password_hash'], p):
                        st.session_state.update({'logged_in': True, 'user': u, 'role': user['role']})
                        st.rerun()
                    else: st.error("Wrong credentials")
                    conn.close()
    with t2:
        with st.form("s"):
            nu, np = st.text_input("New User"), st.text_input("New Pass", type="password")
            if st.form_submit_button("Register"):
                conn = get_connection()
                if conn:
                    try:
                        cur = conn.cursor()
                        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'client')", (nu, generate_password_hash(np)))
                        conn.commit()
                        st.success("Success! Login now.")
                    except: st.error("User exists.")
                    finally: conn.close()

# --- 5. MAIN DASHBOARD ---
def main_dashboard():
    st.sidebar.title(f"User: {st.session_state.user}")
    menu = ["Route Optimizer"]
    if st.session_state.role == "admin": menu.append("Admin Dashboard")
    choice = st.sidebar.radio("Menu", menu)

    if st.sidebar.button("Logout"):
        st.session_state.update({'logged_in': False, 'path_to_draw': None})
        st.rerun()

    if choice == "Route Optimizer":
        locations = {
            "📍 Current GPS": st.session_state.origin_coords,
            "Nairobi CBD": [-1.286389, 36.817223], "Westlands": [-1.2646, 36.8045], 
            "Karen": [-1.3201, 36.7045], "JKIA Airport": [-1.3321, 36.9212],
            "Industrial Area": [-1.3094, 36.8431]
        }
        
        st.header("Global Route Optimization")
        c1, c2 = st.columns([1, 2])
        
        with c1:
            start = st.selectbox("Start", list(locations.keys()))
            stops = st.multiselect("Destinations", [k for k in locations.keys() if k != start])
            
            if st.button("🚀 Find Roads", use_container_width=True):
                full_trip = [locations[start]] + [locations[s] for s in stops]
                if len(full_trip) >= 2:
                    with st.spinner("Fetching roads..."):
                        all_routes = fetch_global_route(full_trip)
                        if all_routes:
                            st.session_state.path_to_draw = all_routes
                            st.session_state.stats_to_show = all_routes[0]['stats']
                else: st.warning("Select more stops.")

            if st.session_state.stats_to_show:
                s = st.session_state.stats_to_show
                st.success(f"Optimal: {round(s['duration']/60, 1)} mins")

        with c2:
            m = folium.Map(location=locations[start], zoom_start=13)
            folium.Marker(locations[start], icon=folium.Icon(color='green')).add_to(m)
            for s in stops: folium.Marker(locations[s], icon=folium.Icon(color='blue')).add_to(m)
            
            if st.session_state.path_to_draw:
                routes = st.session_state.path_to_draw
                # Draw Alternatives (Dashed)
                for i, r in enumerate(routes[1:]):
                    folium.PolyLine(r['path'], color="gray", weight=3, opacity=0.5, dash_array='5').add_to(m)
                # Draw Primary (Bold Blue)
                folium.PolyLine(routes[0]['path'], color="blue", weight=6, opacity=0.8).add_to(m)

            st_folium(m, width="100%", height=500, key="nairobi_map_final")

    elif choice == "Admin Dashboard":
        st.header("Admin Panel")
        conn = get_connection()
        if conn:
            df = pd.read_sql("SELECT username, role FROM users", conn)
            st.table(df)
            conn.close()

if st.session_state.logged_in: main_dashboard()
else: auth_page()
