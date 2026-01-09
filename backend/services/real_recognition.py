import torch
import torch.nn as nn
import cv2
import numpy as np
import timm
from ultralytics import YOLO
from PIL import Image
from torchvision import transforms as T
from typing import List, Dict, Any
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

    def _predict_attrs(self, image_crop):
        # Convert to PIL
        image_pil = Image.fromarray(cv2.cvtColor(image_crop, cv2.COLOR_BGR2RGB))
        input_tensor = self.preprocess(image_pil).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            logits = self.attr_model(input_tensor)
            probs = torch.sigmoid(logits)[0].cpu().numpy()
            
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
            "raw_attrs": detected
        }

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
                    
                    res = RecognitionResult(
                        pedestrian_id=str(uuid.uuid4()),
                        bbox=bbox_obj,
                        attributes=attr_obj
                    )
                    
                    # Monkey patch dictionary for extra info (Python dynamic nature)
                    res.extra_attributes = attrs_dict
                    
                    rec_results.append(res)
                    
        return rec_results

    def analyze_video(self, file_path: str) -> dict:
        # 确保缩略图目录存在
        thumbnail_dir = os.path.join(self.base_path, "thumbnails")
        os.makedirs(thumbnail_dir, exist_ok=True)
        
        cap = cv2.VideoCapture(file_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps
        
        video_results = []
        # Sample 1 frame every second to save time
        sample_rate = int(fps) 
        
        frame_idx = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
            
            if frame_idx % sample_rate == 0:
                timestamp = frame_idx / fps
                
                results = self.yolo_model(frame, classes=[0], verbose=False)
                for result in results:
                    boxes = result.boxes
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                        h, w, _ = frame.shape
                        x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
                        
                        if x2 > x1 and y2 > y1:
                            crop = frame[y1:y2, x1:x2]
                            attrs_dict = self._predict_attrs(crop)
                            
                            upper_color = self._extract_color(crop[:int((y2-y1)/2), :])
                            lower_color = self._extract_color(crop[int((y2-y1)/2):, :])
                            
                            # 生成行人ID并保存缩略图
                            ped_id = str(uuid.uuid4())
                            thumbnail_filename = f"{ped_id}.jpg"
                            thumbnail_path = os.path.join(thumbnail_dir, thumbnail_filename)
                            
                            # 调整缩略图大小（高度150px，保持比例）
                            crop_h, crop_w = crop.shape[:2]
                            target_h = 150
                            scale = target_h / crop_h
                            target_w = int(crop_w * scale)
                            thumbnail = cv2.resize(crop, (target_w, target_h))
                            cv2.imwrite(thumbnail_path, thumbnail, [cv2.IMWRITE_JPEG_QUALITY, 85])
                            
                            ped_dict = {
                                "pedestrian_id": ped_id,
                                "timestamp": float(round(timestamp, 1)),
                                "thumbnail": thumbnail_filename,  # 添加缩略图文件名
                                "bbox": {"x": int(x1), "y": int(y1), "width": int(x2-x1), "height": int(y2-y1)},
                                "attributes": {
                                    "gender": attrs_dict['gender'],
                                    "age_group": attrs_dict['age_group'],
                                    "upper_color": upper_color,
                                    "lower_color": lower_color,
                                    "has_backpack": bool(attrs_dict['has_backpack']),
                                    "confidence": float(box.conf.item()),
                                    # Extras
                                    "has_bag": bool(attrs_dict['has_bag']),
                                    "has_hat": bool(attrs_dict['has_hat']),
                                    "has_glasses": bool(attrs_dict['has_glasses']),
                                    "orientation": attrs_dict['orientation'],
                                    "upper_type": attrs_dict['upper_type'],
                                    "lower_type": attrs_dict['lower_type']
                                }
                            }
                            video_results.append(ped_dict)
            
            frame_idx += 1
            
        cap.release()
        
        return {
            "is_video": True,
            "duration": int(duration),
            "camera_location": "Camera 01", # Default
            "pedestrians": video_results
        }
