import os
from typing import Tuple

import numpy as np
mp = None  # MediaPipe is optional; we won't gate predictions on it

try:
    # Prefer tensorflow.keras if available
    from tensorflow.keras.models import load_model  # type: ignore
    from tensorflow.keras.preprocessing.image import load_img, img_to_array  # type: ignore
    from tensorflow.keras.applications import MobileNetV2  # type: ignore
    from tensorflow.keras.layers import Dense, GlobalAveragePooling2D  # type: ignore
    from tensorflow.keras.models import Model as TFModel  # type: ignore
except Exception:  # pragma: no cover
    # Fallback to keras package if TF import path differs
    try:
        from keras.models import load_model  # type: ignore
        from keras.preprocessing.image import load_img, img_to_array  # type: ignore
        from keras.applications import MobileNetV2  # type: ignore
        from keras.layers import Dense, GlobalAveragePooling2D  # type: ignore
        from keras.models import Model as TFModel  # type: ignore
    except Exception as e:  # pragma: no cover
        load_model = None  # type: ignore
        load_img = None  # type: ignore
        img_to_array = None  # type: ignore

# Optional CV helpers (for hand/no-hand check)
try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore
try:
    import mediapipe as mp  # type: ignore
except Exception:  # pragma: no cover
    mp = None  # type: ignore


_MODEL_INSTANCE = None


def _get_model_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(
        base_dir,
        "data",
        "trained_models",
        "NailShape_Model",
        "nail_shape_model.h5",
    )

def _get_saved_model_dir() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(
        base_dir,
        "data",
        "trained_models",
        "NailShape_Model",
        "nail_shape_model_saved",
    )


