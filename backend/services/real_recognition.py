import torch
import torch.nn as nn
import cv2
import numpy as np
import timm
import queue
import threading
from ultralytics import YOLO
from PIL import Image
from torchvision import transforms as T
from typing import List, Dict, Any, Optional
import os
import uuid
from .recognition import BaseRecognizer, RecognitionResult, BoundingBox, PedestrianAttribute
from sklearn.cluster import KMeans

# Configuration
IMG_SIZE = 112
ATTRIBUTES = [
    'Female', 'AgeOver60', 'Age18-60', 'AgeLess18', 
    'Front', 'Side', 'Back', 
    'Hat', 'Glasses', 
    'HandBag', 'ShoulderBag', 'Backpack', 'HoldObjectsInFront', 
    'ShortSleeve', 'LongSleeve', 
    'UpperStride', 'UpperLogo', 'UpperPlaid', 'UpperSplice', 
    'LowerStripe', 'LowerPattern', 'LongCoat', 
    'Trousers', 'Shorts', 'Skirt&Dress', 'boots'
]

REID_SIM_THRESHOLD = 0.6
REID_SIM_STRICT = 0.75
IOU_THRESHOLD = 0.1
TRACK_MAX_AGE_SECONDS = 5
REID_MAX_AGE_SECONDS = 30
EMBEDDING_MOMENTUM = 0.7

class PedestrianAttributeNet(nn.Module):
    def __init__(self, model_name, num_classes, img_size=112):
        super(PedestrianAttributeNet, self).__init__()
        self.backbone = timm.create_model(
            model_name, 
            pretrained=False, 
            num_classes=0, 
            global_pool='' 
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
                import torchreid  # type: ignore

                name = model_name or "osnet_x1_0"
                self.model = torchreid.models.build_model(name, num_classes=0, pretrained=True)
                self.model.to(self.device)
                self.model.eval()
                self.source = f"torchreid:{name}"
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

        # Load Attribute Model
        attr_path = os.path.join(self.model_dir, "models", "mobilenet", "best_model.pth")
        model_name = 'mobilenetv4_conv_small_050.e3000_r224_in1k'
        self.attr_model = PedestrianAttributeNet(model_name, len(ATTRIBUTES), img_size=IMG_SIZE)
        
        try:
            self.attr_model.load_state_dict(torch.load(attr_path, map_location=self.device))
            self.attr_model.to(self.device)
            self.attr_model.eval()
            print("Attribute model loaded.")
        except Exception as e:
            print(f"Error loading Attribute model: {e}")
            raise e

        self.reid_extractor = ReIDExtractor(self.device)
        if self.reid_extractor.model:
            print(f"ReID model ready ({self.reid_extractor.source}).")
        else:
            print("ReID model not configured, fallback to attribute backbone.")
            
        # Transforms
        self.preprocess = T.Compose([
            T.Resize((IMG_SIZE, IMG_SIZE)),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

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
        # Convert to PIL
        image_pil = Image.fromarray(cv2.cvtColor(image_crop, cv2.COLOR_BGR2RGB))
        input_tensor = self.preprocess(image_pil).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            features = self.attr_model.backbone(input_tensor)
            logits = self.attr_model.head(features)
            probs = torch.sigmoid(logits)[0].cpu().numpy()

        embedding = None
        if return_embedding:
            if features.dim() == 4:
                pooled = features.mean(dim=(2, 3))
            else:
                pooled = features
            embedding = pooled.squeeze(0).detach().cpu().numpy().astype(np.float32)
            norm = np.linalg.norm(embedding) or 1.0
            embedding = embedding / norm
            
        active_indices = np.where(probs > 0.5)[0]
        detected = [ATTRIBUTES[i] for i in active_indices]
        
        # Parse into structured attribute object
        gender = "Female" if "Female" in detected else "Male"
        
        age = "Adult"
        if "AgeLess18" in detected: age = "Child"
        elif "AgeOver60" in detected: age = "Senior"
        
        # Orientation
        orientation = "Front"
        if "Side" in detected: orientation = "Side"
        if "Back" in detected: orientation = "Back"
        
        # Accessories
        hat = "Hat" in detected
        glasses = "Glasses" in detected
        bag = any(k in detected for k in ['HandBag', 'ShoulderBag', 'Backpack'])
        backpack = "Backpack" in detected
        
        # Clothing
        upper_type = "LongSleeve" if "LongSleeve" in detected else "ShortSleeve"
        lower_type = "Trousers"
        if "Shorts" in detected: lower_type = "Shorts"
        elif "Skirt&Dress" in detected: lower_type = "Skirt"
        
        attrs = {
            "gender": gender,
            "age_group": age,
            "has_backpack": backpack,
            "has_bag": bag,
            "has_hat": hat,
            "has_glasses": glasses,
            "orientation": orientation,
            "upper_type": upper_type,
            "lower_type": lower_type,
            "raw_attrs": detected
        }
        if return_embedding:
            return attrs, embedding
        return attrs

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
