
import click
from tkinter import *
from tkinter import ttk
from tkinterdnd2 import TkinterDnD
from tkinter import messagebox
from pycompare.workspace.workspace import Workspace

from pycompare._version import __version__

class Application:
    def __init__(self, root):
        self.root = root        
        self.statusvar = StringVar()
        self.menu()
        self.workspace = Workspace(root, self.statusvar)
        self.status_bar()

    def about(self):
        messagebox.showinfo("关于", "文本对比工具\n版本：" + __version__)

    def menu(self):
        main_menu = Menu(self.root)
        self.root.config(menu=main_menu)

        main_menu.add_command(label="刷新(F5)",
            command=lambda:self.workspace.refresh_compare_F5(None, None, self.workspace.__dict__['__argsdict']))
        # 全局处理快捷键F5
        self.root.bind('<F5>', lambda event: self.workspace.refresh_compare_F5(None, None, self.workspace.__dict__['__argsdict']))

        main_menu.add_command(label="关于",
            command=lambda:self.about())

    def status_bar(self):        
        statusbar = ttk.Label(self.root, relief=RAISED, borderwidth=1, textvariable=self.statusvar)
        statusbar.pack(side=BOTTOM, fill=X)

@click.command()
@click.help_option('-h', '--help')
@click.version_option(version=__version__, prog_name='pycompare')
def cli():
    #set_start_method('spawn', force=True)  # 解决Windows兼容性问题

    root = TkinterDnD.Tk()
    root.title("文本对比工具")
    root.state('zoomed')
    app = Application(root)

    # 运行主循环
    root.mainloop()

if __name__ == "__main__":
    cli()