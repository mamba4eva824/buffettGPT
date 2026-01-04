"""
XGBoost model loading and inference service.

EXTRACTED FROM: handler.py lines 319-499
- load_model(): lines 319-384
- run_inference(): lines 387-499
- _models_cache: line 162

Handles:
- Loading models/scalers/features from S3 with caching
- Running inference with probability-based confidence intervals
- Feature vector construction (continuous + binary features)
"""
import pickle
import logging
import numpy as np
import boto3
from typing import Dict, Any, Tuple, List

from config.settings import MODEL_S3_BUCKET, MODEL_S3_PREFIX

logger = logging.getLogger(__name__)

# AWS clients
s3_client = boto3.client('s3')

# Model cache - persists across Lambda invocations (warm starts)
_models_cache: Dict[str, Tuple[Any, Any, List[str], List[str], List[str]]] = {}


def load_model(model_type: str) -> Tuple[Any, Any, List[str], List[str], List[str]]:
    """
    Load XGBoost model, scaler, and feature lists from S3.

    Args:
        model_type: 'debt', 'cashflow', or 'growth'

    Returns:
        Tuple of (model, scaler, feature_cols, continuous_features, binary_features)
        - feature_cols: All features expected by XGBoost model
        - continuous_features: Features that need scaling (from scaler.feature_names_in_)
        - binary_features: Features that should NOT be scaled (0/1 values)
    """
    global _models_cache

    if model_type in _models_cache:
        return _models_cache[model_type]

    try:
        # Download model files from S3
        model_key = f"{MODEL_S3_PREFIX}/{model_type}_model.pkl"
        scaler_key = f"{MODEL_S3_PREFIX}/{model_type}_scaler.pkl"
        features_key = f"{MODEL_S3_PREFIX}/{model_type}_features.pkl"

        logger.info(f"Loading {model_type} model from s3://{MODEL_S3_BUCKET}/{model_key}")

        # Load model
        model_response = s3_client.get_object(Bucket=MODEL_S3_BUCKET, Key=model_key)
        model = pickle.loads(model_response['Body'].read())

        # Load scaler
        scaler_response = s3_client.get_object(Bucket=MODEL_S3_BUCKET, Key=scaler_key)
        scaler = pickle.loads(scaler_response['Body'].read())

        # Load feature columns
        features_response = s3_client.get_object(Bucket=MODEL_S3_BUCKET, Key=features_key)
        features_data = pickle.loads(features_response['Body'].read())

        # Get feature lists from pkl file
        # feature_cols = all features (what XGBoost expects)
        # continuous_features = features that scaler was trained on
        # binary_features = features that don't need scaling (0/1 flags)
        feature_cols = features_data.get('feature_cols', [])
        binary_features = features_data.get('binary_features', [])

        # Use scaler's feature_names_in_ as authoritative source for continuous features
        if hasattr(scaler, 'feature_names_in_'):
            continuous_features = list(scaler.feature_names_in_)
            logger.info(f"Continuous features from scaler: {len(continuous_features)}")
        else:
            continuous_features = features_data.get('continuous_features', feature_cols)
            logger.info(f"Continuous features from pkl: {len(continuous_features)}")

        # Log feature counts for debugging
        logger.info(f"Feature counts for {model_type}: total={len(feature_cols)}, "
                    f"continuous={len(continuous_features)}, binary={len(binary_features)}")

        # Cache for subsequent invocations
        _models_cache[model_type] = (model, scaler, feature_cols, continuous_features, binary_features)

        logger.info(f"Loaded {model_type} model with {len(feature_cols)} total features")

        # [INFERENCE_DEBUG] Log model loading details
        logger.info(f"[INFERENCE_DEBUG] Model {model_type} loaded: total_features={len(feature_cols)}, "
                    f"continuous={len(continuous_features)}, binary={len(binary_features)}")

        return model, scaler, feature_cols, continuous_features, binary_features

    except Exception as e:
        logger.error(f"Failed to load {model_type} model: {e}")
        raise


