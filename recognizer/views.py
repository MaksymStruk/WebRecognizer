# pylint: disable=E1101
# pylint: disable=W0613

import random
import time
from collections import deque, Counter
from datetime import datetime

import cv2
from django.http import StreamingHttpResponse, JsonResponse
from django.shortcuts import render
from ultralytics import YOLO

# Load YOLO model
MODEL = YOLO('yolov5nu.pt')
MODEL.info()

# Define colors for different classes
COLORS = {}
for i in range(0, 80):
    COLORS[i] = [random.randint(0, 255) for _ in range(3)]

IDENTIFIED_ITEMS_LIST = deque(maxlen=30)


def find_repeating_elements(records):
    """Find repeating elements."""
    classification_counts = Counter()
    for record in records:
        for classification in record:
            classification_counts[classification] += 1

    average_classifications = {
        classification: count / len(records)
        for classification, count in classification_counts.items()
    }

    rounded_average_classifications = {
        classification: round(count)
        for classification, count in average_classifications.items()
    }

    return rounded_average_classifications


def convert_to_dict(items_list):
    """Convert to dictionary."""
    item_count = {}
    for item in items_list:
        if item in item_count:
            item_count[item] += 1
        else:
            item_count[item] = 1
    return item_count


class FeedStatus:
    """Feed status."""
    paused = False
    current_items = []
    identified_items = deque(maxlen=30)
    detected_counts = Counter()
    total_frames = 0


def gen_frames(source=0, fps=30):
    """Generate frames."""
    cap = cv2.VideoCapture(source)
    while True:
        if FeedStatus.paused:
            time.sleep(0.1)
            continue

        success, frame = cap.read()
        if success:
            frame = cv2.flip(frame, 1)
            FeedStatus.current_items.clear()
            results = MODEL(frame)
            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = box.conf[0] * 100
                    cls = int(box.cls[0])
                    label = MODEL.names[cls].capitalize()
                    color = COLORS[cls]
                    FeedStatus.current_items.append(label)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(
                        frame,
                        f'{label} {conf:.2f}%',
                        (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.9,
                        color,
                        2,
                    )

            FeedStatus.identified_items.appendleft(list(FeedStatus.current_items))
            FeedStatus.total_frames += 1

            _, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

            time.sleep(1 / fps)


def video_feed(request):
    """Video feed."""
    return StreamingHttpResponse(
        gen_frames(0),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )


def home(request):
    """Home."""
    return render(request, 'home.html')


def control_feed(request, action):
    """Control feed."""
    if action == 'pause':
        FeedStatus.paused = True
    elif action == 'resume':
        FeedStatus.paused = False
    elif action == 'reload':
        FeedStatus.paused = False
        IDENTIFIED_ITEMS_LIST.clear()
    return JsonResponse({'status': 'ok'})


def get_identified_items(request):
    """Get identified items."""
    if not FeedStatus.paused:
        identified_items = find_repeating_elements(list(FeedStatus.identified_items))
        current_time = datetime.now().strftime("%H:%M:%S")

        if not IDENTIFIED_ITEMS_LIST or IDENTIFIED_ITEMS_LIST[0]['time'] != current_time:
            identified_items_with_time = {'time': current_time, 'data': identified_items}
            IDENTIFIED_ITEMS_LIST.appendleft(identified_items_with_time)

    return JsonResponse({
        'identified_items': list(IDENTIFIED_ITEMS_LIST),
    })
