
#import click
import tkinter as tk
from tkinter import StringVar
from tkinter import ttk, messagebox, Menu, RAISED, BOTTOM, X
from tkinterdnd2 import TkinterDnD
from pycompare.workspace.workspace import Workspace
from pycompare._version import __version__
from pycompare.search_dialog import SearchDialog

class Application:
    def __init__(self, root):
        self.root = root        
        self.statusvar = StringVar()
        self.menu()
        self.workspace = Workspace(root, self.statusvar)
        self.status_bar()
        # 保存搜索对话框实例
        self.search_dialog = None

    def about(self):
        messagebox.showinfo("关于", "文本对比工具\n版本：" + __version__)
        
    def search(self):
        """打开搜索对话框"""
        if self.search_dialog is None or not self.search_dialog.dialog.winfo_exists():
            self.search_dialog = SearchDialog(self.root, self.workspace)
        else:
            # 如果对话框已存在，将其置于前台
            self.search_dialog.dialog.lift()
            self.search_dialog.search_entry.focus_set()

    def menu(self):
        main_menu = Menu(self.root)
        self.root.config(menu=main_menu)

        # 添加编辑菜单
        edit_menu = Menu(main_menu, tearoff=0)
        edit_menu.add_command(label="查找...(Ctrl+F)", command=self.search)
        main_menu.add_cascade(label="编辑", menu=edit_menu)
        
        main_menu.add_command(label="刷新(F5)",
            command=lambda:self.workspace.refresh_compare_F5(None, None, self.workspace.__dict__['__argsdict']))
        # 全局处理快捷键F5
        self.root.bind('<F5>', lambda event: self.workspace.refresh_compare_F5(None, None, self.workspace.__dict__['__argsdict']))
        
        # 绑定Ctrl+F快捷键
        self.root.bind('<Control-f>', lambda event: self.search())
        
        main_menu.add_command(label="关于",
            command=lambda:self.about())

    def status_bar(self):        
        statusbar = ttk.Label(self.root, relief=RAISED, borderwidth=1, textvariable=self.statusvar)
        statusbar.pack(side=BOTTOM, fill=X)

"""
@click.command()
@click.help_option('-h', '--help')
@click.version_option(version=__version__, prog_name='pycompare')
"""
def cli():
    #set_start_method('spawn', force=True)  # 解决Windows兼容性问题

    root = TkinterDnD.Tk()
    root.title("文本对比工具")
    # root.state('zoomed')

    # --- 1. 设置初始窗口大小（适合拖拽）---
    initial_width = 800
    initial_height = 600
    # 获取屏幕尺寸
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    # 计算居中位置
    x = (screen_width - initial_width) // 2
    y = (screen_height - initial_height) // 2
    # 设置初始窗口：位置 + 大小
    root.geometry(f"{initial_width}x{initial_height}+{x}+{y}")
    # --- 2. 设置最小尺寸，防止缩得太小 ---
    root.minsize(400, 230)
    # --- 3. 允许窗口缩放（用户可手动调整或最大化）---
    root.resizable(True, True)

    app = Application(root)
    # 运行主循环
    root.mainloop()

if __name__ == "__main__":
    cli()