import streamlit as st
import pandas as pd
import folium
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from streamlit_folium import st_folium
from streamlit_js_eval import streamlit_js_eval
from werkzeug.security import generate_password_hash, check_password_hash

# --- 1. INITIALIZATION & SESSION STATE ---
if 'logged_in' not in st.session_state:
    st.session_state.update({
        'logged_in': False, 'user': None, 'role': 'client',
        'origin_coords': [-1.286389, 36.817223],
        'path_to_draw': None, 'stats_to_show': None
    })

st.set_page_config(page_title="Nairobi SmartRoute Pro", layout="wide", page_icon="🚚")

# --- 2. DATABASE UTILS ---
def get_connection():
    try: 
        return psycopg2.connect(st.secrets["DB_URL"])
    except: 
        return None

def init_db():
    conn = get_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE,
                    password_hash TEXT,
                    role TEXT DEFAULT 'client'
                )
            """)
            cur.execute("ALTER TABLE users ALTER COLUMN password_hash TYPE TEXT")
            
            admin_hash = generate_password_hash("nairobi2026")
            cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", 
                        ("admin123", admin_hash, "admin"))
            conn.commit()
        finally:
            conn.close()

init_db()

# --- 3. ROUTING ENGINE (FIXED FOR CODE 2011) ---
def fetch_global_route(coords_list):
    api_key = st.secrets.get("ORS_API_KEY")
    if not api_key:
        st.error("Missing ORS_API_KEY in Secrets.")
        return None

    # ORS strictly requires [Longitude, Latitude]
    api_coords = [[c[1], c[0]] for c in coords_list]
    
    # FIX: Alternatives ONLY work if waypoints <= 2
    use_alts = len(api_coords) == 2
    
    payload = {
        "coordinates": api_coords,
        "preference": "fastest",
        "units": "km",
        "instructions": "false"
    }
    
    if use_alts:
        payload["alternative_routes"] = {"target_count": 3, "share_factor": 0.6}
    
    url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
    
    try:
        r = requests.post(url, json=payload, headers={'Authorization': api_key}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            routes = []
            for feature in data['features']:
                # Flip back to [Lat, Lon] for Folium
                raw_geo = feature['geometry']['coordinates']
                flipped = [[p[1], p[0]] for p in raw_geo]
                routes.append({"path": flipped, "stats": feature['properties']['summary']})
            return routes
        else:
            st.error(f"Routing Error: {r.json().get('error', {}).get('message', 'Unknown Error')}")
            return None
    except Exception as e:
        st.error(f"Connection Failed: {e}")
        return None

# --- 4. AUTHENTICATION ---
def auth_page():
    st.title("🚚 Nairobi SmartRoute AI")
    t1, t2 = st.tabs(["Login", "Sign Up"])
    
    with t1:
        with st.form("login"):
            u = st.text_input("Username").strip()
            p = st.text_input("Password", type="password").strip()
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

    with t2:
        with st.form("signup"):
            nu = st.text_input("New Username").strip()
            np = st.text_input("New Password", type="password").strip()
            if st.form_submit_button("Register Driver"):
                if nu and np:
                    conn = get_connection()
                    if conn:
                        try:
                            cur = conn.cursor()
                            cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'client')", 
                                        (nu, generate_password_hash(np)))
                            conn.commit()
                            st.success("Account created! You can now log in.")
                        except: st.error("Username taken.")
                        finally: conn.close()

# --- 5. MAIN DASHBOARD ---
def main_dashboard():
    st.sidebar.title(f"User: {st.session_state.user}")
    st.sidebar.caption(f"Role: {st.session_state.role.upper()}")
    
    menu = ["Route Optimizer"]
    if st.session_state.role == "admin": menu.append("Admin Dashboard")
    choice = st.sidebar.radio("Menu", menu)
    
    if st.sidebar.button("Logout"):
        st.session_state.update({'logged_in': False, 'path_to_draw': None, 'stats_to_show': None})
        st.rerun()

    # GPS Logic
    gps = streamlit_js_eval(js_expressions="navigator.geolocation.getCurrentPosition(pos => {return [pos.coords.latitude, pos.coords.longitude]})", target_id='get_loc', key="GPS_FETCH")
    if gps: st.session_state.origin_coords = gps

    if choice == "Route Optimizer":
        locations = {
            "📍 Current GPS": st.session_state.origin_coords,
            "Nairobi CBD": [-1.286389, 36.817223], "Westlands": [-1.2646, 36.8045], 
            "Karen": [-1.3201, 36.7045], "JKIA Airport": [-1.3321, 36.9212],
            "Industrial Area": [-1.3094, 36.8431], "Kasarani": [-1.2217, 36.8967],
            "Two Rivers": [-1.2133, 36.8056], "Kilimani": [-1.2900, 36.7840]
        }
        
        st.header("Global Route Optimization")
        c1, c2 = st.columns([1, 2])
        
        with c1:
            start = st.selectbox("Start", list(locations.keys()))
            stops = st.multiselect("Stops", [k for k in locations.keys() if k != start])
            
            if st.button("🚀 Optimize Path", use_container_width=True):
                trip = [locations[start]] + [locations[s] for s in stops]
                if len(trip) >= 2:
                    with st.spinner("DRL Agent calculating..."):
                        res = fetch_global_route(trip)
                        if res:
                            st.session_state.path_to_draw = res
                            st.session_state.stats_to_show = res[0]['stats']
                else: st.warning("Select at least one destination.")

            if st.session_state.stats_to_show:
                s = st.session_state.stats_to_show
                st.success(f"**Optimal Trip**\n\n⏱️ {round(s['duration']/60, 1)} mins | 🛣️ {round(s['distance'], 2)} km")

        with c2:
            m = folium.Map(location=locations[start], zoom_start=12)
            folium.Marker(locations[start], icon=folium.Icon(color='green', icon='play')).add_to(m)
            for s in stops:
                folium.Marker(locations[s], icon=folium.Icon(color='blue', icon='info-sign')).add_to(m)
            
            if st.session_state.path_to_draw:
                all_r = st.session_state.path_to_draw
                # Draw Alternatives (Gray Dashed)
                for i, r in enumerate(all_r[1:]):
                    folium.PolyLine(r['path'], color="gray", weight=3, opacity=0.5, dash_array='5').add_to(m)
                # Draw Primary (Bold Blue)
                folium.PolyLine(all_r[0]['path'], color="#1f77b4", weight=6, opacity=0.8).add_to(m)

            st_folium(m, width="100%", height=500, key="persistent_map")

    elif choice == "Admin Dashboard":
        st.header("🛠 Administrator Control Panel")
        conn = get_connection()
        if conn:
            st.subheader("System Users")
            df = pd.read_sql("SELECT username, role FROM users", conn)
            st.table(df)
            
            st.divider()
            st.subheader("Create Admin Account")
            with st.form("new_admin"):
                ad_u, ad_p = st.text_input("User"), st.text_input("Pass", type="password")
                if st.form_submit_button("Grant Admin Access"):
                    cur = conn.cursor()
                    cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin')", (ad_u, generate_password_hash(ad_p)))
                    conn.commit()
                    st.success(f"Admin {ad_u} created.")
            conn.close()

# --- 6. RUN LOGIC ---
if st.session_state.logged_in: main_dashboard()
else: auth_page()
