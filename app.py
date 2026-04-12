import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="SmartRoute Nairobi", layout="wide", page_icon="🚚")

if 'logged_in' not in st.session_state:
    st.session_state.update({
        'logged_in': False, 'username': None, 'role': 'client', 
        'zip_url': "https://github.com/example/model.zip"
    })

# --- 2. DATABASE & UTILS ---
def get_connection():
    try: return psycopg2.connect(st.secrets["DB_URL"])
    except: return None

def log_activity(username, action):
    conn = get_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO activity_logs (username, action) VALUES (%s, %s)", (username, action))
            conn.commit()
            cur.close()
            conn.close()
        except: pass

# --- 3. ORS ROUTING ENGINE ---
def get_ors_route(start_coords, end_coords):
    """Fetches real road coordinates from OpenRouteService."""
    api_key = st.secrets["ORS_API_KEY"]
    # ORS uses [lon, lat] format
    coords = f"{start_coords[1]},{start_coords[0]}|{end_coords[1]},{end_coords[0]}"
    url = f"https://api.openrouteservice.org/v2/directions/driving-car?api_key={api_key}&start={start_coords[1]},{start_coords[0]}&end={end_coords[1]},{end_coords[0]}"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            # Extract geometry coordinates and flip them back to [lat, lon] for Folium
            line = data['features'][0]['geometry']['coordinates']
            return [[p[1], p[0]] for p in line], data['features'][0]['properties']['summary']
    except Exception as e:
        st.error(f"Routing Error: {e}")
    return [start_coords, end_coords], {"distance": 0, "duration": 0}

# --- 4. LOCATION DATA ---
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
    "Gigiri": [-1.2333, 36.8056]
}

# --- 5. UI COMPONENTS ---

def login_page():
    st.title("🚚 Nairobi SmartRoute")
    tab1, tab2 = st.tabs(["Login", "Register"])
    with tab1:
        with st.form("login"):
            u, p = st.text_input("Username"), st.text_input("Password", type="password")
            if st.form_submit_button("Log In"):
                conn = get_connection()
                if conn:
                    cur = conn.cursor(cursor_factory=RealDictCursor)
                    cur.execute("SELECT * FROM users WHERE username = %s", (u,))
                    user = cur.fetchone()
                    if user and check_password_hash(user['password_hash'], p):
                        st.session_state.update({'logged_in': True, 'username': u, 'role': user['role']})
                        st.rerun()
                    else: st.error("Invalid credentials")
    st.info("System Admin: Use the 'Initialize' button in the dashboard if tables are missing.")

def main_dashboard():
    st.sidebar.title(f"User: {st.session_state.username}")
    nav = ["Route Optimizer", "Admin Console"] if st.session_state.role == 'admin' else ["Route Optimizer"]
    choice = st.sidebar.radio("Navigation", nav)
    if st.sidebar.button("Log Out"):
        st.session_state.logged_in = False
        st.rerun()

    if choice == "Route Optimizer":
        st.header("📍 Smart Delivery Optimizer")
        
        # --- BRIEF SUMMARY SECTION ---
        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        col_s1.metric("Active Drivers", "24", "+2")
        col_s2.metric("Avg Delivery Time", "32m", "-4m")
        col_s3.metric("Traffic Level", "Moderate", "High-Risk")
        col_s4.metric("System Status", "Optimal", "100%")
        st.divider()

        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("Search Parameters")
            origin = st.selectbox("Pickup Point", sorted(locations.keys()), index=0)
            destination = st.selectbox("Dropoff Point", sorted(locations.keys()), index=1)
            analyze = st.button("Calculate Optimal Route")
            
        with col2:
            start_coords, dest_coords = locations[origin], locations[destination]
            m = folium.Map(location=[(start_coords[0]+dest_coords[0])/2, (start_coords[1]+dest_coords[1])/2], zoom_start=13)
            
            folium.Marker(start_coords, popup=f"Pickup: {origin}", icon=folium.Icon(color='red')).add_to(m)
            folium.Marker(dest_coords, popup=f"Dropoff: {destination}", icon=folium.Icon(color='green')).add_to(m)

            route_summary = None
            if origin != destination:
                # CALLING REAL ORS API
                road_path, route_summary = get_ors_route(start_coords, dest_coords)
                folium.PolyLine(road_path, color="blue", weight=5, opacity=0.8, tooltip="Real-Road Path").add_to(m)

            st_folium(m, width="100%", height=400, key=f"map_{origin}_{destination}")

        if analyze and route_summary:
            dist_km = round(route_summary['distance'] / 1000, 2)
            time_min = round(route_summary['duration'] / 60, 0)
            
            log_activity(st.session_state.username, f"Optimized: {origin} to {destination}")
            st.subheader("Analysis Results")
            st.table(pd.DataFrame({
                "Route Type": ["ORS Real-Road", "Shortest Path", "Traffic Avoidance"],
                "Distance": [f"{dist_km} km", f"{dist_km * 0.9} km", f"{dist_km * 1.2} km"],
                "ETA": [f"{time_min} mins", f"{time_min + 5} mins", f"{time_min - 3} mins"]
            }))

    elif choice == "Admin Console":
        st.header("🛠 Admin Controls")
        new_url = st.text_input("Update Model ZIP", st.session_state.zip_url)
        if st.button("Save"): st.session_state.zip_url = new_url
        
        st.subheader("Activity Logs")
        conn = get_connection()
        if conn:
            st.dataframe(pd.read_sql("SELECT * FROM activity_logs ORDER BY timestamp DESC", conn), use_container_width=True)
            conn.close()

# --- 6. ROUTING ---
if st.session_state.logged_in: main_dashboard()
else: login_page()
