import cv2
import face_recognition 

input_movie = cv2.VideoCapture("video_recog/messi_and_neymar.mp4")
height, width = (284 *2, 514*2)
# output_movie = cv2.VideoWriter('video_recog/sample_video_out.mp4', fourcc, 20, (height, width), True)
# output_movie = result = cv2.VideoWriter('output_vid.flv',  cv2.VideoWriter_fourcc(*'AVC1'), 
# 10, (height, width)) 
length = int(input_movie.get(cv2.CAP_PROP_FRAME_COUNT))
image_path = ["video_recog/image/messi.jpeg",
              "video_recog/image/neymar1.jpeg"]

known_faces = []
labels = []
for path in image_path:
    image = face_recognition.load_image_file(path)
    face_encoding = face_recognition.face_encodings(image)[0]
    known_faces.append(face_encoding)
    labels.append(path.split('/')[-1].split('.')[0])



face_locations = []
face_encodings = []
face_names = []
frame_number = 0


import os
from shutil import rmtree
folder_path = 'Image Frames'
if os.path.exists(folder_path):
    rmtree(folder_path)
os.makedirs(folder_path)


while True:
    # Grab a single frame of video
    ret, frame = input_movie.read()
    frame_number += 1
    
    # if frame_number==15:
    #     break
    
    print("Writing frame {} / {}".format(frame_number, length))
    

    # Quit when the input video file ends
    if not ret:
        break

    # Convert the image from BGR color (which OpenCV uses) to RGB color (which face_recognition uses)
    # rgb_frame = frame[:, :, ::-1]

    # Find all the faces and face encodings in the current frame of video
    face_locations = face_recognition.face_locations(frame, model="cnn")
    print(f"face locations in frame {frame_number}", len(face_locations))
    face_encodings = face_recognition.face_encodings(frame, face_locations)
    
    
    total_match = []
    face_names = []
    for face_encoding in face_encodings:
        # See if the face is a match for the known face(s)
        matches = face_recognition.compare_faces(known_faces, face_encoding, tolerance=0.55)
        for match in matches:
            if match:
                name = labels[matches.index(match)] 
                print(name)
                face_names.append(name)
            
            
    
    # Label the results
    for (top, right, bottom, left),name in zip(face_locations, face_names):
        if not name:
            continue

        # Draw a box around the face
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)

        
        # Draw a label with a name below the face
        # cv2.rectangle(frame, (left, bottom - 25), (right, bottom), (0, 0, 255), cv2.FILLED)
        font = cv2.FONT_HERSHEY_DUPLEX
        cv2.putText(frame, name, (left + 6, bottom - 6), font, 0.5, (255, 255, 255), 1)
        
    
    # output_movie.write(frame)
    cv2.imwrite(folder_path +'/my_video_frame'+ str(frame_number) +'.png', frame)
'''input_movie.release()
cv2.destroyAllWindows()
'''
