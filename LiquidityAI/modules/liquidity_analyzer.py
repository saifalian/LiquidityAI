class LiquidityAnalyzer:
    def __init__(self, cluster_distance_threshold=0.005):
        self.cluster_distance_threshold = cluster_distance_threshold

    def find_clusters(self, price_levels, current_price):
        """
        price_levels: dict of {price: liquidity_value}
        Cluster prices and aggregate liquidity.
        """
        clusters_above = []
        clusters_below = []
        
        # Sort levels by price
        sorted_levels = sorted(price_levels.items(), key=lambda x: x[0])
        
        raw_above = [(p, v) for p, v in sorted_levels if p > current_price]
        raw_below = [(p, v) for p, v in sorted_levels if p < current_price]
        
        # Combine nearby levels into clusters
        clusters_above = self._merge_clusters(raw_above)
        clusters_below = self._merge_clusters(raw_below)
        
        return clusters_above, clusters_below

    def _merge_clusters(self, levels):
        if not levels: return []
        clusters = []
        current_cluster_price = levels[0][0]
        current_cluster_liq = levels[0][1]
        
        for p, v in levels[1:]:
            # If within threshold percentage distance
            if abs(p - current_cluster_price) / current_cluster_price <= self.cluster_distance_threshold:
                current_cluster_liq += v
                # weighted average price
                current_cluster_price = (current_cluster_price * (current_cluster_liq - v) + p * v) / current_cluster_liq
            else:
                clusters.append((current_cluster_price, current_cluster_liq))
                current_cluster_price = p
                current_cluster_liq = v
                
        clusters.append((current_cluster_price, current_cluster_liq))
        return clusters
