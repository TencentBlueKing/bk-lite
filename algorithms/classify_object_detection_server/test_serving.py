"""Quick test script for serving module."""
import asyncio
import base64
from io import BytesIO
from PIL import Image

# Test imports
try:
    from classify_object_detection_server.serving.config import get_model_config
    from classify_object_detection_server.serving.models import load_model, DummyModel
    from classify_object_detection_server.serving.schemas import (
        PredictRequest,
        PredictConfig,
        Detection,
        BoundingBox
    )
    print("[OK] All imports successful")
except Exception as e:
    print(f"[FAIL] Import failed: {e}")
    exit(1)

# Test 1: Config loading
print("\n=== Test 1: Config Loading ===")
try:
    config = get_model_config()
    print(f"[OK] Config loaded: source={config.source}")
except Exception as e:
    print(f"[FAIL] Config loading failed: {e}")
    exit(1)

# Test 2: Dummy model loading
print("\n=== Test 2: Dummy Model Loading ===")
try:
    model = DummyModel()
    print(f"[OK] Dummy model loaded: version={model.version}")
except Exception as e:
    print(f"[FAIL] Model loading failed: {e}")
    exit(1)

# Test 3: Dummy model prediction
print("\n=== Test 3: Dummy Model Prediction ===")
try:
    # Create a dummy image
    img = Image.new('RGB', (640, 480), color='red')
    result = model.predict({"images": [img]})
    print(f"[OK] Prediction successful: {len(result)} results")
    print(f"   Result[0]: {result[0]['count']} detections")
    print(f"   Labels: {result[0]['labels']}")
except Exception as e:
    print(f"[FAIL] Prediction failed: {e}")
    exit(1)

# Test 4: Schema validation
print("\n=== Test 4: Schema Validation ===")
try:
    # Create a fake base64 image
    img = Image.new('RGB', (100, 100), color='blue')
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    request = PredictRequest(
        images=[img_base64],
        config=PredictConfig(conf_threshold=0.5, iou_threshold=0.45)
    )
    print(f"[OK] Request schema validated: {len(request.images)} images")
    print(f"   Config: conf={request.config.conf_threshold}, iou={request.config.iou_threshold}")
except Exception as e:
    print(f"[FAIL] Schema validation failed: {e}")
    exit(1)

# Test 5: Detection schema
print("\n=== Test 5: Detection Schema ===")
try:
    det = Detection(
        bbox=BoundingBox(x1=0.1, y1=0.2, x2=0.5, y2=0.6),
        class_id=0,
        class_name="cat",
        confidence=0.85
    )
    print(f"[OK] Detection schema validated: {det.class_name} @ {det.confidence:.2f}")
    print(f"   BBox: [{det.bbox.x1:.2f}, {det.bbox.y1:.2f}, {det.bbox.x2:.2f}, {det.bbox.y2:.2f}]")
except Exception as e:
    print(f"[FAIL] Detection schema failed: {e}")
    exit(1)

print("\n=== All Tests Passed! ===")
