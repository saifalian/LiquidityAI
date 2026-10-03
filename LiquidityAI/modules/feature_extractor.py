class FeatureExtractor:
    def __init__(self):
        self.history = []

    def extract(self, current_price, price_levels, clusters_above, clusters_below):
        """
        Constructs a feature vector for ML.
        """
        # 1. Total upper/lower liquidity
        upper_liq = sum(v for p, v in price_levels.items() if p > current_price)
        lower_liq = sum(v for p, v in price_levels.items() if p < current_price)
        
        # 2. Diff
        liquidity_diff = upper_liq - lower_liq
        
        # 3. Cluster counts
        cluster_count_above = len(clusters_above)
        cluster_count_below = len(clusters_below)
        
        # 4. Nearest distances
        nearest_short_dist = (clusters_above[0][0] - current_price) / current_price if clusters_above else 1.0
        nearest_long_dist = (current_price - clusters_below[-1][0]) / current_price if clusters_below else 1.0
        
        # 5. Price Velocity (requires history)
        price_velocity = 0.0
        if self.history:
            prev_price = self.history[-1]['price']
            price_velocity = (current_price - prev_price) / prev_price
            
        recent_sweeps = 0 # Placeholder for swept cluster tracking
        
        features = {
            'upper_liq': upper_liq,
            'lower_liq': lower_liq,
            'liquidity_diff': liquidity_diff,
            'cluster_count_above': cluster_count_above,
            'cluster_count_below': cluster_count_below,
            'nearest_short_dist': nearest_short_dist,
            'nearest_long_dist': nearest_long_dist,
            'price_velocity': price_velocity,
            'recent_sweeps': recent_sweeps
        }
        
        self.history.append({'price': current_price, 'features': features})
        # Keep window manageable
        if len(self.history) > 20: self.history.pop(0)
            
        return features
