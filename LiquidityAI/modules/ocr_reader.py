import cv2
import pytesseract
import numpy as np
import re

# You may need to set tesseract_cmd if it's not in PATH
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class OCRReader:
    def __init__(self, tesseract_path=None):
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        else:
            pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

    def preprocess_image(self, img):
        """
        Preprocesses image for better OCR accuracy:
        - Convert to grayscale
        - Thresholding
        - Scaling
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Scaling up helps Tesseract read small numbers
        scaled = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        
        # Apply thresholding
        _, thresh = cv2.threshold(scaled, 150, 255, cv2.THRESH_BINARY_INV)
        return thresh

    def read_text(self, img):
        """
        Extract raw text from an image region.
        """
        processed = self.preprocess_image(img)
        # --psm 7 is single uniform line of text, good for prices/liquidity values
        config = "--psm 7 -c tessedit_char_whitelist=0123456789.KkMmBb"
        text = pytesseract.image_to_string(processed, config=config).strip()
        return text

    def parse_liquidity_value(self, text):
        """
        Parses strings like '1.4M', '500K' to float values representing raw numbers.
        """
        text = text.upper().replace(' ', '')
        match = re.match(r'^([\d\.]+)([KMB]?)$', text)
        if not match:
            return None
        
        value_str, multiplier_str = match.groups()
        try:
            value = float(value_str)
        except ValueError:
            return None
            
        multiplier = 1
        if multiplier_str == 'K':
            multiplier = 1_000
        elif multiplier_str == 'M':
            multiplier = 1_000_000
        elif multiplier_str == 'B':
            multiplier = 1_000_000_000
            
        return value * multiplier

    def read_liquidity(self, img):
        text = self.read_text(img)
        return self.parse_liquidity_value(text)

if __name__ == "__main__":
    # Test script setup
    print("OCRReader initialization complete.")
