
import facetracker
import gui


import threading
if __name__ == "__main__":
    tracker = facetracker.FaceTracker()
    tracker.terminate = True
#    th = threading.Thread(target=tracker.run)
#    th.start()
    gui.run(tracker)