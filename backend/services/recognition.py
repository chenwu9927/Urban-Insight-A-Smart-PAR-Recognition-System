import uuid
import random
from typing import List
from ..models import RecognitionResult, PedestrianAttribute, BoundingBox

class BaseRecognizer:
    def analyze(self, image_path: str) -> List[RecognitionResult]:
        raise NotImplementedError

class MockPedestrianRecognizer(BaseRecognizer):
    """
    Simulates pedestrian recognition with random data for MVP testing.
    """
    LOCATIONS = ["North Gate", "South Lobby", "Elevator A", "Parking Lot B"]

    def _generate_pedestrian(self) -> RecognitionResult:
        bbox = BoundingBox(
            x=random.randint(0, 500),
            y=random.randint(0, 300),
            width=random.randint(50, 150),
            height=random.randint(100, 300)
        )
        
        attrs = PedestrianAttribute(
            gender=random.choice(["Male", "Female"]),
            age_group=random.choice(["Child", "Teenager", "Adult", "Senior"]),
            upper_color=random.choice(["Red", "Blue", "Black", "White", "Green", "Yellow"]),
            lower_color=random.choice(["Black", "Blue", "Khaki", "Grey", "Jeans"]),
            has_backpack=random.choice([True, False]),
            confidence=random.uniform(0.7, 0.99)
        )
        
        return RecognitionResult(
            pedestrian_id=str(uuid.uuid4()),
            bbox=bbox,
            attributes=attrs
        )

    def analyze(self, file_path: str) -> List[RecognitionResult]:
        # Handle simple image analysis
        results = []
        num_pedestrians = random.randint(1, 4)
        for _ in range(num_pedestrians):
            results.append(self._generate_pedestrian())
        return results

    def analyze_video(self, file_path: str, progress_callback=None) -> dict:
        """
        Mock video analysis. Returns metadata + list of frame results.
        """
        duration = random.randint(10, 60) # Random duration 10-60s
        location = random.choice(self.LOCATIONS)
        
        # Simulate finding pedestrians at different timestamps
        video_results = []
        num_events = random.randint(3, 8)
        num_persons = random.randint(1, max(1, min(4, num_events)))
        person_ids = [f"person_{i+1:03d}" for i in range(num_persons)]

        if progress_callback:
            try:
                progress_callback(0, max(1, num_events))
            except Exception:
                pass
        
        for i in range(num_events):
            ped = self._generate_pedestrian()
            # Add a timestamp field to the mock result for video (not in schema but stored in JSON)
            # We'll just wrap it in a dict for the JSON storage
            event = ped.dict()
            event_id = str(uuid.uuid4())
            person_id = random.choice(person_ids)
            event["person_id"] = person_id
            event["pedestrian_id"] = person_id
            event["event_id"] = event_id
            event['timestamp'] = random.randint(0, duration)
            video_results.append(event)

            if progress_callback:
                try:
                    progress_callback(i + 1, max(1, num_events))
                except Exception:
                    pass
            
        video_results.sort(key=lambda x: x['timestamp'])
            
        return {
            "is_video": True,
            "duration": duration,
            "camera_location": location,
            "pedestrians": video_results
        }
