pyinstaller ^
  --windowed ^
  --icon="emotion_posture_detector.ico" ^
  --add-data "haarcascade_frontalface_default.xml;." ^
  --add-data "emotion_detection.h5;." ^
  --add-data "emotion_posture_detector.ico;." ^
  --add-data "ARIALBD 1.ttf;." ^
  --add-data "C:\Users\ADMIN\AppData\Local\Programs\Python\Python310\Lib\site-packages\mediapipe\modules;mediapipe/modules" ^
  emotion_posture_detector_v3.0.py
