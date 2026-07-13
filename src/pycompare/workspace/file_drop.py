
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
        处理文件拖放事件（单文件）
        """
        data = event.data
        # logger.info(f"Received drop event: {data}")

        # 去除首尾的花括号（如果有）
        if data.startswith('{') and data.endswith('}'):
            file_path = data[1:-1]
        else:
            file_path = data

        # 去除可能存在的引号（有时路径会被引号包裹）
        file_path = file_path.strip('"').strip("'")

        # logger.info(f"Extracted file path: {file_path}")

        # 清空文本框，显示新路径
        self.text_area.delete('1.0', 'end')
        self.text_area.insert('end', file_path)

        # 更新路径变量（触发外部显示）
        self.path_var.set(file_path)