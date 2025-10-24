# Emotion + Posture Detector v3.0
# Tác giả: Nguyễn Tấn Phú, Nguyễn Xuân Trụ
# Giáo viên hướng dẫn: Huỳnh Thị Khánh Nga
# Lớp: 12/5
# Trường: THPT Nguyễn Trãi, Đà Nẵng
import cv2
import numpy as np
import os
import tkinter as tk
import sys
import win32gui
import win32con
import time
import socket
from tkinter import ttk, messagebox
from pygrabber.dshow_graph import FilterGraph
from collections import deque
from PIL import ImageFont, ImageDraw, Image
from threading import Thread, Lock

# Flask cho streaming
from flask import Flask, Response, render_template_string

# Setup đường dẫn
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

icon_path = os.path.join(BASE_DIR, "emotion_posture_detector.ico")
font_path = os.path.join(BASE_DIR, "ARIALBD 1.ttf")

# GLOBALS cho streaming
latest_frame = None
frame_lock = Lock()

def udp_broadcast(message, port=5000, interval=5):
    """Gửi broadcast UDP liên tục để thiết bị trong LAN bắt được link."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.2)
    while True:
        try:
            sock.sendto(message.encode("utf-8"), ("<broadcast>", port))
        except Exception as e:
            print("Broadcast error:", e)
        time.sleep(interval)

# Flask app đơn giản
app = Flask(__name__)


HTML_PAGE = """
<html>
  <head>
    <link rel="icon" href="{{ url_for('static', filename='emotion_posture_detector.ico') }}" type="image/x-icon">
    <title>Emotion + Posture Detector Stream</title>
    <style>
      body {
        background: #a19fa2;
        color: #fff;
        font-family: Arial, sans-serif;
        margin: 0;
        height: 100vh; /* Chiều cao toàn màn hình */
        display: flex;
        flex-direction: column; /* Sắp xếp theo cột */
        justify-content: center; /* Căn giữa theo chiều dọc */
        align-items: center; /* Căn giữa theo chiều ngang */
      }

      h2 {
        margin-bottom: 20px;
      }

      img {
        max-width: 90%;
        height: auto;
        border-radius: 10px; /* Bo góc */
        box-shadow: 0 0 15px rgba(0, 0, 0, 0.3); /* Đổ bóng nhẹ */
      }
    </style>
  </head>

  <body>
    <h2>Emotion + Posture Detector Live - Camera</h2>
    <img src="{{ url_for('video_feed') }}">
  </body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML_PAGE, ip=get_local_ip(), port=5000)

def gen_frames():
    """Generator trả về các multipart JPEG (MJPEG)."""
    global latest_frame, frame_lock
    while True:
        with frame_lock:
            if latest_frame is None:
                # chưa có frame -> chờ
                time.sleep(0.03)
                continue
            # encode frame thành JPEG để stream
            ret, buffer = cv2.imencode('.jpg', latest_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if not ret:
                continue
            jpg = buffer.tobytes()
        # multipart
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpg + b'\r\n')
        # điều chỉnh fps stream nếu cần
        time.sleep(0.03)

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def start_flask_server():
    # chạy Flask trên 0.0.0.0 để có thể truy cập từ LAN
    # debug=False, use_reloader=False để không spawn process phụ
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False, use_reloader=False)

# Utility: lấy IP cục bộ (IPv4)
def get_local_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # kết nối tới 1 địa chỉ công cộng (không gửi dữ liệu) để dò interface
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

# Liệt kê camera
def list_cameras():
    graph = FilterGraph()
    devices = graph.get_input_devices()
    return devices

# Vẽ chữ có viền (dùng PIL)
def draw_text_with_outline(draw, pos, text, font, text_color,
                           outline_color=(0, 0, 0), outline_width=1):
    x, y = pos
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
    draw.text((x, y), text, font=font, fill=text_color)

# Hàm set always on top + nhảy ra trước
def bring_window_to_front(window_name="Emotion + Posture Detector v3.0"):
    hwnd = win32gui.FindWindow(None, window_name)
    if hwnd:
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST,
                              0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNORMAL)  # hiển thị nếu đang bị minimize
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass  # Windows có thể từ chối SetForegroundWindow

