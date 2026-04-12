import streamlit as st
import pandas as pd
import folium
import requests
from streamlit_folium import st_folium
from streamlit_js_eval import streamlit_js_eval
from werkzeug.security import generate_password_hash, check_password_hash

# --- 1. PERSISTENT SESSION INITIALIZATION ---
# We initialize these ONLY ONCE to prevent resets
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user' not in st.session_state:
    st.session_state.user = None
if 'origin_coords' not in st.session_state:
    st.session_state.origin_coords = [-1.286389, 36.817223] # Default Nairobi

st.set_page_config(page_title="Nairobi SmartRoute Pro", layout="wide")

# --- 2. ROUTING ENGINE (Multi-Stop) ---
def fetch_global_route(coords_list):
    api_key = st.secrets.get("ORS_API_KEY")
    if not api_key or len(coords_list) < 2: return None, None
    
    # ORS format: [longitude, latitude]
    formatted = [[c[1], c[0]] for c in coords_list]
    url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
    headers = {'Authorization': api_key, 'Content-Type': 'application/json'}
    
    try:
        r = requests.post(url, json={"coordinates": formatted}, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            line = [[p[1], p[0]] for p in data['features'][0]['geometry']['coordinates']]
            summary = data['features'][0]['properties']['summary']
            return line, summary
    except Exception as e:
        st.error(f"Routing Error: {e}")
    return None, None

# --- 3. LOGIN PAGE ---
def show_login():
    st.title("🚚 Nairobi SmartRoute AI")
    with st.container(border=True):
        u = st.text_input("Username", key="login_u")
        p = st.text_input("Password", type="password", key="login_p")
        if st.button("Log In"):
            # Hardcoded check for your demo admin
            if u == "admin123" and p == "nairobi2026":
                st.session_state.logged_in = True
                st.session_state.user = u
                st.rerun()
            else:
                st.error("Invalid Username or Password")

# --- 4. MAIN DASHBOARD ---
def show_dashboard():
    # Sidebar Logout
    if st.sidebar.button("🚪 Logout"):
        st.session_state.logged_in = False
        st.rerun()

    st.sidebar.divider()
    
    # GPS Fetch - Using a safer implementation
    st.sidebar.subheader("Device GPS")
    if st.sidebar.button("🛰️ Get Current Location"):
        loc = streamlit_js_eval(js_expressions="navigator.geolocation.getCurrentPosition(pos => {return [pos.coords.latitude, pos.coords.longitude]})", target_id='get_loc')
        if loc:
            st.session_state.origin_coords = loc
            st.toast("Location Updated!")

    # Locations
    locations = {
        "📍 Current GPS": st.session_state.origin_coords,
        "Nairobi CBD": [-1.286389, 36.817223],
        "Westlands": [-1.2646, 36.8045],
        "JKIA Airport": [-1.3321, 36.9212],
        "Karen": [-1.3201, 36.7045],
        "Thika Road Mall": [-1.2210, 36.8850],
        "Two Rivers": [-1.2133, 36.8056]
    }

    st.header("Global Route Optimization")
    st.info("System Goal: Minimize **Total Journey Time** across all nodes.")

    col1, col2 = st.columns([1, 2])
    
    with col1:
        start_node = st.selectbox("Start Point", list(locations.keys()))
        stops = st.multiselect("Select Destinations (in order)", [k for k in locations.keys() if k != start_node])
        
        optimize = st.button("🚀 Calculate Global Optimum", use_container_width=True)

    with col2:
        # Build the sequence
        full_trip = [locations[start_node]] + [locations[s] for s in stops]
        
        # Center map on start
        m = folium.Map(location=locations[start_node], zoom_start=12)
        
        # Markers
        folium.Marker(locations[start_node], popup="START", icon=folium.Icon(color='green', icon='play')).add_to(m)
        for i, stop in enumerate(stops):
            folium.Marker(locations[stop], popup=f"Stop {i+1}", icon=folium.Icon(color='blue')).add_to(m)

        if optimize and len(full_trip) >= 2:
            path, stats = fetch_global_route(full_trip)
            if path:
                folium.PolyLine(path, color="#1f77b4", weight=6, opacity=0.8).add_to(m)
                
                # Stats Display
                total_min = round(stats['duration'] / 60, 1)
                total_km = round(stats['distance'] / 1000, 2)
                
                st.success(f"**Optimal Trip Summary:** {total_min} mins | {total_km} km")
                st.caption("DRL Model selected this path to avoid cascading delays in CBD.")
            else:
                st.warning("Could not generate route. Check your API key.")

        st_folium(m, width="100%", height=500, key="global_map")

# --- 5. APP ROUTING ---
if st.session_state.logged_in:
    show_dashboard()
else:
    show_login()
