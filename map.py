pip install osmnx stable-baselines3 gymnasium

import osmnx as ox
import json
import os
import random

# Create a 'data' folder to store everything
if not os.path.exists('data'):
    os.makedirs('data')

def download_materials():
    print("Step 1: Downloading Nairobi Road Network...")
    # Fetching the drivable network for Nairobi
    G = ox.graph_from_place("Nairobi, Kenya", network_type="drive")
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)

    # Save the graph locally so you don't have to download it again
    ox.save_graphml(G, filepath="data/nairobi_graph.graphml")
    print("✅ Nairobi Map saved to data/nairobi_graph.graphml")

    print("Step 2: Creating Traffic Snapshots (Simulated TomTom/Waze)...")
    traffic_profiles = {}

    # Off-peak traffic (base travel times)
    off_peak_profile = {f"{u}_{v}_{k}": 1.0 for u, v, k in G.edges(keys=True)}
    traffic_profiles['off_peak'] = off_peak_profile

    # Morning rush hour (higher multipliers for some edges, simulating congestion)
    morning_rush_profile = {f"{u}_{v}_{k}": 1.0 for u, v, k in G.edges(keys=True)}
    for u, v, k in random.sample(list(G.edges(keys=True)), int(len(G.edges) * 0.3)): # 30% of edges affected
        morning_rush_profile[f"{u}_{v}_{k}"] = random.uniform(1.5, 2.5) # 50% to 150% increase
    traffic_profiles['morning_rush'] = morning_rush_profile

    # Evening rush hour (different set of edges, potentially different multipliers)
    evening_rush_profile = {f"{u}_{v}_{k}": 1.0 for u, v, k in G.edges(keys=True)}
    for u, v, k in random.sample(list(G.edges(keys=True)), int(len(G.edges) * 0.3)): # 30% of edges affected
        evening_rush_profile[f"{u}_{v}_{k}"] = random.uniform(1.7, 3.0) # 70% to 200% increase
    traffic_profiles['evening_rush'] = evening_rush_profile

    with open('data/traffic_profiles.json', 'w') as f:
        json.dump(traffic_profiles, f)
    print("✅ Simulated Traffic Profiles saved to data/traffic_profiles.json")

download_materials()


import gymnasium as gym
from gymnasium import spaces
import numpy as np
import networkx as nx
import random

