import tkinter as tk
import socket
import ctypes
import json

class RiotTrackerOverlay:
    def __init__(self, root):
        self.root = root
        
        # 1. Window Setup (Using transparent purple chroma key)
        self.root.overrideredirect(True) 
        self.root.geometry("300x90+0+0")
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "purple")
        self.root.config(bg="purple")
        
        # 2. UI Elements
        self.label = tk.Label(
            self.root, 
            text="STARTING...", 
            font=("Consolas", 16, "bold"), 
            fg="#00FF00", 
            bg="purple",
            justify="left"
        )
        self.label.pack(expand=True, fill="both", padx=10, pady=10)
        
        # 3. Setup a Non-Blocking TCP Socket directly on the main thread
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(('127.0.0.1', 5555))
        self.server.listen(1)
        
        # Tells Python not to wait around if no data is ready
        self.server.setblocking(False) 
        
        # 4. Inject Windows Click-Through Styles
        self.root.update()
        self.make_window_click_through()
        
        # 5. Start the single-threaded network polling loop
        self.poll_network_data()

    def make_window_click_through(self):
        # Injects Windows OS styles to make the window completely click-through
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_LAYERED = 0x00080000
        
        current_styles = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, 
            GWL_EXSTYLE, 
            current_styles | WS_EX_TRANSPARENT | WS_EX_LAYERED
        )

    def poll_network_data(self):
        # Checks the socket for incoming data from the tracker worker every 100ms
        try:
            conn, addr = self.server.accept()
            raw_text = conn.recv(1024).decode('utf-8')
            conn.close()

            if raw_text:
                actual_data = json.loads(raw_text)

                # Handle the new structured dictionary payloads safely
                if isinstance(actual_data, dict):
                    status = actual_data.get("status", "UNKNOWN")
                    
                    if status == "LIVE":
                        deaths = actual_data.get("deaths", 0)
                        cs_min = actual_data.get("cs_min", 0)
                        
                        # Calculated workout requirements (keeping your multiplier logic)
                        pushups = deaths * 1
                        situps = max(0, 10 - cs_min) * 1
                        
                        # Dynamically change text colors based on state performance vibes
                        self.label.config(
                            text=f"🔴 Deaths: {deaths} ({pushups} PU)\n🟢 CS/Min: {cs_min} ({situps} SU)",
                            fg="#FF3333" if deaths > 3 else "#00FF00"
                        )
                    else:
                        # Display menu/client tracking phase statuses cleanly (SCANNING..., LOADING..., PROCESSING...)
                        # Muted yellow color scheme during phase shifts
                        self.label.config(text=status, fg="#FFD700")
                
                # Fallback handler for raw strings/legacy data blocks
                elif isinstance(actual_data, str):
                    self.label.config(text=actual_data, fg="#00FF00")
            
        except (BlockingIOError, ConnectionResetError):
            # Normal behavior: no new packet received in this 100ms tick window
            pass
        except Exception as e:
            print(f"Network error parsing data packet: {e}")
        
        # Check the socket again in 100 milliseconds
        self.root.after(100, self.poll_network_data)

def start_overlay():
    root = tk.Tk()
    app = RiotTrackerOverlay(root)
    
    def on_closing():
        app.cleanup()
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.cleanup()

if __name__ == "__main__":
    start_overlay()