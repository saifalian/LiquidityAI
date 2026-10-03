import cv2
import numpy as np

class ThresholdLearner:
    def __init__(self, target_ratio=0.35, tolerance=0.05):
        # target_ratio is the ideal percentage of colored pixels (30-40%)
        self.target_ratio = target_ratio
        self.tolerance = tolerance

    def evaluate_heatmap_noise(self, heatmap_img):
        """
        Evaluates what percentage of the heatmap is 'active' (colored vs empty/dark).
        heatmap_img should be a BGR numpy array.
        """
        if heatmap_img is None or heatmap_img.size == 0:
            return 0
            
        # Convert to HSV to easily separate dark/empty background from bright colors
        hsv = cv2.cvtColor(heatmap_img, cv2.COLOR_BGR2HSV)
        # Value (Brightness) channel
        v = hsv[:, :, 2]
        
        # Consider a pixel 'active' if it's reasonably bright
        # Coinglass dark areas are usually low in Value
        active_pixels = cv2.countNonZero(cv2.threshold(v, 40, 255, cv2.THRESH_BINARY)[1])
        total_pixels = heatmap_img.shape[0] * heatmap_img.shape[1]
        
        ratio = active_pixels / total_pixels if total_pixels > 0 else 0
        return ratio
        
    def determine_action(self, current_ratio):
        """
        Given the current ratio, returns an action string for the slider.
        """
        if current_ratio > self.target_ratio + self.tolerance:
            return "increase_threshold"  # Need less color (move slider right)
        elif current_ratio < self.target_ratio - self.tolerance:
            return "decrease_threshold"  # Need more color (move slider left)
        else:
            return "hold"
