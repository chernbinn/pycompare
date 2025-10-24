from tkinter import *
from tkinter import messagebox
from tkinter import filedialog
from pycompare.workspace.events_queue import (
    group_event_decorator,
    update_cursor_position,
    set_event_group
)
from pycompare.workspace.file_selector import FileSelector
from pycompare.config import QUEUE_EVENT_LOG, DEBUG_TAG, GET_AREA_LOG

import logging
from pycompare.logging_config import setup_logging
logger = setup_logging(logging.DEBUG, log_tag=__name__)

TEXT_CONTENT_TAG = set(['equalline', 'somematch', 'linediffer', 
                    'uniqline', 'textcontent', 'spacesimage', 
                    'invalidfilltext', 'newline'])

class Editor:
    class EditorEvent:
        # 定义事件处理函数
        @staticmethod
        # @group_event_decorator(event_type="selection", debounce_time=0, isbreak=True)
        def on_selection(text_area, event, argsdict):
            if QUEUE_EVENT_LOG: logger.debug("Selection事件触发")
            b_remove_selected_tag = False
            try:
                start_index = text_area.index("sel.first")
                end_index = text_area.index("sel.last")
                if end_index == text_area.index("end"):
                    logger.debug(f"end_index: {end_index} equal end")
                    end_index = text_area.index("end-2 lines lineend")
                    # 移除默认选中的默认颜色标记
                    text_area.tag_remove("sel", end_index, "end")

                if QUEUE_EVENT_LOG:
                    selected_text = text_area.get("sel.first", "sel.last")
                    length = len(selected_text)
                    logger.debug(f"起始位置: {start_index}, 结束位置: {end_index}, 长度: {length} 字符")
                    logger.debug(f"选中的文本: '{selected_text}'")
                
                text_area.tag_remove("selected_text", '1.0', 'end')
                text_area.tag_add("selected_text", start_index, end_index)
                
                event_data = { }
                b_remove_selected_tag = start_index == end_index
                
            except Exception as e:
                #logger.error(f"Exception: {e}")
                b_remove_selected_tag = True

            if b_remove_selected_tag:
                text_area.tag_remove("selected_text", '1.0', 'end')
                event_data = None

            # 如果使用group_event_decorator，需要返回event_data
            #return event_data
            return "break"

        @staticmethod
        def on_copy(event, text_area):
            """处理复制操作，对内容进行过滤后放入剪贴板"""
            if QUEUE_EVENT_LOG: logger.debug("Copy事件触发")
            try:
                # 获取选中的文本范围
                start_index = text_area.index("sel.first")
                end_index = text_area.index("sel.last")
                
                # 过滤文本内容 - 移除不需要的字符或标签相关内容
                # filtered_text = Editor._filter_text_for_clipboard(text_area, start_index, end_index)
                filtered_text = Editor.get_area(text_area, start_index, end_index)
                #logger.debug(f"filtered_text lists:\n {filtered_text}")
                filtered_text = "".join(filtered_text)
                #logger.debug(f"filtered_text:\n {filtered_text}")
                
                # 将过滤后的文本放入剪贴板
                text_area.clipboard_clear()
                text_area.clipboard_append(filtered_text)
                
                # 阻止默认的复制行为
                return "break"
            except Exception as e:
                logger.error(f"复制操作失败: {e}")
                # 如果出错，让默认的复制行为继续
                return None

        @staticmethod
        def on_cut(event, text_area):
            """处理剪切操作，对内容进行过滤后放入剪贴板并删除原内容"""
            if QUEUE_EVENT_LOG: logger.debug("Cut事件触发")
            try:
                # 获取选中的文本范围
                start_index = text_area.index("sel.first")
                end_index = text_area.index("sel.last")
                
                # 过滤文本内容
                # filtered_text = Editor._filter_text_for_clipboard(text_area, start_index, end_index)
                filtered_text = Editor.get_area(text_area, start_index, end_index)
                filtered_text = "".join(filtered_text)

                # 将过滤后的文本放入剪贴板
                text_area.clipboard_clear()
                text_area.clipboard_append(filtered_text)
                
                # 删除选中的内容
                text_area.delete(start_index, end_index)
                
                # 阻止默认的剪切行为
                return "break"
            except Exception as e:
                logger.error(f"剪切操作失败: {e}")
                # 如果出错，让默认的剪切行为继续
                return None

        @staticmethod
        def on_compare_end(text_area, event, argsdict):
            logger.debug(f"compareend 事件触发")

            tag_area = argsdict.get('tagarea')
            lln = argsdict.get('textlines')
            rln = argsdict.get('taglines')
            lfl = argsdict.get('textflines')
            rfl = argsdict.get('tagflines')

            for area in [text_area, tag_area]:
                area.__dict__['__modifiedCT'] = 0
            
            maxtextline =  int(text_area.index('end').split('.')[0])
            maxtagline = int(tag_area.index('end').split('.')[0])
            maxlln = int(lln.index('end').split('.')[0])
            maxrln = int(rln.index('end').split('.')[0])
            maxlfl = int(lfl.index('end').split('.')[0])
            maxrfl = int(rfl.index('end').split('.')[0])

            #logger.debug(f"text_area.tag_ranges('invalidfilltext'): {text_area.tag_ranges('invalidfilltext')}")
            #logger.debug(f"tag_area.tag_ranges('invalidfilltext'): {tag_area.tag_ranges('invalidfilltext')}")

            if False: #MODIFY_REVIEW_LOG:
                messagebox.showerror(title="错误", message="对比结果显示行数不一致")

            logger.debug("----------------")
            logger.debug(f"on_compare_end--l_text_area.index('end'): {maxtextline}")
            logger.debug(f"on_compare_end--r_text_area.index('end'): {maxtagline}")
            logger.debug(f"on_compare_end--l_line_numbers.index('end'): {maxlln}")
            logger.debug(f"on_compare_end--r_line_numbers.index('end'): {maxrln}")
            logger.debug(f"on_compare_end--lfl.index('end'): {maxlfl}")
            logger.debug(f"on_compare_end--rfl.index('end'): {maxrfl}")
            logger.debug("----------------")

            vs = [text_area, tag_area, lln, rln, lfl, rfl]
            ls = [maxtextline, maxtagline, maxlln, maxrln, maxlfl, maxrfl]
            maxline = max([maxtextline, maxtagline, maxlln, maxrln, maxlfl, maxrfl])
            minline = min([maxtextline, maxtagline, maxlln, maxrln, maxlfl, maxrfl])
            
            logger.debug(f"maxline: {maxline} minline: {minline}")
        
            for v, maxl in zip(vs, ls):
                prestate = v.cget('state')
                if prestate == 'disabled':
                    v.config(state='normal')
                for i in range(minline, maxline):
                    if i >= maxl:
                        #logger.debug(f"i: {i} maxl: {maxl}")
                        v.insert('end', '\n', 'invalidfilltext')
                v.config(state=prestate)
            
            logger.debug("----------------")
            logger.debug(f"on_compare_end--l_text_area.index('end'): {text_area.index('end')}")
            logger.debug(f"on_compare_end--r_text_area.index('end'): {tag_area.index('end')}")
            logger.debug(f"on_compare_end--l_line_numbers.index('end'): {lln.index('end')}")
            logger.debug(f"on_compare_end--r_line_numbers.index('end'): {rln.index('end')}")
            logger.debug(f"on_compare_end--lfl.index('end'): {lfl.index('end')}")
            logger.debug(f"on_compare_end--rfl.index('end'): {rfl.index('end')}")
            logger.debug("----------------")

            text_area.__dict__['__endline'] = int(text_area.index('end').split('.')[0])
            tag_area.__dict__['__endline'] = int(tag_area.index('end').split('.')[0])

            if DEBUG_TAG:
                import shutil
                logger.debug(f"++++ save text tags")
                cwd = os.getcwd()
                if os.path.exists(f"{cwd}\\ltags.txt"):
                    shutil.copy(f"{cwd}\\ltags.txt", f"{cwd}\\ltags.txt.bak")
                if os.path.exists(f"{cwd}\\rtags.txt"):
                    shutil.copy(f"{cwd}\\rtags.txt", f"{cwd}\\rtags.txt.bak")

                ltags = []
                rtags = []
                for i in range(1, int(text_area.index('end').split('.')[0])):
                    linetags = text_area.tag_names(f'{i}.0') + text_area.tag_names(f'{i}.end')
                    ltags.append(f"{i} {' '.join(linetags)}")
                for i in range(1, int(tag_area.index('end').split('.')[0])):
                    linetags = tag_area.tag_names(f'{i}.0') + tag_area.tag_names(f'{i}.end')
                    rtags.append(f"{i} {' '.join(linetags)}")
                
                with open(f"{cwd}\\ltags.txt", 'w', encoding='utf-8') as f:
                    f.write('\n'.join(ltags))
                with open(f"{cwd}\\rtags.txt", 'w', encoding='utf-8') as f:
                    f.write('\n'.join(rtags))
    
    # ---------- end EditorEvent --------------
    @staticmethod
    def preload_filedialog(root, text_area):
        FileSelector.preload_file_dialog(root)

    @staticmethod
    def text_area_bind(text_area, argsdict):
        text_area.bind("<<Selection>>", lambda event: Editor.EditorEvent.on_selection(text_area, event, argsdict))
        # 绑定复制和剪切事件
        text_area.bind("<<Copy>>", lambda event: Editor.EditorEvent.on_copy(event, text_area))
        text_area.bind("<<Cut>>", lambda event: Editor.EditorEvent.on_cut(event, text_area))
        #text_area.bind("<<Paste>>", lambda event: Editor.EditorEvent.on_paste(text_area, event, argsdict))
        #text_area.bind("<KeyPress>", lambda event: Editor.EditorEvent.on_key_press(text_area, event, argsdict))

        # 自定义事件
        text_area.bind("<<compareend>>", lambda event: Editor.EditorEvent.on_compare_end(text_area, event, argsdict))

        # 鼠标事件
        text_area.bind("<Button-1>", lambda e: update_cursor_position(None, e, argsdict))
        # undo、redo事件
        #text_area.bind("<Control-z>", lambda e: Editor.EditorEvent.on_undo(text_area, e, argsdict))         # 撤销 (Ctrl + Z)
        #text_area.bind("<Control-y>", lambda e: redo_event(text_area, e, argsdict))         # 重做 (Ctrl + Y)
        #text_area.bind("<Control-Shift-Z>", lambda e: redo_event(text_area, e, argsdict))   # 重做 (Ctrl + Shift + Z)

    @staticmethod
    def text_area_reset(text_area, start='1.0', end='end', tags=None):
        prestate = text_area.cget('state')
        if prestate == 'disabled':
            text_area.config(state="normal")
        Editor.text_area_tag_reset(text_area, tags, start, end)
        intend = int(text_area.index(f'{end}').split('.')[0])
        text_area.delete(start, f"{intend+1}.0")
        
        text_area.config(state=prestate)

    @staticmethod
    def text_area_tag_reset(text_area, tags, start='1.0', end='end'):
        prestate = text_area.cget('state')
        if prestate == 'disabled':
            text_area.config(state="normal")

        intend = int(text_area.index(f'{end}').split('.')[0])
        if tags == None:
            tags = set()
            intstart = int(text_area.index(f'{start}').split('.')[0])
            for i in range(intstart, intend+1):
                tags.update(text_area.tag_names(f'{i}.0')+text_area.tag_names(f'{i}.end'))
            #logger.debug(f"text_area_tag_reset-tags: {tags}")

        for tag in tags:
            if tag in TEXT_CONTENT_TAG:
                if tag == "invalidfilltext": continue
                text_area.tag_remove(tag, start, f"{intend+1}.0")
            elif tag.startswith('merge'):
                text_area.tag_delete(tag)
        text_area.config(state=prestate)

    @staticmethod
    def line_number_reset(line_numbers):
        line_numbers.config(state='normal')
        line_numbers.delete('1.0', 'end')    
        line_numbers.tag_delete(*tuple(line_numbers.tag_names()))
        line_numbers.config(state='disabled')

    @staticmethod
    def get_area(text_area, strstart='1.0', strend='end-1c') -> list[str]:
        content = []
        
        start = text_area.index(strstart)
        end = text_area.index(strend)

        #logger.debug(f"get_area, strstart: {strstart} strend: {strend}")
        #logger.debug(f"start char: {start.split('.')[1]}")
        #logger.debug(f"end char: {end.split('.')[1]}")
    
        if GET_AREA_LOG:
            logger.debug(f"get_area, start: {start} end: {end}")
        
        start_c = int(start.split('.')[1])
        end_c = int(end.split('.')[1])

        start = int(start.split('.')[0])
        end = int(end.split('.')[0])        

        for i in range(start, end+1):
            lct = None
            line = text_area.get(f"{i}.0", f"{i}.end")
            line_tags = set(text_area.tag_names(f"{i}.0")+text_area.tag_names(f"{i}.end"))
            
            #logger.debug(f"{i} line_tags: {line_tags} {repr(line)}")
            #logger.debug(f"set(TEXT_CONTENT_TAG)&line_tags): {set(TEXT_CONTENT_TAG)&line_tags}")
            edittags = TEXT_CONTENT_TAG&line_tags

            #logger.debug(f"line {i} content: {repr(line)} len: {len(line)}")
            if "spacesimage" not in line_tags and "invalidfilltext" not in line_tags:
                lct = f"{line}\n"
            elif len(line)>0 and ("spacesimage" in line_tags or "invalidfilltext" in line_tags):
                lct = f"{line}"
            #logger.debug(f"{repr(lct)}")
            if lct != None:
                if i == start and i == end:
                    lct = lct[start_c:end_c]
                elif i == start:
                    lct = lct[start_c:]
                elif i == end:
                    lct = lct[:end_c]
                content.append(lct)
            if 'invalidfilltext' in edittags and len(edittags) == 1: break
        
        """
        line_tags = set(text_area.tag_names(f"{end}.0")+text_area.tag_names(f"{end}.end"))

        line = text_area.get(f"{end}.0", f"{end}.end")
        if len(line) > 0:
            content.append(f"{line}")
        """
        #logger.debug(f"get_area, content:\n {content}")
        return content

    @staticmethod
    def file_to_lines(file_path):
        """读取文件并返回行列表"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()
                logger.info(f"Successfully read {len(lines)} lines from {file_path}")
                return lines
        except Exception as e:
            logger.error(f"Failed to read file {file_path}", error=str(e))
            raise

    @staticmethod
    def configure_tags(text_area):
        # 'uniqline' : {'background': "lightblue"},
        tags_and_styles = {
            'spacesimage': {'background': 'lightgrey'},
            'textcontent': {'background': "lightblue", 'foreground': 'red'},  # 红色字体
            'somematch': {'background': 'lightyellow'}, 
            'linediffer': {'foreground': 'red'},  # 红色字体
            'selected_text': {'background': 'lightblue', 'foreground': 'black'}, # 被选中内容的背景色和字体颜色
            'invalidfilltext' : {'background': 'grey'},
        }

        # 使用 tag_configure 配置每个标签的样式
        for tag, style in tags_and_styles.items():
            text_area.tag_configure(tag, **style)

    @staticmethod
    def update_line_numbers(text_area, left_line_numbers, right_line_numbers):
        """根据文本内容更新行号"""
        
        line_numbers_list = [left_line_numbers, right_line_numbers]
        
        for line_numbers in line_numbers_list:
            line_numbers.config(state='normal')
            line_numbers.delete(1.0, END)

        invalidfiledlines = 0
        # 计算当前文本中的行数
        lines = int(text_area.index('end').split('.')[0])-1
        for i in range(1,lines):
            line_numbers_list[0].insert(END, f"{i}\n")
            line_numbers_list[1].insert(END, f"{i}\n")
        line_numbers_list[0].insert(END, f"{lines}")
        line_numbers_list[1].insert(END, f"{lines}")

        #logger.debug(f"lines: {lines}")
        for i in range(lines-1, 1, -1):
            linetags = set(text_area.tag_names(f"{i}.end")+text_area.tag_names(f"{i}.0"))
            #logger.debug(f"linetags: {linetags}")
            if "invalidfilltext" in linetags:
                invalidfiledlines += 1
            else: break
        
        logger.debug(f"invalidfiledlines: {invalidfiledlines}")
        for i in range(lines+1, lines+6):
            if invalidfiledlines >= 5: break
            line_numbers_list[0].insert(END, f"\n{i}")
            line_numbers_list[1].insert(END, f"\n{i}")
            invalidfiledlines += 1
                
        for line_numbers in line_numbers_list:
            line_numbers.config(state='disabled')
            
        text_area.event_generate("<<compareend>>", data={'invalidfiledlines':invalidfiledlines})    
    
    #————————————————————————————————
    # 文件选择保存栏功能函数
    #————————————————————————————————
    @staticmethod
    def _save_to_path(path, text_area):
        """将内容保存到指定路径"""
        #logger = StructuredLogger()
        try:
            with open(path, 'w', encoding='utf-8') as file:
                contents = Editor.get_area(text_area, '1.0', 'end')
                content = ''.join(contents)
                file.write(content)
            logger.info(f"File successfully saved to {path}")
        except Exception as e:
            logger.error(f"Failed to save file to {path}", error=str(e))
            raise

    @staticmethod
    def update_history(path, filepathbox):
        current_values = list(filepathbox['values'])
        new_entry = path
        if new_entry in current_values:
            current_values.remove(new_entry)
            
        # if new_entry not in current_values:
        current_values.insert(0, new_entry)
        filepathbox['values'] = current_values[:10]  # 限制最多保存10条历史记录
        filepathbox.set(new_entry)

    @staticmethod
    def load_file(path_var, text_area, pathbox, argsdict):
        file_path = path_var.get()
        Editor.update_history(file_path, pathbox)
        if path_var.__dict__.get('__from__', None) == '__save__':
            return

        logger.info("**路径变化，重新加载文件**")
        tag_area = argsdict.get("tagarea")
        text_line_numbers = argsdict.get('textlines')
        tag_line_numbers = argsdict.get('taglines')
        lfl = argsdict.get('textflines', None)
        rfl = argsdict.get('tagflines', None)
        
        Editor.text_area_reset(text_area)
        Editor.line_number_reset(text_line_numbers)
        Editor.line_number_reset(tag_line_numbers)
        Editor.line_number_reset(lfl)
        Editor.line_number_reset(rfl)
        
        logger.info(f"file_path: {file_path}")
        if file_path:
            text_content = Editor.file_to_lines(file_path)
            text_area.insert('1.0', "".join(text_content))
        """
        logger.info("开始对比文件")
        modified = argsdict.get('modified')
        
        if modified == 'left':
            match_pairs = compare_files(text_content, tag_content)
            display_results(text_area, tag_area, text_content, tag_content, match_pairs, lfl, rfl)
        else:
            match_pairs = compare_files(tag_content, text_content)
            display_results(tag_area, text_area, tag_content, text_content, match_pairs, rfl, lfl)
        """
        Editor.update_line_numbers(text_area, text_line_numbers, tag_line_numbers)
        
    @staticmethod
    def select_file(path_var, root):
        FileSelector.select_file(path_var, root)
        """
        file_path = filedialog.askopenfilename(
            title="选择文件",
            filetypes=[("所有文件", "*.*"), ("文本文件", "*.txt"), ("Python 文件", "*.py")],
        )
        if file_path:
            # msgbox.showinfo(title='提示', message=f"选择的文件路径是: {file_path}")
            # 你也可以在这里将文件路径设置到某个控件中，例如 Combobox 或 Entry
            path_var.set(file_path)
        """

    @staticmethod    
    def save_file(filepath_var, text_area):
        """
        打开文件保存对话框，并返回用户选择的文件路径。
        """
        logger.info("**保存文件**")
        file_path = filepath_var.get()
        if file_path:
            Editor._save_to_path(file_path, text_area)
            return 
        # 使用 asksaveasfilename 来获取保存文件的路径
        file_path = filedialog.asksaveasfilename(
            title="保存文件",
            defaultextension=".txt",  # 默认文件扩展名
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],  # 支持的文件类型
        )
        if file_path:
            filepath_var.__dict__["__from__"] = '__save__'
            filepath_var.set(file_path)
            Editor._save_to_path(file_path, text_area)

    # 文件选择保存栏功能函数 end

# 定义事件组, editevent主要编辑事件，触发事件处理；required是必须事件；option是可选发生事件
EVENT_GROUP = [
    #{"editevent": ["Modified"], "required": ["KeyPress"], "handle_func": Editor.EditorHandler.handle_input},
    #{"editevent": [ 'Del', 'BackSpace'], "handle_func": None},
    #{"editevent": ['Cut'], "required": ["selection"], "handle_func": None},
    #{"editevent": ['paste'], "handle_func": Editor.EditorHandler.handle_paste},
]
# 以下两种编辑事件，在获取到粘贴的行数情况下，可以理解为粘贴即可，无需特殊处理
#{"editevent": ['KeyPress'], "required": ["selection"], "handle_func": handle_replace},
#{"editevent": ['paste'], "required": ["selection"], "handle_func": handle_replace},
# 该版本不实现该事件处理
#{"editevent": ['arrowmerge'], "handle_func": handle_arrowmerge},
set_event_group(EVENT_GROUP)