def _get_labels_sidecar() -> Tuple[Tuple[str, ...], bool]:
    """Try to load labels from sidecar files. Returns (labels, found)."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    model_dir = os.path.join(base_dir, "data", "trained_models", "NailShape_Model")
    # Try class_indices.json created during training
    class_indices_path = os.path.join(model_dir, "class_indices.json")
    labels_path = os.path.join(model_dir, "labels.txt")
    try:
        import json  # local import
        if os.path.exists(class_indices_path):
            with open(class_indices_path, "r", encoding="utf-8") as f:
                idx_map = json.load(f)  # {className: index}
            # invert and sort by index
            inv = [(idx, name) for name, idx in idx_map.items()]
            inv.sort(key=lambda x: int(x[0]))
            labels = tuple(name for _idx, name in inv)
            return labels, True
        if os.path.exists(labels_path):
            with open(labels_path, "r", encoding="utf-8") as f:
                labels = tuple([line.strip() for line in f if line.strip()])
            if labels:
                return labels, True
    except Exception:
        pass
    return tuple(), False


def _softmax(logits: np.ndarray) -> np.ndarray:
    logits = logits.astype(np.float64)
    logits -= np.max(logits)
    exp = np.exp(logits)
    return exp / np.sum(exp)


class NailShapeAnalyzer:
    """Wraps the trained nail shape model for image-based prediction."""

    def __init__(self, target_size: Tuple[int, int] = (224, 224)) -> None:
        global _MODEL_INSTANCE
        self.target_size = target_size
        # Prefer sidecar-provided labels; fallback to common defaults
        sidecar_labels, found = _get_labels_sidecar()
        if found:
            self.labels = list(sidecar_labels)
        else:
            # Default to provided class indices order: 0:almond,1:oval,2:squoval,3:square,4:stiletto
            self.labels = ["almond", "oval", "squoval", "square", "stiletto"]

        if _MODEL_INSTANCE is None:
            if load_model is None:
                raise RuntimeError("Keras/TensorFlow is not available to load the model.")
            h5_path = _get_model_path()
            saved_dir = _get_saved_model_dir()
            if not os.path.exists(h5_path) and not os.path.isdir(saved_dir):
                raise FileNotFoundError(f"Nail shape model not found at: {h5_path} or {saved_dir}")
            # Try multiple loaders/fmts to avoid version mismatches
            last_err: Exception | None = None
            for attempt in ("tf_keras_h5_custom", "tf_keras_h5_safe", "tf_keras_h5", "tf_keras_saved", "tf_compat_v1_h5", "keras_h5_custom", "keras_h5"):
                try:
                    if attempt == "tf_keras_h5_custom" and os.path.exists(h5_path):
                        import tensorflow as _tf  # type: ignore
                        _MODEL_INSTANCE = _tf.keras.models.load_model(
                            h5_path,
                            compile=False,
                            custom_objects={
                                'InputLayer': _tf.keras.layers.InputLayer,
                            }
                        )
                        break
                    if attempt == "tf_keras_h5_safe" and os.path.exists(h5_path):
                        _MODEL_INSTANCE = load_model(h5_path, compile=False, safe_mode=False)  # type: ignore[arg-type]
                        break
                    if attempt == "tf_keras_h5" and os.path.exists(h5_path):
                        _MODEL_INSTANCE = load_model(h5_path, compile=False)  # type: ignore[arg-type]
                        break
                    if attempt == "tf_keras_saved" and os.path.isdir(saved_dir):
                        _MODEL_INSTANCE = load_model(saved_dir, compile=False)  # type: ignore[arg-type]
                        break
                    if attempt == "tf_compat_v1_h5" and os.path.exists(h5_path):
                        import tensorflow as _tf  # type: ignore
                        _MODEL_INSTANCE = _tf.compat.v1.keras.models.load_model(h5_path, compile=False)
                        break
                    if attempt == "keras_h5_custom" and os.path.exists(h5_path):
                        import tensorflow as _tf  # type: ignore
                        from keras.models import load_model as _kload  # type: ignore
                        _MODEL_INSTANCE = _kload(
                            h5_path,
                            compile=False,
                            custom_objects={
                                'InputLayer': _tf.keras.layers.InputLayer,
                            }
                        )
                        break
                    if attempt == "keras_h5" and os.path.exists(h5_path):
                        _MODEL_INSTANCE = load_model(h5_path)  # last resort
                        break
                except Exception as e:  # pragma: no cover
                    last_err = e
                    continue
            # Final fallback: rebuild MobileNetV2 head and load weights by name
            if _MODEL_INSTANCE is None and os.path.exists(h5_path) and TFModel is not None:
                try:
                    num_classes = max(2, len(self.labels))
                    base = MobileNetV2(weights=None, include_top=False, input_shape=(self.target_size[0], self.target_size[1], 3))
                    x = base.output
                    x = GlobalAveragePooling2D()(x)
                    x = Dense(128, activation='relu')(x)
                    preds = Dense(num_classes, activation='softmax')(x)
                    rebuilt = TFModel(inputs=base.input, outputs=preds)
                    # Load weights best-effort; skip mismatches between heads
                    rebuilt.load_weights(h5_path, by_name=True, skip_mismatch=True)
                    _MODEL_INSTANCE = rebuilt
                except Exception as e:  # pragma: no cover
                    last_err = e
            if _MODEL_INSTANCE is None:
                raise RuntimeError(f"Failed to load nail shape model: {last_err}")
            if _MODEL_INSTANCE is None:
                raise RuntimeError(f"Failed to load nail shape model: {last_err}")

        self.model = _MODEL_INSTANCE

    def predict_shape(self, image_path: str) -> Tuple[str, float]:
        # Reject non-hand images first if possible
        if not self._looks_like_human_hand(image_path):
            return "Not a human hand", 0.0

        # Predict directly
        if load_img is None or img_to_array is None:
            raise RuntimeError("Image preprocessing utilities are not available.")

        img = load_img(image_path, target_size=self.target_size)
        arr = img_to_array(img)
        arr = arr / 255.0
        arr = np.expand_dims(arr, axis=0)

        preds = self.model.predict(arr, verbose=0)
        preds = preds[0] if isinstance(preds, (list, tuple)) else preds

        # Ensure 1D vector
        preds = np.squeeze(preds)
        if preds.ndim != 1:
            preds = preds.ravel()

        # Convert to probabilities if needed (most models already softmax)
        probs = preds
        try:
            if np.any(probs < 0) or np.any(probs > 1) or not np.isclose(np.sum(probs), 1.0, atol=1e-3):
                probs = _softmax(probs)
        except Exception:
            probs = _softmax(preds)

        # Guard against label/pred length mismatch
        idx = int(np.argmax(probs))
        confidence = float(probs[idx])
        if idx < len(self.labels):
            label = self.labels[idx]
        else:
            # Map best-effort by clipping index
            safe_idx = min(len(self.labels) - 1, idx)
            label = self.labels[safe_idx]
        return label, confidence

    def _looks_like_human_hand(self, image_path: str) -> bool:
        # Try MediaPipe if available for high accuracy
        if mp is not None and cv2 is not None:
            try:
                img = cv2.imread(image_path)
                if img is None:
                    return True  # don't block if read fails
                max_w = 800
                if img.shape[1] > max_w:
                    scale = max_w / img.shape[1]
                    img = cv2.resize(img, (0, 0), fx=scale, fy=scale)
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                with mp.solutions.hands.Hands(static_image_mode=True, max_num_hands=2, min_detection_confidence=0.5) as hands:
                    res = hands.process(img_rgb)
                    return bool(getattr(res, 'multi_hand_landmarks', None))
            except Exception:
                pass

        # Fallback: simple skin-like detection heuristic using HSV
        if cv2 is not None:
            try:
                img = cv2.imread(image_path)
                if img is None:
                    return True
                hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                # Broad skin range; may vary with lighting
                lower = np.array([0, 20, 50], dtype=np.uint8)
                upper = np.array([25, 255, 255], dtype=np.uint8)
                mask = cv2.inRange(hsv, lower, upper)
                skin_ratio = float(np.count_nonzero(mask)) / float(mask.size)
                return skin_ratio > 0.01
            except Exception:
                return True

        # If we cannot check, allow prediction
        return True





