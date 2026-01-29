"""Full service test - simulates service initialization and prediction."""
import asyncio
import base64
import sys
from io import BytesIO
from PIL import Image
import os

# Set dummy model for testing
os.environ['MODEL_SOURCE'] = 'dummy'

async def test_service():
    """Test service initialization and prediction."""
    
    print("=== Test: Service Initialization ===")
    try:
        from classify_object_detection_server.serving.service import MLService
        service = MLService()
        print(f"[OK] Service initialized successfully")
        print(f"   Model source: {service.config.source}")
        print(f"   Model version: {getattr(service.model, 'version', 'unknown')}")
    except Exception as e:
        print(f"[FAIL] Service initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n=== Test: Predict API (Single Image) ===")
    try:
        # Create a test image
        img = Image.new('RGB', (640, 480), color='red')
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        # Call predict
        response = await service.predict(
            images=[img_base64],
            config={"conf_threshold": 0.5, "iou_threshold": 0.45}
        )
        
        print(f"[OK] Prediction successful")
        print(f"   Success: {response.success}")
        print(f"   Batch size: {response.metadata.batch_size}")
        print(f"   Success rate: {response.metadata.success_rate:.1%}")
        print(f"   Total detections: {response.metadata.total_detections}")
        print(f"   Total time: {response.metadata.total_time_ms:.2f}ms")
        print(f"   Results: {len(response.results)} images")
        
        if response.results:
            result = response.results[0]
            print(f"   Image 0: {len(result.detections)} detections, success={result.success}")
            for i, det in enumerate(result.detections[:3]):  # Show first 3
                print(f"      Det {i}: {det.class_name} @ {det.confidence:.2f} "
                      f"[{det.bbox.x1:.2f}, {det.bbox.y1:.2f}, {det.bbox.x2:.2f}, {det.bbox.y2:.2f}]")
        
    except Exception as e:
        print(f"[FAIL] Prediction failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n=== Test: Predict API (Batch) ===")
    try:
        # Create multiple test images
        images = []
        for i in range(3):
            img = Image.new('RGB', (640, 480), color=('red', 'green', 'blue')[i])
            buffered = BytesIO()
            img.save(buffered, format="JPEG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            images.append(img_base64)
        
        # Call predict with batch
        response = await service.predict(
            images=images,
            config={"conf_threshold": 0.3, "max_detections": 100}
        )
        
        print(f"[OK] Batch prediction successful")
        print(f"   Batch size: {response.metadata.batch_size}")
        print(f"   Success count: {response.metadata.success_count}")
        print(f"   Failure count: {response.metadata.failure_count}")
        print(f"   Total detections: {response.metadata.total_detections}")
        print(f"   Avg detections/image: {response.metadata.avg_detections_per_image:.2f}")
        print(f"   Total time: {response.metadata.total_time_ms:.2f}ms")
        print(f"   Avg time/image: {response.metadata.avg_time_per_image_ms:.2f}ms")
        
    except Exception as e:
        print(f"[FAIL] Batch prediction failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n=== Test: Health Check ===")
    try:
        health = await service.health()
        print(f"[OK] Health check successful")
        print(f"   Status: {health['status']}")
        print(f"   Model source: {health['model_source']}")
        print(f"   Model version: {health['model_version']}")
    except Exception as e:
        print(f"[FAIL] Health check failed: {e}")
        return False
    
    print("\n=== All Service Tests Passed! ===")
    return True

if __name__ == "__main__":
    success = asyncio.run(test_service())
    sys.exit(0 if success else 1)
