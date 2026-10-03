"""
A simple script to update config.json with dummy bounding boxes.
In a real environment, this script would launch a PyAutoGUI or OpenCV click-and-drag listener
to allow users to select their exact Coinglass UI coordinates dynamically.
"""
import sys
import json
import os

print("--- LiquidityAI Calibration Wizard ---")
print("We need to mark 3 areas on your screen:")
print("1. Heatmap Area")
print("2. Threshold Slider")
print("3. Price Axis")
print("4. Pair Search Button")
print("")
print("Writing default bounding boxes to config.json ...")

config_file = 'config.json'

if not os.path.exists(config_file):
    print("Run this from the project root where config.json exists.")
    sys.exit(1)

with open(config_file, 'r') as f:
    config = json.load(f)

# Hardcoded defaults for demonstration.
config['heatmap_bbox'] = {'top': 200, 'left': 300, 'width': 800, 'height': 500}
config['slider_bbox'] = {'top': 150, 'left': 600, 'width': 200, 'height': 20}
config['price_axis_bbox'] = {'top': 200, 'left': 1100, 'width': 100, 'height': 500}
config['pair_search_btn_bbox'] = {'top': 50, 'left': 100, 'width': 50, 'height': 25}

with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)

print("Configuration updated inside config.json.")
print("Calibration complete.")
