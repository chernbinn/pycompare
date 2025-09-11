import queue
import threading
from tkinter import *
from tkinter import ttk
import tkinter.messagebox as messagebox

from pycompare.workspace.editor import Editor
from pycompare.compare_core.compare_core import (
    compare_files, MatcherConfig, mySequenceMatcher
)
from pycompare.workspace.events_queue import (
    group_event_decorator,
    clear_event_queue
)
from pycompare.config import MERGE_TAG_LOG, JUNK_STR_PATTERN

import logging
from pycompare.logging_config import setup_logging
logger = setup_logging(logging.DEBUG, log_tag=__name__)

class Workspace:
    def __init__(self, root, statusvar):
        self.is_refreshing = False
        self.root = root
        self.refresh_queue = queue.Queue()
        self.statusvar = statusvar
        #++++++++++++++++++++++++++++
        # 文件对比操作区
        #++++++++++++++++++++++++++++        
        workspace = Frame(root)
        workspace.pack(side=TOP, fill=BOTH, expand=True)
        openORsave = Frame(workspace)
        openORsave.pack(side=TOP, fill=X)
        text_frame = Frame(workspace)
        text_frame.pack(side=TOP, fill=BOTH, expand=True)
        
        # 文件选择
        l_path_var = StringVar()
        l_pathbox = ttk.Combobox(openORsave, textvariable=l_path_var)
        #l_pathbox['values'] = []
        #l_pathbox.bind('<Return>', lambda *args: update_history(l_path_var, l_pathbox))
        l_select_button = ttk.Button(openORsave, text="选择文件")
        l_save_button = ttk.Button(openORsave, text="保存文件")
        x_pos = 0
        l_pathbox.grid(column=x_pos, row=0, pady=10, padx=5, sticky="we")
        openORsave.columnconfigure(x_pos, weight=1)
        x_pos += 1
        l_select_button.grid(column=x_pos, row=0)
        x_pos += 1
        l_save_button.grid(column=x_pos, row=0)
        x_pos += 1
        
        r_path_var = StringVar()
        r_pathbox = ttk.Combobox(openORsave, textvariable=r_path_var)
        #r_pathbox['values'] = []
        #r_pathbox.bind('<Return>', lambda *args: update_history(r_path_var, r_pathbox))
        r_select_button = ttk.Button(openORsave, text="选择文件")
        r_save_button = ttk.Button(openORsave, text="保存文件")
        r_pathbox.grid(column=x_pos, row=0, pady=10, padx=5, sticky="we")
        openORsave.columnconfigure(x_pos, weight=1)
        x_pos += 1
        r_select_button.grid(column=x_pos, row=0)
        x_pos += 1
        r_save_button.grid(column=x_pos, row=0)
        x_pos += 1

        # 左侧文件显示区域
        l_line_numbers = Text(text_frame, width=4, padx=5, takefocus=0, 
                                border=1, background='lightgrey', cursor='arrow')
        l_line_numbers.grid(row=0, column=0, sticky=NS)
        
        lfl = Text(text_frame, width=6, padx=5, takefocus=0,
                                border=1, background='lightgrey', cursor='arrow')
        lfl.grid(row=0, column=1, sticky=NS)

        l_text_area = Text(text_frame, wrap=NONE, undo=True, border=1)
        l_text_area.grid(row=0, column=2, sticky=NSEW)
        
        # 右侧文件显示区域
        r_line_numbers = Text(text_frame, width=4, padx=5, takefocus=0,
                                border=1, background='lightgrey', cursor='arrow')
        r_line_numbers.grid(row=0, column=4, sticky=NS)

        rfl = Text(text_frame, width=6, padx=5, takefocus=0, 
                                border=1, background='lightgrey', cursor='arrow')
        rfl.grid(row=0, column=5, sticky=NS)

        r_text_area = Text(text_frame, wrap=NONE, undo=True, border=1)
        r_text_area.grid(row=0, column=6, sticky=NSEW)

        # 滚动配置
        scroll_ya = ttk.Scrollbar(text_frame, orient=VERTICAL,
                command=lambda *args:self.sync_scroll(
                    l_text_area, r_text_area, l_line_numbers, r_line_numbers, lfl, rfl, *args))
        scroll_ya.grid(row=0, column=3, sticky=NS)
        scroll_yb = ttk.Scrollbar(text_frame, orient=VERTICAL,
                command=lambda *args: self.sync_scroll(
                    l_text_area, r_text_area, l_line_numbers, r_line_numbers, lfl, rfl, *args))
        scroll_yb.grid(row=0, column=7, sticky=NS)

        l_text_area.config(yscrollcommand=lambda *args:self.on_text_scroll(scroll_ya, scroll_yb,
                     l_text_area, r_text_area, l_line_numbers, r_line_numbers, lfl, rfl, *args))
        r_text_area.config(yscrollcommand=lambda *args:self.on_text_scroll(scroll_ya, scroll_yb,
                     l_text_area, r_text_area, l_line_numbers, r_line_numbers, lfl, rfl, *args))
        l_line_numbers.config(yscrollcommand=lambda *args:self.on_text_scroll(scroll_ya, scroll_yb,
                     l_text_area, r_text_area, l_line_numbers, r_line_numbers, lfl, rfl, *args))
        r_line_numbers.config(yscrollcommand=lambda *args:self.on_text_scroll(scroll_ya, scroll_yb,
                     l_text_area, r_text_area, l_line_numbers, r_line_numbers, lfl, rfl, *args))
        lfl.config(yscrollcommand=lambda *args:self.on_text_scroll(scroll_ya, scroll_yb, l_text_area, r_text_area, 
                        l_line_numbers, r_line_numbers, lfl, rfl, *args))
        rfl.config(yscrollcommand=lambda *args:self.on_text_scroll(scroll_ya, scroll_yb, l_text_area,r_text_area, 
                        l_line_numbers, r_line_numbers, lfl, rfl, *args))

        scroll_xa = ttk.Scrollbar(text_frame, orient=HORIZONTAL, 
                command=lambda *args:self.sync_scroll_x(l_text_area, r_text_area, *args))
        scroll_xa.grid(row=1, column=2, sticky=EW)
        scroll_xb = ttk.Scrollbar(text_frame, orient=HORIZONTAL, 
                command=lambda *args:self.sync_scroll_x(l_text_area, r_text_area, *args))
        scroll_xb.grid(row=1, column=6, sticky=EW)
        
        l_text_area.config(xscrollcommand=lambda *args: self.on_text_scroll_x(
            scroll_xa, scroll_xb, l_text_area, r_text_area, *args))
        r_text_area.config(xscrollcommand=lambda *args: self.on_text_scroll_x(
            scroll_xa, scroll_xb, l_text_area, r_text_area, *args))

        # 配置网格布局
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(2, weight=1)
        text_frame.grid_columnconfigure(6, weight=1)
        # 文件对比操作区 end

        # 配置显示样式
        Editor.configure_tags(l_text_area)
        Editor.configure_tags(r_text_area)

        # 绑定事件
        l_args = {
            'tagpathvar': r_path_var,
            'tagarea': r_text_area, 
            'textlines': l_line_numbers, 
            'taglines': r_line_numbers,
            'textflines': lfl,
            'tagflines': rfl,
            'modified': 'left'
        }
        l_select_button.bind('<Button-1>', lambda *args: Editor.select_file(l_path_var, openORsave))
        l_path_var.trace_add('write', lambda *args: Editor.load_file(l_path_var, l_text_area, l_pathbox, l_args))
        r_args = {
            'tagpathvar': l_path_var,
            'tagarea': l_text_area, 
            'textlines': r_line_numbers, 
            'taglines': l_line_numbers,
            'textflines': rfl,
            'tagflines': lfl,
            'modified': 'right'
        }
        r_select_button.bind('<Button-1>', lambda *args: Editor.select_file(r_path_var, openORsave))
        r_path_var.trace_add('write', lambda *args: Editor.load_file(r_path_var, r_text_area, r_pathbox, r_args))

        l_save_button.bind('<Button-1>', lambda *args: Editor.save_file(l_path_var, l_text_area))
        r_save_button.bind('<Button-1>', lambda *args: Editor.save_file(r_path_var, r_text_area))
        
        argsdict = {
            'tagarea': r_text_area, 
            'textlines': l_line_numbers,
            'taglines': r_line_numbers,
            'textflines': lfl,
            'tagflines': rfl,
            'statusbar': self.statusvar,
            'modified': 'left'
        }
        Editor.text_area_bind(l_text_area, argsdict)
        argsdict = {
            'tagarea': l_text_area, 
            'textlines': r_line_numbers,
            'taglines': l_line_numbers,
            'textflines': rfl,
            'tagflines': lfl,
            'statusbar': self.statusvar,
            'modified': 'right'
        }
        Editor.text_area_bind(r_text_area, argsdict)
        l_text_area.__dict__['__eventqueue'] = queue.LifoQueue()
        r_text_area.__dict__['__eventqueue'] = queue.LifoQueue()

        argsdict = {
            'textarea': l_text_area,
            'tagarea': r_text_area, 
            'textlines': l_line_numbers,
            'taglines': r_line_numbers,
            'textflines': lfl,
            'tagflines': rfl,
            'workspace': self
        }
        l_text_area.bind('<F5>', lambda event: self.refresh_compare_F5(None, event, argsdict))
        r_text_area.bind('<F5>', lambda event: self.refresh_compare_F5(None, event, argsdict))

        self.__dict__['__argsdict'] = argsdict
        Editor.initialize(openORsave, l_text_area)
        Editor.initialize(openORsave, r_text_area)

    @staticmethod
    def sync_scroll(text_a, text_b, line_num_a, line_num_b, fl_a, fl_b, *args):
            """同步滚动两个Text组件"""
            text_a.yview(*args)
            text_b.yview(*args)
            line_num_a.yview(*args)
            line_num_b.yview(*args)
            fl_a.yview(*args)
            fl_b.yview(*args)

    @staticmethod
    def on_text_scroll(scroll_ya, scroll_yb, text_a, text_b, line_num_a, line_num_b, fla, flb, *args):
        """当Text组件滚动时调用此方法来更新滚动条的位置"""
        scroll_ya.set(*args)
        scroll_yb.set(*args)
        Workspace.sync_scroll(text_a, text_b, line_num_a, line_num_b, fla, flb, 'moveto', args[0])
    
    @staticmethod
    def sync_scroll_x(text_a, text_b, *args):
        """同步滚动两个Text组件"""
        text_a.xview(*args)
        text_b.xview(*args)

    @staticmethod
    def on_text_scroll_x(scroll_xa, scroll_xb, text_a, text_b, *args):
        """当Text组件滚动时调用此方法来更新滚动条的位置"""
        scroll_xa.set(*args)
        scroll_xb.set(*args)
        Workspace.sync_scroll_x(text_a, text_b, 'moveto', args[0])

    @staticmethod
    def create_fileline_handler(lfl=None, rfl=None, start: int = 1):
        fl = lfl if lfl else rfl
        arrow = '\u27A1' if lfl else '\u2B05'
        direction = "左" if lfl else "右"
        merge_tag_count = len(set(fl.tag_names()))
        
        act_num = 0
        has_arrow = False
        has_closed = False
        pre_tag = None
        pre_line = None
        block_start = None
        block_end = None
        
        def judge_tag(flvalue):
            tag = set()
            ltag = flvalue[0:2].strip()
            if '|' not in ltag and '|_' not in ltag and arrow not in ltag:
                tag.update('equalline')
            elif '|_' in ltag:
                tag.update("closedline")
            elif arrow in ltag:
                tag.update("arrowline")
            num = re.sub(r'[^\d]', '', flvalue)
            if len(num) == 0:
                tag.update('spacesimage')
            return tag
            
        def get_merge_tag(line):
            pattern = re.compile("^merge\d+$")
            linetags = set(fl.tag_names(f'{line}.0') + fl.tag_names(f'{line}.end'))
            linetag = [s for s in linetags if pattern.fullmatch(s)]
            logger.debug(f"{line}行linetags: {linetags} linetag: {linetag}")
            if len(linetag) > 0:
                merge_tag = linetag[0]
                start, end = fl.tag_ranges(merge_tag)
                return merge_tag, start, end
            return None, None, None
        
        def init(start):
            nonlocal pre_line, has_arrow, act_num, block_start, pre_tag
            start -= 1
            fl.config(state="normal")
            found_block_start = False
            for i in range(start, 0, -1):
                flvalue = fl.get(f"{i}.0", f"{i}.end")
                if act_num == 0:
                    num = re.sub(r'[^\d]', '', flvalue)
                    num = int(num) if len(num)>0 else 0
                    if num > 0:
                        act_num = num
                
                if not found_block_start:
                    tags = judge_tag(flvalue)
                    if 'equalline' in tags:
                        found_block_start = True
                    elif 'closedline' in tags:
                        merge_tag, block_start, tmp = get_merge_tag(i)
                        logger.debug(f"{i}行merge_tag: {merge_tag} block_start: {block_start}")
                        fl.tag_delete(merge_tag)
                        fl.delete(f"{i}.0", f"{i}.end")
                        pre_tag = 'openline'
                        pre_line = i
                        has_arrow = True
                        found_block_start = True
                        if act_num > 0 and i == start: act_num -= 1
                    elif 'arrowline' in tags:
                        has_arrow = True
                        block_start = f"{i}.0"
                        found_block_start = True
                        
                if act_num > 0 and found_block_start:
                    break
            fl.config(state="disabled")
        init(start)

        logger.debug(f"start: {start} act_num: {act_num} merge_tag_count: {merge_tag_count}")
        logger.debug(f"has_arrow: {has_arrow} pre_tag: {pre_tag} pre_line: {pre_line} block_start: {block_start}")

        def handle_non_modify(start_line, hand_op_func, *args):
            nonlocal block_end, has_closed
            max_line = args[0]
            begin = start_line
            need_change_num = True
            need_change_tag = True
            found_arrow_count = 0
            lnum = act_num
            end_line = 0
            
            for i in range(begin, max_line+1):
                flvalue = fl.get(f"{i}.0", f"{i}.end")
                if need_change_num:
                    num = re.sub(r'[^\d]', '', flvalue)
                    if len(num) > 0:
                        num = int(num)
                        if (lnum+1) == num:
                            need_change_num = False
                        else:
                            #logger.debug(f"(lnum+1-num): {lnum+1-num}")
                            lnum += 1
                            new_flvalue = f"{flvalue[0:2]}{lnum}"
                            fl.replace(f'{i}.0', f'{i}.end', new_flvalue)
                            
                if need_change_tag:
                    tags = judge_tag(flvalue)
                    if 'arrowline' in tags:
                        found_arrow_count = 1
                        merge_tag, tmp, block_end = get_merge_tag(i)
                        logger.debug(f"{i}行merge_tag: {merge_tag} block_end: {block_end}")
                        if merge_tag: fl.tag_delete(merge_tag)
                        fl.delete(f"{i}.0", f"{i}.end")
                        
                        if 'spacesimage' in tags:
                            hand_op_func(i, 'spacesimage')
                        else: hand_op_func(i, 'othertag')
                    elif found_arrow_count == 1:
                        need_change_tag = False
                        if 'equalline' not in tags: has_closed = True
                        hand_op_func(i, 'equalline')
                        hand_op_func(i+1, 'endline')
                    elif 'equalline' in tags:
                        block_end = f"{i-1}.end"
                        if i != begin: has_closed = True
                        need_change_tag = False
                        hand_op_func(begin, 'equalline')
                        hand_op_func(begin+1, 'endline')
                if not need_change_num and not need_change_tag:
                    end_line = i
                    break
            hand_op_func(end_line, 'endline')
                    
        def generate_file_numbers(line: int, tag, *args):
            nonlocal pre_line, has_arrow, has_closed, act_num, block_start, block_end, pre_tag, merge_tag_count
            
            if tag == 'continue':
                handle_non_modify(line, generate_file_numbers, *args)
                
            if MERGE_TAG_LOG:
                logger.debug("------------")
                logger.debug(f"{direction}--line: {line} tag: {tag} act_num: {act_num} pre_tag: {pre_tag} has_arrow: {has_arrow}")
                
            if not pre_line:
                pre_line = line
                pre_tag = tag
                return

            if tag == 'equalline' and pre_tag != 'equalline':
                if has_arrow:
                    if not has_closed:
                        pre_str = '|_'
                        has_closed = True
                    if block_end == None: block_end = f"{pre_line}.end"
                else:
                    pre_str = arrow
                    block_start = f"{pre_line}.0"
                    if block_end == None: block_end = f"{pre_line}.end"
                    has_arrow = True
                    has_closed = True
            elif pre_tag == 'equalline':
                pre_str = '  '
            else:
                if has_arrow:
                    pre_str = '| '
                else:
                    pre_str = arrow
                    block_start = f"{pre_line}.0"
                    has_arrow = True
                    
            if pre_tag != 'spacesimage': 
                act_num += 1
                end_str = f"{act_num}\n"
            else:
                end_str = f" \n"

            if MERGE_TAG_LOG:
                logger.debug(f"{pre_line}.0 insert: {repr(pre_str)}{repr(end_str)}")
                
            fl.config(state='normal')
            if tag != 'endline':
                if arrow in pre_str:
                    fl.insert(f"{pre_line}.0", f"{pre_str}{end_str}", "arrow_merge")
                    #insert_and_tags(fl, f"{pre_line}.0", f"{pre_str}{end_str}", "arrow_merge")
                else:
                    fl.insert(f"{pre_line}.0", f"{pre_str}{end_str}")
                    #insert_and_tags(fl, f"{pre_line}.0", f"{pre_str}{end_str}")
            
            if MERGE_TAG_LOG:
                logger.debug(f"has_arrow: {has_arrow} has_closed: {has_closed}")
                
            if tag == 'equalline' and has_arrow and has_closed:
                has_closed = False
                has_arrow = False
                block_end = None
                merge_tag_count += 1
                merge_tag = f"merge{merge_tag_count}"
                if MERGE_TAG_LOG:
                    logger.debug(f"merge_tag: {merge_tag} block_start: {block_start} block_end: {block_end}")
                fl.tag_add(merge_tag, block_start, block_end)
            elif tag == 'endline':
                cursor = fl.index(INSERT)
                fl.delete(cursor)
                
            pre_line = line
            pre_tag = tag
            
            fl.config(state='disabled')
            
        return generate_file_numbers

    @staticmethod
    def refresh_compare_F5(text_area, event, argsdict):
        logger.debug(f"refresh 事件触发")
        workspace_instance = argsdict.get('workspace')  # 确保传入了 workspace 实例
        if workspace_instance.is_refreshing:
            logger.debug("刷新对比已在进行中，忽略重复触发")
            return

        text_area = argsdict.get("textarea")
        tag_area = argsdict.get("tagarea")
        text_line_numbers = argsdict.get('textlines')
        tag_line_numbers = argsdict.get('taglines')
        lfl = argsdict.get('textflines', None)
        rfl = argsdict.get('tagflines', None)

        """
        lmodified = False
        if 'modified' in text_area.tag_names():
            lmodified = True
            text_area.tag_delete('modified')

        rmodified = False
        if 'modified' in tag_area.tag_names():
            rmodified = True
            tag_area.tag_delete('modified')
        if lmodified and rmodified:
            msg = "两边文件都有修改，请先保存"
        elif lmodified:
            msg = "左边文件有修改，请先保存"
        elif rmodified:
            msg = "右边文件有修改，请先保存"
        
        if lmodified or rmodified:
            messagebox.showinfo(
                title='保存文件提示',
                message=msg
            )
        """        
        if workspace_instance:
            workspace_instance.start_async_refresh(
                text_area=text_area,
                tag_area=tag_area,
                text_line_numbers=text_line_numbers,
                tag_line_numbers=tag_line_numbers,
                lfl=lfl, rfl=rfl
            )

    def start_async_refresh(self, text_area, tag_area, text_line_numbers, tag_line_numbers, lfl, rfl):
        """启动异步刷新任务"""
        if self.is_refreshing:
            return  # 防止重复执行

        self.is_refreshing = True
        self.statusvar.set("正在刷新对比...")

        # === 主线程：更新 UI 表示正在刷新 ===
        for widget in [text_area, tag_area]:
            widget.config(cursor="wait")
        self.root.update_idletasks()
        
        # 可选：禁用某些控件
        for widget in [text_area, tag_area]:
            if hasattr(widget, 'config'):
                widget.config(state='disabled')

        # 清除旧事件（可在主线程快速完成）
        clear_event_queue(text_area.__dict__.get('__eventqueue'))
        clear_event_queue(tag_area.__dict__.get('__eventqueue'))        

        # 获取文本内容（也可以放子线程）
        left_content = Editor.get_area(text_area)
        right_content = Editor.get_area(tag_area)

        # === 子线程执行耗时操作 ===
        def worker():
            try:
                # 执行耗时的对比逻辑
                logger.debug("后台线程开始执行 compare_files")
                match_pairs = compare_files(left_content, right_content)

                # 成功后将结果放入队列
                self.refresh_queue.put({
                    'status': 'success',
                    'data': {
                        'match_pairs': match_pairs,
                        'left_content': left_content,
                        'right_content': right_content,
                        'widgets': (text_area, tag_area, text_line_numbers, tag_line_numbers, lfl, rfl)
                    }
                })
            except Exception as e:
                import traceback
                error_msg = traceback.format_exc()
                self.refresh_queue.put({
                    'status': 'error',
                    'data': str(e),
                    'traceback': error_msg,
                    'widgets': (text_area, tag_area, text_line_numbers, tag_line_numbers, lfl, rfl)
                })

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        # 启动轮询检查结果
        self.poll_refresh_result()

    def poll_refresh_result(self):
        """检查子线程是否返回结果"""
        try:
            while self.is_refreshing:
                result = self.refresh_queue.get_nowait()
                self.handle_refresh_result(result)
        except:
            # 队列为空，继续等待
            if self.is_refreshing:
                self.root.after(50, self.poll_refresh_result)  # 每 50ms 检查一次

    def handle_refresh_result(self, result):
        """处理刷新结果（在主线程执行）"""
        self.statusvar.set("对比刷新完成")
        self.is_refreshing = False
        self.root.config(cursor="")  # 恢复光标

        text_area, tag_area, text_line_numbers, tag_line_numbers, lfl, rfl = \
            result['data']['widgets']

        # 回复子空间光标
        for widget in [text_area, tag_area]:
            widget.config(cursor="")
        self.root.update_idletasks()

        # 恢复文本框可用状态
        for widget in [text_area, tag_area]:
            if hasattr(widget, 'config'):
                widget.config(state='normal')

        if result['status'] == 'success':
            data = result['data']

            # 重置行号显示（轻量级操作，可放主线程）
            Editor.line_number_reset(text_line_numbers)
            Editor.line_number_reset(tag_line_numbers)
            Editor.line_number_reset(lfl)
            Editor.line_number_reset(rfl)
            
            # 重置文本区域（主线程）
            Editor.text_area_reset(text_area)
            Editor.text_area_reset(tag_area)
            text_area.tag_delete(*text_area.tag_names())
            tag_area.tag_delete(*tag_area.tag_names())

            Editor.configure_tags(text_area)
            Editor.configure_tags(tag_area)

            # 显示结果（确保此方法是线程安全的，通常它是）
            Workspace.display_results(
                text_area, tag_area,
                data['left_content'], data['right_content'],
                data['match_pairs'], lfl, rfl
            )

            # 更新行号
            Editor.update_line_numbers(text_area, text_line_numbers, tag_line_numbers)

            logger.debug("异步刷新完成")
        else:
            logger.error(f"刷新失败: {result['data']}\n{result.get('traceback', '')}")
            messagebox.showerror("刷新错误", f"刷新失败：{result['data']}")

    """
    left_text_area: 被修改区域text控件
    right_text_area: 未被修改区域text控件
    lines1：left_text_area区域内容，按行记录
    lines2：right_text_area区域内容，按行记录
    match_pairs：对比算法（compare_files）对比内容后返回的结果
    lfl: 显示左边区域文件内容实际行数及合并标记的控件
    lfl: 显示右边区域文件内容实际行数及合并标记的控件
    start_line：在text控件中开始插入的行。控件的行数从1开始计数
    """
    @staticmethod
    def display_results(left_text_area, right_text_area, lines1, lines2, match_pairs, 
                        lfl, rfl, start_line=1):
        """在 GUI 中显示对比结果"""
        # 初始化行号
        left_line = 0
        right_line = 0
        area_line = start_line

        lfl_func = Workspace.create_fileline_handler(lfl, None, start_line)
        rfl_func = Workspace.create_fileline_handler(None, rfl, start_line)
        
        for pair in match_pairs:
            # 处理未匹配的行
            while left_line < pair[0]:
                left_text_area.insert(f"{area_line}.0", lines1[left_line], ("uniqline", "textcontent"))
                #left_text_area.tag_add('uniqline', f'{area_line}.0', f"{area_line}.end")
                #left_text_area.tag_add('textcontent', f'{area_line}.0', f"{area_line}.end")
                lfl_func(area_line, "textcontent")

                right_text_area.insert(f"{area_line}.0", "\n", ("uniqline", "spacesimage"))
                #right_text_area.tag_add('uniqline', f'{area_line}.0', f"{area_line}.end")
                #right_text_area.tag_add('spacesimage', f'{area_line}.0', f"{area_line}.end")
                rfl_func(area_line, "spacesimage")
                
                left_line += 1
                area_line += 1
                
            while right_line < pair[1]:
                left_text_area.insert(f"{area_line}.0", "\n", ("uniqline", "spacesimage"))
                #left_text_area.tag_add('uniqline', f'{area_line}.0', f"{area_line}.end")
                #left_text_area.tag_add('spacesimage', f'{area_line}.0', f"{area_line}.end")
                lfl_func(area_line, "spacesimage")
                
                right_text_area.insert(f"{area_line}.0", lines2[right_line], ("uniqline", "textcontent"))
                #right_text_area.tag_add('uniqline', f'{area_line}.0', f"{area_line}.end")
                #right_text_area.tag_add('textcontent', f'{area_line}.0', f"{area_line}.end")
                rfl_func(area_line, "textcontent")
                
                right_line += 1
                area_line += 1

            # 处理匹配的行
            left_line_text = lines1[left_line]
            right_line_text = lines2[right_line]
            match_ratio = pair[5]  # 匹配度

            if abs(match_ratio-MatcherConfig.SCALE) > MatcherConfig.MIN_RATIO:
                # 提取不同字符并标记为红色
                matcher = mySequenceMatcher(lambda c: c in set(JUNK_STR_PATTERN) , left_line_text, right_line_text, process=False)
                left_diff_indices = []
                right_diff_indices = []

                for tag in matcher.get_opcodes():
                    op, i1, i2, j1, j2 = tag
                    if op == 'replace' or op == 'delete':
                        left_diff_indices.append((i1, i2))
                    if op == 'replace' or op == 'insert':
                        right_diff_indices.append((j1, j2))
                
                if repr(left_line_text) == repr('\n'):
                    left_text_area.insert(f"{area_line}.0", "\n", ("somematch"))
                else:
                    # 插入左侧文本，标记不同字符为红色
                    left_start = 0
                    index = f"{area_line}.0"
                    for start, end in left_diff_indices:
                        left_text_area.insert(index, left_line_text[left_start:start], 'somematch')
                        left_text_area.insert(f"{area_line}.{start}", left_line_text[start:end], ('somematch', "linediffer"))
                        left_start = end
                        index = f"{area_line}.{end}"
                    left_text_area.insert(f"{area_line}.{left_start}", left_line_text[left_start:], 'somematch')
                #left_text_area.tag_add('somematch', f'{area_line}.0', f"{area_line}.end")
                lfl_func(area_line, "somematch")
                
                if repr(right_line_text) == repr('\n'):
                    right_text_area.insert(f"{area_line}.0", "\n", ("somematch"))
                else:
                    # 插入右侧文本，标记不同字符为红色
                    right_start = 0
                    index = f"{area_line}.0"
                    for start, end in right_diff_indices:
                        right_text_area.insert(index, right_line_text[right_start:start], 'somematch')
                        right_text_area.insert(f"{area_line}.{start}", right_line_text[start:end], ('somematch', "linediffer"))
                        right_start = end
                        index = f"{area_line}.{end}"
                    right_text_area.insert(f"{area_line}.{right_start}", right_line_text[right_start:], 'somematch')
                #right_text_area.tag_add('somematch', f'{area_line}.0', f"{area_line}.end")
                rfl_func(area_line, "somematch")

            else:
                # 完全匹配的行
                left_text_area.insert(f"{area_line}.0", left_line_text, ('equalline'))
                #left_text_area.tag_add('equalline', f'{area_line}.0', f"{area_line}.end")
                lfl_func(area_line, "equalline")
                
                right_text_area.insert(f"{area_line}.0", right_line_text, ('equalline'))
                #right_text_area.tag_add('equalline', f'{area_line}.0', f"{area_line}.end")
                rfl_func(area_line, "equalline")

            left_line += 1
            right_line += 1
            area_line += 1

        # 处理剩余未匹配的行
        while left_line < len(lines1):
            left_text_area.insert(f"{area_line}.0", lines1[left_line], ("uniqline", "textcontent"))
            #left_text_area.tag_add('uniqline', f'{area_line}.0', f"{area_line}.end")
            #left_text_area.tag_add('textcontent', f'{area_line}.0', f"{area_line}.end")
            lfl_func(area_line, "textcontent")
            
            right_text_area.insert(f"{area_line}.0", "\n", ("uniqline", "spacesimage"))
            #right_text_area.tag_add('uniqline', f'{area_line}.0', f"{area_line}.end")
            #right_text_area.tag_add('spacesimage', f'{area_line}.0', f"{area_line}.end")
            rfl_func(area_line, "spacesimage")
            
            left_line += 1
            area_line += 1
        while right_line < len(lines2):
            left_text_area.insert(f"{area_line}.0", "\n", ("uniqline", "spacesimage"))
            #left_text_area.tag_add('uniqline', f'{area_line}.0', f"{area_line}.end")
            #left_text_area.tag_add('spacesimage', f'{area_line}.0', f"{area_line}.end")
            lfl_func(area_line, "spacesimage")
            
            right_text_area.insert(f"{area_line}.0", lines2[right_line], ("uniqline", "textcontent"))
            #right_text_area.tag_add('uniqline', f'{area_line}.0', f"{area_line}.end")
            #right_text_area.tag_add('textcontent', f'{area_line}.0', f"{area_line}.end")
            rfl_func(area_line, "textcontent")
            
            right_line += 1
            area_line += 1
        
        end_line = int(right_text_area.index('end-1c').split('.')[0])
        logger.debug(f"++++end_line: {end_line} area_line: {area_line}+++")
        if area_line == end_line:
            lfl_func(area_line, "equalline")
            rfl_func(area_line, "equalline")
            lfl_func(area_line+1, "endline")
            rfl_func(area_line+1, "endline")
        else:
            newlins = area_line-start_line
            lfl_func(area_line, "continue", end_line)
            rfl_func(area_line, "continue", end_line)

