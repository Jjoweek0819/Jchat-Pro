# Jchat-Basic

Jchat-Basic is a simple multi-room chat application built with Python. It allows users to chat in different rooms and features a basic voice intercom function.

### 🌐 Connection Requirements
> **Important:** This application requires a direct network connection between the client and server.

* **Network:** Users must be on the **same LAN**, use a **VPN**, or have a **Direct IP** connection to the server.
* **Manual Configuration:** You **must update the Server IP address** in the client-side code before launching the application to ensure it points to the correct host.

### ✨ Key Features
* **Multi-room Chat:** Join different rooms to send text messages and emojis.
* **Voice Chat:** A simple "Voice On/Off" toggle to talk with others in the same room (powered by UDP).
* **Media Sharing:** Send images and videos (up to 8MB). Includes a basic built-in player for quick viewing.
* **Pin Messages:** Keep important notes fixed at the top of the chat window.
* **Custom Profiles:** Set your own avatar and manage basic account settings.

### 🔧 How it Works
* **Backend:** Uses **Flask-SocketIO** for messaging and file transfers. Data is saved in simple **JSON files** (no complex database required).
* **Voice Engine:** A dedicated **UDP script** handles audio data for faster transmission.
* **Desktop UI:** Built with **PyQt6**, using multi-threading to keep the interface smooth while chatting or talking.

### 🚀 Quick Start
1. **Install dependencies:** `pip install flask-socketio pyqt6 pyaudio`
2. **Configure IP:** Open `client_gui.py` and replace `localhost` with the **Server's IP address**.
3. **Run the Servers:** > **Note:** `server.py` and `voice_server.py` only need to be running on the **Server side**.
4. **Run the Client:** Launch `client_gui.py` and start chatting!

---

### 👥 Contributors
Special thanks to my friends who helped with the development and testing:
* **[Wesley Wang](https://github.com/wangwesley1125)** - Assisted with UI Design, Bug fixing, and Testing.

### 🛠 Tools Used
* **Python**: Core programming language.
* **PyQt6**: Desktop GUI framework.
* **Flask-SocketIO**: Real-time messaging and file handling.
* **PyAudio**: Audio capturing and playback.
* **UDP Protocol**: Low-latency voice transmission.
* **JSON**: Lightweight data storage.
* **Claude**: Used for vibe-coding.
* **Gemini**: Used for safety checks and debugging.
