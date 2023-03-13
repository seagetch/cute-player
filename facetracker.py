import os
os.environ["OMP_NUM_THREADS"] = "1"
import numpy as np
import time
import cv2
import socket
import struct
import json
import sys
import copy


sys.path.append("OpenSeeFace")

from OpenSeeFace.input_reader import InputReader, VideoReader, DShowCaptureReader, try_int
from OpenSeeFace.tracker import Tracker, get_model_base_path

class FaceTracker:
    def __init__(self):
        self.fps = 24
        self.capture = 0
        self.width = 640
        self.height = 480
        self.raw_rgb = 0
        self.threshold = None
        self.max_threads = 1
        self.faces = 1
        self.scan_every = 3
        self.silent = 1
        self.model = 3
        self.discard_after = 10
        self.scan_retinaface = 0
        self.gaze_tracking = 0
        self.detection_threshold = 0.6
        self.gaze_tracking = 0
        self.max_feature_updates = 900
        self.no_3d_adapt = 1
        self.try_hard = 0
        self.model_dir = None

        self.latest_faces = [None] * self.faces
        self.features = ["eye_l", "eye_r", "eyebrow_steepness_l", "eyebrow_updown_l", "eyebrow_quirk_l", 
                         "eyebrow_steepness_r", "eyebrow_updown_r", "eyebrow_quirk_r", "mouth_corner_updown_l", "mouth_corner_inout_l", "mouth_corner_updown_r", 
                         "mouth_corner_inout_r", "mouth_open", "mouth_wide"]
        
        self.terminate = False
        self.last_fps_counter = 0

    def run(self):
        model_base_path = get_model_base_path(self.model_dir)
        im = cv2.imread(os.path.join(model_base_path, "benchmark.bin"), cv2.IMREAD_COLOR)
        results = []

        fps = self.fps
        dcap = None
        use_dshowcapture_flag = False
        if os.name == 'nt':
            dcap = self.dcap
            use_dshowcapture_flag = True if self.use_dshowcapture else False
            input_reader = InputReader(self.capture, self.raw_rgb, self.width, self.height, fps, use_dshowcapture=use_dshowcapture_flag, dcap=dcap)
            if self.dcap == -1 and type(input_reader) == DShowCaptureReader:
                fps = min(fps, input_reader.device.get_fps())
        else:
            print("open input")
            input_reader = InputReader(self.capture, self.raw_rgb, self.width, self.height, fps)
            print("open input done")
        if type(input_reader.reader) == VideoReader:
            fps = 0

        first = True
        height = 0
        width = 0
        tracker = None
        sock = None
        total_tracking_time = 0.0
        tracking_time = 0.0
        tracking_frames = 0
        frame_count = 0

        features = self.features
        is_camera = self.capture == str(try_int(self.capture))
        perf_time = time.perf_counter()

        try:
            attempt = 0
            frame_time = time.perf_counter()
            target_duration = 0
            if fps > 0:
                target_duration = 1. / float(fps)
            repeat = False
            need_reinit = 0
            failures = 0
            source_name = input_reader.name
            while not self.terminate and (repeat or input_reader.is_open()):

                if not input_reader.is_open() or need_reinit == 1:
                    print("open input")
                    input_reader = InputReader(self.capture, self.raw_rgb, self.width, self.height, fps, use_dshowcapture=use_dshowcapture_flag, dcap=dcap)
                    if input_reader.name != source_name:
                        print(f"Failed to reinitialize camera and got {input_reader.name} instead of {source_name}.")
                    need_reinit = 1
                    time.sleep(0.02)
                    continue

                if not input_reader.is_ready():
                    time.sleep(0.02)
                    continue

                ret, frame = input_reader.read()
                if not ret:
                    if repeat:
                        if need_reinit == 0:
                            need_reinit = 1
                        continue
                    elif is_camera:
                        attempt += 1
                        if attempt > 30:
                            pass
                            break
                        else:
                            time.sleep(0.02)
                            if attempt == 3:
                                need_reinit = 1
                            continue
                    else:
                        break;

                attempt = 0
                need_reinit = 0
                frame_count += 1
                now = time.time()

                if first:
                    first = False
                    height, width, channels = frame.shape
                    tracker = Tracker(width, height, threshold=self.threshold, max_threads=self.max_threads, max_faces=self.faces, discard_after=self.discard_after, 
                                      scan_every=self.scan_every, silent=False if not self.silent else True, model_type=self.model, model_dir=self.model_dir, 
                                      no_gaze=False if self.gaze_tracking and self.model != -1 else True, detection_threshold=self.detection_threshold, 
                                      use_retinaface=self.scan_retinaface, max_feature_updates=self.max_feature_updates, static_model=True if self.no_3d_adapt else False, 
                                      try_hard=self.try_hard == 1)

                try:
                    inference_start = time.perf_counter()
                    faces = tracker.predict(frame)
                    if len(faces) > 0:
                        inference_time = (time.perf_counter() - inference_start)
                        total_tracking_time += inference_time
                        tracking_time += inference_time / len(faces)
                        tracking_frames += 1
                    detected = False
                    for face_num, f in enumerate(faces):
                        f = copy.copy(f)
                        if f.eye_blink is None:
                            f.eye_blink = [1, 1]
                        self.latest_faces[face_num] = f

                        if f.current_features is None:
                            f.current_features = {}
                        for feature in features:
                            if not feature in f.current_features:
                                f.current_features[feature] = 0

                    if detected and len(faces) < 40:
                        sock.sendto(packet, (target_ip, target_port))
                        
                    failures = 0
                except Exception as e:
                    if e.__class__ == KeyboardInterrupt:
                        if self.silent == 0:
                            pass
                        break
                    traceback.print_exc()
                    failures += 1
                    if failures > 30:
                        break

                collected = False
                del frame
                
                duration = time.perf_counter() - frame_time
                while duration < target_duration:
                    if not collected:
                        gc.collect()
                        collected = True
                    duration = time.perf_counter() - frame_time
                    sleep_time = target_duration - duration
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    duration = time.perf_counter() - frame_time
                frame_time = time.perf_counter()
                
                time_diff = time.perf_counter() - perf_time
                if time_diff >= 1:
                    self.last_fps_counter = frame_count / time_diff
                    frame_count = 0
                    perf_time = time.perf_counter()
                    if self.silent == 0:
                        print("%5.2f fps"%self.last_fps_counter)

                repeat = True
        except KeyboardInterrupt:
            if not self.silent:
                print("Quitting")

        input_reader.close()
        print("Terminated")