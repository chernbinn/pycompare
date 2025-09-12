import os
from tkinter import filedialog, StringVar

class FileSelector:
    # 类变量：缓存上次打开的目录 + 预加载标记
    _last_open_dir = ""
    _is_filedialog_preloaded = False

    @classmethod
    def preload_file_dialog(cls, root):
        """
        【建议在主程序启动后调用一次】
        预加载 filedialog，避免首次弹窗卡顿
        """
        if cls._is_filedialog_preloaded:
            return

        def _preload():
            try:
                # 触发一次轻量级 dialog 初始化
                filedialog.Open(root=root).show()
            except:
                pass
            finally:
                cls._is_filedialog_preloaded = True

        # 延迟执行，避免阻塞启动
        root.after(100, _preload)

    @staticmethod
    def select_file(path_var, root=None):
        """
        弹出文件选择框，并将路径设置到 StringVar
        :param path_var: tkinter.StringVar 实例
        :param root: 主窗口实例（用于 parent 和 after 调度）
        """
        if not isinstance(path_var, StringVar):
            raise TypeError("path_var 必须是 StringVar 类型")

        def _show_dialog():
            try:
                # 使用缓存的上一次目录
                initialdir = FileSelector._last_open_dir or None

                file_path = filedialog.askopenfilename(
                    parent=root,  # ✅ 关键：绑定父窗口，防止层级错乱
                    title="选择文件",
                    initialdir=initialdir,
                    filetypes=[
                        ("所有文件", "*.*"),
                        ("文本文件", "*.txt"),
                        ("Python 文件", "*.py"),
                    ],
                )

                if file_path:
                    # 更新变量
                    path_var.set(file_path)
                    # 缓存目录供下次使用
                    FileSelector._last_open_dir = os.path.dirname(file_path)

            except Exception as e:
                # 防止对话框异常影响主流程
                #logger.error(f"文件选择失败: {e}")
                pass

        # ✅ 使用 after 调度，让当前事件循环先完成，避免卡顿
        if root:
            root.after(10, _show_dialog)
        else:
            _show_dialog()  # fallback