import sys
import os
import time
import threading
import psutil
import win32pipe
import win32file
import pywintypes
import win32con
import win32job
import win32api
import shutil
import base64
import random
from PyQt6.QtCore import Qt, QRectF, QSize, QRect, QPoint, QPointF, QTimer
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QGroupBox, QCheckBox, QPushButton, QSizePolicy
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QLinearGradient, QRadialGradient

pipe_name = r'\\.\pipe\933823D3-C77B-4BAE-89D7-A92B567236BC'
valorant_running = False
stopped_once = False
current_job = None
log_callback = None
pipe_threads = []
pipe_handles = []
monitor_thread = None
monitored_pids = set()
monitored_lock = threading.Lock()
monitoring_active = False

def make_shutdown_event():
    return threading.Event()

shutdown_event = make_shutdown_event()

def log_message(msg):
    global log_callback
    if log_callback:
        log_callback(msg)

def stop_and_restart_vgc():
    os.system('sc stop vgc')
    time.sleep(0.5)
    os.system('sc start vgc')
    time.sleep(0.5)

def override_vgc_pipe():
    try:
        pipe = win32file.CreateFile(
            pipe_name,
            win32con.GENERIC_READ | win32con.GENERIC_WRITE,
            0, None, win32con.OPEN_EXISTING, 0, None)
        win32file.CloseHandle(pipe)
    except Exception:
        pass

def handle_client(pipe):
    global stopped_once
    try:
        while not shutdown_event.is_set():
            try:
                data = win32file.ReadFile(pipe, 4096)
                if data:
                    if not stopped_once:
                        os.system('sc stop vgc')
                        try:
                            import winsound
                            winsound.Beep(1000, 500)
                        except:
                            pass
                        stopped_once = True
                    win32file.WriteFile(pipe, data[1])
            except pywintypes.error as e:
                if getattr(e, 'winerror', None) == 109:
                    break
                time.sleep(0.1)
    finally:
        try:
            win32file.CloseHandle(pipe)
        except Exception:
            pass

def create_named_pipe():
    global pipe_handles
    while not shutdown_event.is_set():
        try:
            pipe = win32pipe.CreateNamedPipe(
                pipe_name,
                win32con.PIPE_ACCESS_DUPLEX,
                win32con.PIPE_TYPE_MESSAGE | win32con.PIPE_WAIT,
                win32con.PIPE_UNLIMITED_INSTANCES,
                1048576, 1048576, 500, None)
            pipe_handles.append(pipe)
            win32pipe.ConnectNamedPipe(pipe, None)
            t = threading.Thread(target=handle_client, args=(pipe,), daemon=True)
            t.start()
            pipe_threads.append(t)
        except Exception:
            time.sleep(1)

def create_job_object():
    job = win32job.CreateJobObject(None, "")
    extended_info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    extended_info['BasicLimitInformation']['LimitFlags'] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, extended_info)
    return job

def assign_valorant_to_job():
    global current_job
    if current_job:
        try:
            win32job.TerminateJobObject(current_job, 0)
            current_job.Close()
        except Exception:
            pass
        current_job = None
        time.sleep(2)

    current_job = create_job_object()
    found = False

    while not found and not shutdown_event.is_set():
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and "VALORANT-Win64-Shipping.exe" in proc.info['name']:
                    h_process = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, False, proc.info['pid'])
                    win32job.AssignProcessToJobObject(current_job, h_process)
                    found = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not found:
            time.sleep(1)

def find_riot_client_path():
    for proc in psutil.process_iter(['name', 'exe']):
        try:
            if proc.info['name'] and proc.info['name'].lower() == "riotclientservices.exe":
                if proc.info['exe'] and os.path.exists(proc.info['exe']):
                    return proc.info['exe']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    common_dirs = [
        r"C:\Riot Games",
        r"C:\Program Files\Riot Games",
        r"C:\Program Files (x86)\Riot Games",
    ]

    for base in common_dirs:
        candidate = os.path.join(base, "Riot Client", "RiotClientServices.exe")
        if os.path.exists(candidate):
            return candidate

    exe_in_path = shutil.which("RiotClientServices.exe")
    if exe_in_path:
        return exe_in_path

    search_roots = [r"C:\Program Files", r"C:\Program Files (x86)", r"C:\Riot Games"]
    for root in search_roots:
        for dirpath, _, filenames in os.walk(root):
            if "RiotClientServices.exe" in filenames:
                return os.path.join(dirpath, "RiotClientServices.exe")

    return None