def run_inference(model_type: str, features: dict) -> dict:
    """
    Run XGBoost inference with probability-based CI.

    The scaler was trained on continuous features only, but the XGBoost model
    expects all features (continuous + binary). We handle this by:
    1. Scaling only continuous features
    2. Keeping binary features unscaled (they're already 0/1)
    3. Concatenating in the order expected by feature_cols

    Args:
        model_type: 'debt', 'cashflow', or 'growth'
        features: Extracted features dict

    Returns:
        dict with prediction, confidence, ci_width, probabilities
    """
    try:
        model, scaler, feature_cols, continuous_features, binary_features = load_model(model_type)

        # Get features for this model type
        model_features = features.get(model_type, {}).get('current', {})

        # Build continuous feature vector (for scaling)
        continuous_vector = []
        for col in continuous_features:
            value = model_features.get(col, 0.0)
            if value is None:
                value = 0.0
            continuous_vector.append(float(value))

        # Build binary feature vector (no scaling needed)
        binary_vector = []
        for col in binary_features:
            value = model_features.get(col, 0.0)
            if value is None:
                value = 0.0
            binary_vector.append(float(value))

        logger.info(f"Running inference for {model_type}: "
                    f"{len(continuous_vector)} continuous + {len(binary_vector)} binary features")

        # Calculate data quality score - percentage of non-zero features
        total_features = len(continuous_vector) + len(binary_vector)
        non_zero_continuous = sum(1 for v in continuous_vector if v != 0.0)
        non_zero_binary = sum(1 for v in binary_vector if v != 0.0)
        non_zero_count = non_zero_continuous + non_zero_binary
        data_quality = round((non_zero_count / total_features) * 100, 1) if total_features > 0 else 0.0

        # Interpret data quality
        if data_quality >= 80:
            data_quality_interpretation = "HIGH"
        elif data_quality >= 50:
            data_quality_interpretation = "MEDIUM"
        else:
            data_quality_interpretation = "LOW"

        # [FEATURE_QUALITY] Log feature quality metrics
        logger.info(f"[FEATURE_QUALITY] {model_type}: {non_zero_count}/{total_features} features populated ({data_quality}%)")
        if data_quality < 50:
            logger.warning(f"[FEATURE_QUALITY] {model_type}: Low data quality ({data_quality}%) - predictions may be unreliable")

        # Log which specific features are zero/missing for debugging
        zero_continuous = [col for col, val in zip(continuous_features, continuous_vector) if val == 0.0]
        zero_binary = [col for col, val in zip(binary_features, binary_vector) if val == 0.0]
        if zero_continuous or zero_binary:
            logger.info(f"[FEATURE_QUALITY] {model_type} zero features: continuous={zero_continuous}, binary={zero_binary}")

        # [INFERENCE_DEBUG] Log input features
        logger.info(f"[INFERENCE_DEBUG] {model_type} input: continuous={len(continuous_vector)}, binary={len(binary_vector)}")

        # Scale only continuous features
        X_continuous = np.array([continuous_vector])
        X_scaled = scaler.transform(X_continuous)

        # Build final feature vector in the order expected by feature_cols
        # This ensures the model receives features in the correct order it was trained on
        final_vector = []
        scaled_dict = dict(zip(continuous_features, X_scaled[0]))
        binary_dict = dict(zip(binary_features, binary_vector))

        for col in feature_cols:
            if col in scaled_dict:
                final_vector.append(scaled_dict[col])
            elif col in binary_dict:
                final_vector.append(binary_dict[col])
            else:
                # Feature not found - use 0 as default
                logger.warning(f"Feature {col} not found in scaled or binary features")
                final_vector.append(0.0)

        X_final = np.array([final_vector])
        logger.info(f"Final feature vector shape: {X_final.shape}")

        # Get probability predictions from XGBoost
        probs = model.predict_proba(X_final)[0]

        # Map to class labels (XGBoost uses 0=SELL, 1=HOLD, 2=BUY)
        class_labels = ['SELL', 'HOLD', 'BUY']
        prediction_idx = int(np.argmax(probs))
        prediction = class_labels[prediction_idx]

        # Confidence = max probability
        confidence = float(max(probs))

        # CI width = 1 - gap between top two probabilities
        sorted_probs = sorted(probs, reverse=True)
        ci_width = 1.0 - (sorted_probs[0] - sorted_probs[1])

        # Confidence interpretation
        if confidence >= 0.7 and ci_width <= 0.3:
            confidence_interpretation = "STRONG"
        elif confidence >= 0.5 and ci_width <= 0.5:
            confidence_interpretation = "MODERATE"
        else:
            confidence_interpretation = "WEAK"

        logger.info(f"{model_type} inference: {prediction} ({confidence:.0%} confidence)")

        # [INFERENCE_DEBUG] Log prediction details
        logger.info(f"[INFERENCE_DEBUG] {model_type} probabilities: SELL={probs[0]:.3f}, HOLD={probs[1]:.3f}, BUY={probs[2]:.3f}")
        logger.info(f"[INFERENCE_DEBUG] {model_type} result: prediction={prediction}, confidence={confidence:.2f}, ci_width={ci_width:.2f}")

        return {
            'prediction': prediction,
            'confidence': round(confidence, 2),
            'ci_width': round(ci_width, 2),
            'confidence_interpretation': confidence_interpretation,
            'probabilities': {
                'SELL': round(float(probs[0]), 2),
                'HOLD': round(float(probs[1]), 2),
                'BUY': round(float(probs[2]), 2)
            },
            'data_quality': data_quality,
            'data_quality_interpretation': data_quality_interpretation
        }

    except Exception as e:
        logger.error(f"Inference failed for {model_type}: {e}", exc_info=True)
        # Return default uncertain prediction
        return {
            'prediction': 'HOLD',
            'confidence': 0.33,
            'ci_width': 0.95,
            'confidence_interpretation': 'WEAK',
            'probabilities': {'SELL': 0.33, 'HOLD': 0.34, 'BUY': 0.33},
            'data_quality': 0.0,
            'data_quality_interpretation': 'ERROR',
            'error': str(e)
        }


def clear_model_cache():
    """Clear the model cache (useful for testing or forcing reload)."""
    global _models_cache
    _models_cache.clear()
    logger.info("Model cache cleared")
