import sys
import json
import time
import argparse
from datetime import datetime

# Import modules
from modules.screen_capture import ScreenCapture
from modules.ocr_reader import OCRReader
from modules.threshold_learner import ThresholdLearner
from modules.liquidity_analyzer import LiquidityAnalyzer
from modules.feature_extractor import FeatureExtractor
from modules.online_model import OnlineModel
from modules.prediction_engine import PredictionEngine
from modules.log_manager import LogManager

def load_config():
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("config.json not found! Run calibrate.py first.")
        sys.exit(1)

def run_bot(mode, pair, duration_minutes=None):
    config = load_config()
    
    # Initialize components
    capturer = ScreenCapture()
    ocr = OCRReader()
    threshold_learner = ThresholdLearner(target_ratio=0.35)
    analyzer = LiquidityAnalyzer()
    extractor = FeatureExtractor()
    model = OnlineModel()
    predictor = PredictionEngine(confidence_threshold=config.get('confidence_min', 0.6))
    logger = LogManager(log_dir=config.get('log_dir', './logs'))
    
    # Load past memory
    past_weights = logger.load_model_weights(pair)
    if past_weights:
        model.model = past_weights
        print(f"Loaded existing memory for {pair}.")
        
    print(f"Starting LiquidityAI in {mode.upper()} mode for {pair}...")
    
    start_time = time.time()
    
    if mode == 'predict':
        print("NOTE: For the overlay UI to run, launch python modules/overlay.py separately.")

    while True:
        try:
            # 1. Capture screen
            heatmap_img = capturer.capture_region(config['heatmap_bbox'])
            
            # 2. Threshold check
            noise_ratio = threshold_learner.evaluate_heatmap_noise(heatmap_img)
            action = threshold_learner.determine_action(noise_ratio)
            if action != "hold":
                print(f"Auto-adjusting slider: {action}")
                # Real implementation would pyautogui.drag the slider here.
                
            # 3. Simulate Data Read (OCR on price axis)
            # Because we lack a live browser, we use mock price levels to simulate the loop
            current_price = 1.0
            dummy_levels = {
                1.01: 500000, 1.02: 1200000, 1.05: 3000000,
                0.99: 400000, 0.98: 1500000, 0.95: 2500000 
            }
            
            # 4. Analyze liquidity
            clusters_above, clusters_below = analyzer.find_clusters(dummy_levels, current_price)
            
            # 5. Extract Features
            features = extractor.extract(current_price, dummy_levels, clusters_above, clusters_below)
            
            # 6. Predict & Train
            if mode == 'observe':
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Observing {pair} -> Features Extracted. Waiting...")
                
            elif mode == 'predict':
                probs = model.predict_proba(features)
                signal = predictor.evaluate(probs, current_price, features)
                
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {signal['direction']} (Conf: {signal['confidence']:.2f}) -> {signal['reason']}")
                
                logger.log_prediction(pair, features, signal)
            
            # Save periodic weights
            logger.save_model_weights(pair, model.model)
            
            # Duration limit
            if duration_minutes and (time.time() - start_time) > (duration_minutes * 60):
                print("Time limit reached. Exiting.")
                break
                
            time.sleep(config.get('scan_interval_seconds', 3))
            
        except KeyboardInterrupt:
            print("Stopping...")
            break
            
    capturer.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=['observe', 'predict'], required=True)
    parser.add_argument("--pair", type=str, required=True, help="e.g. XRPUSDT")
    parser.add_argument("--duration", type=int, help="Minutes to run before stopping (for observe)")
    args = parser.parse_args()
    
    run_bot(args.mode, args.pair, args.duration)
