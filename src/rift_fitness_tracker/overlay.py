import tkinter as tk
import socket
import ctypes
import json

class RiotTrackerOverlay:
    def __init__(self, root):
        self.root = root

        # Keep hidden during setup to not focus on it instead of cmd window
        self.root.withdraw()
        
        # Window Setup (Using transparent purple chroma key)
        self.root.overrideredirect(True) 
        self.root.geometry("300x90+0+0")
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "purple")
        self.root.config(bg="purple")
        
        # UI Elements
        self.label = tk.Label(
            self.root, 
            text="STARTING...", 
            font=("Consolas", 16, "bold"), 
            fg="#00FF00", 
            bg="purple",
            justify="left"
        )
        self.label.pack(expand=True, fill="both", padx=10, pady=10)
        
        # Setup a Non-Blocking TCP Socket directly on the main thread
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(('127.0.0.1', 5555))
        self.server.listen(1)
        
        # Tells Python not to wait around if no data is ready
        self.server.setblocking(False) 
        
        # Initialize layout handles WITHOUT drawing or activating the window
        self.root.update_idletasks()

        # Apply Windows styles & reveal window non-actively
        self.make_window_click_through()

        # Start the single-threaded network polling loop
        self.poll_network_data()

    def make_window_click_through(self):
        # GA_ROOT (2) gets the true top-level HWND even with overrideredirect
        GA_ROOT = 2
        hwnd = ctypes.windll.user32.GetAncestor(self.root.winfo_id(), GA_ROOT)
        if not hwnd:
            hwnd = self.root.winfo_id()

        GWL_EXSTYLE       = -20
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_LAYERED     = 0x00080000
        WS_EX_NOACTIVATE  = 0x08000000  # Do not steal focus on show
        WS_EX_TOPMOST     = 0x00000008  # Keep on top
        WS_EX_TOOLWINDOW  = 0x00000080  # Hide from taskbar and alt-tab focus

        current_styles = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        new_styles = current_styles | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOPMOST | WS_EX_TOOLWINDOW
        
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_styles)

        # SW_SHOWNOACTIVATE (4) reveals window without stealing active focus
        ctypes.windll.user32.ShowWindow(hwnd, 4)

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

    def cleanup(self):
        """Safely closes the TCP socket when the window closes."""
        try:
            if hasattr(self, 'server') and self.server:
                self.server.close()
                print("[OVERLAY] TCP socket closed.")
        except Exception as e:
            print(f"[OVERLAY] Error during cleanup: {e}")

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
        root.destroy()

if __name__ == "__main__":
    start_overlay()