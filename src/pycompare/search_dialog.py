import re
import tkinter as tk
from tkinter import Toplevel, Label, Entry, StringVar, IntVar, Checkbutton, Radiobutton, Button, Frame, messagebox, INSERT, LEFT, W


class SearchDialog:
    def __init__(self, parent, workspace):
        self.parent = parent
        self.workspace = workspace
        self.dialog = Toplevel(parent)
        self.dialog.title("查找")
        self.dialog.geometry("350x180")
        self.dialog.transient(parent)
        self.dialog.resizable(False, False)
        # 设置对话框为模态，确保用户必须与它交互
        self.dialog.grab_set()
        
        # 搜索关键词
        Label(self.dialog, text="查找内容:").grid(row=0, column=0, sticky=W, padx=5, pady=5)
        self.search_var = StringVar()
        self.search_entry = Entry(self.dialog, textvariable=self.search_var, width=25)
        self.search_entry.grid(row=0, column=1, padx=5, pady=5)
        # 在对话框显示时确保搜索框获取焦点
        self.dialog.after(10, lambda: self.search_entry.focus_set())
        
        # 区分大小写
        self.case_var = IntVar()
        self.case_check = Checkbutton(self.dialog, text="区分大小写", variable=self.case_var)
        self.case_check.grid(row=1, column=0, columnspan=2, sticky=W, padx=5)
        
        # 搜索窗口选择
        Label(self.dialog, text="搜索范围:").grid(row=2, column=0, sticky=W, padx=5, pady=5)
        self.target_var = StringVar(value="left")
        left_radio = Radiobutton(self.dialog, text="左侧窗口", variable=self.target_var, value="left")
        right_radio = Radiobutton(self.dialog, text="右侧窗口", variable=self.target_var, value="right")
        left_radio.grid(row=2, column=1, sticky=W)
        right_radio.grid(row=3, column=1, sticky=W)
        
        # 按钮
        button_frame = Frame(self.dialog)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)
        
        self.find_next_btn = Button(button_frame, text="查找下一个", command=self.find_next)
        self.find_next_btn.pack(side=LEFT, padx=5)
        
        self.find_prev_btn = Button(button_frame, text="查找上一个", command=self.find_previous)
        self.find_prev_btn.pack(side=LEFT, padx=5)
        
        self.close_btn = Button(button_frame, text="关闭", command=self.dialog.destroy)
        self.close_btn.pack(side=LEFT, padx=5)
        
        # 绑定快捷键
        self.dialog.bind('<Return>', lambda event: self.find_next())
        self.dialog.bind('<Escape>', lambda event: self.dialog.destroy())
        
        # 保存当前搜索状态
        self.last_search = ""
        self.last_position = {"left": "1.0", "right": "1.0"}
        self.current_window = "left"
    
    def find_next(self):
        self._find(direction=1)
    
    def find_previous(self):
        self._find(direction=-1)
    
    def _find(self, direction=1):
        search_text = self.search_var.get()
        if not search_text:
            messagebox.showinfo("提示", "请输入要查找的内容")
            return
        
        # 根据选择确定目标文本区域
        target_window = self.target_var.get()
        if target_window == "left":
            text_area = self.workspace.l_text_area
            self.current_window = "left"
        else:
            text_area = self.workspace.r_text_area
            self.current_window = "right"
        
        # 获取文本内容
        text = text_area.get("1.0", "end-1c")
        
        # 获取当前窗口的搜索状态
        current_last_position = self.last_position[self.current_window]
        
        # 如果搜索文本改变，重置位置
        if search_text != self.last_search:
            self.last_search = search_text
            for window in ["left", "right"]:
                if direction == 1:
                    self.last_position[window] = "1.0"
                else:
                    # 对于反向搜索，使用文本的末尾位置
                    if window == "left":
                        self.last_position[window] = self.workspace.l_text_area.index("end-1c")
                    else:
                        self.last_position[window] = self.workspace.r_text_area.index("end-1c")
        
        # 设置搜索标志
        flags = 0 if self.case_var.get() else re.IGNORECASE
        
        # 执行搜索
        try:
            # 对于不区分大小写的搜索，我们需要使用re.escape和IGNORECASE
            if self.case_var.get():
                # 区分大小写，直接搜索
                matches = list(re.finditer(search_text, text))
            else:
                # 不区分大小写，转义特殊字符并使用IGNORECASE
                matches = list(re.finditer(re.escape(search_text), text, re.IGNORECASE))
        except re.error:
            # 如果正则表达式有错误，使用简单的字符串搜索
            matches = []
            search_lower = search_text.lower() if not self.case_var.get() else search_text
            text_to_search = text.lower() if not self.case_var.get() else text
            pos = 0
            while True:
                pos = text_to_search.find(search_lower, pos)
                if pos == -1:
                    break
                matches.append(type('obj', (object,), {'start': lambda: pos, 'end': lambda: pos + len(search_text)}))
                pos += 1
        
        if not matches:
            messagebox.showinfo("提示", f"在{'左侧' if target_window == 'left' else '右侧'}窗口找不到 '{search_text}'")
            return
        
        # 找到当前位置之后的匹配项
        last_line, last_col = map(int, current_last_position.split('.'))
        found = False
        
        if direction == 1:
            # 查找下一个
            for match in matches:
                start_line, start_col = self._index_to_line_col(text, match.start())
                # 确保正确比较位置
                if (start_line > last_line) or (start_line == last_line and start_col > last_col):
                    self._highlight_match(text_area, match.start(), match.end())
                    self.last_position[self.current_window] = f"{start_line}.{start_col}"
                    found = True
                    break
            # 如果没找到，从开头重新查找
            if not found and matches:
                match = matches[0]
                self._highlight_match(text_area, match.start(), match.end())
                start_line, start_col = self._index_to_line_col(text, match.start())
                self.last_position[self.current_window] = f"{start_line}.{start_col}"
        else:
            # 查找上一个
            for match in reversed(matches):
                start_line, start_col = self._index_to_line_col(text, match.start())
                # 确保正确比较位置
                if (start_line < last_line) or (start_line == last_line and start_col < last_col):
                    self._highlight_match(text_area, match.start(), match.end())
                    self.last_position[self.current_window] = f"{start_line}.{start_col}"
                    found = True
                    break
            # 如果没找到，从末尾开始查找
            if not found and matches:
                match = matches[-1]
                self._highlight_match(text_area, match.start(), match.end())
                start_line, start_col = self._index_to_line_col(text, match.start())
                self.last_position[self.current_window] = f"{start_line}.{start_col}"
    
    def _index_to_line_col(self, text, index):
        """将字符索引转换为行号和列号"""
        lines = text[:index].split('\n')
        line_num = len(lines)
        col_num = len(lines[-1]) if lines else 0
        return line_num, col_num
    
    def _highlight_match(self, text_area, start, end):
        """高亮显示匹配项并滚动到视图中"""
        # 移除两个文本区域的所有高亮
        self.workspace.l_text_area.tag_remove("search_highlight", "1.0", "end")
        self.workspace.r_text_area.tag_remove("search_highlight", "1.0", "end")
        
        # 计算开始和结束位置
        text = text_area.get("1.0", "end-1c")
        start_line, start_col = self._index_to_line_col(text, start)
        end_line, end_col = self._index_to_line_col(text, end)
        
        # 添加高亮
        text_area.tag_add("search_highlight", f"{start_line}.{start_col}", f"{end_line}.{end_col}")
        text_area.tag_config("search_highlight", background="yellow", foreground="black")
        
        # 滚动到视图中并设置光标位置
        text_area.see(f"{start_line}.{start_col}")
        text_area.mark_set(INSERT, f"{end_line}.{end_col}")
        text_area.focus_set()