# Vẽ ô có viền
def draw_filled_rectangle_with_outline(img, pt1, pt2, color,
                                       outline_color=(0, 0, 0),
                                       outline_width=1):
    cv2.rectangle(img,
                  (pt1[0] - outline_width, pt1[1] - outline_width),
                  (pt2[0] + outline_width, pt2[1] + outline_width),
                  outline_color, -1)
    cv2.rectangle(img, pt1, pt2, color, -1)

# Hiện cảnh báo
def show_warning(msg):
    win = tk.Toplevel()
    win.withdraw()
    win.attributes('-topmost', True)
    messagebox.showwarning("Cảnh báo", msg, parent=win)
    win.destroy()

# Hàm tính góc
def calculate_angle(a, b, c):
    import math
    ax, ay = a
    bx, by = b
    cx, cy = c
    angle = math.degrees(
        math.atan2(cy - by, cx - bx) - math.atan2(ay - by, ax - bx)
    )
    return abs(angle)

def copy_link_to_clipboard(link, link_window):
    """Sao chép đường link vào clipboard."""
    root.clipboard_clear()
    root.clipboard_append(link)
    messagebox.showinfo("Thông báo", "Đã sao chép đường link vào Clipboard!")
    link_window.destroy() # Đóng cửa sổ sau khi copy

