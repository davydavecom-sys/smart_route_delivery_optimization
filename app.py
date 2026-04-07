import streamlit as st
import folium
from streamlit_folium import st_folium
import osmnx as ox
from stable_baselines3 import PPO
import networkx as nx
import os

# --- 1. CONFIG & ASSETS ---
st.set_page_config(page_title="Nairobi Multi-Stop AI", layout="wide")

@st.cache_resource
def load_assets():
    model_path = "nairobi_smart_delivery_v1.zip"
    model = PPO.load(model_path) if os.path.exists(model_path) else None
    # Loading a larger 5km radius to cover more delivery areas
    try:
        G = ox.graph_from_point((-1.286389, 36.817223), dist=5000, network_type='drive')
    except:
        G = None
    return model, G

model, G = load_assets()

# --- 2. SESSION STATE ---
if 'optimized_path' not in st.session_state:
    st.session_state.optimized_path = None
if 'ordered_labels' not in st.session_state:
    st.session_state.ordered_labels = []

# --- 3. DELIVERY LOCATIONS ---
locations = {
    "Nairobi CBD": (-1.286389, 36.817223),
    "Westlands": (-1.3115, 36.8117),
    "Upper Hill": (-1.2997, 36.8143),
    "Kilimani": (-1.2921, 36.7845),
    "Kasarani": (-1.2268, 36.8938),
    "South C": (-1.3265, 36.8256),
    "Eastleigh": (-1.2748, 36.8465),
    "Karen": (-1.3201, 36.7024)
}

# --- 4. SIDEBAR ---
st.sidebar.title("📦 Smart Dispatcher")
start_node_label = st.sidebar.selectbox("Current Location (Start)", list(locations.keys()))
delivery_stops = st.sidebar.multiselect("Select All Pickups & Drops (In any order)", 
                                        [k for k in locations.keys() if k != start_node_label])

optimize_btn = st.sidebar.button("⛽ Optimize Fuel & Time", use_container_width=True)

# --- 5. THE OPTIMIZATION ENGINE ---
def get_best_sequence(start_label, stops_list):
    """Reorders stops to minimize total distance (Greedy TSP)"""
    ordered = [start_label]
    remaining = list(stops_list)
    
    current_label = start_label
    while remaining:
        # Find the physically closest stop to the current location
        next_label = min(remaining, key=lambda x: ox.distance.euclidean(
            locations[current_label][0], locations[current_label][1],
            locations[x][0], locations[x][1]
        ))
        ordered.append(next_label)
        remaining.remove(next_label)
        current_label = next_label
    return ordered

if optimize_btn:
    if not delivery_stops:
        st.error("Please select at least one delivery stop.")
    else:
        with st.spinner("Reordering stops to save fuel..."):
            # A. AUTO-REORDER (The Manager)
            best_sequence = get_best_sequence(start_node_label, delivery_stops)
            st.session_state.ordered_labels = best_sequence
            
            # B. NAVIGATE EACH LEG (The AI Model)
            full_coords = []
            for i in range(len(best_sequence) - 1):
                loc_a = locations[best_sequence[i]]
                loc_b = locations[best_sequence[i+1]]
                
                node_a = ox.distance.nearest_nodes(G, X=loc_a[1], Y=loc_a[0])
                node_b = ox.distance.nearest_nodes(G, X=loc_b[1], Y=loc_b[0])
                
                # Here, the model's learned 'weights' would guide the path
                # For this UI, we use the shortest path between the optimized stops
                path = nx.shortest_path(G, node_a, node_b, weight='length')
                for node in path:
                    full_coords.append((G.nodes[node]['y'], G.nodes[node]['x']))
            
            st.session_state.optimized_path = full_coords

# --- 6. MAP & DISPLAY ---
st.title("🚀 Nairobi AI Fleet Optimizer")

if st.session_state.ordered_labels:
    st.subheader("Optimized Manifest")
    # Show the sequence to the driver
    arrow_path = " ⮕ ".join([f"**{lbl}**" for lbl in st.session_state.ordered_labels])
    st.markdown(arrow_path)

# Build Map
m = folium.Map(location=locations["Nairobi CBD"], zoom_start=12, tiles="cartodbpositron")

if st.session_state.optimized_path:
    # Draw the AI's full path
    folium.PolyLine(st.session_state.optimized_path, color="#2A9D8F", weight=6).add_to(m)
    
    # Place markers in the correct order
    for idx, label in enumerate(st.session_state.ordered_labels):
        color = 'blue' if idx == 0 else ('red' if idx == len(st.session_state.ordered_labels)-1 else 'green')
        folium.Marker(
            locations[label], 
            popup=f"Stop {idx}: {label}",
            icon=folium.Icon(color=color, icon='play' if idx==0 else 'info-sign')
        ).add_to(m)
    
    m.fit_bounds(st.session_state.optimized_path)

st_folium(m, width=1200, height=550, key="nairobi_delivery_map")