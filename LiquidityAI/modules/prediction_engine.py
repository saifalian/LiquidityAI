class PredictionEngine:
    def __init__(self, confidence_threshold=0.60):
        self.confidence_threshold = confidence_threshold

    def evaluate(self, probabilities, current_price, features):
        """
        Evaluates class probabilities and outputs a trade signal structure.
        """
        p_up = probabilities.get("UP", 0)
        p_down = probabilities.get("DOWN", 0)
        
        direction = "NEUTRAL"
        confidence = probabilities.get("NEUTRAL", 0)
        
        # Determine direction based on threshold
        if p_up > self.confidence_threshold and p_up > p_down:
            direction = "UP"
            confidence = p_up
        elif p_down > self.confidence_threshold and p_down > p_up:
            direction = "DOWN"
            confidence = p_down
            
        # Construct reason string
        liq_diff = features.get('liquidity_diff', 0)
        prefix = "+" if liq_diff > 0 else ""
        reason = f"Diff: {prefix}{liq_diff:.1f}, Clusters Above: {features.get('cluster_count_above',0)}"
            
        # Rough target estimate based on simple 0.5% move (could integrate with nearest_cluster dist)
        target_price = current_price
        stop_loss = current_price
        if direction == "UP":
            target_price = current_price * 1.005 # 0.5% TP
            stop_loss = current_price * 0.995    # 0.5% SL
        elif direction == "DOWN":
            target_price = current_price * 0.995 # 0.5% TP
            stop_loss = current_price * 1.005    # 0.5% SL
            
        return {
            "direction": direction,
            "confidence": confidence,
            "target_price": target_price,
            "stop_loss": stop_loss,
            "reason": reason
        }