def show_stream_link(link):
    """Hiển thị hộp thoại chứa link stream và nút copy."""
    link_window = tk.Toplevel(root)
    link_window.title("Đường Link Stream")
    
    # Ép cửa sổ này luôn nằm trên cùng và hiện ra trước
    link_window.attributes('-topmost', True)
    link_window.update()
    
    tk.Label(link_window, text="Đường link truy cập Stream:", font=("Arial", 10, "bold")).pack(pady=10, padx=20)
    
    # Tạo Entry để hiển thị link
    link_entry = tk.Entry(link_window, width=50, justify='center')
    link_entry.insert(0, link)
    link_entry.config(state="readonly")
    link_entry.pack(pady=5, padx=20)

    # Nút Copy
    copy_btn = tk.Button(link_window, 
                         text="Sao chép Link và Đóng", 
                         command=lambda: copy_link_to_clipboard(link, link_window), 
                         bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
    copy_btn.pack(pady=15)
    
    # Căn giữa cửa sổ mới
    root.update_idletasks()
    x = root.winfo_x() + (root.winfo_width() - link_window.winfo_reqwidth()) // 2
    y = root.winfo_y() + (root.winfo_height() - link_window.winfo_reqheight()) // 2
    link_window.geometry(f"+{x}+{y}")


# Chạy nhận diện
def run_detection(cam_index):
    global latest_frame, frame_lock

    # start Flask server lần đầu (1 thread)
    if not hasattr(run_detection, "_flask_started"):
        update_progress(10, "Khởi động Flask server...")
        t = Thread(target=start_flask_server, daemon=True)
        t.start()
        
        # CHỜ MỘT CHÚT ĐỂ SERVER KHỞI ĐỘNG
        time.sleep(1) 
        
        run_detection._flask_started = True

    # Tiến trình 25%
    update_progress(25, "Đang tải mô hình nhận diện cảm xúc (Keras)...")

    # Luôn lấy link IP và hiển thị hộp thoại mỗi lần mở camera
    local_ip = get_local_ip()
    link = f"http://{local_ip}:5000/"
    print(f"Flask server: {link}")

    # Bắt đầu broadcast link (nếu chưa chạy thì mới chạy)
    if not hasattr(run_detection, "_broadcast_started"):
        tb = Thread(target=udp_broadcast, args=(link,), daemon=True)
        tb.start()
        print(f"Broadcasting link: {link}")
        run_detection._broadcast_started = True


    import mediapipe as mp
    from tensorflow.keras.models import load_model

    face_xml = os.path.join(BASE_DIR, "haarcascade_frontalface_default.xml")
    model_h5 = os.path.join(BASE_DIR, "emotion_detection.h5")

    face_classifier = cv2.CascadeClassifier(face_xml)
    if face_classifier.empty():
        messagebox.showerror("Lỗi", f"Không tìm thấy file cascade: {face_xml}")
        return

    classifier = load_model(model_h5)
    # Tiến trình 50%
    update_progress(50, "Đang tải mô hình tư thế (MediaPipe)...")

    class_labels = ['Giận dữ', 'Ghê sợ', 'Sợ hãi',
                    'Vui vẻ', 'Buồn', 'Bất ngờ', 'Trung lập']

    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
    mp_drawing = mp.solutions.drawing_utils

    # Tiến trình 70%
    update_progress(70, "Đang mở camera...")

    cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)
    WIDTH, HEIGHT = 1280, 720
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)

    if not cap.isOpened():
        messagebox.showerror("Lỗi", "Không thể mở camera.")
        return

    # Tiến trình 100%
    update_progress(100, "Hoàn tất! Mở camera...")
    root.after(0, lambda: loading_window.destroy() if loading_window and loading_window.winfo_exists() else None)

    #gọi show_stream_link sau khi OpenCV mở lên
    root.after(100, show_stream_link, link)

    history = deque(maxlen=150)
    start_time = time.time()
    interval = 120
    scale_factor = 1.0  # tỷ lệ hiển thị (1.0 = 100%)
    first_show = True  # Đánh dấu lần show đầu tiên

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # --- giữ nguyên logic nhận diện ---
        frame_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(frame_pil)
        font = ImageFont.truetype(font_path, 28)
        font2 = ImageFont.truetype(font_path, 20)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_classifier.detectMultiScale(gray, 1.3, 5)

        labels = []
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (242, 248, 68), 2)

            roi_gray = gray[y:y + h, x:x + w]
            roi_gray = cv2.resize(roi_gray, (48, 48), interpolation=cv2.INTER_AREA)
            roi = roi_gray.astype("float") / 255.0
            roi = np.expand_dims(roi, axis=-1)
            roi = np.expand_dims(roi, axis=0)

            preds = classifier.predict(roi, verbose=0)[0]
            label = class_labels[preds.argmax()]
            labels.append(label)

            frame_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(frame_pil)
            font = ImageFont.truetype(font_path, 28)

            draw_text_with_outline(draw, (x, y - 35), label, font,
                                   text_color=(0, 255, 0),
                                   outline_color=(0, 0, 0),
                                   outline_width=1)
            frame = cv2.cvtColor(np.array(frame_pil), cv2.COLOR_RGB2BGR)

        if labels:
            if labels.count("Trung lập") >= len(labels) / 2:
                history.append(1)
            else:
                history.append(0)

        neutral_ratio = sum(history) / len(history) if len(history) > 0 else 0

        elapsed = time.time() - start_time
        if elapsed >= interval:
            if neutral_ratio > 0.6:
                show_warning("Pause / đổi hoạt động / nghỉ 2 phút")
            start_time = time.time()

        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(image_rgb)

        status = "Đang phân tích..."
        color = (255, 255, 255)

        if results.pose_landmarks:
            landmarks = results.pose_landmarks.landmark
            shoulder = [landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value].x,
                        landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value].y]
            ear = [landmarks[mp_pose.PoseLandmark.LEFT_EAR.value].x,
                   landmarks[mp_pose.PoseLandmark.LEFT_EAR.value].y]
            hip = [landmarks[mp_pose.PoseLandmark.LEFT_HIP.value].x,
                   landmarks[mp_pose.PoseLandmark.LEFT_HIP.value].y]

            angle = calculate_angle(ear, shoulder, hip)

            if angle >= 170:
                status = "Ngồi thẳng"
                color = (0, 255, 0)
            elif 150 <= angle < 170:
                status = "Ngồi hơi cúi"
                color = (255, 255, 0)
            else:
                status = "Ngồi cúi nhiều"
                color = (255, 0, 0)

            mp_drawing.draw_landmarks(frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)

        # Chọn màu box
        if neutral_ratio > 0.6:
            box_color = (0, 0, 255)
        elif 0.2 <= neutral_ratio <= 0.6:
            box_color = (0, 255, 255)
        else:
            box_color = (0, 255, 0)

        frame_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(frame_pil)

        draw_text_with_outline(draw, (30, 30), status, font, color,
                               outline_color=(0, 0, 0), outline_width=1)
        draw_text_with_outline(draw, (30, 75), f"Số lượng: {len(faces)}", font,
                               (255, 0, 255), outline_color=(0, 0, 0), outline_width=1)
        draw_text_with_outline(draw, (30, 120), "Trạng thái:", font,
                               (0, 0, 255), outline_color=(0, 0, 0), outline_width=1)
        draw_text_with_outline(draw, (960, 680), "Bấm phím 'Q' để thoát", font,
                               (255, 255, 0), outline_color=(0, 0, 0), outline_width=1)
        draw_text_with_outline(draw, (1000, 20), "Bấm phím 'M' để phóng to", font2,
                               (255, 255, 0), outline_color=(0, 0, 0), outline_width=1)
        draw_text_with_outline(draw, (1000, 50), "Bấm phím 'N' để thu nhỏ", font2,
                               (255, 255, 0), outline_color=(0, 0, 0), outline_width=1)

        frame = cv2.cvtColor(np.array(frame_pil), cv2.COLOR_RGB2BGR)
        draw_filled_rectangle_with_outline(frame, (190, 120), (230, 160),
                                           box_color, outline_color=(0, 0, 0), outline_width=2)

        # Phím tắt thu nhỏ, phóng to và chú thích
        key = cv2.waitKey(10) & 0xFF
        if key == ord('m'):  # phóng to
            scale_factor = min(1.0, scale_factor + 0.1)
        elif key == ord('n'):  # thu nhỏ
            scale_factor = max(0.2, scale_factor - 0.1)
        elif key == ord('q'):
            break

        if scale_factor != 1.0:
            new_w = int(WIDTH * scale_factor)
            new_h = int(HEIGHT * scale_factor)
            frame = cv2.resize(frame, (new_w, new_h))

        # Hiển thị trên máy
        cv2.imshow('Emotion + Posture Detector v3.0', frame)

        # Cập nhật frame cho Flask stream (giảm kích thước để tiết kiệm băng thông)
        small = cv2.resize(frame, (int(frame.shape[1]*0.6), int(frame.shape[0]*0.6)))
        with frame_lock:
            latest_frame = small.copy()

        # Lần đầu mở -> ép nhảy ra trước
        if first_show:
            bring_window_to_front("Emotion + Posture Detector v3.0")
            first_show = False
        else:
            # Các lần sau vẫn giữ topmost
            hwnd = win32gui.FindWindow(None, "Emotion + Posture Detector v3.0")
            if hwnd:
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST,
                                      0, 0, 0, 0,
                                      win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)

    cap.release()
    cv2.destroyAllWindows()

