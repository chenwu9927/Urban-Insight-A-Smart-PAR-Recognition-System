import os
import queue
import site
import threading
import uuid
import importlib.util
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import timm
import torch
import torch.nn as nn
from PIL import Image
from sklearn.cluster import KMeans
from torchvision import transforms as T
from ultralytics import YOLO

from .recognition import BaseRecognizer, RecognitionResult, BoundingBox, PedestrianAttribute

# Configuration
ATTRIBUTES = [
    'Female', 'AgeOver60', 'Age18-60', 'AgeLess18',
    'Front', 'Side', 'Back',
    'Hat', 'Glasses',
    'HandBag', 'ShoulderBag', 'Backpack', 'HoldObjectsInFront',
    'ShortSleeve', 'LongSleeve',
    'UpperStripe', 'UpperLogo', 'UpperPlaid', 'UpperSplice',
    'LowerStripe', 'LowerPattern', 'LongCoat',
    'Trousers', 'Shorts', 'Skirt&Dress', 'boots'
]
AGE_ATTRS = ["AgeOver60", "Age18-60", "AgeLess18"]
VIEW_ATTRS = ["Front", "Side", "Back"]
DEFAULT_ATTR_MODEL_NAME = "mobilenetv4_conv_small_050.e3000_r224_in1k"
DEFAULT_ATTR_MODEL_PATH = os.path.join("model", "models", "mobilenet", "best_model.pth")
DEFAULT_ATTR_IMAGE_SIZE = 224

REID_SIM_THRESHOLD = 0.6
REID_SIM_STRICT = 0.75
IOU_THRESHOLD = 0.1
TRACK_MAX_AGE_SECONDS = 5
REID_MAX_AGE_SECONDS = 30
EMBEDDING_MOMENTUM = 0.7


def _load_checkpoint_compat(path: str, device: torch.device):
    try:
        return torch.load(path, map_location=device, weights_only=True)
    except TypeError:
        return torch.load(path, map_location=device)
    except Exception:
        return torch.load(path, map_location=device, weights_only=False)


def _resolve_path(base_path: str, raw_path: str) -> str:
    if os.path.isabs(raw_path):
        return raw_path
    return os.path.join(base_path, raw_path)


def _derive_group_indices(attr_names: List[str]) -> Tuple[List[int], List[int], List[int]]:
    attr_to_idx = {name: i for i, name in enumerate(attr_names)}
    age_indices = [attr_to_idx[name] for name in AGE_ATTRS if name in attr_to_idx]
    view_indices = [attr_to_idx[name] for name in VIEW_ATTRS if name in attr_to_idx]
    grouped = set(age_indices + view_indices)
    binary_indices = [i for i in range(len(attr_names)) if i not in grouped]
    return binary_indices, age_indices, view_indices


def _grouped_probs_to_raw_probs(
    binary_probs: np.ndarray,
    age_probs: np.ndarray,
    view_probs: np.ndarray,
    attr_count: int,
    binary_indices: List[int],
    age_indices: List[int],
    view_indices: List[int],
) -> np.ndarray:
    raw_probs = np.zeros((binary_probs.shape[0], attr_count), dtype=np.float32)
    raw_probs[:, binary_indices] = binary_probs
    raw_probs[:, age_indices] = age_probs
    raw_probs[:, view_indices] = view_probs
    return raw_probs


def _grouped_preds_to_raw_preds(
    binary_preds: np.ndarray,
    age_pred: np.ndarray,
    view_pred: np.ndarray,
    attr_count: int,
    binary_indices: List[int],
    age_indices: List[int],
    view_indices: List[int],
) -> np.ndarray:
    raw_preds = np.zeros((binary_preds.shape[0], attr_count), dtype=np.int64)
    raw_preds[:, binary_indices] = binary_preds
    raw_preds[np.arange(binary_preds.shape[0]), np.array(age_indices)[age_pred]] = 1
    raw_preds[np.arange(binary_preds.shape[0]), np.array(view_indices)[view_pred]] = 1
    return raw_preds


def _build_eval_transform(model_name: str, image_size: int) -> T.Compose:
    backbone = timm.create_model(model_name, pretrained=False)
    data_cfg = timm.data.resolve_model_data_config(backbone)
    mean = data_cfg.get("mean", (0.485, 0.456, 0.406))
    std = data_cfg.get("std", (0.229, 0.224, 0.225))
    del backbone
    return T.Compose([
        T.Resize((image_size, image_size), interpolation=T.InterpolationMode.BICUBIC),
        T.ToTensor(),
        T.Normalize(mean=mean, std=std),
    ])