class SmartDeliveryEnv(gym.Env):
    def __init__(self, graph, num_packages=3, traffic_data=None):
        super(SmartDeliveryEnv, self).__init__()

        # 1. Setup the Map (Nairobi Graph)
        self.G = graph
        self.nodes = list(graph.nodes())
        self.node_to_idx = {node: i for i, node in enumerate(self.nodes)}
        self.num_nodes = len(self.nodes)
        self.num_packages = num_packages

        # 2. Define Action Space: Choose index of the next node to visit
        self.action_space = spaces.Discrete(self.num_nodes)

        # 3. Define Observation Space: [CurrentNodeIdx, Target1, Target2, Target3, WeatherIdx]
        # All values normalized between 0 and 1 to help the AI learn faster
        self.observation_space = spaces.Box(
            low=0, high=1, shape=(self.num_packages + 3,), dtype=np.float32 # Added space for time_of_day
        )

        # Initialize variables
        self.traffic_data = traffic_data if traffic_data is not None else {'off_peak': {}}
        self.current_traffic = {}
        self.weather_multiplier = 1.0
        self.current_time_of_day = 0 # 0:off_peak, 0.5:morning_rush, 1.0:evening_rush

    def _get_obs(self):
        """Calculates the normalized state vector for the model."""
        obs = [self.node_to_idx[self.current_node] / self.num_nodes]
        for target in self.delivery_targets:
            obs.append(self.node_to_idx[target] / self.num_nodes)

        # Add weather (0.0 for clear, 1.0 for rain)
        obs.append(0.0 if self.weather_multiplier == 1.0 else 1.0)

        # Add time of day (0.0 for off-peak, 0.5 for morning rush, 1.0 for evening rush)
        obs.append(self.current_time_of_day)

        return np.array(obs, dtype=np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)

        # Randomize Start and Arrivals in Nairobi
        self.current_node = random.choice(self.nodes)
        self.delivery_targets = random.sample(self.nodes, self.num_packages)

        # Randomize Weather for this episode
        self.weather_multiplier = random.choice([1.0, 1.3, 1.8]) # Clear, Rain, Heavy Rain

        # Randomize Traffic Scenario (Time of Day)
        time_of_day_choice = random.choice(list(self.traffic_data.keys()))
        self.current_traffic = self.traffic_data[time_of_day_choice]

        if time_of_day_choice == 'off_peak':
            self.current_time_of_day = 0.0
        elif time_of_day_choice == 'morning_rush':
            self.current_time_of_day = 0.5
        else: # evening_rush
            self.current_time_of_day = 1.0

        return self._get_obs(), {}

    def step(self, action):
        target_node = self.nodes[action]

        # 1. Calculate travel cost using the Nairobi graph weights
        try:
            # We use 'travel_time' from OSMnx + our multipliers
            # Find the edge between current_node and target_node
            # OSMnx graphs can have multiple edges between two nodes (multigraph)
            # We'll take the minimum travel time edge
            min_base_time = float('inf')
            selected_edge_key = None

            for k, data in self.G.get_edge_data(self.current_node, target_node, default={}).items(): # Changed unpack from 4 to 2
                if 'travel_time' in data:
                    if data['travel_time'] < min_base_time:
                        min_base_time = data['travel_time']
                        selected_edge_key = k

            if selected_edge_key is None: # No direct edge found, try shortest path length
                base_time = nx.shortest_path_length(self.G, self.current_node, target_node, weight='travel_time')
                traffic_mult = 1.0 # No specific edge for traffic, use general multiplier
            else:
                base_time = min_base_time
                traffic_mult = self.current_traffic.get(f"{self.current_node}_{target_node}_{selected_edge_key}", 1.0)

            total_cost = base_time * traffic_mult * self.weather_multiplier
            reward = -total_cost / 100.0 # Reward is negative minutes spent

            # Move the agent
            self.current_node = target_node

        except nx.NetworkXNoPath:
            # Huge penalty if the agent picks a disconnected part of Nairobi
            reward = -5.0
            total_cost = 5.0

        # 2. Check if a delivery was made
        if self.current_node in self.delivery_targets:
            reward += 100.0 # Delivery Bonus!
            self.delivery_targets.remove(self.current_node)
            # Add a new random delivery to keep the simulation going
            self.delivery_targets.append(random.choice(self.nodes))

        # 3. Termination Logic
        # In this version, we let it run for a fixed number of steps or until 10 deliveries
        terminated = False
        truncated = False # Add logic here if you want a time limit per episode

        return self._get_obs(), reward, terminated, truncated, {}



from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor
import json
import os

# Load the local graph
import osmnx as ox
G = ox.load_graphml("data/nairobi_graph.graphml")

# Load simulated traffic profiles
with open('data/traffic_profiles.json', 'r') as f:
    traffic_profiles_data = json.load(f)

# Define the log directory (consistent with plotting cell)
log_dir = "/content/drive/MyDrive/Nairobi_Project/logs/"
os.makedirs(log_dir, exist_ok=True)

# Initialize Environment with traffic data and wrap it with Monitor
env = SmartDeliveryEnv(graph=G, num_packages=5, traffic_data=traffic_profiles_data)
env = Monitor(env, log_dir) # Wrap the environment with Monitor HERE

# Initialize Model (The Brain)
model = PPO("MlpPolicy", env, verbose=1, tensorboard_log="./logs/")

print("Starting Training...")
model.learn(total_timesteps=500000)
print("✅ Training Complete.")


