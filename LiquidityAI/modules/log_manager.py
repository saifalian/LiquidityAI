import os
import csv
from datetime import datetime

class LogManager:
    def __init__(self, log_dir="./logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
    def log_prediction(self, pair, features, prediction):
        """
        Logs a single prediction iteration to CSV.
        """
        filepath = os.path.join(self.log_dir, f"{pair.lower()}_predictions.csv")
        file_exists = os.path.isfile(filepath)
        
        with open(filepath, 'a', newline='') as csvfile:
            fieldnames = ['timestamp', 'pair', 'direction', 'confidence', 'target_price', 'reason', 'actual_outcome', 'correct']
            for k in features.keys():
                fieldnames.append(f"feat_{k}")
                
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
                
            row = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'pair': pair,
                'direction': prediction['direction'],
                'confidence': prediction['confidence'],
                'target_price': prediction['target_price'],
                'reason': prediction['reason'],
                'actual_outcome': '',
                'correct': ''
            }
            for k, v in features.items():
                row[f"feat_{k}"] = v
                
            writer.writerow(row)
            
    def save_model_weights(self, pair, model):
        """Saves model state using pickle."""
        import pickle
        filepath = os.path.join(self.log_dir, f"{pair.lower()}_model.pkl")
        with open(filepath, 'wb') as f:
            pickle.dump(model, f)
            
    def load_model_weights(self, pair):
        """Loads model if it exists."""
        import pickle
        filepath = os.path.join(self.log_dir, f"{pair.lower()}_model.pkl")
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                return pickle.load(f)
        return None
