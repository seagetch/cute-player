
from .facetracker import FaceTracker
from .gui import run


import threading
if __name__ == "__main__":
    tracker = FaceTracker()
    tracker.terminate = True
#    th = threading.Thread(target=tracker.run)
#    th.start()
    run(tracker)