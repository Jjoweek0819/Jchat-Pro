import engineio.async_drivers.threading
import socketio
import sys, threading, socket, pyaudio, base64, os, json, re, tempfile, mimetypes
from PyQt6.QtWidgets import *
from PyQt6.QtCore import pyqtSignal, QObject, Qt, QTimer, QSize, QUrl, QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPainterPath, QFont, QColor, QIcon, QMovie
try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    HAS_MULTIMEDIA = True
except ImportError:
    HAS_MULTIMEDIA = False
from datetime import datetime

SERVER_IP  = "Server_ip"
VOICE_PORT = 5006

def _find_svg_path() -> str:
    """找到 JChat.svg 的絕對路徑（支援一般執行與 PyInstaller 打包）"""
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "JChat.svg"),
        os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "JChat.svg"),
        os.path.join(os.getcwd(), "JChat.svg"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return ""

def _load_svg_pixmap(size: int) -> "QPixmap":
    """用 QSvgRenderer 把 SVG 渲染成指定尺寸的 QPixmap；失敗回傳空 QPixmap"""
    path = _find_svg_path()
    if not path:
        return QPixmap()
    try:
        from PyQt6.QtSvg import QSvgRenderer
        from PyQt6.QtCore import QRectF
        renderer = QSvgRenderer(path)
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        return pm
    except ImportError:
        pm = QPixmap(path)
        if not pm.isNull():
            return pm.scaled(size, size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        return QPixmap()
AVATAR_SIZE  = 40
EMOJI_DIR    = "custom_emojis"
EMOJI_INDEX  = os.path.join(EMOJI_DIR, "index.json")
os.makedirs(EMOJI_DIR, exist_ok=True)

# 伺服器同步的 emoji：{code: {b64, ext}}
_server_emojis: dict = {}
# GIF 動畫暫存檔路徑 {code: tmp_path}
_gif_tmp_files: dict = {}
# 個人資料快取 {username: {bio, status}}
_profiles_cache: dict = {}

# ── Discord 風格色系 ──
DISCORD_DARK      = "#313338"   # 主背景
DISCORD_DARKER    = "#2b2d31"   # 側邊欄
DISCORD_DARKEST   = "#1e1f22"   # 最深（房間列）
DISCORD_CHANNEL   = "#404249"   # channel hover
DISCORD_INPUT_BG  = "#383a40"   # 輸入框背景
DISCORD_TEXT      = "#dbdee1"   # 主文字
DISCORD_TEXT_MUTED= "#80848e"   # 次要文字
DISCORD_BLUE      = "#5865f2"   # 強調藍
DISCORD_GREEN     = "#23a559"   # 在線綠
DISCORD_HOVER     = "#35373c"   # hover 背景

DISCORD_QSS = """
QMainWindow, QWidget#central {
    background: """ + DISCORD_DARK + """;
    color: """ + DISCORD_TEXT + """;
}
QWidget {
    background: """ + DISCORD_DARK + """;
    color: """ + DISCORD_TEXT + """;
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
}
/* 側邊欄 */
QWidget#room_panel, QWidget#user_panel_widget {
    background: """ + DISCORD_DARKER + """;
}
QListWidget {
    background: """ + DISCORD_DARKER + """;
    color: """ + DISCORD_TEXT + """;
    border: none;
    outline: none;
}
QListWidget::item {
    padding: 4px 8px;
    border-radius: 4px;
    color: """ + DISCORD_TEXT_MUTED + """;
}
QListWidget::item:hover {
    background: """ + DISCORD_HOVER + """;
    color: """ + DISCORD_TEXT + """;
}
QListWidget::item:selected {
    background: """ + DISCORD_CHANNEL + """;
    color: white;
    font-weight: bold;
}
/* 聊天區 */
QTextBrowser {
    background: """ + DISCORD_DARK + """;
    color: """ + DISCORD_TEXT + """;
    border: none;
    selection-background-color: #5865f2;
}
/* 輸入框 */
QLineEdit {
    background: """ + DISCORD_INPUT_BG + """;
    color: """ + DISCORD_TEXT + """;
    border: none;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
}
QLineEdit:focus { border: none; outline: none; }
QLineEdit::placeholder { color: """ + DISCORD_TEXT_MUTED + """; }
/* 按鈕 */
QPushButton {
    background: """ + DISCORD_BLUE + """;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton:hover { background: #4752c4; }
QPushButton:pressed { background: #3c45a5; }
QPushButton#ghost_btn {
    background: transparent;
    color: """ + DISCORD_TEXT_MUTED + """;
    font-size: 18px;
    border-radius: 4px;
    padding: 4px;
}
QPushButton#ghost_btn:hover {
    background: """ + DISCORD_HOVER + """;
    color: """ + DISCORD_TEXT + """;
}
/* 釘選欄 */
QLabel#pin_bar {
    background: #2b2d31;
    color: #dbdee1;
    border-bottom: 1px solid #1e1f22;
    padding: 6px 14px;
    font-size: 13px;
}
/* 房間標題 */
QLabel#room_title {
    color: white;
    font-size: 15px;
    font-weight: 700;
    padding: 0 6px;
}
/* 滾動條 */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #1a1b1e;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
/* 選單 */
QMenuBar {
    background: """ + DISCORD_DARKEST + """;
    color: """ + DISCORD_TEXT_MUTED + """;
    font-size: 13px;
}
QMenuBar::item:selected { background: """ + DISCORD_HOVER + """; color: white; }
QMenu {
    background: #111214;
    color: """ + DISCORD_TEXT + """;
    border: 1px solid #000;
    border-radius: 4px;
}
QMenu::item:selected { background: """ + DISCORD_BLUE + """; color: white; border-radius: 3px; }
/* 分組框 */
QGroupBox {
    border: 1px solid #3f4147;
    border-radius: 6px;
    margin-top: 8px;
    color: """ + DISCORD_TEXT_MUTED + """;
    font-size: 12px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
/* 文字編輯 */
QTextEdit {
    background: """ + DISCORD_INPUT_BG + """;
    color: """ + DISCORD_TEXT + """;
    border: none;
    border-radius: 6px;
    padding: 6px;
}
/* 對話框 */
QDialog { background: #313338; color: #dbdee1; }
QMessageBox { background: #313338; color: #dbdee1; }
QMessageBox QPushButton { min-width: 80px; }
/* Tab */
QTabWidget::pane { border: none; background: """ + DISCORD_DARKER + """; }
QTabBar::tab {
    background: transparent;
    color: """ + DISCORD_TEXT_MUTED + """;
    padding: 6px 14px;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: white;
    border-bottom: 2px solid """ + DISCORD_BLUE + """;
}
/* 狀態列 */
QStatusBar {
    background: """ + DISCORD_DARKEST + """;
    color: """ + DISCORD_TEXT_MUTED + """;
    font-size: 11px;
}
"""

BUILTIN_EMOJI = [
    "😀","😁","😂","🤣","🥹","😍","🥰","😘","😎","🤔",
    "😭","😡","🥳","😴","😱","🤯","😏","🙄","😅","😬",
    "🤩","😇","🥺","😤","😒","😔","🤗","😋","😜","🤪",
    "👍","👎","👏","🙏","💪","🤝","✌️","🤞","👀","🫶",
    "🤙","👋","🫡","💅","🤌","👌","🫰","🙌","🫂","🤷",
    "❤️","🧡","💛","💚","💙","💜","🖤","💔","❤️‍🔥","💯",
    "✅","❌","⭐","🌟","💫","🔥","💥","🎉","🎊","🚀",
    "🐱","🐶","🐸","🦊","🐼","🦁","🐧","🦋","🍕","🍜",
    "💀","🤡","👻","💩","🎮","🎵","📸","🌈","☀️","🌙",
]

# 支援的檔案類型
FILE_ICONS = {
    '.pdf': '📄', '.doc': '📝', '.docx': '📝', '.xls': '📊',
    '.xlsx': '📊', '.ppt': '🖥', '.pptx': '🖥', '.zip': '🗜',
    '.rar': '🗜', '.7z': '🗜', '.txt': '📃', '.mp4': '🎬',
    '.mp3': '🎵', '.wav': '🎵', '.png': '🖼', '.jpg': '🖼',
    '.jpeg': '🖼', '.gif': '🖼',
}

def get_file_icon(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return FILE_ICONS.get(ext, '📎')

# ══════════════════════════════════════════════════════════
def b64_to_pixmap(b64: str, size: int) -> QPixmap:
    try:
        data = base64.b64decode(b64)
        img  = QImage.fromData(data)
        img  = img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                          Qt.TransformationMode.SmoothTransformation)
        x = (img.width()  - size) // 2
        y = (img.height() - size) // 2
        img = img.copy(x, y, size, size)
        result = QImage(size, size, QImage.Format.Format_ARGB32)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        painter.drawImage(0, 0, img)
        painter.end()
        return QPixmap.fromImage(result)
    except:
        return QPixmap()

def default_avatar_pixmap(name: str, size: int) -> QPixmap:
    colors = ["#5C6BC0","#26A69A","#EF5350","#AB47BC","#FFA726","#66BB6A"]
    color  = colors[hash(name) % len(colors)]
    img    = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)
    painter.fillRect(0, 0, size, size, QColor(color))
    painter.setPen(Qt.GlobalColor.white)
    font = QFont(); font.setPointSize(size // 3); font.setBold(True)
    painter.setFont(font)
    painter.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter,
                     (name[0] if name else "?").upper())
    painter.end()
    return QPixmap.fromImage(img)

def get_avatar_pixmap(name: str, avatars: dict, size: int) -> QPixmap:
    b64 = avatars.get(name, "")
    if b64:
        pm = b64_to_pixmap(b64, size)
        if not pm.isNull():
            return pm
    return default_avatar_pixmap(name, size)

# ══════════════════════════════════════════════════════════
class CommSignals(QObject):
    message_received  = pyqtSignal(dict)
    history_received  = pyqtSignal(dict)
    user_list_updated = pyqtSignal(dict)
    pinned_updated    = pyqtSignal(dict)
    room_list_updated = pyqtSignal(list)
    force_join        = pyqtSignal(dict)
    avatars_loaded    = pyqtSignal(dict)
    avatar_updated    = pyqtSignal(dict)
    connection_failed = pyqtSignal()
    login_result      = pyqtSignal(dict)
    register_result   = pyqtSignal(str)
    emojis_loaded     = pyqtSignal(dict)
    emoji_updated     = pyqtSignal(dict)
    emoji_deleted     = pyqtSignal(str)
    profile_updated   = pyqtSignal(dict)   # {username, bio, status}
    profile_fetched   = pyqtSignal(dict)   # {username, bio, status, avatar}
    connection_status = pyqtSignal(bool, str)  # (is_connected, status_text)

# ══════════════════════════════════════════════════════════
class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JChat")
        self.setFixedSize(440, 460)
        self.setStyleSheet("""
            QDialog { background:#313338; }
            QLabel  { color:#dbdee1; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(12)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("background:transparent;")
        _pm = _load_svg_pixmap(64)
        if not _pm.isNull():
            logo.setPixmap(_pm)
        else:
            logo.setText("💬")
            logo.setStyleSheet("font-size:48px;background:transparent;")
        layout.addWidget(logo)

        title = QLabel("歡迎回來！")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:22px;font-weight:700;color:white;background:transparent;")
        layout.addWidget(title)

        sub = QLabel("我們迫不及待想見到你")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("font-size:13px;color:#b5bac1;background:transparent;")
        layout.addWidget(sub)
        layout.addSpacing(8)

        u_lbl = QLabel("帳號")
        u_lbl.setStyleSheet("font-size:11px;font-weight:700;letter-spacing:1px;color:#b5bac1;background:transparent;")
        layout.addWidget(u_lbl)
        self.u_input = QLineEdit()
        self.u_input.setPlaceholderText("輸入帳號")
        self.u_input.setFixedHeight(40)
        self.u_input.setStyleSheet("background:#1e1f22;color:#dbdee1;border:none;border-radius:4px;padding:0 12px;font-size:14px;")
        layout.addWidget(self.u_input)

        p_lbl = QLabel("密碼")
        p_lbl.setStyleSheet("font-size:11px;font-weight:700;letter-spacing:1px;color:#b5bac1;background:transparent;")
        layout.addWidget(p_lbl)
        self.p_input = QLineEdit()
        self.p_input.setPlaceholderText("輸入密碼")
        self.p_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.p_input.setFixedHeight(40)
        self.p_input.setStyleSheet("background:#1e1f22;color:#dbdee1;border:none;border-radius:4px;padding:0 12px;font-size:14px;")
        layout.addWidget(self.p_input)
        layout.addSpacing(4)

        self.login_btn = QPushButton("登入")
        self.login_btn.setFixedHeight(44)
        self.login_btn.setStyleSheet("""
            QPushButton { background:#5865f2;color:white;border:none;border-radius:4px;
                          font-size:15px;font-weight:700; }
            QPushButton:hover { background:#4752c4; }
        """)
        layout.addWidget(self.login_btn)

        reg_row = QHBoxLayout()
        reg_lbl = QLabel("還沒有帳號？")
        reg_lbl.setStyleSheet("color:#b5bac1;font-size:13px;background:transparent;")
        self.reg_btn = QPushButton("立即註冊")
        self.reg_btn.setStyleSheet("""
            QPushButton { background:transparent;color:#00a8fc;border:none;
                          font-size:13px;font-weight:600;padding:0; }
            QPushButton:hover { text-decoration:underline; }
        """)
        reg_row.addStretch()
        reg_row.addWidget(reg_lbl)
        reg_row.addWidget(self.reg_btn)
        reg_row.addStretch()
        layout.addLayout(reg_row)

# ══════════════════════════════════════════════════════════
class AvatarDialog(QDialog):
    def __init__(self, current_b64: str, username: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🖼 設定頭像")
        self.setFixedSize(320, 420)
        self.new_b64 = ""
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>目前頭像預覽：</b>"))
        self.preview = QLabel()
        self.preview.setFixedSize(120, 120)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_preview(current_b64, username)
        preview_row = QHBoxLayout()
        preview_row.addStretch()
        preview_row.addWidget(self.preview)
        preview_row.addStretch()
        layout.addLayout(preview_row)
        layout.addSpacing(6)
        rules = QLabel(
            "<b>圖片規則：</b><br>"
            "• 格式：JPG、PNG、BMP、WEBP<br>"
            "• 大小：上限 <b>2 MB</b><br>"
            "• 尺寸：自動裁切為 <b>256 × 256</b> 正方形<br>"
            "• 顯示時會套用<b>圓形遮罩</b>"
        )
        rules.setStyleSheet(
            "background:#f0f4ff;border:1px solid #c5d0e8;"
            "border-radius:6px;padding:8px;font-size:12px;line-height:1.6;"
        )
        rules.setWordWrap(True)
        layout.addWidget(rules)
        layout.addSpacing(6)
        upload_btn = QPushButton("📂 選擇圖片（JPG / PNG）")
        upload_btn.setStyleSheet("padding:8px;font-size:13px;")
        upload_btn.clicked.connect(self._pick_image)
        layout.addWidget(upload_btn)
        self.status_label = QLabel("選擇圖片後可預覽，確認後按儲存")
        self.status_label.setStyleSheet("color:gray;font-size:11px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        layout.addStretch()
        btn_row = QHBoxLayout()
        self.ok_btn = QPushButton("✅ 儲存")
        self.ok_btn.setStyleSheet("background:#28a745;color:white;font-weight:bold;padding:6px;")
        self.ok_btn.setEnabled(False)
        self.ok_btn.clicked.connect(self.accept)
        ca_btn = QPushButton("取消"); ca_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.ok_btn); btn_row.addWidget(ca_btn)
        layout.addLayout(btn_row)
        self._username = username
        self._current_b64 = current_b64

    def _set_preview(self, b64: str, name: str):
        pm = get_avatar_pixmap(name, {name: b64} if b64 else {}, 120)
        self.preview.setPixmap(pm)

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇頭像", "", "圖片檔 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        try:
            pixmap = QPixmap(path)
            if pixmap.isNull():
                raise ValueError("無法讀取圖片")
            pixmap = pixmap.scaled(256, 256,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            x = (pixmap.width()  - 256) // 2
            y = (pixmap.height() - 256) // 2
            pixmap = pixmap.copy(x, y, 256, 256)
            qbuf = QBuffer()
            qbuf.open(QIODevice.OpenModeFlag.ReadWrite)
            pixmap.save(qbuf, "PNG")
            raw = bytes(qbuf.data())
            qbuf.close()
            if not raw:
                raise ValueError("圖片轉換失敗")
            if len(raw) > 2 * 1024 * 1024:
                self.status_label.setText("❌ 圖片太大（上限 2MB），請換一張")
                return
            self.new_b64 = base64.b64encode(raw).decode()
            self._set_preview(self.new_b64, self._username)
            self.ok_btn.setEnabled(True)
            self.status_label.setText(f"✅ 已選擇，大小 {len(raw)//1024} KB")
        except Exception as e:
            self.status_label.setText(f"❌ 錯誤：{e}")

# ══════════════════════════════════════════════════════════
#  個人資料卡（點他人頭像時顯示）
# ══════════════════════════════════════════════════════════
class ProfileCard(QDialog):
    def __init__(self, username: str, avatars: dict, sio, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"👤 {username} 的個人資料")
        self.setFixedSize(320, 420)
        self.setModal(True)
        self._username = username
        self._sio = sio

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 頭像
        self.avatar_lbl = QLabel()
        self.avatar_lbl.setFixedSize(90, 90)
        self.avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = get_avatar_pixmap(username, avatars, 90)
        self.avatar_lbl.setPixmap(pm)
        avatar_row = QHBoxLayout()
        avatar_row.addStretch()
        avatar_row.addWidget(self.avatar_lbl)
        avatar_row.addStretch()
        layout.addLayout(avatar_row)

        # 名稱
        name_lbl = QLabel(f"<h2 style='margin:0;text-align:center'>{username}</h2>")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_lbl)

        # 動態
        self.status_lbl = QLabel("⏳ 載入中…")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setStyleSheet(
            "color:#555;font-size:13px;background:#f0f4ff;"
            "border-radius:12px;padding:6px 12px;")
        self.status_lbl.setWordWrap(True)
        layout.addWidget(self.status_lbl)

        # 自介
        bio_title = QLabel("<b>個人自介</b>")
        bio_title.setStyleSheet("color:#333;font-size:13px;")
        layout.addWidget(bio_title)
        self.bio_lbl = QTextEdit()
        self.bio_lbl.setReadOnly(True)
        self.bio_lbl.setPlaceholderText("這個人沒有留下自介…")
        self.bio_lbl.setStyleSheet(
            "background:#fafafa;border:1px solid #ddd;border-radius:6px;padding:6px;font-size:13px;")
        self.bio_lbl.setFixedHeight(100)
        layout.addWidget(self.bio_lbl)

        layout.addStretch()
        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        # 非同步載入資料
        def _fetch():
            try:
                res = sio.call('get_profile', {'username': username}, timeout=8)
                # 伺服器 get_profile 回傳：{'status':'success', 'bio':..., 'user_status':..., 'avatar':...}
                if res and res.get('status') == 'success':
                    QTimer.singleShot(0, lambda: self._fill(res))
                else:
                    QTimer.singleShot(0, lambda: self.status_lbl.setText("（無資料）"))
            except Exception as e:
                print(f"ProfileCard fetch error: {e}")
                QTimer.singleShot(0, lambda: self.status_lbl.setText("（載入失敗）"))
        threading.Thread(target=_fetch, daemon=True).start()

    def _fill(self, data: dict):
        # 注意：data['status'] 是 'success'（回應狀態），個人動態在 data['user_status']
        # 為了相容舊版伺服器，同時嘗試 'user_status' 和 'profile_status'
        user_status = (data.get('user_status') or data.get('profile_status') or '').strip()
        bio         = data.get('bio', '').strip()
        self.status_lbl.setText(f"💬 {user_status}" if user_status else "（尚未設定動態）")
        self.bio_lbl.setPlainText(bio if bio else "")
        # 更新頭像（如果伺服器有回傳）
        avatar_b64 = data.get('avatar', '')
        if avatar_b64:
            pm = b64_to_pixmap(avatar_b64, 90)
            if not pm.isNull():
                self.avatar_lbl.setPixmap(pm)

# ══════════════════════════════════════════════════════════
#  帳號設定對話框（改名 + 自介 + 動態）
# ══════════════════════════════════════════════════════════
class AccountSettingsDialog(QDialog):
    def __init__(self, nickname: str, avatars: dict, sio, current_profile: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("👤 我的帳號設定")
        self.setFixedSize(380, 560)
        self._sio = sio
        self._nickname = nickname
        self._avatars = avatars
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 頭像預覽
        self.avatar_lbl = QLabel()
        self.avatar_lbl.setFixedSize(80, 80)
        self.avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = get_avatar_pixmap(nickname, avatars, 80)
        self.avatar_lbl.setPixmap(pm)
        avatar_btn = QPushButton("🖼 更換頭像")
        avatar_btn.clicked.connect(self._change_avatar)
        av_row = QHBoxLayout()
        av_row.addStretch()
        av_col = QVBoxLayout()
        av_col.addWidget(self.avatar_lbl)
        av_col.addWidget(avatar_btn)
        av_row.addLayout(av_col)
        av_row.addStretch()
        layout.addLayout(av_row)

        layout.addWidget(QLabel(f"<b>目前帳號：</b> {nickname}"))

        # ── 改名區域 ──
        rename_box = QGroupBox("✏️ 更改帳號名稱（需密碼驗證）")
        rename_layout = QVBoxLayout(rename_box)
        self.new_name_input = QLineEdit()
        self.new_name_input.setPlaceholderText("新的帳號名稱")
        self.rename_pw_input = QLineEdit()
        self.rename_pw_input.setPlaceholderText("請輸入目前密碼")
        self.rename_pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.rename_btn = QPushButton("確認改名")
        self.rename_btn.setStyleSheet("background:#0066cc;color:white;font-weight:bold;padding:5px;")
        self.rename_btn.clicked.connect(self._do_rename)
        rename_layout.addWidget(self.new_name_input)
        rename_layout.addWidget(self.rename_pw_input)
        rename_layout.addWidget(self.rename_btn)
        layout.addWidget(rename_box)

        # ── 個人自介 ──
        bio_box = QGroupBox("📝 個人自介")
        bio_layout = QVBoxLayout(bio_box)
        self.bio_edit = QTextEdit()
        self.bio_edit.setPlaceholderText("介紹一下自己吧（上限 200 字）…")
        self.bio_edit.setFixedHeight(80)
        self.bio_edit.setPlainText(current_profile.get('bio', ''))
        bio_layout.addWidget(self.bio_edit)
        layout.addWidget(bio_box)

        # ── 個人動態 ──
        status_box = QGroupBox("💬 個人動態")
        status_layout = QVBoxLayout(status_box)
        self.status_edit = QLineEdit()
        self.status_edit.setPlaceholderText("今天的狀態是…（上限 100 字）")
        self.status_edit.setText(current_profile.get('status', ''))
        status_layout.addWidget(self.status_edit)
        layout.addWidget(status_box)

        # 儲存按鈕
        save_btn = QPushButton("💾 儲存自介與動態")
        save_btn.setStyleSheet("background:#28a745;color:white;font-weight:bold;padding:8px;font-size:13px;")
        save_btn.clicked.connect(self._save_profile)
        layout.addWidget(save_btn)

        self.status_bar = QLabel("")
        self.status_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_bar.setStyleSheet("color:gray;font-size:11px;")
        layout.addWidget(self.status_bar)

        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _change_avatar(self):
        dlg = AvatarDialog(self._avatars.get(self._nickname, ""), self._nickname, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.new_b64:
            def _upload():
                res = self._sio.call('upload_avatar', {'image_b64': dlg.new_b64})
                if res and res.get('status') == 'success':
                    self._avatars[self._nickname] = dlg.new_b64
                    pm = b64_to_pixmap(dlg.new_b64, 80)
                    QTimer.singleShot(0, lambda: self.avatar_lbl.setPixmap(pm))
                    QTimer.singleShot(0, lambda: self.status_bar.setText("✅ 頭像已更新"))
                else:
                    msg = res.get('message','') if res else '無回應'
                    QTimer.singleShot(0, lambda: QMessageBox.warning(self, "失敗", msg))
            threading.Thread(target=_upload, daemon=True).start()

    def _do_rename(self):
        new_name = self.new_name_input.text().strip()
        password = self.rename_pw_input.text().strip()
        if not new_name or not password:
            QMessageBox.warning(self, "提示", "請填寫新帳號名稱和目前密碼")
            return
        self.rename_btn.setEnabled(False)
        self.rename_btn.setText("處理中…")
        def _call():
            try:
                res = self._sio.call('rename_account',
                                     {'new_username': new_name, 'password': password}, timeout=10)
                QTimer.singleShot(0, lambda: self._on_rename_result(res))
            except Exception as e:
                QTimer.singleShot(0, lambda: self._on_rename_result({'status':'fail','message':str(e)}))
        threading.Thread(target=_call, daemon=True).start()

    def _on_rename_result(self, res):
        self.rename_btn.setEnabled(True)
        self.rename_btn.setText("確認改名")
        if res and res.get('status') == 'success':
            new_name = res.get('new_username', '')
            self._nickname = new_name
            QMessageBox.information(self, "成功", f"帳號已改名為：{new_name}\n請重新登入以套用更改。")
            self.accept()
            # 通知主視窗重新登入
            if hasattr(self.parent(), '_handle_rename_success'):
                self.parent()._handle_rename_success(new_name)
        else:
            msg = res.get('message', '未知錯誤') if res else '無回應'
            QMessageBox.warning(self, "改名失敗", msg)

    def _save_profile(self):
        bio    = self.bio_edit.toPlainText().strip()
        status = self.status_edit.text().strip()
        if len(bio) > 200:
            QMessageBox.warning(self, "提示", "自介超過 200 字")
            return
        if len(status) > 100:
            QMessageBox.warning(self, "提示", "動態超過 100 字")
            return
        def _call():
            try:
                res = self._sio.call('update_profile', {'bio': bio, 'status': status}, timeout=10)
                if res and res.get('status') == 'success':
                    _profiles_cache[self._nickname] = {'bio': bio, 'status': status}
                    QTimer.singleShot(0, lambda: self.status_bar.setText("✅ 自介與動態已儲存"))
                    QTimer.singleShot(0, lambda: QMessageBox.information(
                        self, "✅ 儲存成功", "自介與個人動態已成功儲存！"))
                else:
                    msg = res.get('message','') if res else '無回應'
                    QTimer.singleShot(0, lambda: QMessageBox.warning(self, "失敗", msg))
            except Exception as e:
                QTimer.singleShot(0, lambda: QMessageBox.warning(self, "失敗", str(e)))
        threading.Thread(target=_call, daemon=True).start()

# ══════════════════════════════════════════════════════════
#  自訂 Emoji
# ══════════════════════════════════════════════════════════
def load_custom_emojis() -> dict:
    return _server_emojis

def save_custom_emojis(data: dict):
    with open(EMOJI_INDEX, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def custom_emoji_b64(entry: dict) -> str:
    b64 = entry.get("b64", "")
    if b64:
        return b64
    path = entry.get("path", "")
    if path and os.path.exists(path):
        with open(path, 'rb') as f:
            return base64.b64encode(f.read()).decode()
    return ""

def get_gif_tmp_path(code: str, b64: str) -> str:
    if code in _gif_tmp_files and os.path.exists(_gif_tmp_files[code]):
        return _gif_tmp_files[code]
    try:
        raw = base64.b64decode(b64)
        fd, path = tempfile.mkstemp(suffix=".gif")
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
        _gif_tmp_files[code] = path
        return path
    except Exception:
        return ""

# ══════════════════════════════════════════════════════════
class ManageEmojiDialog(QDialog):
    def __init__(self, parent=None, sio=None):
        super().__init__(parent)
        self.setWindowTitle("🎨 管理自訂 Emoji")
        self.setMinimumSize(480, 500)
        self._sio = sio
        self._emojis = load_custom_emojis()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>已新增的自訂 Emoji：</b>"))
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(32, 32))
        layout.addWidget(self.list_widget, 3)
        self._refresh_list()
        del_btn = QPushButton("🗑️ 刪除選取")
        del_btn.clicked.connect(self._delete_selected)
        layout.addWidget(del_btn)

        # 重新同步按鈕（修正他人看不到的問題）
        sync_btn = QPushButton("🔄 重新同步伺服器貼圖")
        sync_btn.setStyleSheet("color:#0066cc;font-size:11px;padding:3px;")
        sync_btn.clicked.connect(self._sync_from_server)
        layout.addWidget(sync_btn)

        layout.addWidget(QLabel("<hr><b>新增自訂 Emoji：</b>"))
        code_row = QHBoxLayout()
        code_row.addWidget(QLabel("代號（如 :wave:）："))
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText(":myemoji:")
        code_row.addWidget(self.code_input)
        layout.addLayout(code_row)
        img_row = QHBoxLayout()
        self.img_label = QLabel("尚未選擇圖片")
        self.img_label.setStyleSheet("color:gray;font-size:11px;")
        pick_btn = QPushButton("📂 選擇圖片 / GIF")
        pick_btn.clicked.connect(self._pick_image)
        img_row.addWidget(self.img_label, 1)
        img_row.addWidget(pick_btn)
        layout.addLayout(img_row)
        rules = QLabel("支援 PNG、JPG、GIF（動態）｜上限 2MB｜建議 64×64 px")
        rules.setStyleSheet("color:gray;font-size:11px;")
        layout.addWidget(rules)
        self._new_path = ""
        self._new_b64  = ""
        add_btn = QPushButton("➕ 新增")
        add_btn.setStyleSheet("background:#28a745;color:white;font-weight:bold;padding:6px;")
        add_btn.clicked.connect(self._add_emoji)
        layout.addWidget(add_btn)
        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _sync_from_server(self):
        if not self._sio:
            return
        def _call():
            try:
                res = self._sio.call('request_emojis', {}, timeout=10)
                if res:
                    QTimer.singleShot(0, lambda: QMessageBox.information(
                        self, "同步完成", f"已從伺服器載入 {res.get('count', 0)} 個貼圖"))
                    QTimer.singleShot(100, lambda: self._refresh_list())
            except Exception as e:
                QTimer.singleShot(0, lambda: QMessageBox.warning(self, "失敗", str(e)))
        threading.Thread(target=_call, daemon=True).start()

    def _refresh_list(self):
        self._emojis = load_custom_emojis()
        self.list_widget.clear()
        for code, entry in self._emojis.items():
            item = QListWidgetItem(f"  {code}")
            b64 = custom_emoji_b64(entry)
            if b64:
                try:
                    pm = QPixmap()
                    pm.loadFromData(base64.b64decode(b64))
                    if not pm.isNull():
                        item.setIcon(QIcon(pm.scaled(32, 32,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)))
                except Exception:
                    pass
            self.list_widget.addItem(item)

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇 Emoji 圖片", "",
            "圖片檔 (*.png *.jpg *.jpeg *.gif *.webp)")
        if not path:
            return
        size = os.path.getsize(path)
        if size > 2 * 1024 * 1024:
            QMessageBox.warning(self, "檔案太大", "圖片上限為 2MB")
            return
        with open(path, 'rb') as f:
            self._new_b64 = base64.b64encode(f.read()).decode()
        self._new_path = path
        self.img_label.setText(f"✅ {os.path.basename(path)}  ({size//1024} KB)")

    def _add_emoji(self):
        code = self.code_input.text().strip()
        if not code:
            QMessageBox.warning(self, "提示", "請輸入代號"); return
        if not code.startswith(":") or not code.endswith(":") or len(code) < 3:
            QMessageBox.warning(self, "格式錯誤", "代號格式須為 :名稱: 例如 :wave:"); return
        if not self._new_b64:
            QMessageBox.warning(self, "提示", "請先選擇圖片"); return
        ext = os.path.splitext(self._new_path)[1].lower() if self._new_path else ".png"
        safe = code.strip(":").replace(" ", "_")
        dest = os.path.join(EMOJI_DIR, f"{safe}{ext}")
        with open(dest, 'wb') as f:
            f.write(base64.b64decode(self._new_b64))
        if self._sio:
            def _upload():
                try:
                    res = self._sio.call('upload_emoji',
                                        {'code': code, 'b64': self._new_b64, 'ext': ext},
                                        timeout=15)
                    if res and res.get('status') != 'success':
                        QTimer.singleShot(0, lambda: QMessageBox.warning(
                            self, "上傳失敗", res.get('message', '未知錯誤')))
                except Exception as e:
                    QTimer.singleShot(0, lambda: QMessageBox.warning(
                        self, "上傳失敗", str(e)))
            threading.Thread(target=_upload, daemon=True).start()
        # 本地即時更新（伺服器廣播回來時會再次更新所有客戶端）
        _server_emojis[code] = {'b64': self._new_b64, 'ext': ext}
        self._emojis = _server_emojis
        self._refresh_list()
        self.code_input.clear()
        self.img_label.setText("尚未選擇圖片")
        self._new_path = self._new_b64 = ""
        QMessageBox.information(self, "成功", f"{code} 已新增並上傳！")

    def _delete_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "請先選取一個 emoji"); return
        code = item.text().strip()
        if QMessageBox.question(self, "確認", f"刪除 {code}？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
            return
        if self._sio:
            def _delete():
                try:
                    self._sio.call('delete_emoji', {'code': code}, timeout=10)
                except Exception:
                    pass
            threading.Thread(target=_delete, daemon=True).start()
        _server_emojis.pop(code, None)
        tmp = _gif_tmp_files.pop(code, None)
        if tmp and os.path.exists(tmp):
            try: os.remove(tmp)
            except: pass
        self._emojis = _server_emojis
        save_custom_emojis(self._emojis)
        self._refresh_list()

# ══════════════════════════════════════════════════════════
class EmojiPicker(QFrame):
    emoji_selected = pyqtSignal(str)

    def __init__(self, parent=None, sio=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self._sio = sio
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            QFrame { background:#2b2d31; border:1px solid #1e1f22; border-radius:8px; }
            QPushButton { background:transparent; border:none; border-radius:4px; }
            QPushButton:hover { background:#35373c; }
            QTabWidget::pane { border:none; background:#2b2d31; }
            QTabBar::tab { background:transparent; color:#80848e; padding:6px 14px;
                           border-bottom:2px solid transparent; font-size:12px; }
            QTabBar::tab:selected { color:white; border-bottom:2px solid #5865f2; }
            QScrollArea { border:none; background:transparent; }
            QScrollBar:vertical { background:transparent; width:6px; margin:0; }
            QScrollBar::handle:vertical { background:#1a1b1e; border-radius:3px; min-height:20px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
        """)
        # 寬：10 欄 × 32px + 左右 padding 8px + 捲軸 8px = 336 → 用 350 留裕度
        self.setFixedSize(370, 340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        tabs = QTabWidget()

        # ── 內建 emoji（捲動區）──
        builtin_container = QWidget()
        builtin_container.setStyleSheet("background:transparent;")
        grid = QGridLayout(builtin_container)
        grid.setSpacing(2)
        grid.setContentsMargins(4, 4, 4, 4)
        cols = 10
        for i, em in enumerate(BUILTIN_EMOJI):
            btn = QPushButton(em)
            btn.setFixedSize(32, 32)
            btn.setStyleSheet("font-size:18px; border:none; background:transparent; border-radius:4px;")
            btn.clicked.connect(lambda _, e=em: self._pick(e))
            grid.addWidget(btn, i // cols, i % cols)

        builtin_scroll = QScrollArea()
        builtin_scroll.setWidgetResizable(True)
        builtin_scroll.setWidget(builtin_container)
        builtin_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        builtin_scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        tabs.addTab(builtin_scroll, "😀 內建")

        # ── 自訂 emoji（捲動區）──
        self.custom_container = QWidget()
        self.custom_container.setStyleSheet("background:transparent;")
        self.custom_layout = QGridLayout(self.custom_container)
        self.custom_layout.setSpacing(4)
        self.custom_layout.setContentsMargins(4, 4, 4, 4)

        custom_scroll = QScrollArea()
        custom_scroll.setWidgetResizable(True)
        custom_scroll.setWidget(self.custom_container)
        custom_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        custom_scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        tabs.addTab(custom_scroll, "🎨 自訂")

        tabs.currentChanged.connect(lambda i: self._reload_custom() if i == 1 else None)
        layout.addWidget(tabs)

        mgr_btn = QPushButton("⚙ 管理自訂 Emoji")
        mgr_btn.setStyleSheet(
            "font-size:11px; padding:4px; color:#80848e;"
            "background:transparent; border-top:1px solid #1e1f22; border-radius:0;")
        mgr_btn.clicked.connect(self._open_manager)
        layout.addWidget(mgr_btn)

    def _pick(self, code: str):
        self.emoji_selected.emit(code)
        self.hide()

    def _reload_custom(self):
        while self.custom_layout.count():
            w = self.custom_layout.takeAt(0).widget()
            if w: w.deleteLater()
        emojis = load_custom_emojis()
        if not emojis:
            lbl = QLabel("尚無自訂 Emoji\n請點下方「管理」新增")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color:#80848e;font-size:12px;padding:20px;background:transparent;")
            self.custom_layout.addWidget(lbl, 0, 0)
            return
        cols = 6
        for i, (code, entry) in enumerate(emojis.items()):
            b64 = custom_emoji_b64(entry)
            # 用 QLabel 顯示圖片，完全不會被 Qt icon 機制裁切
            cell = QLabel()
            cell.setFixedSize(48, 48)
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.setToolTip(code)
            cell.setStyleSheet(
                "border:1px solid #3f4147; border-radius:6px;"
                "background:#313338;")
            if b64:
                try:
                    pm = QPixmap()
                    pm.loadFromData(base64.b64decode(b64))
                    if not pm.isNull():
                        pm_fit = pm.scaled(42, 42,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
                        cell.setPixmap(pm_fit)
                except Exception:
                    cell.setText(code[:4])
            else:
                cell.setText(code[:4])
            # 點擊事件
            cell.mousePressEvent = lambda e, c=code: self._pick(c)
            # hover 效果
            cell.enterEvent = lambda e, w=cell: w.setStyleSheet(
                "border:1px solid #5865f2; border-radius:6px; background:#35373c;")
            cell.leaveEvent = lambda e, w=cell: w.setStyleSheet(
                "border:1px solid #3f4147; border-radius:6px; background:#313338;")
            self.custom_layout.addWidget(cell, i // cols, i % cols)

    def _open_manager(self):
        self.hide()
        dlg = ManageEmojiDialog(self.parent(), sio=self._sio)
        dlg.exec()

# ══════════════════════════════════════════════════════════
class PinDialog(QDialog):
    def __init__(self, history, current_pin, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📌 釘選管理")
        self.setMinimumSize(520, 440)
        self.selected_text = current_pin
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>目前釘選：</b>"))
        self.current_label = QLabel(current_pin or "（無）")
        self.current_label.setWordWrap(True)
        self.current_label.setStyleSheet(
            "background:#fff3cd;padding:8px;border:1px solid #ffeeba;border-radius:4px;")
        layout.addWidget(self.current_label)
        layout.addWidget(QLabel("<b>從歷史訊息中選擇：</b>"))
        self.history_list = QListWidget()
        self.history_list.setAlternatingRowColors(True)
        for msg in reversed(history):
            item = QListWidgetItem(f"[{msg.get('time','')}] {msg['sender']}: {msg['text']}")
            item.setData(Qt.ItemDataRole.UserRole, msg['text'])
            self.history_list.addItem(item)
        self.history_list.itemClicked.connect(
            lambda i: self.manual_input.setPlainText(i.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.history_list, 3)
        layout.addWidget(QLabel("<b>或手動輸入：</b>"))
        self.manual_input = QPlainTextEdit()
        self.manual_input.setPlaceholderText("輸入想釘選的文字…")
        self.manual_input.setFixedHeight(70)
        if current_pin:
            self.manual_input.setPlainText(current_pin)
        layout.addWidget(self.manual_input)
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("✅ 確認釘選")
        ok_btn.setStyleSheet("background:#28a745;color:white;font-weight:bold;padding:6px;")
        ok_btn.clicked.connect(self._confirm)
        un_btn = QPushButton("❌ 解除釘選")
        un_btn.setStyleSheet("background:#dc3545;color:white;font-weight:bold;padding:6px;")
        un_btn.clicked.connect(self._unpin)
        ca_btn = QPushButton("取消"); ca_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn); btn_row.addWidget(un_btn); btn_row.addWidget(ca_btn)
        layout.addLayout(btn_row)

    def _confirm(self):
        self.selected_text = self.manual_input.toPlainText().strip()
        if not self.selected_text:
            QMessageBox.warning(self, "提示", "請選擇或輸入釘選內容"); return
        self.done(QDialog.DialogCode.Accepted)

    def _unpin(self):
        self.selected_text = ""; self.done(2)

# ══════════════════════════════════════════════════════════
#  媒體播放器（影片 / 音訊）
# ══════════════════════════════════════════════════════════
class MediaPlayerDialog(QDialog):
    def __init__(self, file_path: str, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"▶ {title}")
        self.setMinimumSize(640, 420)
        self._file_path = file_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        ext = os.path.splitext(file_path)[1].lower()
        is_video = ext in ('.mp4', '.avi', '.mov', '.mkv')

        # 影片畫面區域
        self._video_widget = None
        if is_video and HAS_MULTIMEDIA:
            from PyQt6.QtMultimediaWidgets import QVideoWidget
            self._video_widget = QVideoWidget()
            self._video_widget.setMinimumHeight(320)
            self._video_widget.setStyleSheet("background:black;")
            layout.addWidget(self._video_widget)
        else:
            # 音訊：顯示提示圖示
            audio_lbl = QLabel("🎵")
            audio_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            audio_lbl.setStyleSheet("font-size:72px;background:#1a1a2e;border-radius:8px;")
            audio_lbl.setMinimumHeight(160)
            layout.addWidget(audio_lbl)

        # 進度條
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self._seek)
        layout.addWidget(self.slider)

        # 時間標籤
        time_row = QHBoxLayout()
        self.time_lbl   = QLabel("00:00")
        self.total_lbl  = QLabel("00:00")
        self.time_lbl.setStyleSheet("color:gray;font-size:11px;")
        self.total_lbl.setStyleSheet("color:gray;font-size:11px;")
        time_row.addWidget(self.time_lbl)
        time_row.addStretch()
        time_row.addWidget(self.total_lbl)
        layout.addLayout(time_row)

        # 控制按鈕列
        ctrl_row = QHBoxLayout()
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.setFixedHeight(36)
        self.play_btn.setStyleSheet(
            "background:#0066cc;color:white;font-weight:bold;"
            "border-radius:6px;font-size:13px;padding:0 16px;")
        self.play_btn.clicked.connect(self._toggle_play)
        stop_btn = QPushButton("⏹ 停止")
        stop_btn.setFixedHeight(36)
        stop_btn.setStyleSheet(
            "background:#555;color:white;border-radius:6px;font-size:13px;padding:0 12px;")
        stop_btn.clicked.connect(self._stop)

        # 音量
        vol_lbl = QLabel("🔊")
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(80)
        self.vol_slider.setFixedWidth(90)
        self.vol_slider.valueChanged.connect(self._set_volume)

        ctrl_row.addWidget(self.play_btn)
        ctrl_row.addWidget(stop_btn)
        ctrl_row.addStretch()
        ctrl_row.addWidget(vol_lbl)
        ctrl_row.addWidget(self.vol_slider)
        layout.addLayout(ctrl_row)

        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        # 初始化播放器
        if HAS_MULTIMEDIA:
            from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
            self._player = QMediaPlayer()
            self._audio_out = QAudioOutput()
            self._audio_out.setVolume(0.8)
            self._player.setAudioOutput(self._audio_out)
            if self._video_widget:
                self._player.setVideoOutput(self._video_widget)
            self._player.setSource(QUrl.fromLocalFile(file_path))
            self._player.durationChanged.connect(self._on_duration)
            self._player.positionChanged.connect(self._on_position)
            self._player.playbackStateChanged.connect(self._on_state_changed)
            self._player.errorOccurred.connect(self._on_error)
        else:
            self._player = None

    def _fmt(self, ms: int) -> str:
        s = ms // 1000
        return f"{s//60:02d}:{s%60:02d}"

    def _toggle_play(self):
        if not self._player:
            return
        from PyQt6.QtMultimedia import QMediaPlayer
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _stop(self):
        if self._player:
            self._player.stop()

    def _seek(self, pos: int):
        if self._player:
            self._player.setPosition(pos)

    def _set_volume(self, val: int):
        if self._player and hasattr(self, '_audio_out'):
            self._audio_out.setVolume(val / 100.0)

    def _on_duration(self, dur: int):
        self.slider.setRange(0, dur)
        self.total_lbl.setText(self._fmt(dur))

    def _on_position(self, pos: int):
        if not self.slider.isSliderDown():
            self.slider.setValue(pos)
        self.time_lbl.setText(self._fmt(pos))

    def _on_state_changed(self, state):
        from PyQt6.QtMultimedia import QMediaPlayer
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("⏸ 暫停")
        else:
            self.play_btn.setText("▶ 播放")

    def _on_error(self, error, error_str):
        QMessageBox.warning(self, "播放錯誤",
            f"無法播放此檔案：{error_str}\n\n"
            "您可以點「⬇ 下載」後用系統播放器開啟。")

    def closeEvent(self, event):
        if self._player:
            self._player.stop()
        super().closeEvent(event)

# ══════════════════════════════════════════════════════════
#  圖片放大檢視（Discord 風格）
# ══════════════════════════════════════════════════════════
class ImageViewerDialog(QDialog):
    """點擊縮圖後彈出的全螢幕風格圖片檢視器"""
    def __init__(self, b64_data: str, file_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"🖼 {file_name}")
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # 取得螢幕大小
        screen = QApplication.primaryScreen().availableGeometry()
        self.setFixedSize(screen.width(), screen.height())
        self.move(screen.left(), screen.top())

        # 暗色遮罩背景
        bg = QWidget(self)
        bg.setStyleSheet("background:rgba(0,0,0,210);")
        bg.setFixedSize(self.size())

        # 解碼圖片
        try:
            raw = base64.b64decode(b64_data)
            self._pixmap = QPixmap()
            self._pixmap.loadFromData(raw)
        except Exception:
            self._pixmap = QPixmap()

        # 圖片標籤（置中）
        self._img_lbl = QLabel(self)
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet("background:transparent;")
        self._update_image()
        # 填滿整個視窗
        self._img_lbl.setFixedSize(self.size())
        self._img_lbl.move(0, 0)

        # 關閉提示
        hint = QLabel("按 ESC 或點擊任意處關閉", self)
        hint.setStyleSheet(
            "color:rgba(255,255,255,160);font-size:12px;"
            "background:transparent;padding:4px;")
        hint.adjustSize()
        hint.move(screen.width() // 2 - hint.width() // 2, screen.height() - 40)

        # 檔案名稱
        name_lbl = QLabel(file_name, self)
        name_lbl.setStyleSheet(
            "color:white;font-size:13px;font-weight:600;"
            "background:transparent;padding:4px;")
        name_lbl.adjustSize()
        name_lbl.move(screen.width() // 2 - name_lbl.width() // 2, 16)

        self._img_lbl.mousePressEvent = lambda e: self.close()
        bg.mousePressEvent           = lambda e: self.close()

    def _update_image(self):
        if self._pixmap.isNull():
            self._img_lbl.setText("（無法顯示圖片）")
            return
        screen = QApplication.primaryScreen().availableGeometry()
        max_w  = int(screen.width()  * 0.90)
        max_h  = int(screen.height() * 0.85)
        scaled = self._pixmap.scaled(
            max_w, max_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self._img_lbl.setPixmap(scaled)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        self.close()


# ══════════════════════════════════════════════════════════
class RoomPanel(QWidget):
    request_create = pyqtSignal()
    request_join   = pyqtSignal(str)
    request_rename = pyqtSignal(str, str)
    request_delete = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("room_panel")
        self.setFixedWidth(170)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        title = QLabel("💬 聊天室")
        title.setStyleSheet("font-weight:700;font-size:11px;letter-spacing:1px;color:#80848e;padding:8px 8px 4px 8px;text-transform:uppercase;")
        layout.addWidget(title)
        self.list_widget = QListWidget()
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._room_context_menu)
        self.list_widget.itemClicked.connect(
            lambda item: self.request_join.emit(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.list_widget)
        add_btn = QPushButton("＋ 新增頻道")
        add_btn.setStyleSheet("background:transparent;color:#80848e;border:none;font-size:12px;text-align:left;padding:4px 8px;font-weight:600;")
        add_btn.clicked.connect(self.request_create)
        layout.addWidget(add_btn)
        self.rooms = {}

    def update_rooms(self, room_list):
        current_id = self._selected_id()
        self.rooms = {r['id']: r['name'] for r in room_list}
        self.list_widget.clear()
        for r in room_list:
            item = QListWidgetItem(r['name'])
            item.setData(Qt.ItemDataRole.UserRole, r['id'])
            self.list_widget.addItem(item)
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) == current_id:
                self.list_widget.setCurrentRow(i); break

    def highlight_room(self, room_id):
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) == room_id:
                self.list_widget.setCurrentRow(i); break

    def _selected_id(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _room_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item: return
        room_id   = item.data(Qt.ItemDataRole.UserRole)
        room_name = self.rooms.get(room_id, item.text())
        menu = QMenu()
        join_act   = menu.addAction("🚪 進入房間")
        rename_act = menu.addAction("✏️ 重新命名")
        delete_act = menu.addAction("🗑️ 刪除房間")
        chosen = menu.exec(self.list_widget.mapToGlobal(pos))
        if chosen == join_act:   self.request_join.emit(room_id)
        elif chosen == rename_act: self.request_rename.emit(room_id, room_name)
        elif chosen == delete_act: self.request_delete.emit(room_id)

# ══════════════════════════════════════════════════════════
#  主視窗
# ══════════════════════════════════════════════════════════
class ChatClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.zt_server_ip   = SERVER_IP
        self.signals        = CommSignals()
        self.sio            = socketio.Client(reconnection=True)
        self.nickname       = ""
        self.is_voice_on    = False
        self.current_room   = "general"
        self.room_histories = {}
        self.room_pins      = {}
        self.avatars        = {}
        self._gif_movies    = {}
        self._my_profile    = {'bio': '', 'status': ''}

        self.init_ui()
        self.init_audio()
        self.start_socket_thread()
        self._start_heartbeat()
        self._login_shown = False
        QTimer.singleShot(3000, self.show_login)

    # ── UI ────────────────────────────────────────────────
    def init_ui(self):
        self.setWindowTitle("JChat 專業版")
        self.setGeometry(100, 100, 960, 640)
        # 設定程式圖標
        _pm = _load_svg_pixmap(64)
        if not _pm.isNull():
            self.setWindowIcon(QIcon(_pm))
        root = QHBoxLayout()

        self.room_panel = RoomPanel()
        self.room_panel.request_create.connect(self.create_room)
        self.room_panel.request_join.connect(self.join_room)
        self.room_panel.request_rename.connect(self.rename_room)
        self.room_panel.request_delete.connect(self.delete_room)
        root.addWidget(self.room_panel)

        right = QVBoxLayout()

        # 標題列
        title_row = QHBoxLayout()
        self.room_title = QLabel("# 一般")
        self.room_title.setObjectName("room_title")
        rename_btn = QPushButton("✏️"); rename_btn.setFixedWidth(30)
        rename_btn.setToolTip("重新命名此房間")
        rename_btn.clicked.connect(lambda: self.rename_room(
            self.current_room, self.room_panel.rooms.get(self.current_room,"")))
        title_row.addWidget(self.room_title)
        title_row.addWidget(rename_btn)
        title_row.addStretch()
        right.addLayout(title_row)

        # 釘選欄
        pin_row = QHBoxLayout()
        self.pin_bar = QLabel("📌 目前尚無釘選訊息")
        self.pin_bar.setWordWrap(True)
        self.pin_bar.setObjectName("pin_bar")
        pin_mgr_btn = QPushButton("⚙ 管理"); pin_mgr_btn.setFixedWidth(70)
        pin_mgr_btn.clicked.connect(self.open_pin_dialog)
        pin_row.addWidget(self.pin_bar, 9); pin_row.addWidget(pin_mgr_btn, 1)
        right.addLayout(pin_row)

        # 聊天 + 使用者清單
        mid = QHBoxLayout()
        left_box = QVBoxLayout()
        self.chat_window = QTextBrowser(); self.chat_window.setReadOnly(True)
        self.chat_window.document().setDefaultStyleSheet(
            "body { line-height: 1.5; }"
            "a { color: #00aff4; text-decoration: none; }"
            "a:hover { text-decoration: underline; }"
        )
        self.chat_window.setOpenLinks(False)
        self.chat_window.setOpenExternalLinks(False)
        self.chat_window.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_window.customContextMenuRequested.connect(self.show_context_menu)
        self.chat_window.anchorClicked.connect(self._on_link_clicked)
        self._gif_movies: dict = {}

        input_row = QHBoxLayout()
        self.input_field = QLineEdit(); self.input_field.setPlaceholderText("輸入訊息…")
        self.input_field.returnPressed.connect(self.send_message)
        send_btn = QPushButton("傳送"); send_btn.clicked.connect(self.send_message)
        send_btn.setFixedHeight(36)
        self.voice_btn = QPushButton("🎤"); self.voice_btn.clicked.connect(self.toggle_voice)
        self.voice_btn.setFixedSize(36, 36)
        self.voice_btn.setObjectName("ghost_btn")
        self.voice_btn.setToolTip("語音: 關閉")

        # Emoji 按鈕
        self._emoji_picker = EmojiPicker(self, sio=self.sio)
        self._emoji_picker.emoji_selected.connect(self._insert_emoji)
        emoji_btn = QPushButton("😀")
        emoji_btn.setFixedSize(36, 36)
        emoji_btn.setObjectName("ghost_btn")
        emoji_btn.setToolTip("Emoji / 自訂貼圖")
        emoji_btn.clicked.connect(self._toggle_emoji_picker)

        # 附件按鈕（只傳圖片）
        attach_btn = QPushButton("🖼")
        attach_btn.setFixedSize(36, 36)
        attach_btn.setObjectName("ghost_btn")
        attach_btn.setToolTip("傳送圖片")
        attach_btn.clicked.connect(self._send_file_dialog)

        input_row.addWidget(emoji_btn)
        input_row.addWidget(attach_btn)
        input_row.addWidget(self.input_field)
        input_row.addWidget(send_btn)
        input_row.addWidget(self.voice_btn)
        left_box.addWidget(self.chat_window)
        left_box.addLayout(input_row)

        # 使用者清單（點頭像跳個人資料卡）
        user_panel = QVBoxLayout()
        user_title = QLabel("成員")
        user_title.setStyleSheet("font-weight:bold;padding:4px;")
        self.user_list = QListWidget()
        self.user_list.setFixedWidth(160)
        self.user_list.setIconSize(QSize(AVATAR_SIZE, AVATAR_SIZE))
        self.user_list.itemClicked.connect(self._on_user_clicked)
        user_panel.addWidget(user_title)
        user_panel.addWidget(self.user_list)

        mid.addLayout(left_box, 8)
        mid.addLayout(user_panel, 2)
        right.addLayout(mid)

        root.addLayout(right, 1)
        container = QWidget(); container.setLayout(root)
        self.setCentralWidget(container)

        # 訊號連接
        self.signals.message_received.connect(self.on_message)
        self.signals.history_received.connect(self.on_history)
        self.signals.user_list_updated.connect(self.on_user_list)
        self.signals.pinned_updated.connect(self.on_pinned)
        self.signals.room_list_updated.connect(self.on_room_list)
        self.signals.force_join.connect(self.on_force_join)
        self.signals.avatars_loaded.connect(self.on_avatars_loaded)
        self.signals.avatar_updated.connect(self.on_avatar_updated)
        self.signals.connection_failed.connect(self.on_connection_failed)
        self.signals.emojis_loaded.connect(self.on_emojis_loaded)
        self.signals.emoji_updated.connect(self.on_emoji_updated)
        self.signals.emoji_deleted.connect(self.on_emoji_deleted)
        self.signals.profile_updated.connect(self.on_profile_updated)

        self.signals.connection_status.connect(self._on_connection_status)

        # 狀態列
        self._status_bar_label = QLabel("🟡 連線中…")
        self._status_bar_label.setStyleSheet(
            "padding:2px 8px;font-size:11px;color:#f0b232;font-weight:bold;")
        self.statusBar().addPermanentWidget(self._status_bar_label)

        # 選單列
        menubar = self.menuBar()
        profile_menu = menubar.addMenu("👤 我的帳號")
        settings_act = profile_menu.addAction("⚙ 帳號設定")
        settings_act.triggered.connect(self.open_account_settings)
        profile_menu.addSeparator()
        logout_act = profile_menu.addAction("🚪 登出")
        logout_act.triggered.connect(self.logout)

    # ── Socket.IO ─────────────────────────────────────────
    def start_socket_thread(self):
        @self.sio.on('receive_message')
        def on_msg(d):   self.signals.message_received.emit(d)
        @self.sio.on('load_history')
        def on_hist(d):  self.signals.history_received.emit(d)
        @self.sio.on('update_user_list')
        def on_ul(d):    self.signals.user_list_updated.emit(d)
        @self.sio.on('update_pinned')
        def on_pin(d):   self.signals.pinned_updated.emit(d)
        @self.sio.on('update_room_list')
        def on_rl(d):    self.signals.room_list_updated.emit(d)
        @self.sio.on('force_join_room')
        def on_fj(d):    self.signals.force_join.emit(d)
        @self.sio.on('load_avatars')
        def on_avs(d):   self.signals.avatars_loaded.emit(d)
        @self.sio.on('avatar_updated')
        def on_av(d):    self.signals.avatar_updated.emit(d)
        @self.sio.on('load_custom_emojis')
        def on_emjs(d):  self.signals.emojis_loaded.emit(d)
        @self.sio.on('emoji_updated')
        def on_emj(d):   self.signals.emoji_updated.emit(d)
        @self.sio.on('emoji_deleted')
        def on_emj_del(d): self.signals.emoji_deleted.emit(d.get('code','') if isinstance(d,dict) else str(d))
        @self.sio.on('profile_updated')
        def on_profile(d): self.signals.profile_updated.emit(d)

        def run():
            import time, traceback
            connected = False
            # 先嘗試純 websocket，失敗再 fallback 到 polling
            for transports in (['websocket'], ['polling']):
                if connected:
                    break
                try:
                    print(f'嘗試連線（{transports}）...')
                    self.sio.connect(
                        f'http://{self.zt_server_ip}:5000',
                        transports=transports,
                        wait_timeout=10,
                    )
                    connected = True
                    print(f'連線成功（{transports}）')
                    self.signals.connection_status.emit(True, '🟢 已連線')
                    self.sio.wait()  # 阻塞直到斷線
                    return  # 正常結束（如登出），不發失敗 signal
                except Exception as e:
                    traceback.print_exc()
                    print(f"連線嘗試失敗（{transports}）: {type(e).__name__}: {e}")
                    try:
                        if self.sio.connected:
                            self.sio.disconnect()
                    except: pass
                    time.sleep(1)
            self.signals.connection_failed.emit()
        threading.Thread(target=run, daemon=True).start()

    def _on_connection_status(self, is_connected: bool, text: str):
        self._status_bar_label.setText(text)
        if is_connected:
            self._status_bar_label.setStyleSheet(
                "padding:2px 8px;font-size:11px;color:#23a559;font-weight:bold;")
        else:
            self._status_bar_label.setStyleSheet(
                "padding:2px 8px;font-size:11px;color:#f23f42;font-weight:bold;")

    def _start_heartbeat(self):
        _state = {'connected': True, 'fail_count': 0}
        def _check():
            import time
            while True:
                time.sleep(15)
                try:
                    currently = self.sio.connected
                except Exception:
                    currently = False
                if currently:
                    _state['fail_count'] = 0
                    _state['connected']  = True
                    self.signals.connection_status.emit(True, "🟢 已連線")
                else:
                    _state['fail_count'] += 1
                    if _state['connected']:
                        _state['connected'] = False
                        ts = datetime.now().strftime('%H:%M:%S')
                        self.signals.connection_status.emit(
                            False, f"🔴 斷線（{ts}）")
                        if self.nickname:
                            QTimer.singleShot(0, self._on_server_disconnected)
        threading.Thread(target=_check, daemon=True).start()

    def _on_server_disconnected(self):
        QMessageBox.warning(
            self, "⚠️ 連線中斷",
            "與伺服器的連線已中斷。\n程式將自動嘗試重連，重連後請重新登入。")

    def on_connection_failed(self):
        self.show()
        ret = QMessageBox.critical(
            self, "連線失敗",
            f"無法連線到伺服器 IP: {self.zt_server_ip}\n\n"
            "請確認：\n"
            "① 伺服器是否已啟動（server.py）\n"
            "② ZeroTier 是否已連線且加入同一網路\n"
            "③ SERVER_IP 是否設定正確\n\n"
            "是否要重試連線？",
            QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Close,
        )
        if ret == QMessageBox.StandardButton.Retry:
            self.start_socket_thread()
        else:
            QApplication.instance().quit()

    # ── 頭像事件 ──────────────────────────────────────────
    def on_avatars_loaded(self, avs: dict):
        self.avatars.update(avs)
        self._refresh_user_list()
        self._redraw_chat()

    def on_avatar_updated(self, data: dict):
        self.avatars[data['username']] = data.get('avatar', '')
        self._avatar_html_cache = {k: v for k, v in self._avatar_html_cache.items()
                                   if k[0] != data['username']}
        self._refresh_user_list()
        self._redraw_chat()

    # ── 個人資料事件 ──────────────────────────────────────
    def on_profile_updated(self, data: dict):
        username = data.get('username', '')
        if username:
            # 伺服器廣播的動態欄位為 'user_status'，本地快取統一用 'status'
            status_val = data.get('user_status') or data.get('status', '')
            _profiles_cache[username] = {
                'bio': data.get('bio', ''),
                'status': status_val,
            }
            if username == self.nickname:
                self._my_profile = _profiles_cache[username]

    # ── 自訂 Emoji 同步事件 ───────────────────────────────
    def on_emojis_loaded(self, emojis: dict):
        global _server_emojis
        _server_emojis.clear()
        _server_emojis.update(emojis)
        for code, entry in emojis.items():
            if entry.get('ext','').lower() == '.gif' and entry.get('b64',''):
                self._ensure_gif_movie(code, entry['b64'])
        self._redraw_chat()

    def on_emoji_updated(self, data: dict):
        """收到他人新增 emoji 的廣播（修正：所有人包含自己都會更新）"""
        code = data.get('code','')
        if not code:
            return
        _server_emojis[code] = {'b64': data.get('b64',''), 'ext': data.get('ext','.png')}
        if data.get('ext','').lower() == '.gif' and data.get('b64',''):
            self._ensure_gif_movie(code, data['b64'])
        self._redraw_chat()

    def on_emoji_deleted(self, code: str):
        _server_emojis.pop(code, None)
        movie = self._gif_movies.pop(code, None)
        if movie:
            movie.stop()
        tmp = _gif_tmp_files.pop(code, None)
        if tmp and os.path.exists(tmp):
            try: os.remove(tmp)
            except: pass
        self._redraw_chat()

    # ── 帳號設定 ───────────────────────────────────────────
    def open_account_settings(self):
        if not self.nickname:
            QMessageBox.warning(self, "提示", "請先登入"); return
        dlg = AccountSettingsDialog(
            self.nickname, self.avatars, self.sio, self._my_profile, self)
        dlg.exec()
        # 更新本地顯示的頭像（如果在設定裡換了）
        self._refresh_user_list()

    def _handle_rename_success(self, new_name: str):
        """改名成功後登出讓使用者重新登入"""
        self.nickname = new_name
        QTimer.singleShot(500, self.logout)

    # ── 點使用者清單中的成員 ──────────────────────────────
    def _on_user_clicked(self, item: QListWidgetItem):
        name = item.data(Qt.ItemDataRole.UserRole)
        if not name or name == self.nickname:
            # 點自己 → 開帳號設定
            self.open_account_settings()
            return
        dlg = ProfileCard(name, self.avatars, self.sio, self)
        dlg.exec()

    # ── 連結點擊（檔案下載 / 影片播放）──────────────────────────────
    def _on_link_clicked(self, url: QUrl):
        scheme = url.scheme()
        if scheme == 'file_download':
            msg_index_str = url.host()
            file_name = url.path().lstrip('/')
            if msg_index_str.isdigit() and file_name:
                self._download_file(int(msg_index_str), file_name)
        elif scheme == 'image_view':
            # 點縮圖放大
            msg_index_str = url.host()
            file_name = url.path().lstrip('/')
            if msg_index_str.isdigit() and file_name:
                self._view_image(int(msg_index_str), file_name)
        elif scheme == 'video_play':
            msg_index_str = url.host()
            file_name = url.path().lstrip('/')
            if msg_index_str.isdigit() and file_name:
                self._play_media(int(msg_index_str), file_name)

    def _view_image(self, msg_index: int, file_name: str):
        history = self.room_histories.get(self.current_room, [])
        if msg_index >= len(history):
            return
        msg = history[msg_index]
        b64_data = msg.get('data', '')
        if not b64_data:
            return
        dlg = ImageViewerDialog(b64_data, file_name, self)
        dlg.exec()

    def _download_file(self, msg_index: int, file_name: str):
        history = self.room_histories.get(self.current_room, [])
        if msg_index >= len(history):
            return
        msg = history[msg_index]
        b64_data = msg.get('data', '')
        if not b64_data:
            QMessageBox.warning(self, "錯誤", "無法取得檔案資料")
            return
        save_path, _ = QFileDialog.getSaveFileName(self, "儲存檔案", file_name)
        if not save_path:
            return
        try:
            raw = base64.b64decode(b64_data)
            with open(save_path, 'wb') as f:
                f.write(raw)
            QMessageBox.information(self, "完成", f"已儲存至：{save_path}")
        except Exception as e:
            QMessageBox.warning(self, "儲存失敗", str(e))

    def _play_media(self, msg_index: int, file_name: str):
        """將影片/音訊寫入暫存檔後開視窗播放"""
        history = self.room_histories.get(self.current_room, [])
        if msg_index >= len(history):
            return
        msg = history[msg_index]
        b64_data = msg.get('data', '')
        if not b64_data:
            QMessageBox.warning(self, "錯誤", "無法取得媒體資料")
            return

        if not HAS_MULTIMEDIA:
            QMessageBox.warning(self, "無法播放",
                "您的環境缺少 PyQt6-Qt6-Multimedia 套件。\n"
                "請執行：pip install PyQt6-Qt6-Multimedia\n\n"
                "您仍可點「⬇ 下載」後用系統播放器開啟。")
            return

        try:
            raw = base64.b64decode(b64_data)
            ext = os.path.splitext(file_name)[1].lower() or '.mp4'
            fd, tmp_path = tempfile.mkstemp(suffix=ext)
            with os.fdopen(fd, 'wb') as f:
                f.write(raw)
        except Exception as e:
            QMessageBox.warning(self, "播放失敗", f"暫存檔建立失敗：{e}")
            return

        dlg = MediaPlayerDialog(tmp_path, file_name, self)
        dlg.exec()
        # 播放完畢後刪除暫存檔
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    # ── 登出 ──────────────────────────────────────────────
    def logout(self):
        if QMessageBox.question(self, "登出", "確定要登出嗎？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
            return
        if self.is_voice_on:
            self.is_voice_on = False
            self.voice_btn.setText("🎤 語音: 關閉")
            self.sio.emit('toggle_voice', False)
        self.nickname       = ""
        self.current_room   = "general"
        self.room_histories = {}
        self.room_pins      = {}
        self.avatars        = {}
        self._my_profile    = {'bio': '', 'status': ''}
        self.chat_window.clear()
        self.user_list.clear()
        self.room_panel.list_widget.clear()
        self.room_panel.rooms = {}
        self.pin_bar.setText("📌 目前尚無釘選訊息")
        self.room_title.setText("# 一般")
        self.hide()
        def _reconnect():
            import time, traceback
            try:
                if self.sio.connected:
                    self.sio.disconnect()
            except Exception:
                pass
            time.sleep(0.5)
            # 先試 websocket，失敗再試 polling
            connected = False
            for transports in (['websocket'], ['polling']):
                try:
                    self.sio.connect(
                        f'http://{self.zt_server_ip}:5000',
                        transports=transports,
                        wait_timeout=10,
                    )
                    connected = True
                    break
                except Exception as e:
                    traceback.print_exc()
                    print(f"登出後重連失敗（{transports}）: {type(e).__name__}: {e}")
                    time.sleep(0.5)
            if connected:
                QTimer.singleShot(0, self._open_login_dialog)
            else:
                self.signals.connection_failed.emit()
        threading.Thread(target=_reconnect, daemon=True).start()

    # ── 登入 ──────────────────────────────────────────────
    def show_login(self):
        self._login_shown = True
        if not self.sio.connected:
            QTimer.singleShot(1500, self._check_conn_and_login)
            return
        self._open_login_dialog()

    def _check_conn_and_login(self):
        if not self.sio.connected:
            # 還沒連上，再等 1.5 秒重檢查（最多等 10 秒共 7 次）
            self._conn_retry = getattr(self, '_conn_retry', 0) + 1
            if self._conn_retry < 7:
                QTimer.singleShot(1500, self._check_conn_and_login)
                return
            # 超過等待上限，交由 on_connection_failed 處理
            return
        self._conn_retry = 0
        self._open_login_dialog()

    def _open_login_dialog(self):
        self._login_dlg = LoginDialog()
        self._login_dlg.login_btn.clicked.connect(self._do_login)
        self._login_dlg.reg_btn.clicked.connect(self._do_register)
        self.signals.login_result.connect(self._on_login_result)
        self.signals.register_result.connect(self._on_register_result)
        if self._login_dlg.exec() != QDialog.DialogCode.Accepted:
            QApplication.instance().quit()

    def _do_login(self):
        dlg = self._login_dlg
        u, p = dlg.u_input.text().strip(), dlg.p_input.text().strip()
        if not u or not p:
            QMessageBox.warning(dlg, "提示", "請輸入帳號與密碼"); return
        if not self.sio.connected:
            QMessageBox.warning(dlg, "尚未連線", "與伺服器的連線尚未建立，請稍候再試。")
            return
        dlg.login_btn.setEnabled(False)
        dlg.login_btn.setText("登入中…")
        def _call():
            import traceback
            try:
                res = self.sio.call('login', {'username': u, 'password': p}, timeout=30)
                self.signals.login_result.emit(res if res else {'status':'fail','message':'伺服器無回應，請重試'})
            except Exception as e:
                traceback.print_exc()
                err_type = type(e).__name__
                err_msg  = str(e) or '（無詳細訊息）'
                self.signals.login_result.emit({'status':'fail','message':f'連線錯誤 [{err_type}]: {err_msg}'})
        threading.Thread(target=_call, daemon=True).start()

    def _on_login_result(self, res):
        dlg = self._login_dlg
        dlg.login_btn.setEnabled(True)
        dlg.login_btn.setText("登入")
        if res.get('status') == 'success':
            self.nickname = res.get('nickname', '')
            if res.get('avatar'):
                self.avatars[self.nickname] = res['avatar']
            # 載入個人資料
            p = res.get('profile', {})
            self._my_profile = {'bio': p.get('bio',''), 'status': p.get('status','')}
            _profiles_cache[self.nickname] = self._my_profile
            dlg.accept()
            self.show()
            # 登入後主動同步 emoji（確保看到最新的）
            def _sync_emojis():
                try:
                    self.sio.call('request_emojis', {}, timeout=10)
                except Exception:
                    pass
            threading.Thread(target=_sync_emojis, daemon=True).start()
            self.register_voice()
            threading.Thread(target=self.voice_send_loop,    daemon=True).start()
            threading.Thread(target=self.voice_receive_loop, daemon=True).start()
        else:
            QMessageBox.warning(dlg, "登入失敗", res.get('message', '未知'))

    def _do_register(self):
        dlg = self._login_dlg
        u, p = dlg.u_input.text().strip(), dlg.p_input.text().strip()
        if not u or not p:
            QMessageBox.warning(dlg, "提示", "請輸入帳號與密碼"); return
        dlg.reg_btn.setEnabled(False)
        dlg.reg_btn.setText("註冊中…")
        def _call():
            try:
                res = self.sio.call('register', {'username': u, 'password': p}, timeout=10)
                msg = res.get('message', '未知') if res else '無回應'
                self.signals.register_result.emit(msg)
            except Exception as e:
                self.signals.register_result.emit(f'連線錯誤: {e}')
        threading.Thread(target=_call, daemon=True).start()

    def _on_register_result(self, msg):
        dlg = self._login_dlg
        dlg.reg_btn.setEnabled(True)
        dlg.reg_btn.setText("註冊")
        QMessageBox.information(dlg, "提示", msg)

    # ── 房間 ──────────────────────────────────────────────
    def on_room_list(self, room_list):
        self.room_panel.update_rooms(room_list)
        self.room_panel.highlight_room(self.current_room)

    def on_force_join(self, data):
        self.current_room = data['room_id']
        self.room_title.setText(f"# {data['name']}")
        self.room_panel.highlight_room(self.current_room)

    def create_room(self):
        name, ok = QInputDialog.getText(self, "新增聊天室", "請輸入聊天室名稱：")
        if not ok or not name.strip(): return
        def _call():
            try:
                res = self.sio.call('create_room', {'name': name.strip()}, timeout=10)
                if res and res.get('status') == 'success':
                    QTimer.singleShot(0, lambda: self.join_room(res['room_id']))
                else:
                    msg = res.get('message','') if res else '無回應'
                    QTimer.singleShot(0, lambda: QMessageBox.warning(self, "失敗", msg))
            except Exception as e:
                QTimer.singleShot(0, lambda: QMessageBox.warning(self, "失敗", str(e)))
        threading.Thread(target=_call, daemon=True).start()

    def join_room(self, room_id):
        if room_id == self.current_room: return
        self.current_room = room_id
        name = self.room_panel.rooms.get(room_id, room_id)
        self.room_title.setText(f"# {name}")
        self.room_panel.highlight_room(room_id)
        self.chat_window.clear()
        for i, m in enumerate(self.room_histories.get(room_id, [])):
            self._append_msg(m, msg_index=i)
        pin = self.room_pins.get(room_id, "")
        self.pin_bar.setText(f"📌 釘選：{pin}" if pin else "📌 目前尚無釘選訊息")
        def _call():
            self.sio.call('join_room', {'room_id': room_id})
        threading.Thread(target=_call, daemon=True).start()

    def rename_room(self, room_id, current_name):
        name, ok = QInputDialog.getText(self, "重新命名", "新的聊天室名稱：", text=current_name)
        if not ok or not name.strip(): return
        n = name.strip()
        def _call():
            try:
                res = self.sio.call('rename_room', {'room_id': room_id, 'name': n}, timeout=10)
                if res and res.get('status') == 'success':
                    if room_id == self.current_room:
                        QTimer.singleShot(0, lambda: self.room_title.setText(f"# {n}"))
                else:
                    msg = res.get('message','') if res else '無回應'
                    QTimer.singleShot(0, lambda: QMessageBox.warning(self, "失敗", msg))
            except Exception as e:
                QTimer.singleShot(0, lambda: QMessageBox.warning(self, "失敗", str(e)))
        threading.Thread(target=_call, daemon=True).start()

    def delete_room(self, room_id):
        name = self.room_panel.rooms.get(room_id, room_id)
        if QMessageBox.question(self, "確認", f"確定刪除「{name}」？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes: return
        def _call():
            try:
                res = self.sio.call('delete_room', {'room_id': room_id}, timeout=10)
                if res and res.get('status') != 'success':
                    msg = res.get('message','') if res else '無回應'
                    QTimer.singleShot(0, lambda: QMessageBox.warning(self, "失敗", msg))
            except Exception as e:
                QTimer.singleShot(0, lambda: QMessageBox.warning(self, "失敗", str(e)))
        threading.Thread(target=_call, daemon=True).start()

    # ── 傳送圖片（影片/檔案功能已移除）──────────────────────
    def _send_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "傳送圖片", "",
            "圖片 (*.png *.jpg *.jpeg *.gif *.webp *.bmp)"
        )
        if not path:
            return
        file_name = os.path.basename(path)
        ext = os.path.splitext(file_name)[1].lower()
        file_size = os.path.getsize(path)
        max_size = 8 * 1024 * 1024
        if file_size > max_size:
            size_mb = file_size / 1024 / 1024
            QMessageBox.warning(self, "圖片太大",
                f"圖片大小為 {size_mb:.1f} MB，超過上限 8 MB。")
            return
        try:
            with open(path, 'rb') as f:
                raw = f.read()
            b64_data = base64.b64encode(raw).decode()
        except Exception as e:
            QMessageBox.warning(self, "讀取失敗", str(e))
            return
        def _send():
            try:
                self.sio.emit('chat_message', {
                    'type':      'image',
                    'text':      f'[🖼 {file_name}]',
                    'data':      b64_data,
                    'file_name': file_name,
                    'file_size': file_size,
                })
            except Exception as e:
                QTimer.singleShot(0, lambda: QMessageBox.warning(self, "傳送失敗", str(e)))
        threading.Thread(target=_send, daemon=True).start()

    # ── 聊天訊息 ──────────────────────────────────────────
    def on_message(self, data):
        room_id = data.get('room_id', self.current_room)
        hist = self.room_histories.setdefault(room_id, [])

        # 去重：如果是自己剛才本地已顯示的訊息（sender + text + type 相同），跳過
        if (data.get('sender') == self.nickname
                and data.get('type', 'text') == 'text'):
            text = data.get('text', '')
            # 檢查最後幾條是否已存在相同訊息（避免伺服器 echo 重複顯示）
            for m in hist[-5:]:
                if (m.get('sender') == self.nickname
                        and m.get('text') == text
                        and m.get('type', 'text') == 'text'):
                    return  # 已顯示過，忽略伺服器 echo

        hist.append(data)
        if room_id == self.current_room:
            self._append_msg(data, msg_index=len(hist) - 1)
        else:
            for i in range(self.room_panel.list_widget.count()):
                item = self.room_panel.list_widget.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == room_id:
                    if not item.text().startswith("🔴"):
                        item.setText(f"🔴 {item.text()}")
                    break

    def on_history(self, data):
        room_id = data.get('room_id', 'general')
        history = data.get('history', [])
        self.room_histories[room_id] = list(history)
        if room_id == self.current_room:
            self.chat_window.clear()
            for i, m in enumerate(history):
                self._append_msg(m, msg_index=i)
            pin = self.room_pins.get(room_id, "")
            self.pin_bar.setText(f"📌 釘選：{pin}" if pin else "📌 目前尚無釘選訊息")

    _avatar_html_cache: dict = {}

    def _avatar_html(self, sender: str) -> str:
        cache_key = (sender, self.avatars.get(sender, ''))
        if cache_key in self._avatar_html_cache:
            return self._avatar_html_cache[cache_key]
        b64 = self.avatars.get(sender, "")
        if not b64:
            size = 20
            colors = ["#5C6BC0","#26A69A","#EF5350","#AB47BC","#FFA726","#66BB6A"]
            color  = colors[hash(sender) % len(colors)]
            img = QImage(size, size, QImage.Format.Format_ARGB32)
            img.fill(Qt.GlobalColor.transparent)
            painter = QPainter(img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addEllipse(0, 0, size, size)
            painter.setClipPath(path)
            painter.fillRect(0, 0, size, size, QColor(color))
            painter.setPen(Qt.GlobalColor.white)
            font = QFont(); font.setPointSize(7); font.setBold(True)
            painter.setFont(font)
            painter.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter,
                             (sender[0] if sender else "?").upper())
            painter.end()
            pm = QPixmap.fromImage(img)
            qbuf = QBuffer()
            qbuf.open(QIODevice.OpenModeFlag.ReadWrite)
            pm.save(qbuf, "PNG")
            b64 = base64.b64encode(bytes(qbuf.data())).decode()
            qbuf.close()
        result = (f"<img src='data:image/png;base64,{b64}' width='20' height='20' "
                  f"style='border-radius:10px;vertical-align:middle;margin-right:4px;'>")
        if len(self._avatar_html_cache) > 200:
            self._avatar_html_cache.clear()
        self._avatar_html_cache[cache_key] = result
        return result

    def _append_msg(self, data, msg_index: int = None):
        sender   = data.get('sender', '?')
        t        = data.get('time') or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg_type = data.get('type', 'text')
        text     = data.get('text', '')

        if msg_index is None:
            history   = self.room_histories.get(self.current_room, [])
            msg_index = len(history) - 1

        header = (f"{self._avatar_html(sender)}"
                  f"<b style='color:#dbdee1'>{sender}</b>"
                  f"&nbsp;<span style='color:#80848e;font-size:11px'>{t}</span>&nbsp; ")

        if msg_type == 'image':
            b64_data  = data.get('data', '')
            file_name = data.get('file_name', 'image')
            if b64_data:
                ext  = os.path.splitext(file_name)[1].lower()
                mime = 'image/gif' if ext == '.gif' else 'image/png'
                # 縮圖可點擊放大（image_view scheme）
                img_html = (
                    f"<br>"
                    f"<a href='image_view://{msg_index}/{file_name}'>"
                    f"<img src='data:{mime};base64,{b64_data}' "
                    f"style='max-width:300px;max-height:300px;"
                    f"border-radius:6px;cursor:pointer;'>"
                    f"</a>"
                    f"<br><small style='color:#80848e;'>"
                    f"<a href='file_download://{msg_index}/{file_name}' "
                    f"style='color:#00aff4;'>⬇ 下載 {file_name}</a>"
                    f"&nbsp;・&nbsp;點圖片放大</small>"
                )
                self.chat_window.append(header + img_html)
            else:
                self.chat_window.append(header + self._render_emoji_in_text(text))

        else:
            rendered = self._render_emoji_in_text(text)
            self.chat_window.append(header + rendered)

        # 自動捲到底
        sb = self.chat_window.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _toggle_emoji_picker(self):
        if self._emoji_picker.isVisible():
            self._emoji_picker.hide()
        else:
            btn = self.sender()
            gp  = btn.mapToGlobal(btn.rect().topLeft())
            self._emoji_picker.move(gp.x(), gp.y() - self._emoji_picker.sizeHint().height() - 4)
            self._emoji_picker.show()
            self._emoji_picker.raise_()

    def _insert_emoji(self, code: str):
        self.input_field.insert(code)
        self.input_field.setFocus()

    def _render_emoji_in_text(self, text: str) -> str:
        emojis = load_custom_emojis()
        if not emojis:
            return text
        def replace(m):
            code = m.group(0)
            entry = emojis.get(code)
            if not entry:
                return code
            b64 = custom_emoji_b64(entry)
            if not b64:
                return code
            ext = entry.get("ext", ".png").lower()
            if ext == ".gif":
                self._ensure_gif_movie(code, b64)
                return (f"<img src='emoji://{code.strip(':')}' "
                        f"width='24' height='24' "
                        f"style='vertical-align:middle;margin:0 2px;'>")
            else:
                mime = "image/png"
                return (f"<img src='data:{mime};base64,{b64}' "
                        f"width='24' height='24' "
                        f"style='vertical-align:middle;margin:0 2px;'>")
        pattern = r':[a-zA-Z0-9_]+:'
        return re.sub(pattern, replace, text)

    def _ensure_gif_movie(self, code: str, b64: str):
        if code in self._gif_movies:
            return
        tmp_path = get_gif_tmp_path(code, b64)
        if not tmp_path:
            return
        movie = QMovie(tmp_path)
        movie.setCacheMode(QMovie.CacheMode.CacheAll)
        movie.frameChanged.connect(lambda _: self._on_gif_frame(code))
        movie.start()
        self._gif_movies[code] = movie

    def _on_gif_frame(self, code: str):
        movie = self._gif_movies.get(code)
        if not movie:
            return
        frame = movie.currentPixmap()
        if frame.isNull():
            return
        key = f"emoji://{code.strip(':')}"
        self.chat_window.document().addResource(
            3, QUrl(key), frame.toImage())
        self.chat_window.document().markContentsDirty(
            0, self.chat_window.document().characterCount())

    def _redraw_chat(self):
        sb = self.chat_window.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        self.chat_window.clear()
        for i, m in enumerate(self.room_histories.get(self.current_room, [])):
            self._append_msg(m, msg_index=i)
        if at_bottom:
            sb.setValue(sb.maximum())

    def on_user_list(self, data):
        if data.get('room_id') == self.current_room:
            new_users = data.get('users', [])
            for u in new_users:
                if u.get('avatar'):
                    self.avatars[u['name']] = u['avatar']
            # 偵測語音狀態變化，播放提示音
            self._detect_voice_change(new_users)
            self._refresh_user_list_data(new_users)

    def _detect_voice_change(self, new_users):
        """比較新舊使用者語音狀態，播放加入/離開提示音"""
        old_voice = getattr(self, '_prev_voice_users', set())
        new_voice = {u['name'] for u in new_users if u.get('voice')}
        joined = new_voice - old_voice
        left   = old_voice - new_voice
        if joined or left:
            self._prev_voice_users = new_voice
            if joined:
                self._play_voice_sound('join')
            elif left:
                self._play_voice_sound('leave')
        else:
            self._prev_voice_users = new_voice

    def _play_voice_sound(self, kind: str):
        """用 PyAudio 播放語音加入/離開的短促提示音"""
        if not getattr(self, 'audio_ok', False) or self.stream_out is None:
            # fallback：系統提示音
            QApplication.beep()
            return
        import math, struct
        rate = 16000
        try:
            if kind == 'join':
                # 上升音：880 Hz → 1046 Hz，各 0.12s
                freqs   = [880, 1046]
                dur_ms  = 120
            else:
                # 下降音：880 Hz → 659 Hz，各 0.12s
                freqs   = [880, 659]
                dur_ms  = 120
            frames_per_tone = int(rate * dur_ms / 1000)
            pcm = b''
            for freq in freqs:
                for i in range(frames_per_tone):
                    # 簡單正弦波，帶淡入淡出避免爆音
                    t = i / rate
                    env = min(i, frames_per_tone - i, 200) / 200.0
                    sample = int(32767 * 0.35 * env * math.sin(2 * math.pi * freq * t))
                    pcm += struct.pack('<h', sample)
            def _write():
                try:
                    self.stream_out.write(pcm)
                except Exception:
                    pass
            threading.Thread(target=_write, daemon=True).start()
        except Exception as e:
            print(f"[提示音] 播放失敗: {e}")

    def _refresh_user_list_data(self, users_data):
        self._current_users = users_data
        self._refresh_user_list()

    def _refresh_user_list(self):
        users_data = getattr(self, '_current_users', [])
        self.user_list.clear()
        for u in users_data:
            name = u['name']
            display = f"  {'🔊' if u['voice'] else '　'} {name}"
            if name == self.nickname:
                display += " (我)"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, name)  # 儲存純名稱方便點擊使用
            pm = get_avatar_pixmap(name, self.avatars, AVATAR_SIZE)
            item.setIcon(QIcon(pm))
            self.user_list.addItem(item)

    def send_message(self):
        t = self.input_field.text().strip()
        if not t:
            return
        if not self.sio.connected:
            QMessageBox.warning(self, "未連線", "與伺服器的連線已中斷，請稍候重連後再試。")
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = {
            'type':    'text',
            'text':    t,
            'sender':  self.nickname,
            'time':    now,
            'room_id': self.current_room,
        }
        # 本地立即顯示（不依賴伺服器回傳，斷線重連後也看得到）
        hist = self.room_histories.setdefault(self.current_room, [])
        hist.append(msg)
        self._append_msg(msg, msg_index=len(hist) - 1)
        self.sio.emit('chat_message', {'type': 'text', 'text': t})
        self.input_field.clear()

    def show_context_menu(self, pos):
        sel = self.chat_window.textCursor().selectedText().strip()
        if not sel: return
        m = QMenu()
        pin_act   = m.addAction("📌 釘選此訊息")
        unpin_act = m.addAction("❌ 解除釘選")
        chosen = m.exec(self.chat_window.mapToGlobal(pos))
        if chosen == pin_act:
            self.sio.emit('pin_request', {'room_id': self.current_room, 'text': sel})
        elif chosen == unpin_act:
            self.sio.emit('pin_request', {'room_id': self.current_room, 'text': ''})

    def on_pinned(self, data):
        room_id = data.get('room_id', self.current_room)
        text    = data.get('text','')
        self.room_pins[room_id] = text
        if room_id == self.current_room:
            self.pin_bar.setText(f"📌 釘選：{text}" if text else "📌 目前尚無釘選訊息")

    def open_pin_dialog(self):
        history = self.room_histories.get(self.current_room,[])
        pin     = self.room_pins.get(self.current_room,'')
        dlg = PinDialog(history, pin, self)
        result = dlg.exec()
        if result == QDialog.DialogCode.Accepted:
            self.sio.emit('pin_request',{'room_id':self.current_room,'text':dlg.selected_text})
        elif result == 2:
            self.sio.emit('pin_request',{'room_id':self.current_room,'text':''})

    # ── 語音 ──────────────────────────────────────────────
    def toggle_voice(self):
        self.is_voice_on = not self.is_voice_on
        status = '開啟' if self.is_voice_on else '關閉'
        self.voice_btn.setToolTip(f"語音: {status}")
        self.voice_btn.setText("🎤" if not self.is_voice_on else "🔴")
        self.sio.emit('toggle_voice', self.is_voice_on)

    def init_audio(self):
        self.audio_ok = False
        self.p = None
        self.stream_in = None
        self.stream_out = None
        self.udp_sock = None
        try:
            self.p = pyaudio.PyAudio()
            self.stream_in  = self.p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                                          input=True, frames_per_buffer=512)
            self.stream_out = self.p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                                          output=True, frames_per_buffer=512)
            self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_sock.settimeout(1.0)
            self.udp_sock.bind(('0.0.0.0', 0))
            self.audio_ok = True
            print(f"音訊初始化成功，UDP port={self.udp_sock.getsockname()[1]}")
        except Exception as e:
            print(f"音訊初始化失敗（語音功能將停用）: {e}")
            try:
                if self.stream_in:  self.stream_in.close()
                if self.stream_out: self.stream_out.close()
                if self.p:          self.p.terminate()
                if self.udp_sock:   self.udp_sock.close()
            except: pass
            self.stream_in = self.stream_out = self.p = self.udp_sock = None

    def register_voice(self):
        if not self.audio_ok: return
        try:
            self.udp_sock.sendto(b'PING', (self.zt_server_ip, VOICE_PORT))
            def _heartbeat():
                import time
                while True:
                    time.sleep(10)
                    try: self.udp_sock.sendto(b'PING', (self.zt_server_ip, VOICE_PORT))
                    except: break
            threading.Thread(target=_heartbeat, daemon=True).start()
        except Exception as e:
            print(f"語音登記失敗: {e}")

    def voice_send_loop(self):
        if not self.audio_ok: return
        while True:
            try:
                data = self.stream_in.read(512, exception_on_overflow=False)
                if self.is_voice_on:
                    try:
                        self.udp_sock.sendto(data, (self.zt_server_ip, VOICE_PORT))
                    except OSError as e:
                        # Windows WinError 10054：對方強制關閉，屬正常現象，靜默忽略
                        if getattr(e, 'winerror', None) == 10054:
                            pass
                        else:
                            print(f"語音傳送錯誤: {e}")
            except Exception as e:
                print(f"語音讀取錯誤: {e}")

    def voice_receive_loop(self):
        if not self.audio_ok: return
        while True:
            try:
                data, _ = self.udp_sock.recvfrom(65536)
                if data == b'PING': continue
                if self.is_voice_on:
                    self.stream_out.write(data)
            except socket.timeout:
                continue
            except OSError as e:
                # Windows WinError 10054：UDP 收到 ICMP 不可達，靜默忽略繼續
                if getattr(e, 'winerror', None) == 10054:
                    continue
                print(f"語音接收錯誤: {e}")
            except Exception as e:
                print(f"語音接收錯誤: {e}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(DISCORD_QSS)
    client = ChatClient()
    sys.exit(app.exec())
