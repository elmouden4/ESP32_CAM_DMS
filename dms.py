import time
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
import requests

# =============== CONFIGURATION ===============

ESP32_IP = "10.160.99.22"

BASE = f"http://{ESP32_IP}"

CLOSED_SECONDS = 1.5
FACE_MISSING_SECONDS = 3.0
DEFAULT_EAR_THRESHOLD = 0.21
CALIBRATION_SAMPLES = 25
HEARTBEAT_SECONDS = 1.0

OUTPUT = Path(__file__).with_name("dms_recording.mp4")
MODEL = Path(__file__).with_name("face_landmarker.task")

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/"
    "face_landmarker.task"
)

LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]


# =============== EAR CALCULATION ===============

def ear_of(lms, indices, w, h):
    pts = np.array(
        [(lms[i].x * w, lms[i].y * h) for i in indices],
        dtype=np.float32
    )

    horizontal = np.linalg.norm(pts[0] - pts[3])

    if horizontal < 1:
        return None

    vertical1 = np.linalg.norm(pts[1] - pts[5])
    vertical2 = np.linalg.norm(pts[2] - pts[4])

    return float(
        (vertical1 + vertical2) / (2 * horizontal)
    )


# =============== MAIN PROGRAM ===============

def main():

    session = requests.Session()

    # Download MediaPipe model automatically
    if not MODEL.exists():
        print("Downloading Face Landmarker model...")
        urllib.request.urlretrieve(MODEL_URL, MODEL)

    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    options = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(
            model_asset_path=str(MODEL)
        ),
        running_mode=vision.RunningMode.IMAGE,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    mesh = vision.FaceLandmarker.create_from_options(
        options
    )

    threshold = DEFAULT_EAR_THRESHOLD

    opened = []
    closed = []

    calibration = None
    writer = None

    hardware_state = None
    last_success = 0.0

    closed_since = None
    missing_since = None

    # ============ ESP32 CONTROL ============

    def set_hardware(state, force=False):

        nonlocal hardware_state, last_success

        now = time.monotonic()

        if (
            not force
            and state == hardware_state
            and now - last_success < HEARTBEAT_SECONDS
        ):
            return

        url = BASE + (
            "/alert" if state == "ALERT" else "/safe"
        )

        try:
            response = session.get(url, timeout=1.5)
            response.raise_for_status()

            hardware_state = state
            last_success = time.monotonic()

        except requests.RequestException as exc:
            hardware_state = None
            print("ESP32 connection error:", exc)

    # ============ DISPLAY ============

    def label(img, line, y, color=(255, 255, 255)):

        cv2.putText(
            img, line, (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58, (0, 0, 0), 4, cv2.LINE_AA
        )

        cv2.putText(
            img, line, (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58, color, 2, cv2.LINE_AA
        )

    # ============ DETECTION LOOP ============

    try:

        print("Starting DMS...")
        print("ESP32-CAM:", BASE)
        print("C = calibrate open eyes")
        print("X = calibrate closed eyes")
        print("Q = quit")

        set_hardware("SAFE", force=True)

        while True:

            try:
                response = session.get(
                    BASE + "/capture",
                    timeout=4,
                    headers={
                        "Cache-Control": "no-cache"
                    }
                )

                response.raise_for_status()

                image_array = np.frombuffer(
                    response.content,
                    dtype=np.uint8
                )

                frame = cv2.imdecode(
                    image_array,
                    cv2.IMREAD_COLOR
                )

                if frame is None:
                    raise ValueError("Invalid JPEG")

            except (
                requests.RequestException,
                ValueError,
                cv2.error
            ) as exc:

                print("Camera error:", exc)

                set_hardware("ALERT")

                closed_since = None

                time.sleep(0.2)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

                continue

            now = time.monotonic()

            h, w = frame.shape[:2]

            # ============ VIDEO RECORDING ============

            if writer is None:

                fourcc = cv2.VideoWriter_fourcc(
                    *"mp4v"
                )

                writer = cv2.VideoWriter(
                    str(OUTPUT),
                    fourcc,
                    10.0,
                    (w, h)
                )

                if not writer.isOpened():
                    print("Video recording unavailable")
                    writer = None

            # ============ FACE LANDMARKER ============

            rgb = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB
            )

            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=np.ascontiguousarray(rgb)
            )

            result = mesh.detect(mp_image)

            eye_value = None
            status = "NO FACE"
            alarm = False

            if result.face_landmarks:

                missing_since = None

                lms = result.face_landmarks[0]

                left_ear = ear_of(
                    lms, LEFT_EYE, w, h
                )

                right_ear = ear_of(
                    lms, RIGHT_EYE, w, h
                )

                if (
                    left_ear is not None
                    and right_ear is not None
                ):

                    eye_value = (
                        left_ear + right_ear
                    ) / 2

                    # Draw eyes
                    for indices in (
                        LEFT_EYE,
                        RIGHT_EYE
                    ):

                        pts = np.array([
                            (
                                int(lms[i].x * w),
                                int(lms[i].y * h)
                            )
                            for i in indices
                        ])

                        cv2.polylines(
                            frame,
                            [pts],
                            True,
                            (0, 255, 255),
                            1
                        )

                    # ============ CALIBRATION ============

                    if calibration == "open":
                        opened.append(eye_value)

                    elif calibration == "closed":
                        closed.append(eye_value)

                    if calibration:

                        samples = (
                            opened
                            if calibration == "open"
                            else closed
                        )

                        if len(samples) >= CALIBRATION_SAMPLES:

                            calibration = None

                            if opened and closed:

                                open_med = float(
                                    np.median(
                                        opened[-CALIBRATION_SAMPLES:]
                                    )
                                )

                                closed_med = float(
                                    np.median(
                                        closed[-CALIBRATION_SAMPLES:]
                                    )
                                )

                                if open_med - closed_med >= 0.035:

                                    threshold = (
                                        open_med + closed_med
                                    ) / 2

                                    print(
                                        "Calibration successful:",
                                        f"OPEN={open_med:.3f}",
                                        f"CLOSED={closed_med:.3f}",
                                        f"THRESHOLD={threshold:.3f}"
                                    )

                                else:
                                    print(
                                        "Calibration failed. "
                                        "Improve lighting and retry."
                                    )

                    # ============ DROWSINESS ============

                    if eye_value < threshold:

                        if closed_since is None:
                            closed_since = now

                        duration = now - closed_since

                        alarm = (
                            duration >= CLOSED_SECONDS
                        )

                        if alarm:
                            status = "DROWSINESS ALERT!"
                        else:
                            status = (
                                f"EYES CLOSED {duration:.1f}s"
                            )

                    else:

                        closed_since = None
                        status = "AWAKE"

                else:

                    closed_since = None
                    status = "EYES NOT MEASURABLE"

            else:

                closed_since = None

                if missing_since is None:
                    missing_since = now

                alarm = (
                    now - missing_since
                    >= FACE_MISSING_SECONDS
                )

                if alarm:
                    status = "FACE LOST - ALERT"

            # ============ LED + BUZZER ============

            if alarm:
                set_hardware("ALERT")
            else:
                set_hardware("SAFE")

            # ============ SCREEN ============

            if eye_value is not None:

                label(
                    frame,
                    f"EAR: {eye_value:.3f} "
                    f"Threshold: {threshold:.3f}",
                    27,
                    (255, 255, 0)
                )

            else:

                label(
                    frame,
                    f"EAR: -- Threshold: {threshold:.3f}",
                    27
                )

            label(
                frame,
                status,
                56,
                (0, 0, 255)
                if alarm
                else (0, 255, 0)
            )

            label(
                frame,
                f"Hardware: {hardware_state or 'NO ACK'}",
                85
            )

            if calibration:

                samples = (
                    opened
                    if calibration == "open"
                    else closed
                )

                label(
                    frame,
                    f"Calibrating {calibration.upper()}: "
                    f"{len(samples)}/{CALIBRATION_SAMPLES}",
                    114
                )

            label(
                frame,
                "C=OPEN  X=CLOSED  Q=QUIT",
                h - 12
            )

            if writer is not None:
                writer.write(frame)

            cv2.imshow(
                "ESP32-CAM DMS",
                frame
            )

            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break

            elif key == ord("c"):

                opened.clear()
                calibration = "open"

                print(
                    "Keep eyes OPEN for 25 frames"
                )

            elif key == ord("x"):

                closed.clear()
                calibration = "closed"

                print(
                    "Keep eyes CLOSED for 25 frames"
                )

    finally:

        try:
            session.get(
                BASE + "/stop",
                timeout=2
            )
        except requests.RequestException:
            print("Could not stop alarm remotely")

        if writer is not None:
            writer.release()

        mesh.close()
        session.close()

        cv2.destroyAllWindows()

        print("Recording saved:", OUTPUT)


if __name__ == "__main__":
    main()