def _load_torchreid_osnet_module():
    candidate_roots = []
    try:
        candidate_roots.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        user_site = site.getusersitepackages()
        if user_site:
            candidate_roots.append(user_site)
    except Exception:
        pass

    for root in candidate_roots:
        module_path = os.path.join(root, "torchreid", "reid", "models", "osnet.py")
        if not os.path.exists(module_path):
            continue
        spec = importlib.util.spec_from_file_location("_torchreid_osnet_dynamic", module_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    raise ImportError("torchreid osnet.py not found in site-packages")


class LegacyPedestrianAttributeNet(nn.Module):
    def __init__(self, model_name: str, num_classes: int, img_size: int = DEFAULT_ATTR_IMAGE_SIZE):
        super().__init__()
        self.backbone = timm.create_model(
            model_name,
            pretrained=False,
            num_classes=0,
            global_pool=""
        )
        with torch.no_grad():
            dummy = torch.randn(1, 3, img_size, img_size)
            features = self.backbone(dummy)
            self.in_features = features.shape[1]

        self.head = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.BatchNorm1d(self.in_features),
            nn.Dropout(0.2),
            nn.Linear(self.in_features, num_classes)
        )

    def forward(self, x):
        x = self.backbone(x)
        return self.head(x)


class UnifiedMultiHeadPA100KNet(nn.Module):
    def __init__(
        self,
        model_name: str,
        binary_dim: int,
        age_dim: int,
        view_dim: int,
        head_dropout: float = 0.25,
        drop_rate: float = 0.0,
        drop_path_rate: float = 0.0,
    ):
        super().__init__()
        self.backbone = timm.create_model(
            model_name,
            pretrained=False,
            num_classes=0,
            global_pool="avg",
            drop_rate=drop_rate,
            drop_path_rate=drop_path_rate,
        )
        feat_dim = self.backbone.num_features
        self.pre_head = nn.Sequential(
            nn.LayerNorm(feat_dim),
            nn.Dropout(head_dropout),
        )
        self.binary_head = nn.Linear(feat_dim, binary_dim)
        self.age_head = nn.Linear(feat_dim, age_dim)
        self.view_head = nn.Linear(feat_dim, view_dim)

    def forward_with_features(self, x):
        feat = self.backbone(x)
        feat = self.pre_head(feat)
        outputs = {
            "binary": self.binary_head(feat),
            "age": self.age_head(feat),
            "view": self.view_head(feat),
        }
        return outputs, feat

    def forward(self, x):
        outputs, _ = self.forward_with_features(x)
        return outputs


