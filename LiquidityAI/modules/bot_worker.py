from PyQt5.QtCore import QThread, pyqtSignal
import time
import json
import os
import threading
from datetime import datetime

from modules.screen_capture import ScreenCapture
from modules.ocr_reader import OCRReader
from modules.threshold_learner import ThresholdLearner
from modules.liquidity_analyzer import LiquidityAnalyzer
from modules.feature_extractor import FeatureExtractor
from modules.online_model import OnlineModel
from modules.prediction_engine import PredictionEngine
from modules.log_manager import LogManager
from modules.coinglass_automator import CoinglassAutomator


class BotWorker(QThread):
    log_msg        = pyqtSignal(str)
    prediction_made = pyqtSignal(dict)
    bot_stopped    = pyqtSignal()

    def __init__(self, pair, mode='predict'):
        super().__init__()
        self.pair       = pair
        self.mode       = mode
        self.is_running = True
        self.is_paused  = False
        # Use a threading.Event so stop() wakes the thread immediately
        self._stop_event = threading.Event()

    def load_config(self):
        try:
            with open("config.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            self.log_msg.emit("config.json not found! Please run Calibration first.")
            return None

    def run(self):
        config = self.load_config()
        if not config:
            self.bot_stopped.emit()
            return

        self.log_msg.emit(f"Initializing bot for {self.pair}...")

        capturer        = ScreenCapture()
        ocr             = OCRReader()
        threshold_learner = ThresholdLearner(target_ratio=0.35)
        analyzer        = LiquidityAnalyzer()
        extractor       = FeatureExtractor()
        model           = OnlineModel()
        predictor       = PredictionEngine(confidence_threshold=config.get('confidence_min', 0.6))
        logger          = LogManager(log_dir=config.get('log_dir', './logs'))
        automator       = CoinglassAutomator(config)

        past_weights = logger.load_model_weights(self.pair)
        if past_weights:
            model.model = past_weights
            self.log_msg.emit(f"Loaded existing AI memory for {self.pair}.")

        self.log_msg.emit(f"Starting in {self.mode.upper()} mode for {self.pair}...")

        scan_interval = config.get('scan_interval_seconds', 3)

        while self.is_running and not self._stop_event.is_set():
            if self.is_paused:
                # Sleep in small chunks so stop() is responsive
                self._stop_event.wait(timeout=1)
                continue

            try:
                # Always wait for the spinner to clear before reading the screen
                automator.wait_for_loading()

                heatmap_img = capturer.capture_region(config['heatmap_bbox'])

                noise_ratio = threshold_learner.evaluate_heatmap_noise(heatmap_img)
                action      = threshold_learner.determine_action(noise_ratio)
                if action != "hold":
                    self.log_msg.emit(f"Auto-adjusting slider: {action}")
                    automator.adjust_slider(action)

                current_price = 1.0
                dummy_levels  = {
                    1.01: 500000, 1.02: 1200000, 1.05: 3000000,
                    0.99: 400000, 0.98: 1500000, 0.95: 2500000
                }

                clusters_above, clusters_below = analyzer.find_clusters(dummy_levels, current_price)
                features = extractor.extract(current_price, dummy_levels, clusters_above, clusters_below)

                if self.mode == 'observe':
                    self.log_msg.emit(
                        f"[{datetime.now().strftime('%H:%M:%S')}] Observing -> Features Extracted."
                    )

                elif self.mode == 'predict':
                    probs  = model.predict_proba(features)
                    signal = predictor.evaluate(probs, current_price, features)

                    self.log_msg.emit(
                        f"[{datetime.now().strftime('%H:%M:%S')}] "
                        f"{signal['direction']} (Conf: {signal['confidence']:.2f}) -> {signal['reason']}"
                    )

                    signal['time']          = datetime.now().strftime('%H:%M:%S')
                    signal['current_price'] = current_price
                    self.prediction_made.emit(signal)
                    logger.log_prediction(self.pair, features, signal)

                logger.save_model_weights(self.pair, model.model)

            except Exception as e:
                self.log_msg.emit(f"Error during scan: {e}")

            # Interruptible sleep — wakes immediately when stop() is called
            self._stop_event.wait(timeout=scan_interval)

        capturer.close()
        self.log_msg.emit(f"Bot for {self.pair} stopped.")
        self.bot_stopped.emit()

    def pause(self):
        self.is_paused = True
        self.log_msg.emit(f"Bot for {self.pair} paused.")

    def resume(self):
        self.is_paused = False
        self.log_msg.emit(f"Bot for {self.pair} resumed.")

    def stop(self):
        self.is_running = False
        self._stop_event.set()   # wake the sleeping thread immediately
        self.log_msg.emit(f"Stopping bot for {self.pair}...")
