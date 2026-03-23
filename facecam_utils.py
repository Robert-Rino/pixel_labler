from ultralytics import YOLO
import cv2
import collections
import os

def detect_facecam(video_path, sample_rate=10, max_frames=300):
    """
    Detects the facecam region in a video using YOLOv8 person detection.
    
    Args:
        video_path: Path to the video file.
        sample_rate: Every Nth frame to process.
        max_frames: Total frames to process (limit).
        
    Returns:
        A string in FFMPEG crop format "w:h:x:y" or None if not found.
    """
    # Load YOLOv8 model (downloads automatically if not present)
    try:
        model = YOLO('yolov8n.pt') 
    except Exception as e:
        print(f"Error loading YOLO model: {e}")
        return None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video {video_path}")
        return None

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    person_regions = []
    
    frame_count = 0
    while cap.isOpened() and frame_count < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        
        if frame_count % sample_rate == 0:
            # Predict
            results = model(frame, verbose=False, classes=[0]) # class 0 is person
            
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # x1, y1, x2, y2
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    w = x2 - x1
                    h = y2 - y1
                    
                    # Store
                    person_regions.append((int(x1), int(y1), int(w), int(h)))
        
        frame_count += 1
            
    cap.release()
    
    if not person_regions:
        return None
        
    # Group regions into clusters to find the most stable one
    clusters = []
    for region in person_regions:
        x, y, w, h = region
        cx, cy = x + w/2, y + h/2
        
        found_cluster = False
        for cluster in clusters:
            last_x, last_y, last_w, last_h = cluster['last']
            last_cx, last_cy = last_x + last_w/2, last_y + last_h/2
            
            # If center is within 10% of width/height
            if abs(cx - last_cx) < width * 0.10 and abs(cy - last_cy) < height * 0.10:
                cluster['count'] += 1
                cluster['sum_x'] += x
                cluster['sum_y'] += y
                cluster['sum_w'] += w
                cluster['sum_h'] += h
                cluster['last'] = region
                found_cluster = True
                break
        
        if not found_cluster:
            clusters.append({
                'count': 1,
                'sum_x': x,
                'sum_y': y,
                'sum_w': w,
                'sum_h': h,
                'last': region
            })
            
    if not clusters:
        return None
        
    # Sort clusters by count
    clusters.sort(key=lambda x: x['count'], reverse=True)
    best_cluster = clusters[0]
    
    avg_x = int(best_cluster['sum_x'] / best_cluster['count'])
    avg_y = int(best_cluster['sum_y'] / best_cluster['count'])
    avg_w = int(best_cluster['sum_w'] / best_cluster['count'])
    avg_h = int(best_cluster['sum_h'] / best_cluster['count'])
    
    # Heuristic: Expand the bounding box to capture the facecam area
    padding_x = int(avg_w * 0.2)
    padding_y = int(avg_h * 0.2)
    
    final_x = max(0, avg_x - padding_x)
    final_y = max(0, avg_y - padding_y)
    final_w = min(width - final_x, avg_w + 2 * padding_x)
    final_h = min(height - final_y, avg_h + 2 * padding_y)
    
    # If it's near the edge, snap it to the edge
    if final_x < width * 0.05: final_x = 0
    if final_y < height * 0.05: final_y = 0
    if final_x + final_w > width * 0.95: final_w = width - final_x
    if final_y + final_h > height * 0.95: final_h = height - final_y

    return f"{final_w}:{final_h}:{final_x}:{final_y}"