class AttributePredictor:
    def __init__(self, base_path: str, device: torch.device):
        self.base_path = base_path
        self.device = device
        self.mode = "legacy"
        self.model = None
        self.model_name = os.getenv("ATTR_MODEL_NAME", "").strip()
        self.image_size = int(os.getenv("ATTR_IMAGE_SIZE", str(DEFAULT_ATTR_IMAGE_SIZE)))
        self.attr_names = list(ATTRIBUTES)
        self.binary_indices, self.age_indices, self.view_indices = _derive_group_indices(self.attr_names)
        self.thresholds = np.full(len(self.binary_indices), 0.5, dtype=np.float32)

        raw_path = os.getenv("ATTR_MODEL_PATH", DEFAULT_ATTR_MODEL_PATH)
        self.model_path = _resolve_path(self.base_path, raw_path)
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Attribute model not found: {self.model_path}")

        checkpoint = _load_checkpoint_compat(self.model_path, self.device)
        if self._looks_like_unified_checkpoint(checkpoint):
            self._load_unified(checkpoint)
        else:
            self._load_legacy(checkpoint)

        self.preprocess = _build_eval_transform(self.model_name, self.image_size)

    @staticmethod
    def _looks_like_unified_checkpoint(checkpoint: Any) -> bool:
        return isinstance(checkpoint, dict) and any(k in checkpoint for k in ("ema_state_dict", "model_state_dict"))

    def _load_unified(self, checkpoint: Dict[str, Any]):
        config = checkpoint.get("config") or {}
        self.model_name = self.model_name or config.get("model_name") or DEFAULT_ATTR_MODEL_NAME
        self.image_size = int(config.get("image_size") or self.image_size or DEFAULT_ATTR_IMAGE_SIZE)
        self.attr_names = list(checkpoint.get("attr_names") or ATTRIBUTES)
        self.binary_indices = list(checkpoint.get("binary_indices") or [])
        self.age_indices = list(checkpoint.get("age_indices") or [])
        self.view_indices = list(checkpoint.get("view_indices") or [])
        if not (self.binary_indices and self.age_indices and self.view_indices):
            self.binary_indices, self.age_indices, self.view_indices = _derive_group_indices(self.attr_names)

        state_dict = checkpoint.get("ema_state_dict") or checkpoint.get("model_state_dict")
        if not isinstance(state_dict, dict):
            raise ValueError(f"Invalid unified checkpoint: {self.model_path}")

        self.model = UnifiedMultiHeadPA100KNet(
            model_name=self.model_name,
            binary_dim=len(self.binary_indices),
            age_dim=len(self.age_indices),
            view_dim=len(self.view_indices),
            head_dropout=float(config.get("head_dropout", 0.25)),
            drop_rate=float(config.get("drop_rate", 0.0)),
            drop_path_rate=float(config.get("drop_path_rate", 0.0)),
        )
        self.model.load_state_dict(state_dict, strict=True)
        self.model.to(self.device)
        self.model.eval()
        thresholds = checkpoint.get("thresholds") or [0.5] * len(self.binary_indices)
        self.thresholds = np.asarray(thresholds, dtype=np.float32)
        self.mode = "unified"

    def _load_legacy(self, checkpoint: Any):
        state_dict = checkpoint if isinstance(checkpoint, dict) else checkpoint.state_dict()
        self.model_name = self.model_name or DEFAULT_ATTR_MODEL_NAME
        self.model = LegacyPedestrianAttributeNet(
            self.model_name,
            len(self.attr_names),
            img_size=self.image_size,
        )
        self.model.load_state_dict(state_dict, strict=True)
        self.model.to(self.device)
        self.model.eval()
        self.mode = "legacy"

    def _raw_predictions_to_attrs(self, raw_preds: np.ndarray) -> Dict[str, Any]:
        detected = [self.attr_names[i] for i, active in enumerate(raw_preds) if int(active) == 1]

        gender = "Female" if "Female" in detected else "Male"
        if "AgeLess18" in detected:
            age = "Child"
        elif "AgeOver60" in detected:
            age = "Senior"
        else:
            age = "Adult"

        if "Back" in detected:
            orientation = "Back"
        elif "Side" in detected:
            orientation = "Side"
        else:
            orientation = "Front"

        backpack = "Backpack" in detected
        bag = any(name in detected for name in ["HandBag", "ShoulderBag", "Backpack", "HoldObjectsInFront"])
        hat = "Hat" in detected
        glasses = "Glasses" in detected

        if "LongSleeve" in detected:
            upper_type = "LongSleeve"
        elif "ShortSleeve" in detected:
            upper_type = "ShortSleeve"
        else:
            upper_type = "Unknown"

        if "Skirt&Dress" in detected:
            lower_type = "Skirt"
        elif "Shorts" in detected:
            lower_type = "Shorts"
        elif "Trousers" in detected:
            lower_type = "Trousers"
        else:
            lower_type = "Unknown"

        return {
            "gender": gender,
            "age_group": age,
            "has_backpack": backpack,
            "has_bag": bag,
            "has_hat": hat,
            "has_glasses": glasses,
            "orientation": orientation,
            "upper_type": upper_type,
            "lower_type": lower_type,
            "raw_attrs": detected,
        }

    def predict(self, image_crop, return_embedding: bool = False):
        image_pil = Image.fromarray(cv2.cvtColor(image_crop, cv2.COLOR_BGR2RGB))
        input_tensor = self.preprocess(image_pil).unsqueeze(0).to(self.device)

        with torch.no_grad():
            if self.mode == "unified":
                outputs, embedding_tensor = self.model.forward_with_features(input_tensor)
                binary_probs = torch.sigmoid(outputs["binary"]).cpu().numpy()
                age_probs = torch.softmax(outputs["age"], dim=1).cpu().numpy()
                view_probs = torch.softmax(outputs["view"], dim=1).cpu().numpy()
                binary_preds = (binary_probs[0] >= self.thresholds).astype(np.int64)
                age_pred = age_probs.argmax(axis=1)
                view_pred = view_probs.argmax(axis=1)
                raw_preds = _grouped_preds_to_raw_preds(
                    binary_preds[None, :],
                    age_pred,
                    view_pred,
                    len(self.attr_names),
                    self.binary_indices,
                    self.age_indices,
                    self.view_indices,
                )[0]
                embedding = embedding_tensor.squeeze(0).detach().cpu().numpy().astype(np.float32)
            else:
                features = self.model.backbone(input_tensor)
                logits = self.model.head(features)
                probs = torch.sigmoid(logits)[0].cpu().numpy()
                raw_preds = (probs >= 0.5).astype(np.int64)
                if features.dim() == 4:
                    features = features.mean(dim=(2, 3))
                embedding = features.squeeze(0).detach().cpu().numpy().astype(np.float32)

        norm = np.linalg.norm(embedding) or 1.0
        embedding = embedding / norm
        attrs = self._raw_predictions_to_attrs(raw_preds)
        if return_embedding:
            return attrs, embedding
        return attrs


