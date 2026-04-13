# --- 3. ROUTING ENGINE (Updated for Alternatives) ---
def fetch_global_route(coords_list):
    api_key = st.secrets.get("ORS_API_KEY")
    if not api_key: return None, None
    
    formatted = [[c[1], c[0]] for c in coords_list]
    url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
    
    # Requesting up to 2 alternative routes
    payload = {
        "coordinates": formatted,
        "alternative_routes": {"target_count": 2, "share_factor": 0.6}
    }
    
    try:
        r = requests.post(url, json=payload, 
                          headers={'Authorization': api_key, 'Content-Type': 'application/json'}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            routes = []
            for feature in data['features']:
                # Extract coordinates and stats for each route
                path = [[p[1], p[0]] for p in feature['geometry']['coordinates']]
                stats = feature['properties']['summary']
                routes.append({"path": path, "stats": stats})
            return routes # Now returns a list of route objects
    except Exception as e:
        st.error(f"Routing Error: {e}")
    return None

# --- 5. MAIN DASHBOARD (Updated Map Drawing) ---
# ... inside your choice == "Route Optimizer" logic ...

    if st.button("🚀 Optimize Path", use_container_width=True):
        full_trip = [locations[start]] + [locations[s] for s in stops]
        if len(full_trip) >= 2:
            with st.spinner("Calculating all possible paths..."):
                all_routes = fetch_global_route(full_trip)
                # Store the list of routes in session state
                st.session_state.path_to_draw = all_routes 
        else: st.warning("Add stops to optimize.")

# ... inside the with c2: block (Map Drawing) ...

    if st.session_state.path_to_draw:
        all_routes = st.session_state.path_to_draw
        
        # Draw Alternatives first (so they are 'under' the main route)
        for i, route in enumerate(all_routes[1:]):
            folium.PolyLine(
                route['path'], 
                color="#7FB3D5", # Lighter blue for alternatives
                weight=4, 
                opacity=0.6,
                dash_array='10', # Dashed line to distinguish it
                tooltip=f"Alternative {i+1}: {round(route['stats']['duration']/60, 1)} mins"
            ).add_to(m)
            
        # Draw the Primary Route (always the first one in the list)
        primary = all_routes[0]
        folium.PolyLine(
            primary['path'], 
            color="#1f77b4", 
            weight=7, 
            opacity=0.9,
            tooltip=f"Optimal: {round(primary['stats']['duration']/60, 1)} mins"
        ).add_to(m)
        
        st.success(f"Best Route: {round(primary['stats']['duration']/60, 1)} mins")
