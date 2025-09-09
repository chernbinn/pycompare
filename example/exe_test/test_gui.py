# test_gui.py
import tkinter as tk
import sys
import os

# 强制写日志到当前目录
log_path = os.path.join(os.getcwd(), "nuitka_test.log")
with open(log_path, "w", encoding="utf-8") as f:
    f.write("Start\n")

try:
    root = tk.Tk()
    root.title("Test")
    label = tk.Label(root, text="Hello from Nuitka!")
    label.pack(padx=20, pady=20)
    root.after(3000, root.destroy)  # 3秒后自动关闭
    root.mainloop()
    with open(log_path, "a") as f:
        f.write("GUI ran successfully.\n")
except Exception as e:
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"Error: {type(e).__name__}: {e}\n")
    print(f"TK Error: {e}", file=sys.stderr)