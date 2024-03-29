import face_recognition
from imutils.video import VideoStream
import imutils
import cv2

import pickle
import time


print("Loading Embeddings...")
data = pickle.load(open('/home/rduser/project/WebCam_Image_Recognition/Face_Recognition/pickles/l5.pickle', 'rb'))
known_encodings = data['encodings']
length = 6
known_faces = data['labels']


print("Initializing Webcam..")
video_source = VideoStream(src=0).start()

while True:
    ## Getting the frame from the video
    frame = video_source.read()
    # convert the input frame from BGR to RGB then resize it to have
    # a width of 750px (to speedup processing)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb = imutils.resize(frame, width=750)
    r = frame.shape[1] / float(rgb.shape[1])
    
    boxes = face_recognition.face_locations(rgb)
    encodings = face_recognition.face_encodings(rgb, boxes, model='large')
    
    names = []
    ## Iterate through the detected faces from the test image
    for encoding in encodings:
        ## Iterate through the known face inside the trained known faces
        true_count = []
        for each_label in known_encodings:
            matches = face_recognition.compare_faces(each_label, encoding)
            print(matches)
            count = matches.count(True)
            true_count.append(count)
        index = true_count.index(max(true_count))
        if max(true_count) > length/2:
            names.append(known_faces[index])
        else:
            names.append("Unknown")
    for ((top, right, bottom, left), name) in zip(boxes, names):
        top = int(top * r)
        right = int(right * r)
        bottom = int(bottom * r)
        left = int(left * r)

        cv2.rectangle(frame, (left, top), (right, bottom),
			(0, 255, 0), 2)
        y = top - 15 if top - 15 > 15 else top + 15
        cv2.putText(frame, name, (left, y), cv2.FONT_HERSHEY_SIMPLEX,
			0.75, (0, 255, 0), 2)
        
    if True:
        cv2.imshow("Frame", frame)
        key = cv2.waitKey(1) & 0xFF

        # if the `q` key was pressed, break from the loop
        if key == ord("q"):
            break
        
cv2.destroyAllWindows()
video_source.stop()
