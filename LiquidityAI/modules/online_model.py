from river import forest

class OnlineModel:
    def __init__(self):
        # Using Adaptive Random Forest from river for online learning
        self.model = forest.ARFClassifier(n_models=10, seed=42)
        
    def train_step(self, features_dict, target_label):
        """
        Updates the model with a single new observation.
        features_dict: dictionary mapping feature names to values
        target_label: "UP", "DOWN", or "NEUTRAL"
        """
        self.model.learn_one(features_dict, target_label)
        
    def predict_proba(self, features_dict):
        """
        Predicts probabilities for each class.
        Returns a dictionary like {"UP": 0.6, "DOWN": 0.3, "NEUTRAL": 0.1}
        """
        proba = self.model.predict_proba_one(features_dict)
        
        # Ensure all classes are present in output (river might omit unseen classes)
        for label in ["UP", "DOWN", "NEUTRAL"]:
            if label not in proba:
                proba[label] = 0.0
                
        return proba
