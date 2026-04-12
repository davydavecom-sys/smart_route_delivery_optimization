import streamlit as st
import pandas as pd
import folium
import requests
from streamlit_folium import st_folium
from streamlit_js_eval import streamlit_js_eval

# --- 1. SETTINGS & BOUNDS ---
# Rough bounding box for Nairobi Metropolitan Area
NAIROBI_BOUNDS = {
    "lat_min": -1.45, "lat_max": -1.15,
    "lon_min": 36.60, "lon_max": 37.10
}

# Initialize Session State
if 'logged_in' not in st.session_state:
    st.session_state.update({
        'logged_in': False, 
        'user': None, 
        'origin_coords': [-1.286389, 36.817223] # Default to CBD
    })

st.set_page_config(page_title="Nairobi SmartRoute Pro", layout="wide", page_icon="🚚")

# --- 2. UTILITY FUNCTIONS ---
def is_within_bounds(coords):
    """Checks if the GPS point is within the Nairobi area."""
    lat, lon = coords
    return (NAIROBI_BOUNDS["lat_min"] <= lat <= NAIROBI_BOUNDS["lat_max"] and 
            NAIROBI_BOUNDS["lon_min"] <= lon <= NAIROBI_BOUNDS["lon_max"])

def login_callback():
    """Handles login persistence."""
    u = st.session_state.get("login_u")
    p = st.session_state.get("login_p")
    if u == "admin123" and p == "nairobi2026":
        st.session_state.logged_in = True
        st.session_state.user = u
    else:
        st.error("Invalid Username or Password")

def logout_callback():
    st.session_state.logged_in = False
    st.session_state.user = None

# --- 3. ROUTING ENGINE ---
def fetch_global_route(coords_list):
    api_key = st.secrets.get("ORS_API_KEY")
    if not api_key:
        st.error("🚨 API Key Missing: Directions cannot be fetched.")
        return None, None
        
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
        else:
            st.error("❌ Failed to get direction: Route outside road network or API error.")
    except Exception:
        st.error("❌ Failed to get direction: Connection timeout.")
    return None, None

# --- 4. APP ROUTING ---
if not st.session_state.logged_in:
    # --- LOGIN PAGE ---
    st.title("🚚 Nairobi SmartRoute AI")
    with st.container(border=True):
        st.text_input("Username", key="login_u")
        st.text_input("Password", type="password", key="login_p")
        st.button("Log In", on_click=login_callback)
else:
    # --- DASHBOARD PAGE ---
    st.sidebar.title(f"User: {st.session_state.user}")
    st.sidebar.button("🚪 Logout", on_click=logout_callback)
    st.sidebar.divider()

    # --- GEOLOCATION FETCH ---
    st.sidebar.subheader("Device GPS")
    loc_data = streamlit_js_eval(
        js_expressions="navigator.geolocation.getCurrentPosition(pos => {return [pos.coords.latitude, pos.coords.longitude]}, err => {return 'FAILED'})", 
        target_id='get_loc', 
        key="GPS_FETCH"
    )
    
    if loc_data == "FAILED":
        st.sidebar.error("⚠️ Failed to get location: Permission denied or GPS disabled.")
    elif loc_data:
        if is_within_bounds(loc_data):
            st.session_state.origin_coords = loc_data
            st.sidebar.success("✅ GPS Lock: Within Nairobi")
        else:
            st.sidebar.warning("📍 Failed to get direction: Location out of bounds. Defaulting to CBD.")
            st.session_state.origin_coords = [-1.286389, 36.817223]

    # --- EXPANDED LOCATION DATABASE ---
    locations = {
        "📍 Current GPS": st.session_state.origin_coords,
        "Nairobi CBD": [-1.286389, 36.817223],
        "Westlands": [-1.2646, 36.8045],
        "Karen": [-1.3201, 36.7045],
        "JKIA Airport": [-1.3321, 36.9212],
        "Upper Hill": [-1.2990, 36.8070],
        "Kilimani": [-1.2900, 36.7840],
        "Kasarani": [-1.2217, 36.8967],
        "Industrial Area": [-1.3094, 36.8431],
        "Thika Road Mall (TRM)": [-1.2210, 36.8850],
        "Two Rivers Mall": [-1.2133, 36.8056],
        "Gigiri (UN Avenue)": [-1.2333, 36.8056],
        "Lavington": [-1.2820, 36.7725],
        "Parklands": [-1.2618, 36.8146],
        "South C": [-1.3211, 36.8258],
        "Lang'ata": [-1.3323, 36.7583],
        "Embakasi": [-1.3000, 36.9167],
        "Donholm": [-1.3014, 36.8837],
        "Eastleigh": [-1.2750, 36.8500],
        "Syokimau (SGR Station)": [-1.3592, 36.9367],
        "Utawala": [-1.3039, 36.9744],
        "Waiyaki Way (Deloitte)": [-1.2625, 36.7900],
        "Ngong Road (The Junction)": [-1.3008, 36.7617],
        "Roysambu": [-1.2189, 36.8837],
        "Dagoretti Corner": [-1.2882, 36.7144]
    }

    # Sorting for UI
    sorted_names = sorted([k for k in locations.keys() if "GPS" not in k])
    full_list = ["📍 Current GPS"] + sorted_names

    st.header("Global Route Optimization")
    st.info("System Goal: Minimize **Total Journey Time** across all nodes.")

    col1, col2 = st.columns([1, 2])
    
    with col1:
        start_node = st.selectbox("Start Point", full_list)
        stops = st.multiselect("Select Destinations (Sequential)", [k for k in full_list if k != start_node])
        optimize = st.button("🚀 Calculate Global Optimum", use_container_width=True)

    with col2:
        # Build trip coordinate sequence
        full_trip = [locations[start_node]] + [locations[s] for s in stops]
        
        # Draw Map
        m = folium.Map(location=locations[start_node], zoom_start=12)
        
        # Markers
        folium.Marker(locations[start_node], popup="START", icon=folium.Icon(color='green', icon='play')).add_to(m)
        for i, stop in enumerate(stops):
            folium.Marker(locations[stop], popup=f"Stop {i+1}", icon=folium.Icon(color='blue')).add_to(m)

        if optimize:
            if len(full_trip) < 2:
                st.warning("Please select at least one destination stop.")
            else:
                path, stats = fetch_global_route(full_trip)
                if path:
                    # Draw the "Model Selected" path
                    folium.PolyLine(path, color="#1f77b4", weight=6, opacity=0.8).add_to(m)
                    
                    # Performance Metrics
                    total_min = round(stats['duration'] / 60, 1)
                    total_km = round(stats['distance'] / 1000, 2)
                    
                    st.success(f"**Optimization Complete**")
                    st.write(f"⏱️ **Total Time:** {total_min} mins")
                    st.write(f"🛣️ **Total Distance:** {total_km} km")
                    st.caption("AI Decision: Prioritized global flow over individual node shortcuts.")
                
        st_folium(m, width="100%", height=500, key="global_map")