class ReIDExtractor:
    def __init__(self, device):
        self.device = device
        self.model = None
        self.source = "none"
        self.input_size = (256, 128)

        size_env = os.getenv("REID_INPUT_SIZE")
        if size_env:
            try:
                raw = size_env.lower().replace("x", ",")
                h, w = raw.split(",", 1)
                self.input_size = (int(h.strip()), int(w.strip()))
            except Exception:
                pass

        self.preprocess = T.Compose([
            T.Resize(self.input_size),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

        model_path = os.getenv("REID_MODEL_PATH")
        model_name = os.getenv("REID_MODEL_NAME")
        backend = os.getenv("REID_BACKEND")

        if backend == "torchreid":
            try:
                from collections import OrderedDict

                name = model_name or "osnet_x1_0"
                if name.startswith("osnet_"):
                    osnet_module = _load_torchreid_osnet_module()
                    factory = getattr(osnet_module, name, None)
                    if factory is None:
                        raise KeyError(f"Unknown OSNet variant: {name}")
                    self.model = factory(
                        num_classes=0,
                        pretrained=not bool(model_path),
                        loss="softmax",
                        use_gpu=(self.device.type == "cuda"),
                    )
                else:
                    from torchreid.reid import models as torchreid_models  # type: ignore

                    self.model = torchreid_models.build_model(
                        name,
                        num_classes=0,
                        pretrained=not bool(model_path),
                        use_gpu=(self.device.type == "cuda"),
                    )
                if model_path:
                    loaded = _load_checkpoint_compat(model_path, self.device)
                    if not isinstance(loaded, dict):
                        raise ValueError(f"Unsupported torchreid checkpoint: {model_path}")
                    raw_state_dict = OrderedDict()
                    for key, value in loaded.items():
                        normalized = key[7:] if key.startswith("module.") else key
                        raw_state_dict[normalized] = value
                    model_state = self.model.state_dict()
                    matched_state = OrderedDict()
                    for key, value in raw_state_dict.items():
                        if key in model_state and model_state[key].shape == value.shape:
                            matched_state[key] = value
                    self.model.load_state_dict(matched_state, strict=False)
                self.model.to(self.device)
                self.model.eval()
                self.source = f"torchreid:{name}" if not model_path else f"torchreid:{name}:{model_path}"
                return
            except Exception as e:
                print(f"[warn] torchreid unavailable: {e}")

        if model_path:
            try:
                self.model = torch.jit.load(model_path, map_location=self.device)
                self.model.eval()
                self.source = f"jit:{model_path}"
                return
            except Exception:
                try:
                    loaded = torch.load(model_path, map_location=self.device)
                    if isinstance(loaded, nn.Module):
                        self.model = loaded
                        self.model.to(self.device)
                        self.model.eval()
                        self.source = f"torch:{model_path}"
                        return
                except Exception as e:
                    print(f"[warn] Failed to load REID model from {model_path}: {e}")

        if model_name:
            try:
                self.model = timm.create_model(model_name, pretrained=True, num_classes=0, global_pool="avg")
                self.model.to(self.device)
                self.model.eval()
                self.source = f"timm:{model_name}"
            except Exception as e:
                print(f"[warn] Failed to init timm ReID model: {e}")

    def extract(self, image_crop) -> Optional[np.ndarray]:
        if not self.model:
            return None
        image_pil = Image.fromarray(cv2.cvtColor(image_crop, cv2.COLOR_BGR2RGB))
        input_tensor = self.preprocess(image_pil).unsqueeze(0).to(self.device)
        with torch.no_grad():
            features = self.model(input_tensor)
        if isinstance(features, (list, tuple)):
            features = features[0]
        if features.dim() == 4:
            features = features.mean(dim=(2, 3))
        embedding = features.squeeze(0).detach().cpu().numpy().astype(np.float32)
        norm = np.linalg.norm(embedding) or 1.0
        return embedding / norm

class RealPedestrianRecognizer(BaseRecognizer):
    def __init__(self):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"Using device: {self.device}")

        # Paths
        self.base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.model_dir = os.path.join(self.base_path, "model")
        
        # Load YOLO
        yolo_path = os.path.join(self.model_dir, "yolov8n.pt")
        try:
            self.yolo_model = YOLO(yolo_path)
            print("YOLOv8 loaded.")
        except Exception as e:
            print(f"Error loading YOLO: {e}")
            raise e

        try:
            self.attr_predictor = AttributePredictor(self.base_path, self.device)
            print(
                "Attribute model loaded "
                f"({self.attr_predictor.mode}:{self.attr_predictor.model_name} @ {self.attr_predictor.model_path})."
            )
        except Exception as e:
            print(f"Error loading Attribute model: {e}")
            raise e

        self.reid_extractor = ReIDExtractor(self.device)
        if self.reid_extractor.model:
            print(f"ReID model ready ({self.reid_extractor.source}).")
        else:
            print("ReID model not configured, fallback to attribute backbone.")

    def _extract_color(self, image_crop):
        """
        Simple K-Means to extract dominant color from center of crop.
        Returns closest CSS color name (Red, Blue, Black, White, Grey, Green, Yellow).
        """
        # Crop center 50% to avoid background
        h, w = image_crop.shape[:2]
        center_crop = image_crop[int(h*0.25):int(h*0.75), int(w*0.25):int(w*0.75)]
        if center_crop.size == 0: return "Unknown"
        
        center_crop = cv2.cvtColor(center_crop, cv2.COLOR_BGR2RGB)
        pixels = center_crop.reshape(-1, 3)
        
        if len(pixels) < 10: return "Unknown"
        
        kmeans = KMeans(n_clusters=1, n_init=5)
        kmeans.fit(pixels)
        dominant_color = kmeans.cluster_centers_[0]
        
        # Simple Euclidean distance mapping to color names
        r, g, b = dominant_color
        colors = {
            "Black": (30, 30, 30),
            "White": (240, 240, 240),
            "Grey": (128, 128, 128),
            "Red": (200, 50, 50),
            "Blue": (50, 50, 200),
            "Green": (50, 150, 50),
            "Yellow": (200, 200, 50),
            "Khaki": (195, 176, 145) # Typical pants color
        }
        
        best_color = "Grey"
        min_dist = float('inf')
        
        for name, rgb in colors.items():
            dist = np.sqrt((r-rgb[0])**2 + (g-rgb[1])**2 + (b-rgb[2])**2)
            if dist < min_dist:
                min_dist = dist
                best_color = name
                
        return best_color

    def _predict_attrs(self, image_crop, return_embedding: bool = False):
        return self.attr_predictor.predict(image_crop, return_embedding=return_embedding)

    @staticmethod
    def _bbox_iou(a, b) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        inter_w = max(0, inter_x2 - inter_x1)
        inter_h = max(0, inter_y2 - inter_y1)
        inter_area = inter_w * inter_h
        if inter_area == 0:
            return 0.0
        area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
        area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
        denom = area_a + area_b - inter_area
        if denom <= 0:
            return 0.0
        return inter_area / denom

    def analyze(self, file_path: str) -> List[RecognitionResult]:
        # For single image
        frame = cv2.imread(file_path)
        if frame is None: return []
        
        results = self.yolo_model(frame, classes=[0], verbose=False)
        rec_results = []
        
        for result in results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                h, w, _ = frame.shape
                x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
                
                if x2 > x1 and y2 > y1:
                    crop = frame[y1:y2, x1:x2]
                    
                    # Attributes
                    attrs_dict = self._predict_attrs(crop)
                    # Color (Upper/Lower separation is hard without pose estimation, distinct by center vs bottom?)
                    # Simplified: Use center for Upper, Bottom 25% for Lower?
                    
                    upper_crop = crop[:int((y2-y1)/2), :]
                    lower_crop = crop[int((y2-y1)/2):, :]
                    
                    upper_color = self._extract_color(upper_crop)
                    lower_color = self._extract_color(lower_crop)
                    
                    bbox_obj = BoundingBox(x=int(x1), y=int(y1), width=int(x2-x1), height=int(y2-y1))
                    
                    attr_obj = PedestrianAttribute(
                        gender=attrs_dict['gender'],
                        age_group=attrs_dict['age_group'],
                        upper_color=upper_color,
                        lower_color=lower_color,
                        has_backpack=attrs_dict['has_backpack'],
                        confidence=float(box.conf)
                    )
                    
                    # Inject extra fields into attribute object dynamically if Pydantic allows or just use raw dict for extra
                    # The BaseRecogzier returns RecognitionResult with strict schema.
                    # We will rely on returning dicts in the main app anyway.
                    
                    # Hack: Attach extra info to object for main.py to unpack if needed, 
                    # OR just return dicts from here if we change interface. 
                    # But interface is typed.
                    # Let's stick to strict schema for core, but we can update the Schema definition? 
                    # For now, let's just pack standard fields and maybe abuse one field or add to JSON later.
                    
                    # Return plain dict for compatibility with Pydantic v2 (no dynamic extra fields).
                    # Keep extended attributes so image-search can use richer matching signals.
                    rec_results.append(
                        {
                            "pedestrian_id": str(uuid.uuid4()),
                            "bbox": {
                                "x": int(x1),
                                "y": int(y1),
                                "width": int(x2 - x1),
                                "height": int(y2 - y1),
                            },
                            "attributes": {
                                "gender": attrs_dict["gender"],
                                "age_group": attrs_dict["age_group"],
                                "upper_color": upper_color,
                                "lower_color": lower_color,
                                "has_backpack": bool(attrs_dict["has_backpack"]),
                                "confidence": float(box.conf),
                                "has_bag": bool(attrs_dict["has_bag"]),
                                "has_hat": bool(attrs_dict["has_hat"]),
                                "has_glasses": bool(attrs_dict["has_glasses"]),
                                "orientation": attrs_dict["orientation"],
                                "upper_type": attrs_dict["upper_type"],
                                "lower_type": attrs_dict["lower_type"],
                            },
                        }
                    )
                    
        return rec_results

    def analyze_video(self, file_path: str, progress_callback=None) -> dict:
        thumbnail_dir = os.path.join(self.base_path, "thumbnails")
        os.makedirs(thumbnail_dir, exist_ok=True)

        cap = cv2.VideoCapture(file_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        if fps <= 0:
            fps = 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        duration = (total_frames / fps) if fps else 0

        video_results = []
        tracks: Dict[str, Dict[str, Any]] = {}
        next_track_id = 1
        max_age_frames = int(fps * TRACK_MAX_AGE_SECONDS)
        reid_max_age_frames = int(fps * REID_MAX_AGE_SECONDS)

        sample_seconds = float(os.getenv("VIDEO_SAMPLE_SECONDS", "1"))
        sample_rate = max(1, int(round(fps * sample_seconds)))
        total_sampled_frames = max(1, (total_frames + sample_rate - 1) // sample_rate) if total_frames > 0 else 1
        attr_refresh_seconds = float(os.getenv("ATTR_REFRESH_SECONDS", "3"))
        attr_refresh_frames = max(1, int(round(fps * attr_refresh_seconds)))
        queue_size = max(2, int(os.getenv("PIPELINE_QUEUE_SIZE", "8")))
        save_thumbnails = os.getenv("SAVE_THUMBNAILS", "1").lower() not in {"0", "false", "no"}
        thumbnail_height = max(64, int(os.getenv("THUMBNAIL_HEIGHT", "150")))
        thumbnail_quality = max(50, min(95, int(os.getenv("THUMBNAIL_JPEG_QUALITY", "85"))))
        thumbnail_queue_size = max(4, int(os.getenv("THUMBNAIL_QUEUE_SIZE", str(queue_size * 2))))

        frame_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=queue_size)
        detect_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=queue_size)
        thumbnail_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=thumbnail_queue_size)
        reader_done = threading.Event()
        detector_done = threading.Event()
        analyzer_done = threading.Event()
        state_lock = threading.Lock()
        pipeline_error: Dict[str, Optional[Exception]] = {"exc": None}
        analyzed_sampled_frames = [0]

        if progress_callback:
            try:
                progress_callback(0, total_sampled_frames)
            except Exception:
                pass

        def set_error(exc: Exception):
            with state_lock:
                if pipeline_error["exc"] is None:
                    pipeline_error["exc"] = exc

        def make_track(embedding, bbox, frame_index):
            return {
                "embedding": embedding,
                "bbox": bbox,
                "last_frame": frame_index,
                "attrs": None,
                "upper_color": None,
                "lower_color": None,
                "last_attr_frame": -10**9,
                "last_color_frame": -10**9,
            }

        def assign_track(embedding, bbox, frame_index, used_tracks):
            nonlocal next_track_id
            if embedding is None:
                best_id = None
                best_iou = 0.0
                for track_id, track in tracks.items():
                    if track_id in used_tracks:
                        continue
                    age = frame_index - track["last_frame"]
                    if age > max_age_frames:
                        continue
                    iou_score = self._bbox_iou(bbox, track["bbox"])
                    if iou_score >= IOU_THRESHOLD and iou_score > best_iou:
                        best_iou = iou_score
                        best_id = track_id

                if best_id is not None:
                    track = tracks[best_id]
                    track["bbox"] = bbox
                    track["last_frame"] = frame_index
                    used_tracks.add(best_id)
                    return best_id

                best_id = f"person_{next_track_id:04d}"
                next_track_id += 1
                tracks[best_id] = make_track(None, bbox, frame_index)
                used_tracks.add(best_id)
                return best_id

            best_id = None
            best_score = -1.0
            for track_id, track in tracks.items():
                if track_id in used_tracks:
                    continue
                age = frame_index - track["last_frame"]
                if age > reid_max_age_frames:
                    continue
                if track["embedding"] is None:
                    continue

                sim = float(np.dot(embedding, track["embedding"]))
                iou_score = self._bbox_iou(bbox, track["bbox"]) if age <= max_age_frames else 0.0
                if age <= max_age_frames:
                    if sim < REID_SIM_THRESHOLD and iou_score < IOU_THRESHOLD:
                        continue
                    score = sim + iou_score
                else:
                    if sim < REID_SIM_STRICT:
                        continue
                    score = sim

                if score > best_score:
                    best_score = score
                    best_id = track_id

            if best_id is None:
                best_id = f"person_{next_track_id:04d}"
                next_track_id += 1
                tracks[best_id] = make_track(embedding, bbox, frame_index)
            else:
                track = tracks[best_id]
                if track["embedding"] is None:
                    track["embedding"] = embedding
                else:
                    merged = EMBEDDING_MOMENTUM * track["embedding"] + (1 - EMBEDDING_MOMENTUM) * embedding
                    norm = np.linalg.norm(merged) or 1.0
                    track["embedding"] = merged / norm
                track["bbox"] = bbox
                track["last_frame"] = frame_index

            used_tracks.add(best_id)
            return best_id

        def put_with_backpressure(q, item):
            while True:
                if pipeline_error["exc"] is not None:
                    return
                try:
                    q.put(item, timeout=0.2)
                    return
                except queue.Full:
                    continue

        def reader_worker():
            frame_idx = 0
            try:
                while cap.isOpened():
                    if pipeline_error["exc"] is not None:
                        break
                    ret, frame = cap.read()
                    if not ret:
                        break
                    if frame_idx % sample_rate == 0:
                        packet = {
                            "frame_idx": frame_idx,
                            "timestamp": frame_idx / fps,
                            "frame": frame,
                        }
                        put_with_backpressure(frame_queue, packet)
                    frame_idx += 1
            except Exception as exc:
                set_error(exc)
            finally:
                reader_done.set()

        def detector_worker():
            try:
                while True:
                    if pipeline_error["exc"] is not None and reader_done.is_set() and frame_queue.empty():
                        break
                    try:
                        packet = frame_queue.get(timeout=0.2)
                    except queue.Empty:
                        if reader_done.is_set():
                            break
                        continue

                    frame = packet["frame"]
                    detections = []
                    results = self.yolo_model(frame, classes=[0], verbose=False)
                    for result in results:
                        for box in result.boxes:
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                            confidence = float(box.conf.item()) if hasattr(box.conf, "item") else float(box.conf)
                            detections.append((x1, y1, x2, y2, confidence))

                    packet["detections"] = detections
                    put_with_backpressure(detect_queue, packet)
            except Exception as exc:
                set_error(exc)
            finally:
                detector_done.set()

        def analyzer_worker():
            try:
                while True:
                    if pipeline_error["exc"] is not None and detector_done.is_set() and detect_queue.empty():
                        break
                    if detector_done.is_set() and detect_queue.empty():
                        break
                    try:
                        packet = detect_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue

                    frame_idx = packet["frame_idx"]
                    timestamp = packet["timestamp"]
                    frame = packet["frame"]
                    h, w, _ = frame.shape
                    used_tracks = set()

                    for x1, y1, x2, y2, conf in packet.get("detections", []):
                        x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
                        if x2 <= x1 or y2 <= y1:
                            continue

                        crop = frame[y1:y2, x1:x2]
                        if crop.size == 0:
                            continue

                        attrs_dict = None
                        if self.reid_extractor and self.reid_extractor.model:
                            embedding = self.reid_extractor.extract(crop)
                            if embedding is None:
                                attrs_dict, embedding = self._predict_attrs(crop, return_embedding=True)
                        else:
                            embedding = None

                        bbox_tuple = (int(x1), int(y1), int(x2), int(y2))
                        person_id = assign_track(embedding, bbox_tuple, frame_idx, used_tracks)
                        track = tracks[person_id]

                        attr_due = (frame_idx - track["last_attr_frame"]) >= attr_refresh_frames or track["attrs"] is None
                        if attr_due:
                            if attrs_dict is None:
                                attrs_dict = self._predict_attrs(crop)
                            track["attrs"] = attrs_dict
                            track["last_attr_frame"] = frame_idx
                        elif attrs_dict is None:
                            attrs_dict = track["attrs"]

                        if attrs_dict is None:
                            attrs_dict = self._predict_attrs(crop)
                            track["attrs"] = attrs_dict
                            track["last_attr_frame"] = frame_idx

                        color_due = (frame_idx - track["last_color_frame"]) >= attr_refresh_frames or track["upper_color"] is None
                        if color_due:
                            half = int((y2 - y1) / 2)
                            track["upper_color"] = self._extract_color(crop[:half, :])
                            track["lower_color"] = self._extract_color(crop[half:, :])
                            track["last_color_frame"] = frame_idx

                        upper_color = track["upper_color"]
                        lower_color = track["lower_color"]

                        event_id = str(uuid.uuid4())
                        thumbnail_filename = None
                        if save_thumbnails:
                            thumbnail_filename = f"{event_id}.jpg"
                            thumbnail_path = os.path.join(thumbnail_dir, thumbnail_filename)
                            put_with_backpressure(
                                thumbnail_queue,
                                {"path": thumbnail_path, "crop": crop.copy()},
                            )

                        video_results.append(
                            {
                                "pedestrian_id": person_id,
                                "person_id": person_id,
                                "event_id": event_id,
                                "timestamp": float(round(timestamp, 1)),
                                "thumbnail": thumbnail_filename,
                                "bbox": {
                                    "x": int(x1),
                                    "y": int(y1),
                                    "width": int(x2 - x1),
                                    "height": int(y2 - y1),
                                },
                                "attributes": {
                                    "gender": attrs_dict["gender"],
                                    "age_group": attrs_dict["age_group"],
                                    "upper_color": upper_color,
                                    "lower_color": lower_color,
                                    "has_backpack": bool(attrs_dict["has_backpack"]),
                                    "confidence": conf,
                                    "has_bag": bool(attrs_dict["has_bag"]),
                                    "has_hat": bool(attrs_dict["has_hat"]),
                                    "has_glasses": bool(attrs_dict["has_glasses"]),
                                    "orientation": attrs_dict["orientation"],
                                    "upper_type": attrs_dict["upper_type"],
                                    "lower_type": attrs_dict["lower_type"],
                                },
                            }
                        )

                    for track_id in list(tracks.keys()):
                        if frame_idx - tracks[track_id]["last_frame"] > reid_max_age_frames:
                            del tracks[track_id]

                    analyzed_sampled_frames[0] += 1
                    if progress_callback:
                        try:
                            progress_callback(analyzed_sampled_frames[0], total_sampled_frames)
                        except Exception:
                            pass
            except Exception as exc:
                set_error(exc)
            finally:
                analyzer_done.set()

        def thumbnail_writer_worker():
            try:
                while True:
                    if analyzer_done.is_set() and thumbnail_queue.empty():
                        break
                    try:
                        job = thumbnail_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue

                    crop = job["crop"]
                    thumbnail_path = job["path"]
                    crop_h, crop_w = crop.shape[:2]
                    scale = thumbnail_height / crop_h if crop_h > 0 else 1.0
                    target_w = max(1, int(crop_w * scale))
                    thumbnail = cv2.resize(crop, (target_w, thumbnail_height))
                    cv2.imwrite(thumbnail_path, thumbnail, [cv2.IMWRITE_JPEG_QUALITY, thumbnail_quality])
            except Exception as exc:
                set_error(exc)

        threads = [
            threading.Thread(target=reader_worker, name="video-reader", daemon=True),
            threading.Thread(target=detector_worker, name="video-detector", daemon=True),
            threading.Thread(target=analyzer_worker, name="video-analyzer", daemon=True),
            threading.Thread(target=thumbnail_writer_worker, name="video-thumb-writer", daemon=True),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        cap.release()
        if pipeline_error["exc"] is not None:
            raise pipeline_error["exc"]

        return {
            "is_video": True,
            "duration": int(duration),
            "camera_location": "Camera 01",
            "pedestrians": video_results,
        }