loading_window = None
progress_bar = None
progress_label = None

def show_loading_window():
    """Tạo cửa sổ hiển thị tiến trình load thật."""
    global loading_window, progress_bar, progress_label

    loading_window = tk.Toplevel(root)
    loading_window.title("Đang khởi động camera...")
    loading_window.geometry("400x140")
    loading_window.resizable(False, False)
    loading_window.attributes('-topmost', True)

    tk.Label(loading_window, text="Đang khởi động hệ thống, vui lòng chờ...", 
             font=("Arial", 10)).pack(pady=10)

    progress_bar = ttk.Progressbar(loading_window, orient="horizontal", length=350, mode="determinate")
    progress_bar.pack(pady=10)
    progress_bar["maximum"] = 100
    progress_bar["value"] = 0

    progress_label = tk.Label(loading_window, text="0%", font=("Arial", 10, "bold"))
    progress_label.pack()

def update_progress(percent, text=None):
    """Cập nhật tiến trình lên giao diện."""
    if progress_bar and progress_label and loading_window and loading_window.winfo_exists():
        progress_bar["value"] = percent
        if text:
            progress_label.config(text=f"{text} ({percent}%)")
        else:
            progress_label.config(text=f"{percent}%")
        loading_window.update_idletasks()


# GUI chọn camera
def open_camera():
    selected = combo.current()
    if selected == -1:
        messagebox.showwarning("Chưa chọn", "Vui lòng chọn một camera.")
        return

    # Hiển thị cửa sổ loading
    show_loading_window()

    def start_detection():
        try:
            run_detection(selected)  # chạy nhận diện
        finally:
            # Nếu cửa sổ loading vẫn tồn tại, đóng nó
            root.after(0, lambda: loading_window.destroy() if loading_window and loading_window.winfo_exists() else None)

    t = Thread(target=start_detection, daemon=True)
    t.start()


# GUI khởi động ngay lập tức
root = tk.Tk()
root.title("Emotion + Posture Detector v3.0 - Camera Selection")
root.attributes('-topmost', True)
root.update()
root.attributes('-topmost', False)

if os.path.exists(icon_path):
    root.iconbitmap(icon_path)

cameras = list_cameras()

label = tk.Label(root, text="Chọn camera:")
label.pack(pady=5)

combo = ttk.Combobox(root, values=cameras, state="readonly", width=50)
combo.pack(pady=5)

btn = tk.Button(root, text="Mở Camera", command=open_camera)
btn.pack(pady=10)

root.mainloop()

