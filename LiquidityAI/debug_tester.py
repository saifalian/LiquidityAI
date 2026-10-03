import pyautogui
import cv2
import numpy as np
import time
import os

def test_find_price():
    # Attempt to capture the screen and find the price label like the automator does.
    print("Testing price finding...")
    win_left, win_top, win_width, win_height = 0, 0, 1920, 1080 # Assuming full screen for testing, or we can use the whole screen
    screenshot = pyautogui.screenshot()
    img_rgb = np.array(screenshot)
    img_bgr = img_rgb[:, :, ::-1]

    # Limit to rightmost 80 pixels instead of 120
    axis_l = max(0, win_left + win_width - 80)
    axis_r = min(img_bgr.shape[1], win_left + win_width)
    axis_t = max(0, win_top + 30)
    axis_b = min(img_bgr.shape[0], win_top + win_height - 30)

    roi = img_bgr[axis_t:axis_b, axis_l:axis_r]
    cv2.imwrite("debug_axis_crop.png", roi)
    
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hsv_ranges = [
        (np.array([35, 60, 60], dtype=np.uint8),  np.array([90, 255, 255], dtype=np.uint8)),
        (np.array([80, 60, 60], dtype=np.uint8),  np.array([100, 255, 255], dtype=np.uint8)),
        (np.array([25, 40, 40], dtype=np.uint8),  np.array([105, 255, 255], dtype=np.uint8)),
        (np.array([0, 60, 60], dtype=np.uint8),   np.array([10, 255, 255], dtype=np.uint8)),
        (np.array([160, 60, 60], dtype=np.uint8), np.array([180, 255, 255], dtype=np.uint8)),
    ]

    best_contour = None
    best_area = 0

    for low, high in hsv_ranges:
        mask = cv2.inRange(hsv, low, high)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest)
            if area > best_area:
                best_area = area
                best_contour = largest
                cv2.imwrite("debug_best_mask.png", mask)

    if best_contour is None or best_area < 30:
        print(f"Could not detect the price label. Best area={best_area}")
        return False

    bx, by, bw, bh = cv2.boundingRect(best_contour)
    # Draw logic to see what it found
    debug_roi = roi.copy()
    cv2.rectangle(debug_roi, (bx, by), (bx+bw, by+bh), (0, 255, 0), 2)
    cv2.imwrite("debug_found_price.png", debug_roi)
    
    price_screen_y = axis_t + by + bh // 2
    scan_x = win_left + int(win_width * 0.75)  # Deeper into the chart
    print(f"Anchoring scan at X={scan_x}, Base Y={price_screen_y}")
    return True

if __name__ == "__main__":
    time.sleep(3) # Give user a sec to focus window
    test_find_price()
