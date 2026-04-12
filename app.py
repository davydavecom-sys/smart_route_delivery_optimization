import streamlit as st
import pandas as pd
import folium
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from streamlit_folium import st_folium
from streamlit_js_eval import streamlit_js_eval
from werkzeug.security import generate_password_hash, check_password_hash

# --- 1. INITIALIZATION ---
if 'logged_in' not in st.session_state:
    st.session_state.update({
        'logged_in': False, 'user': None, 'role': 'client',
        'origin_coords': [-1.286389, 36.817223],
        'path_to_draw': None, 'stats_to_show': None
    })

st.set_page_config(page_title="Nairobi SmartRoute Pro", layout="wide")

# --- 2. DATABASE & ROUTING (Same as before) ---
def get_connection():
    try: return psycopg2.connect(st.secrets["DB_URL"])
    except: return None

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

# --- 3. DASHBOARD LOGIC ---
def main_dashboard():
    st.sidebar.title(f"User: {st.session_state.user}")
    
    menu = ["Route Optimizer"]
    if st.session_state.role == "admin": menu.append("Admin Dashboard")
    choice = st.sidebar.radio("Menu", menu)
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    # Optimized Location Fetch
    loc_data = streamlit_js_eval(js_expressions="navigator.geolocation.getCurrentPosition(pos => {return [pos.coords.latitude, pos.coords.longitude]})", target_id='get_loc', key="GPS_FETCH")
    if loc_data: st.session_state.origin_coords = loc_data

    if choice == "Route Optimizer":
        locations = {
            "📍 Current GPS": st.session_state.origin_coords,
            "Nairobi CBD": [-1.286389, 36.817223], "Westlands": [-1.2646, 36.8045], 
            "Karen": [-1.3201, 36.7045], "JKIA Airport": [-1.3321, 36.9212],
            "Kasarani": [-1.2217, 36.8967], "Industrial Area": [-1.3094, 36.8431],
            "Two Rivers Mall": [-1.2133, 36.8056], "Syokimau SGR": [-1.3592, 36.9367]
        }
        full_list = ["📍 Current GPS"] + sorted([k for k in locations.keys() if "GPS" not in k])

        st.header("Global Route Optimization")
        c1, c2 = st.columns([1, 2])
        
        with c1:
            start = st.selectbox("Start Node", full_list)
            stops = st.multiselect("Destinations", [k for k in full_list if k != start])
            
            # --- ACTION: Logic is decoupled from the Button ---
            if st.button("🚀 Optimize Path", use_container_width=True):
                full_trip = [locations[start]] + [locations[s] for s in stops]
                if len(full_trip) >= 2:
                    with st.spinner("DRL Agent calculating..."):
                        path, stats = fetch_global_route(full_trip)
                        # Save to state so it persists during map reruns
                        st.session_state.path_to_draw = path
                        st.session_state.stats_to_show = stats
                else:
                    st.warning("Please select at least one stop.")

            if st.session_state.stats_to_show:
                s = st.session_state.stats_to_show
                st.success(f"**Trip Summary**\n\n⏱️ Time: {round(s['duration']/60, 1)} mins\n\n🛣️ Dist: {round(s['distance']/1000, 2)} km")

        with c2:
            # Create Map
            m = folium.Map(location=locations[start], zoom_start=12)
            folium.Marker(locations[start], icon=folium.Icon(color='green', icon='play')).add_to(m)
            for s in stops:
                folium.Marker(locations[s], icon=folium.Icon(color='blue', icon='info-sign')).add_to(m)
            
            # --- DRAWING: This happens EVERY rerun if data exists in state ---
            if st.session_state.path_to_draw:
                folium.PolyLine(st.session_state.path_to_draw, color="#1f77b4", weight=6, opacity=0.8).add_to(m)

            # CRITICAL: Using a unique but STATIC key for the map
            st_folium(m, width="100%", height=500, key="nairobi_map_persistent")

    # (Admin Dashboard code remains the same as previous version)

# --- AUTH & RUN ---
# [Include your auth_page() and init_db() functions here]
if st.session_state.logged_in: main_dashboard()
else: # show auth_page
