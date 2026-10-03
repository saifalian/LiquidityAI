import argparse
import pandas as pd
import os

def analyze(pair, log_dir):
    filepath = os.path.join(log_dir, f"{pair.lower()}_predictions.csv")
    if not os.path.exists(filepath):
        print(f"No logs found for {pair} at {filepath}")
        return
        
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    if len(df) == 0:
        print("Log is empty.")
        return
        
    print(f"--- Performance Dashboard for {pair} ---")
    print(f"Total Predictions Logged: {len(df)}")
    
    # In a full live product, a secondary script populates 'actual_outcome' and 'correct'.
    if 'correct' in df.columns and pd.to_numeric(df['correct'], errors='coerce').notnull().sum() > 0:
        # Assuming 'correct' is 1 for True, 0 for False (or boolean)
        df['correct_numeric'] = pd.to_numeric(df['correct'], errors='coerce')
        correct_count = df['correct_numeric'].sum()
        
        accuracy = (correct_count / len(df)) * 100 if len(df) > 0 else 0
        print(f"Overall Accuracy: {accuracy:.2f}%")
        
        up_preds = df[df['direction'] == 'UP']
        if len(up_preds) > 0:
            up_acc = (up_preds['correct_numeric'].sum() / len(up_preds)) * 100
            print(f"UP Signal Accuracy: {up_acc:.2f}% (Count: {len(up_preds)})")
            
        down_preds = df[df['direction'] == 'DOWN']
        if len(down_preds) > 0:
            down_acc = (down_preds['correct_numeric'].sum() / len(down_preds)) * 100
            print(f"DOWN Signal Accuracy: {down_acc:.2f}% (Count: {len(down_preds)})")
    else:
        print("Note: 'correct' column not yet populated by outcome validator.")
        print("Signal Distribution:")
        print(df['direction'].value_counts())
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", type=str, required=True)
    parser.add_argument("--logs", type=str, default="./logs")
    args = parser.parse_args()
    
    analyze(args.pair, args.logs)
