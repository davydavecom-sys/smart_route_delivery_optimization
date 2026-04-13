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

# Initialize Session State
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
        st.error("Database Connection Error. Check your Streamlit Secrets.")
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
        except Exception as e:
            st.error(f"Initialization Error: {e}")
        finally:
            cur.close()
            conn.close()

init_db()

# --- 3. ROUTING ENGINE ---
def fetch_global_route(coords_list):
    api_key = st.secrets.get("ORS_API_KEY")
    if not api_key: return None
    
    formatted = [[c[1], c[0]] for c in coords_list]
    url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
    
    # Payload for 3 alternative routes
    payload = {
        "coordinates": formatted,
        "alternative_routes": {"target_count": 3, "share_factor": 0.6}
    }
    
    try:
        r = requests.post(url, json=payload, 
                          headers={'Authorization': api_key, 'Content-Type': 'application/json'}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            routes = []
            for feature in data['features']:
                path = [[p[1], p[0]] for p in feature['geometry']['coordinates']]
                summary = feature['properties']['summary']
                routes.append({"path": path, "stats": summary})
            return routes
    except: pass
    return None

# --- 4. AUTHENTICATION PAGE ---
def auth_page():
    st.title("🚚 Nairobi SmartRoute AI")
    tab1, tab2 = st.tabs(["Login", "Sign Up (Driver)"])
    
    with tab1:
        with st.form("login_form"):
            u = st.text_input("Username").strip()
            p = st.text_input("Password", type="password").strip()
            if st.form_submit_button("Enter Dashboard"):
                conn = get_connection()
                if conn:
                    cur = conn.cursor(cursor_factory=RealDictCursor)
                    cur.execute("SELECT * FROM users WHERE username = %s", (u,))
                    user = cur.fetchone()
                    conn.close()
                    if user and check_password_hash(user['password_hash'], p):
                        st.session_state.update({'logged_in': True, 'user': u, 'role': user['role']})
                        st.rerun()
                    else: st.error("Invalid Username or Password")

    with tab2:
        st.info("New accounts are registered as standard Drivers.")
        with st.form("register_form"):
            new_u = st.text_input("Username").strip()
            new_p = st.text_input("Password", type="password").strip()
            if st.form_submit_button("Create Driver Account"):
                if new_u and new_p:
                    conn = get_connection()
                    if conn:
                        try:
                            cur = conn.cursor()
                            hashed = generate_password_hash(new_p)
                            cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'client')", 
                                        (new_u, hashed))
                            conn.commit()
                            st.success("Account created! You can now log in.")
                        except: st.error("Username already exists.")
                        finally: conn.close()
                else: st.warning("Please provide both username and password.")

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

    # GPS Fetch
    loc_data = streamlit_js_eval(js_expressions="navigator.geolocation.getCurrentPosition(pos => {return [pos.coords.latitude, pos.coords.longitude]})", target_id='get_loc', key="GPS_FETCH")
    if loc_data and (NAIROBI_BOUNDS["lat_min"] <= loc_data[0] <= NAIROBI_BOUNDS["lat_max"]):
        st.session_state.origin_coords = loc_data

    if choice == "Route Optimizer":
        locations = {
            "📍 Current GPS": st.session_state.origin_coords,
            "Nairobi CBD": [-1.286389, 36.817223], "Westlands": [-1.2646, 36.8045], 
            "Karen": [-1.3201, 36.7045], "JKIA Airport": [-1.3321, 36.9212],
            "Kasarani": [-1.2217, 36.8967], "Industrial Area": [-1.3094, 36.8431],
            "Two Rivers Mall": [-1.2133, 36.8056], "Syokimau SGR": [-1.3592, 36.9367],
            "Kilimani": [-1.2900, 36.7840], "Parklands": [-1.2618, 36.8146]
        }
        full_list = ["📍 Current GPS"] + sorted([k for k in locations.keys() if "GPS" not in k])

        st.header("Global Route Optimization")
        c1, c2 = st.columns([1, 2])
        
        with c1:
            start = st.selectbox("Start Node", full_list)
            stops = st.multiselect("Destinations", [k for k in full_list if k != start])
            if st.button("🚀 Optimize Path", use_container_width=True):
                full_trip = [locations[start]] + [locations[s] for s in stops]
                if len(full_trip) >= 2:
                    with st.spinner("Calculating all possible paths..."):
                        all_routes = fetch_global_route(full_trip)
                        if all_routes:
                            st.session_state.path_to_draw = all_routes
                            st.session_state.stats_to_show = all_routes[0]['stats']
                else: st.warning("Add stops to optimize.")

            if st.session_state.stats_to_show:
                s = st.session_state.stats_to_show
                st.success(f"**Trip Summary**\n\n⏱️ Time: {round(s['duration']/60, 1)} mins\n\n🛣️ Dist: {round(s['distance']/1000, 2)} km")

        with c2:
            m = folium.Map(location=locations[start], zoom_start=12)
            folium.Marker(locations[start], icon=folium.Icon(color='green', icon='play')).add_to(m)
            for s in stops: folium.Marker(locations[s], icon=folium.Icon(color='blue', icon='info-sign')).add_to(m)
            
            if st.session_state.path_to_draw:
                routes = st.session_state.path_to_draw
                
                # Draw Alternatives (Dashed)
                for i, r in enumerate(routes[1:]):
                    folium.PolyLine(
                        r['path'], color="#7FB3D5", weight=4, opacity=0.6, 
                        dash_array='10', tooltip=f"Alt {i+1}: {round(r['stats']['duration']/60, 1)} mins"
                    ).add_to(m)
                
                # Draw Primary (Solid)
                folium.PolyLine(
                    routes[0]['path'], color="#1f77b4", weight=7, opacity=0.9,
                    tooltip=f"Optimal: {round(routes[0]['stats']['duration']/60, 1)} mins"
                ).add_to(m)

            st_folium(m, width="100%", height=500, key="nairobi_map_persistent")

    elif choice == "Admin Dashboard":
        st.header("🛠 Administrator Control Panel")
        adm_tab1, adm_tab2 = st.tabs(["User Management", "System Health"])
        with adm_tab1:
            st.subheader("Register New Administrator")
            with st.form("admin_reg"):
                adm_u = st.text_input("New Admin Username").strip()
                adm_p = st.text_input("New Admin Password", type="password").strip()
                if st.form_submit_button("Create Admin Account"):
                    conn = get_connection()
                    if conn and adm_u and adm_p:
                        try:
                            cur = conn.cursor()
                            cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin')", 
                                        (adm_u, generate_password_hash(adm_p)))
                            conn.commit()
                            st.success(f"Admin account created for {adm_u}.")
                        except: st.error("Database error or username taken.")
                        finally: conn.close()
            st.divider()
            st.subheader("Active System Users")
            conn = get_connection()
            if conn:
                df = pd.read_sql("SELECT username, role FROM users", conn)
                st.table(df)
                conn.close()

# --- 6. RUN LOGIC ---
if st.session_state.logged_in:
    main_dashboard()
else:
    auth_page()
