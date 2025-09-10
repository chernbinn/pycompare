
import click
from tkinter import *
from tkinter import ttk
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

    def menu(self):
        main_menu = Menu(self.root)
        self.root.config(menu=main_menu)

        main_menu.add_command(label="刷新",
            comman=lambda:messagebox.showinfo(title='tip', message="maybe wait!"))
        # 帮助
        help_menu = Menu(main_menu, tearoff=False)
        main_menu.add_cascade(label="帮助", menu=help_menu)

    def status_bar(self):        
        statusbar = ttk.Label(self.root, relief=RAISED, borderwidth=1, textvariable=self.statusvar)
        statusbar.pack(side=BOTTOM, fill=X)

@click.command()
@click.help_option('-h', '--help')
@click.version_option(version=__version__, prog_name='pycompare')
def cli():
    #set_start_method('spawn', force=True)  # 解决Windows兼容性问题

    root = Tk()
    root.title("文本对比工具")
    root.state('zoomed')
    app = Application(root)

    # 运行主循环
    root.mainloop()

if __name__ == "__main__":
    cli()