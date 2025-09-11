
class FileDrop:
    def __init__(self, root, text_area, path_var):
        self.root = root
        self.text_area = text_area
        self.path_var = path_var

    def on_drag_enter(self, event):
        """鼠标进入文本框时的反馈"""
        self.text_area.configure(highlightbackground="blue", highlightthickness=2)
        # print("进入拖拽区域")

    def on_drag_leave(self, event):
        """鼠标离开时恢复样式"""
        self.text_area.configure(highlightbackground="gray", highlightthickness=2)

    def on_drop(self, event):
        """
        处理文件拖放事件
        event.data 是一个花括号包围的字符串，如 {C:/path/to/file.txt}
        """
        # 获取拖入的数据
        data = event.data

        # 清理数据：去除大括号和引号
        if data.startswith('{') and data.endswith('}'):
            file_paths = data[1:-1]  # 去掉首尾 {}
            # 分割多个文件（如果有空格或换行）
            paths = file_paths.split()
        else:
            paths = [data]

        # 插入到文本框
        for path in paths:
            self.text_area.insert('end', path + '\n')

        # 恢复样式
        #self.on_drag_leave(None)
        # 设置文件路径，触发显示文件内容
        self.path_var.set(paths[0])