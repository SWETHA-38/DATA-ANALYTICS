import cv2
import numpy as np
import face_recognition
# imagepath = 'Face-Detection/face_detection/images/boyImage1.jpg'
# imagepath1 = 'Face-Detection/face_detection/images/boyImage2.jpg'
# img_bgr = face_recognition.load_image_file('Face-Detection/face_detection/images/boyImage1.jpg')
# img_rgb = cv2.cvtColor(img_bgr,cv2.COLOR_BGR2RGB)
# cv2.imshow('bgr', img_bgr)
# cv2.imshow('rgb', img_rgb)

import matplotlib.pyplot as plt

image_name = []
image_encoding = []


def training():
    image_paths = ['/home/swetha/Project/Face-Recognition/face_detection/images/johneydepp.jpeg',
                '/home/swetha/Project/Face-Recognition/face_detection/images/messi.jpeg',
                '/home/swetha/Project/Face-Recognition/face_detection/images/rdj.jpeg',
                # 'Face-Recognition/face_detection/images/narash1.jpeg', 
                '/home/swetha/Project/Face-Recognition/face_detection/images/ronaldo.jpeg',
                # 'Face-Recognition/face_detection/images/tomhardy.jpeg',
                # 'Face-Recognition/face_detection/images/chirstianbale.jpeg',
                # 'Face-Recognition/face_detection/images/pratbitt.jpeg'
                ]

    for image in image_paths:
        curimage = face_recognition.load_image_file(image)
        train_encode = face_recognition.face_encodings(curimage)[0]
        image_name.append(image.split('/')[-1].split('.')[0])
        image_encoding.append(train_encode)

training()

## Testing
def predict(imagepath):
    data = face_recognition.load_image_file(imagepath)
    test_encode = face_recognition.face_encodings(data)
    print(test_encode)
    for face in test_encode:
        match = face_recognition.compare_faces(image_encoding, face)
        matchIndex = None
        for i in range(len(match)):
            if match[i] == True:
                matchIndex = i
                break
        if matchIndex is not None:
            print('Matched Index: ', matchIndex )
            print("Person Name:",image_name[matchIndex])
        else:
            print('No Match')
    

image_for_prediction = '/home/swetha/Project/Face-Recognition/face_detection/images/rdj3.jpeg'
predict(image_for_prediction)





































## Hog (Histogram of Oriented Gradients) is a feature descriptor commonly used for object and face detections

# import cv2

# # Load the image
# image = cv2.imread('Face-Detection/face_detection/images/messi6.png')

# # Convert the image to grayscale
# gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# # Initialize HOG descriptor
# hog = cv2.HOGDescriptor()

# Compute HOG features
# print(hog.compute(gray_image))

# Display the HOG features
# print(features)