def launch_valorant():
    os.system('"C:\\Riot Games\\Riot Client\\RiotClientServices.exe" --launch-product=valorant --launch-patchline=live')
    assign_valorant_to_job()

def start_valorant():
    global valorant_running, current_job
    if not valorant_running:
        threading.Thread(target=launch_valorant, daemon=True).start()
        valorant_running = True
    else:
        if current_job:
            try:
                win32job.TerminateJobObject(current_job, 0)
                current_job.Close()
            except Exception:
                pass
            current_job = None

        os.system('taskkill /f /im VALORANT-Win64-Shipping.exe')
        valorant_running = False

def monitor_new_exes():
    global monitored_pids, monitoring_active
    prev_pids = set(p.info['pid'] for p in psutil.process_iter(['pid']))
    while monitoring_active and not shutdown_event.is_set():
        current_pids = set(p.info['pid'] for p in psutil.process_iter(['pid']))
        new_pids = current_pids - prev_pids
        with monitored_lock:
            for pid in new_pids:
                try:
                    proc = psutil.Process(pid)
                    exe = proc.exe()
                    if exe:
                        monitored_pids.add(pid)
                except Exception:
                    continue
        prev_pids = current_pids
        time.sleep(0.5)

def start_monitoring_exes():
    global monitoring_active, monitor_thread, monitored_pids
    with monitored_lock:
        monitored_pids.clear()
    monitoring_active = True
    monitor_thread = threading.Thread(target=monitor_new_exes, daemon=True)
    monitor_thread.start()

def stop_monitoring_exes():
    global monitoring_active, monitor_thread
    monitoring_active = False
    if monitor_thread:
        monitor_thread.join(timeout=2)
        monitor_thread = None

def kill_monitored_exes():
    killed = []
    with monitored_lock:
        for pid in list(monitored_pids):
            try:
                proc = psutil.Process(pid)
                exe = proc.exe()
                if exe and proc.is_running():
                    proc.kill()
                    killed.append(exe)
            except Exception:
                pass
        monitored_pids.clear()
    return killed

def reset_shutdown_event():
    global shutdown_event
    shutdown_event = make_shutdown_event()

def close_all_pipes():
    global pipe_handles
    for h in pipe_handles:
        try:
            win32file.CloseHandle(h)
        except Exception:
            pass
    pipe_handles.clear()

def start_with_emulate():
    global stopped_once, valorant_running, current_job, pipe_threads
    stopped_once = False
    reset_shutdown_event()
    close_all_pipes()
    pipe_threads.clear()
    if current_job:
        try:
            win32job.TerminateJobObject(current_job, 0)
            current_job.Close()
        except Exception:
            pass
        current_job = None
    stop_and_restart_vgc()
    override_vgc_pipe()
    threading.Thread(target=create_named_pipe, daemon=True).start()
    start_monitoring_exes()
    threading.Thread(target=launch_valorant, daemon=True).start()
    valorant_running = True

def safe_exit():
    global valorant_running, current_job, stopped_once, pipe_threads
    shutdown_event.set()
    stopped_once = False
    try:
        for t in pipe_threads:
            t.join(timeout=1)
    except:
        pass
    pipe_threads.clear()

close_all_pipes()
if current_job:
    try:
        win32job.TerminateJobObject(current_job, 0)
        current_job.Close()
    except Exception:
        pass
    current_job = None

os.system('taskkill /f /im VALORANT-Win64-Shipping.exe')
os.system('sc stop vgc')
valorant_running = False

stop_monitoring_exes()
kill_monitored_exes()

class SystemMonitorWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.fan_angle = 0
        self.setMinimumSize(360, 400)
        self.temperature = 34.0
        self.rpm = 0
        self.sensor_data = {
            "CPU": 27,
            "System 1": 26,
            "System 2": 26,
            "Chipset": 29,
            "VRM MOS": 34,
            "PCIE X16": 27,
            "PCIE X8": 26
        }
        self.fan_curve = {
            30: 25,
            40: 40,
            50: 50,
            60: 65,
            70: 85,
            80: 97,
            90: 100
        }
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_data)
        self.timer.start(1000)

    def update_data(self):
        self.temperature += random.uniform(-0.3, 0.3)
        self.temperature = max(30, min(95, self.temperature))
        self.rpm = int((self.temperature - 30) * 100)

        for key in self.sensor_data:
            if isinstance(self.sensor_data[key], int):
                self.sensor_data[key] += random.randint(-1, 1)

        self.fan_angle += self.rpm / 60
        self.fan_angle %= 360
        self.update()

    def draw_temp_icon(self, painter, x, y, height=60):
        bulb_radius = 14
        width = 16
        tube_height = height - bulb_radius * 2
        min_temp = -20
        max_temp = 45

        temperature = max(min(self.temperature, max_temp), min_temp)
        temp_ratio = (temperature - min_temp) / (max_temp - min_temp)
        temp_ratio = min(max(temp_ratio, 0), 1)
        fill_height = int(tube_height * temp_ratio)
        fill_y = y + tube_height - fill_height

        tube_rect = QRectF(x, y, width, tube_height)
        tube_gradient = QLinearGradient(x, y, x + width, y + tube_height)
        tube_gradient.setColorAt(0, QColor("#2c2c2c"))
        tube_gradient.setColorAt(1, QColor("#1a1a1a"))
        painter.setPen(QPen(QColor("#aaaaaa"), 2))
        painter.setBrush(tube_gradient)
        painter.drawRoundedRect(tube_rect, 6, 6)

        mercury_gradient = QLinearGradient(x, fill_y, x, fill_y + fill_height)
        mercury_gradient.setColorAt(0, QColor("#ff7043"))
        mercury_gradient.setColorAt(1, QColor("#c62828"))
        painter.setBrush(mercury_gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(x + 2, fill_y, width - 4, fill_height, 4, 4)

        bulb_x = x - (bulb_radius - width // 2)
        bulb_y = y + tube_height - 2
        bulb_rect = QRectF(bulb_x, bulb_y, bulb_radius * 2, bulb_radius * 2)
        bulb_gradient = QRadialGradient(bulb_x + bulb_radius, bulb_y + bulb_radius, bulb_radius)
        bulb_gradient.setColorAt(0, QColor("#ff5722"))
        bulb_gradient.setColorAt(1, QColor("#b71c1c"))
        painter.setBrush(bulb_gradient)
        painter.setPen(QPen(QColor("#eeeeee"), 1))
        painter.drawEllipse(bulb_rect)
        highlight = QRadialGradient(bulb_x + bulb_radius, bulb_y + bulb_radius - 4, bulb_radius)
        highlight.setColorAt(0, QColor(255, 255, 255, 100))
        highlight.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setBrush(highlight)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(bulb_rect)

    def draw_fan_curve_graph(self, painter, x, y, width=300, height=180):
           margin = 40
           graph_rect = QRect(x, y, width, height)
           painter.setPen(QPen(QColor("#444444")))
           painter.setBrush(QColor("#121212"))
           painter.drawRoundedRect(graph_rect, 8, 8)
           painter.setPen(QPen(QColor("#888888")))
           painter.drawLine(x + margin, y + height - margin, x + width - margin, y + height - margin)
           painter.drawLine(x + margin, y + height - margin, x + margin, y + margin)
           temps = sorted(self.fan_curve.keys())
           points = []
           for temp in temps:
               pwm = self.fan_curve[temp]
               px = x + margin + ((temp - 30) / 60) * (width - 2 * margin)
               py = y + height - margin - ((pwm) / 100) * (height - 2 * margin)
               points.append(QPointF(px, py))
           painter.setPen(QPen(QColor("#ff7043"), 2))
           for i in range(len(points) - 1):
               painter.drawLine(points[i], points[i + 1])
           for pt in points:
               painter.setBrush(QColor("#ff8a65"))
               painter.setPen(Qt.PenStyle.NoPen)
               painter.drawEllipse(pt, 4, 4)
           painter.setPen(QColor("#aaaaaa"))
           painter.setFont(QFont("Segoe UI", 9))
           for i in range(0, 101, 20):
               py = y + height - margin - (i / 100) * (height - 2 * margin)
               painter.drawText(x + 10, int(py + 5), f"{i}%")
           for temp in range(30, 91, 10):
               px = x + margin + ((temp - 30) / 60) * (width - 2 * margin)
               painter.drawText(int(px - 10), y + height - 20, f"{temp}")
           painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
           painter.setPen(QColor("#ffffff"))
           painter.drawText(x + margin, y + 20, "Fan Curve")

    def draw_fan_icon(self, painter, x, y, size=60):
            center_x = x + size // 2
            center_y = y + size // 2
            radius = size // 2 - 5
            blade_length = radius - 5
            blade_width = blade_length // 3
            painter.setBrush(QColor(0, 0, 0, 50))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(center_x - radius, center_y - radius + 3, radius * 2, radius * 2)
            painter.setBrush(QColor("#2e2e2e"))
            painter.setPen(QPen(QColor("#444"), 2))
            painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)
            painter.save()
            painter.translate(center_x, center_y)
            painter.rotate(self.fan_angle)
            for i in range(4):
                painter.rotate(90)
                path = QPainterPath()
                path.moveTo(0, 0)
                path.cubicTo(-blade_width, -blade_length//2, blade_width, -blade_length//1.5, 0, -blade_length)
                painter.setBrush(QColor("#e53935"))
                painter.setPen(QPen(QColor("#b71c1c"), 1))
                painter.drawPath(path)
            painter.restore()
            radial = QRadialGradient(center_x, center_y, 12)
            radial.setColorAt(0, QColor("#bbbbbb"))
            radial.setColorAt(0.5, QColor("#666666"))
            radial.setColorAt(1, QColor("#444444"))
            painter.setBrush(radial)
            painter.setPen(QPen(QColor("#222222"), 1))
            painter.drawEllipse(center_x - 12, center_y - 12, 24, 24)
            highlight = QRadialGradient(center_x - 3, center_y - 3, radius)
            highlight.setColorAt(0, QColor(255, 255, 255, 60))
            highlight.setColorAt(1, QColor(255, 255, 255, 0))
            painter.setBrush(highlight)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)

    def draw_warning_icon(self, painter, x, y):
            painter.setBrush(QColor("#ffca28"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(*[QPoint(x + 10, y), QPoint(x, y + 20), QPoint(x + 20, y + 20)])
            painter.setPen(QColor("#000"))
            painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
            painter.drawText(x + 6, y + 17, "!")

    def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.fillRect(self.rect(), QColor("#1c1c1c"))
            painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(20, 30, "System Monitor")
            self.draw_temp_icon(painter, 20, 50)
            painter.setFont(QFont("Segoe UI", 13))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(60, 70, f"Temperature: {self.temperature:.1f}")
            fan_x = 5
            fan_y = 120
            self.draw_fan_icon(painter, fan_x, fan_y, size=60)
            painter.setFont(QFont("Segoe UI", 13))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(fan_x + 60, fan_y + 30, f"Fan Speed: {self.rpm} RPM")
            self.draw_fan_curve_graph(painter, 260, 200)
            painter.setPen(QPen(QColor("#555555")))
            painter.setBrush(QColor("#2a2a2a"))
            painter.drawRoundedRect(20, 200, self.width() - 360, 180, 10, 10)
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Segoe UI", 11))
            y = 230
            for key, value in self.sensor_data.items():
                val_text = f"{value}" if isinstance(value, int) else "--"
                painter.drawText(30, y, f"{key}: {val_text}")
                y += 22

class CustomGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Staff Besting Crack")
        self.setStyleSheet("""
            QWidget#MainWindow {
                background-color: #121212;
                color: #fff;
                font-family: 'Segoe UI';
                border: 4px solid #8e24aa;
                border-radius: 12px;
            }
            QWidget {
                background-color: #121212;
                color: #ffffff;
            }
            QTabWidget::pane { border: 2px solid #8e24aa; border-radius: 10px; padding: 5px; background: #1f1f1f; }
            QTabBar::tab { background: #1e1e1e; padding: 14px 30px; border-radius: 8px; margin-right: 3px; }
            QTabBar::tab:selected { background: #8e24aa; color: #ffffff; font-weight: bold; }
            QGroupBox { border: 1px solid #444; border-radius: 12px; margin-top: 14px; padding: 15px; background: #2a2a2a; }
            QGroupBox:title { subcontrol-origin: margin; left: 15px; padding: 0 5px 0 5px; font-weight: bold; font-size: 14px; }
            QCheckBox { spacing: 10px; font-size: 15px; }
            QCheckBox::indicator { width: 22px; height: 22px; border-radius: 6px; border: 2px solid #777; background: #1e1e1e; }
            QCheckBox::indicator:checked { background-color: #8e24aa; border: 2px solid #ba68c8; }
            QPushButton { background-color:#8e24aa; border-radius:12px; padding:14px; font-weight:bold; font-size:15px; color:#fff; }
            QPushButton:hover { background-color:#ba68c8; }
            QPushButton:pressed { background-color:#6a1b9a; }
        """)
        layout = QVBoxLayout()
        self.logo_label = QLabel("Staff Besting AntiVgc Cracked")
        self.logo_label.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.logo_label)
        self.status_label = QLabel("Status: Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFont(QFont("Segoe UI", 14))
        layout.addWidget(self.status_label)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.visuals(), "Main")
        layout.addWidget(self.tabs)
        self.monitor_widget = SystemMonitorWidget()
        layout.addWidget(self.monitor_widget)
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Valorant")
        self.emulate_btn = QPushButton("Start with Emulate")
        self.exit_btn = QPushButton("Clean Close")
        for btn in (self.start_btn, self.emulate_btn, self.exit_btn):
            btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)
        self.start_btn.clicked.connect(self.toggle_start_stop)
        self.emulate_btn.clicked.connect(self.start_with_emulate_ui)
        self.exit_btn.clicked.connect(self.safe_exit_ui)
        self.setLayout(layout)
        self.setMinimumSize(610, 410)

    def visuals(self):
            tab = QWidget()
            layout = QVBoxLayout()
            filters_group = QGroupBox("Filters")
            filters_group.setStyleSheet("QGroupBox:title { color: #ffffff; }")
            filter_layout = QVBoxLayout()
            filters = [
                ("Vgc fix", "Fixes Vanguard game client issues."),
                ("1Pc Vgc", "Enable Vanguard emulation for 1 PC."),
                ("2Pc Vgc", "Enable Vanguard emulation for 2 PCs.")
            ]
            for name, description in filters:
                container = QWidget()
                container_layout = QHBoxLayout()
                container_layout.setContentsMargins(0, 0, 0, 0)
                checkbox = QCheckBox(name)
                checkbox.setFont(QFont("Segoe UI", 12, QFont.Weight.Medium))
                checkbox.setStyleSheet("""
                    QCheckBox {
                        spacing: 10px;
                        color: #ffffff;
                    }
                    QCheckBox::indicator {
                        width: 24px;
                        height: 24px;
                        border-radius: 6px;
                        border: 2px solid #777;
                        background: #1e1e1e;
                    }
                    QCheckBox::indicator:hover {
                        border-color: #e53935;
                    }
                    QCheckBox::indicator:checked {
                        background-color: #e53935;
                        border: 2px solid #ff1744;
                    }
                """)
                if name in ("Vgc fix", "1Pc Vgc"):
                    checkbox.setChecked(True)
                desc_label = QLabel(description)
                desc_label.setFont(QFont("Segoe UI", 10))
                desc_label.setStyleSheet("color: #aaaaaa;")
                desc_label.setWordWrap(True)
                container_layout.addWidget(checkbox)
                container_layout.addWidget(desc_label)
                container.setLayout(container_layout)
                filter_layout.addWidget(container)
            filters_group.setLayout(filter_layout)
            layout.addWidget(filters_group)
            layout.addStretch()
            tab.setLayout(layout)
            return tab

    def toggle_start_stop(self):
            global valorant_running
            if not valorant_running:
                self.status_label.setText("Status: Starting Valorant...")
                threading.Thread(target=self.start_valorant_ui, daemon=True).start()
            else:
                self.status_label.setText("Status: Stopping Valorant...")
                safe_exit()
                self.status_label.setText("Status: Stopped")

    def start_valorant_ui(self):
            start_valorant()
            self.status_label.setText("Status: Valorant running")

    def start_with_emulate_ui(self):
            self.status_label.setText("Status: Starting with emulate...")
            threading.Thread(target=self.do_emulate_and_update, daemon=True).start()

    def do_emulate_and_update(self):
            start_with_emulate()
            self.status_label.setText("Status: Emulate running")

    def safe_exit_ui(self):
            self.status_label.setText("Status: Clean Close...")
            threading.Thread(target=self.do_safe_exit_and_update, daemon=True).start()

    def do_safe_exit_and_update(self):
            safe_exit()
            self.status_label.setText("Status: Stopped")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CustomGUI()
    window.show()
    sys.exit(app.exec())
