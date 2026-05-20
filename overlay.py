import tkinter as tk
import socket
import ctypes
import json

class SingleThreadedOverlay:
    def __init__(self, root):
        self.root = root
        
        # 1. Window Setup (Switch to "purple" and uncomment overrideredirect once confirmed working!)
        self.root.overrideredirect(True) 
        self.root.geometry("300x90+0+0")
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "purple")
        self.root.config(bg="purple")
        
        # 2. UI Elements
        self.label = tk.Label(
            self.root, 
            text="Waiting for tracker...", 
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
        
        # THIS IS THE KEY: Tells Python not to wait around if no data is ready
        self.server.setblocking(False) 
        
        # 4. Inject Windows Click-Through Styles
        self.root.update()
        self.make_window_click_through()
        
        # 5. Start the single-threaded network polling loop
        self.poll_network_data()

    def make_window_click_through(self):
        #Injects Windows OS styles to make the window completely click-through
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
        #Checks the socket for incoming data from kda_tracker.py every 100ms
        try:
            # Try to accept a connection. Because of setblocking(False), if 
            # kda_tracker hasn't sent anything, it immediately raises a BlockingIOError.
            conn, addr = self.server.accept()
            raw_text = conn.recv(1024).decode('utf-8')
            conn.close()

            if raw_text:
                actual_data = json.loads(raw_text)

            if isinstance(actual_data, str):
                self.label.config(text=actual_data)
            elif isinstance(actual_data, list):
                self.label.config(text=f"Push ups: {actual_data[0] * 5}\nSit ups: {10 - actual_data[1]}")
            
        except (BlockingIOError, ConnectionResetError):
            # This is normal behavior! It means no new data was sent in this 100ms window.
            pass
        except Exception as e:
            # If a real structural error happens, it will print here instead of exiting silently
            print(f"Network error: {e}")
        
        # Check the socket again in 100 milliseconds
        self.root.after(100, self.poll_network_data)

if __name__ == "__main__":
    root = tk.Tk()
    app = SingleThreadedOverlay(root)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nOverlay closed cleanly.")