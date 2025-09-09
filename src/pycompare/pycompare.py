
import queue
import difflib
import re
import os, time, sys
import uuid
import click
import psutil
import numpy as np
import concurrent.futures
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from multiprocessing import shared_memory
from tkinter import *
from tkinter import ttk
from tkinter import messagebox
from tkinter import filedialog
from cmdbox_commands.pycompare.logger import StructuredLogger, log_function

from pycompare._version import __version__

QUEUE_EVENT_LOG = False
TEXT_TAG_LOG = False
GET_AREA_LOG = False
DEBUG_TAG = False
MERGE_TAG_LOG = False
MODIFY_REVIEW_LOG = False

COMPARE_RESULT_LOG = False
COMPARE_AUTOJUNK = False

TEXT_CONTENT_TAG = set(['equalline', 'somematch', 'linediffer', 
                    'uniqline', 'textcontent', 'spacesimage', 
                    'invalidfilltext', 'newline'])
JUNK_STR_PATTERN = " \n"

logger = StructuredLogger('PyCompare')

class MatcherConfig:
    # 修正后的精度参数
    SCALE = 1_000_000      # 1e6 (对应1e-6精度)
    MIN_RATIO = 1          # ratio > 1e-6 → scaled > 1
    DTYPE = np.int32       # 必须使用32位整数

@log_function('INFO')
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

# 预处理缓存优化
# 根据系统内存动态计算缓存大小
def get_cache_size():
    try:
        total_memory = psutil.virtual_memory().total
        # 假设使用 1% 的内存作为缓存，可根据实际情况调整
        cache_memory = total_memory * 0.01
        # 假设每个缓存项平均占用 100 字节，可根据实际情况调整
        item_size = 300
        return max(1000, int(cache_memory / item_size))
    except:
        return 10000  # 默认值，当无法获取内存信息时使用

pattern = re.compile(r'['f"{JUNK_STR_PATTERN }"']')
# 预处理缓存优化
@lru_cache(maxsize=get_cache_size())
def preprocess(text):
    return pattern.sub('', text)

def mySequenceMatcher(isjunk=None, a='', b='', autojunk=COMPARE_AUTOJUNK, process=True):
    if process:
        a = preprocess(a)
        b = preprocess(b)
    return difflib.SequenceMatcher(isjunk, a, b, autojunk)

class DynamicSharedArray:
    def __init__(self, data_list: list[str]):
        separator = chr(30) #\x1E
        self.byte_data = f"{separator.join(data_list)}{separator}".encode('utf-8')
        self.shm_name = f"shm_{uuid.uuid4().hex}"
        self.shm = shared_memory.SharedMemory(
            create=True, 
            size=len(self.byte_data),
            name=self.shm_name
        )
        np_array = np.ndarray(
            (len(self.byte_data),),
            dtype=np.uint8, 
            buffer=self.shm.buf
        )
        np_array[:] = list(self.byte_data)

    def get_reader(self) -> str:
        """返回共享内存名称以供其他进程访问"""
        return self.shm_name
    
    def release(self):
        self.shm.close()
        if sys.platform != 'win32':
            self.shm.unlink()

class ParallelMatcher:
    SCALE = MatcherConfig.SCALE # 精度缩放因子
    _shared_cache = None
    @classmethod
    def init_shared_cache(cls):
        """初始化多进程共享缓存"""
        if cls._shared_cache is None:
            cls._shared_cache = {}
    @classmethod
    def get_ratio(cls, i, j) -> int:
        # 带缓存的相似度计算
        a = preprocess(cls.lines1[i])
        b = preprocess(cls.lines2[j])
        key = (hash(a), hash(b))  # 使用哈希值减少内存占用
        if key not in cls._shared_cache:
            ratio = difflib.SequenceMatcher(
                None, a, b, autojunk=COMPARE_AUTOJUNK
            ).ratio()
            cls._shared_cache[key] = ratio

        ratio = cls._shared_cache[key]
        #print(f"ratio: {ratio} a: {repr(a)} b: {repr(b)}")
        return int(round(ratio * cls.SCALE))
    
    @classmethod
    def clear_cache(cls):
        if cls._shared_cache is not None:
            cls._shared_cache.clear()
    
    @classmethod
    def process_row(cls, i, shm_name1, shm_name2, matrix_shm_name, m):
        shm1 = shm2 = shm_matrix = None
        cls.lines1 = []
        cls.lines2 = []
        cls.init_shared_cache()
        try:
            # 动态加载数据
            shm1 = shared_memory.SharedMemory(name=shm_name1)
            byte_data = bytes(np.ndarray(
                (shm1.size,), 
                dtype=np.uint8, 
                buffer=shm1.buf
            ))
            cls.lines1 = byte_data.decode('utf-8').split('\x1E')[:-1]
            
            shm2 = shared_memory.SharedMemory(name=shm_name2)
            byte_data = bytes(np.ndarray(
                (shm2.size,), 
                dtype=np.uint8, 
                buffer=shm2.buf
            ))
            cls.lines2 = byte_data.decode('utf-8').split('\x1E')[:-1]
            
            shm_matrix = shared_memory.SharedMemory(name=matrix_shm_name)
            matrix = np.ndarray(
                (len(cls.lines1), len(cls.lines2)), 
                dtype=MatcherConfig.DTYPE,  # float32->MatcherConfig.DTYPE
                buffer=shm_matrix.buf
            )
            for j in range(m):
                matrix[i][j] = ParallelMatcher.get_ratio(i, j)

            return i
        finally:
            # 清理共享缓存
            ParallelMatcher.clear_cache()
            for shm in [shm1, shm2, shm_matrix]:
                if shm is not None:
                    try:
                        shm.close()
                    except:
                        pass

def parallel_sim_matrix(content1, content2):
    arr1 = arr2 = shm_matrix = None
    try:
        # 动态存储初始化
        arr1 = DynamicSharedArray(content1)
        arr2 = DynamicSharedArray(content2)
        n, m = len(content1), len(content2)

        # 结果矩阵共享内存
        shm_matrix = shared_memory.SharedMemory(
            create=True,
            size=n * m * np.dtype(MatcherConfig.DTYPE).itemsize,  # float32-->MatcherConfig.DTYPE
            name=f"matrix_shm_{uuid.uuid4().hex}"
        )
    except Exception as e:
        print(f"初始化共享内存失败: {str(e)}")
        raise

    # 动态获取CPU核心数
    workers = os.cpu_count() or 2  # 默认取逻辑核心数，若获取失败则设为2

    try:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    ParallelMatcher.process_row,
                    i,
                    arr1.get_reader(),  # 传递共享内存名称
                    arr2.get_reader(),
                    shm_matrix.name,    # 传递结果矩阵名称
                    m
                )
                for i in range(n)
            ]
        
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"任务失败: {str(e)}")
        #return np.ndarray((n, m), dtype=np.float32, buffer=shm_matrix.buf).copy()
        return np.ndarray((n, m), dtype=MatcherConfig.DTYPE, buffer=shm_matrix.buf).copy()
    except Exception as e:
        print(f"并行计算相似度矩阵时出错: {str(e)}")
        raise
    finally:
        try:
            for resource in [arr1, arr2]:
                if resource is not None:
                    resource.release()
            if shm_matrix is not None:
                shm_matrix.close()
                if sys.platform != 'win32':
                    shm_matrix.unlink()
        except Exception as e:
            print(f"释放资源时出错: {str(e)}")
            

def compare_files(content1, content2):
    lines1 = content1 or []
    lines2 = content2 or []
    m, n = len(lines1), len(lines2)

    # 并行计算相似度矩阵
    if lines1 and lines2:
        sim_matrix = parallel_sim_matrix(lines1, lines2)
    else:
        sim_matrix = np.zeros((len(lines1), len(lines2)), dtype=MatcherConfig.DTYPE)
    #print(f"sim_matrix: {sim_matrix}")

    # 初始化动态规划表
    dp = np.zeros((m+1, n+1), dtype=np.int64)

    # 填充动态规划表
    for i in range(1, m+1):
        for j in range(1, n+1):
            dp[i][j] = max(
                dp[i-1][j-1] + sim_matrix[i-1][j-1],
                dp[i-1][j],
                dp[i][j-1]
            )

    # 回溯找到匹配对
    match_pairs = []
    i, j = m, n
    while i > 0 and j > 0:
        ratio = sim_matrix[i-1][j-1]
        if abs(dp[i][j]-dp[i - 1][j - 1]-ratio) < MatcherConfig.MIN_RATIO:
            if ratio > MatcherConfig.MIN_RATIO:
                # 提取匹配行中相同的部分内容
                if COMPARE_RESULT_LOG:
                    matcher = mySequenceMatcher(None, lines1[i - 1], lines2[j - 1])
                    matches = matcher.get_matching_blocks()
                    common_content = []
                    for match in matches:
                        if match.size > 0:
                            common_content.append(lines1[i - 1][match.a:match.a + match.size])
                    common_content = "".join(common_content)
                    match_pairs.append((i - 1, j - 1, lines1[i - 1], lines2[j - 1], common_content, ratio))
                else:
                    match_pairs.append((i - 1, j - 1, "", "", "", ratio))
            i -= 1
            j -= 1
        elif abs(dp[i][j] - dp[i - 1][j]) < MatcherConfig.MIN_RATIO:
            i -= 1
        else:
            j -= 1

    # 反转匹配对列表，使其按行号递增
    match_pairs.reverse()

    if COMPARE_RESULT_LOG:
        for match in match_pairs:
            print("----------")
            print(f"{match[0]}-{match[1]} {repr(match[4])} {match[5]}")
            print(f"{repr(match[2])}-{repr(match[3])}")

    return match_pairs

def configure_tags(text_area):
    # 'uniqline' : {'background': "lightblue"},
    tags_and_styles = {
        'spacesimage': {'background': 'lightgrey'},
        'textcontent': {'background': "lightblue", 'foreground': 'red'},  # 红色字体
        'somematch': {'background': 'lightyellow'}, 
        'linediffer': {'foreground': 'red'},  # 红色字体
        'selected_text': {'background': 'blue'}, # 被选中内容的背景色和字体颜色
        'invalidfilltext' : {'background': 'grey'},
    }

    # 使用 tag_configure 配置每个标签的样式
    for tag, style in tags_and_styles.items():
        text_area.tag_configure(tag, **style)

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
                    print(f"{i}行merge_tag: {merge_tag} block_start: {block_start}")
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
                        #print(f"(lnum+1-num): {lnum+1-num}")
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
def display_results(left_text_area, right_text_area, lines1, lines2, match_pairs, 
                    lfl, rfl, start_line=1):
    """在 GUI 中显示对比结果"""
    # 初始化行号
    left_line = 0
    right_line = 0
    area_line = start_line

    lfl_func = create_fileline_handler(lfl, None, start_line)
    rfl_func = create_fileline_handler(None, rfl, start_line)
    
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

def sync_scroll(text_a, text_b, line_num_a, line_num_b, fl_a, fl_b, *args):
        """同步滚动两个Text组件"""
        text_a.yview(*args)
        text_b.yview(*args)
        line_num_a.yview(*args)
        line_num_b.yview(*args)
        fl_a.yview(*args)
        fl_b.yview(*args)

def on_text_scroll(scroll_ya, scroll_yb, text_a, text_b, line_num_a, line_num_b, fla, flb, *args):
    """当Text组件滚动时调用此方法来更新滚动条的位置"""
    scroll_ya.set(*args)
    scroll_yb.set(*args)
    sync_scroll(text_a, text_b, line_num_a, line_num_b, fla, flb, 'moveto', args[0])
    
def sync_scroll_x(text_a, text_b, *args):
    """同步滚动两个Text组件"""
    text_a.xview(*args)
    text_b.xview(*args)

def on_text_scroll_x(scroll_xa, scroll_xb, text_a, text_b, *args):
    """当Text组件滚动时调用此方法来更新滚动条的位置"""
    scroll_xa.set(*args)
    scroll_xb.set(*args)
    sync_scroll_x(text_a, text_b, 'moveto', args[0])
    
def text_area_reset(text_area, start='1.0', end='end', tags=None):
    prestate = text_area.cget('state')
    if prestate == 'disabled':
        text_area.config(state="normal")
    text_area_tag_reset(text_area, tags, start, end)
    intend = int(text_area.index(f'{end}').split('.')[0])
    text_area.delete(start, f"{intend+1}.0")
    
    text_area.config(state=prestate)

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
        #print(f"text_area_tag_reset-tags: {tags}")

    for tag in tags:
        if tag in TEXT_CONTENT_TAG:
            if tag == "invalidfilltext": continue
            text_area.tag_remove(tag, start, f"{intend+1}.0")
        elif tag.startswith('merge'):
            text_area.tag_delete(tag)
    text_area.config(state=prestate)

def line_number_reset(line_numbers):
    line_numbers.config(state='normal')
    line_numbers.delete('1.0', 'end')    
    line_numbers.tag_delete(*tuple(line_numbers.tag_names()))
    line_numbers.config(state='disabled')
    
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

    #print(f"lines: {lines}")
    for i in range(lines-1, 1, -1):
        linetags = set(text_area.tag_names(f"{i}.end")+text_area.tag_names(f"{i}.0"))
        #print(f"linetags: {linetags}")
        if "invalidfilltext" in linetags:
            invalidfiledlines += 1
        else: break
    
    print(f"invalidfiledlines: {invalidfiledlines}")
    for i in range(lines+1, lines+6):
        if invalidfiledlines >= 5: break
        line_numbers_list[0].insert(END, f"\n{i}")
        line_numbers_list[1].insert(END, f"\n{i}")
        invalidfiledlines += 1
            
    for line_numbers in line_numbers_list:
        line_numbers.config(state='disabled')
        
    text_area.event_generate("<<compareend>>", data={'invalidfiledlines':invalidfiledlines})

def get_area(text_area, strstart='1.0', strend='end-1c'):
    content = []
    
    start = text_area.index(strstart)
    end = text_area.index(strend)
 
    if GET_AREA_LOG:
        logger.debug(f"get_area, start: {start} end: {end}")
    
    start = int(start.split('.')[0])
    end = int(end.split('.')[0])

    for i in range(start, end+1):
        lct = None
        line = text_area.get(f"{i}.0", f"{i}.end")
        line_tags = set(text_area.tag_names(f"{i}.0")+text_area.tag_names(f"{i}.end"))
        
        #print(f"{i} line_tags: {line_tags} {repr(line)}")
        #print(f"set(TEXT_CONTENT_TAG)&line_tags): {set(TEXT_CONTENT_TAG)&line_tags}")
        edittags = TEXT_CONTENT_TAG&line_tags
        if 'invalidfilltext' in edittags and len(edittags) == 1: break

        if "spacesimage" not in line_tags and "invalidfilltext" not in line_tags:
            lct = f"{line}\n"
        elif len(line)>0 and ("spacesimage" in line_tags or "invalidfilltext" in line_tags):
            lct = f"{line}"
        #print(f"{repr(lct)}")
        if lct != None:
            content.append(lct)
    
    """
    line_tags = set(text_area.tag_names(f"{end}.0")+text_area.tag_names(f"{end}.end"))

    line = text_area.get(f"{end}.0", f"{end}.end")
    if len(line) > 0:
        content.append(f"{line}")
    """
    return content

# --文本标签处理函数 end
    
#-------------------------
# 文本编辑事件处理
#-------------------------

# 汇总处理函数
def process_group_events(text_area, group, event_data, argsdict):
    """处理事件组"""
    text_area.tag_add('modified', '1.0', 'end')
    tag_area = argsdict.get('tagarea')

    handle_fucn = group.get('handle_func')
    start = None
    end = None
    if handle_fucn != None:
        cs_index, start, end = handle_fucn(text_area, event_data, tag_area)
    else:
        print("不需要处理的事件")

    if start != None and end != None:
        text_area_tag_reset(text_area, None, start, end)
        logger.debug(f"start: {start} end: {end}")
        text_area.tag_add('newline', start, end)
    
    for area in [text_area, tag_area]:
        modified_count = area.__dict__.get('__modifiedCT', 0)
        area.__dict__['__modifiedCT'] = modified_count+1
    
def handle_cut(text_area, events_data, tag_area):
    print(f"处理剪切操作")
    pass

def handle_delete(text_area, events_data, tag_area):
    """处理删除或剪切操作"""
    pass
    
def handle_paste(text_area, events_data, tag_area):
    """处理粘贴操作"""
    #current_index = text_area.index(INSERT)
    #print(f"cursor index: {current_index}")

    newlines = events_data.get('editevent').get('newlines', 0)
    print(f"newlines: {newlines}")    
    if newlines == 0: return None, None, None

    start_line = events_data.get('editevent').get('startline', 0)
    #start_line = int(current_index.split('.')[0]) - difflines + 1
    start_index = f"{start_line}.0"
    
    end_index = f"{events_data.get('editevent').get('endline', 0)}.end"
    #end_index = f"{start_line+newlines-1}.end"
    #end_index = current_index
    print(f"start_index: {start_index} end_index: {end_index}")

    return end_index, start_index, end_index

def handle_input(text_area, events_data, tag_area):
    """处理输入操作"""
    print(f"**处理输入或粘贴操作**")
    current_index = text_area.index(INSERT)
    print(f"cursor index: {current_index}")

    #prelines = text_area.__dict__.get('__endline', None)
    #print(f"prelines: {prelines}")
    start_line = int(current_index.split('.')[0])
    start_index = f"{start_line}.0"
    
    end_index = current_index
    print(f"start_index: {start_index} end_index: {end_index}")
    
    text_start = start_index
    text_end = f"{int(end_index.split('.')[0])}.end"
    print(f"text_start: {text_start} text_end: {text_end}")
    """
    if events_data.get('keysym', None) == "Return":
        text_area.__dict__['__endline'] = prelines+1
    """
    return current_index, text_start, text_end
    
def handle_arrowmerge(text_area, events_data, tag_area):
    return None, None, None

def handle_replace(text_area, events_data, tag_area):
    print(f"**处理替换操作**")
    return None, None, None
    
# 定义事件组, editevent主要编辑事件，触发事件处理；required是必须事件；option是可选发生事件
EVENT_GROUP = [
    {"editevent": ["Modified"], "required": ["KeyPress"], "handle_func": handle_input},
    {"editevent": [ 'Del', 'BackSpace'], "handle_func": None},
    {"editevent": ['Cut'], "required": ["selection"], "handle_func": None},
    {"editevent": ['paste'], "handle_func": handle_paste},
]
# 以下两种编辑事件，在获取到粘贴的行数情况下，可以理解为粘贴即可，无需特殊处理
#{"editevent": ['KeyPress'], "required": ["selection"], "handle_func": handle_replace},
#{"editevent": ['paste'], "required": ["selection"], "handle_func": handle_replace},
# 该版本不实现该事件处理
#{"editevent": ['arrowmerge'], "handle_func": handle_arrowmerge},
# 防抖装饰器, isbreak==True，直接返回'break'，终止底层默认操作
def debounce(wait, isbreak=False):
    root = None
    def decorator(func):
        def wrapper(text_area, event=None, *args):
            nonlocal root
            if wait == 0 or not text_area:
                if QUEUE_EVENT_LOG: print("exec right now!")
                func(text_area, event, *args)
                if isbreak: return 'break'
                else: return
            # 获取事件或编辑区的唯一标识
            event_key = (event.widget, func.__name__) if event else func.__name__
            
            if not root: root = text_area.winfo_toplevel()
            # 取消之前的定时器（如果存在）
            if hasattr(wrapper, '_timers'):
                if event_key in wrapper._timers:
                    root.after_cancel(wrapper._timers[event_key])

            # 设置新的定时器
            wrapper._timers[event_key] = root.after(wait, func, text_area, event, *args)
            if isbreak: return 'break'

        # 初始化 _timers 字典
        if not hasattr(wrapper, '_timers'):
            wrapper._timers = {}
        return wrapper
    return decorator

# 装饰函数工厂（结合防抖）
def group_event_decorator(event_type, debounce_time, isbreak=False):
    """创建一个装饰函数，用于捕获事件并更新组内状态"""
    def decorator(func):
        @debounce(debounce_time, isbreak)  # 应用防抖
        def wrapper(text_area, event=None, *args):
            if QUEUE_EVENT_LOG: print(f"event_type: {event_type}")
            # current_time = time.time()
            # 获取事件数据
            event_data = {
                "type": event_type  # 事件类型
            }

            event_data1 = None
            if func:
                event_data1 = func(text_area, event, *args)
            if not text_area: return

            discard = any([
                event_data1 == None,
                event_type == "KeyPress" and event_data1.get("invalidkey"),
            ])

            if event_data1 and not discard: event_data.update(event_data1)

            event_queue = text_area.__dict__.get('__eventqueue')
            # 将事件添加到队列且相同事件替换或删掉无效的事件
            replace_same_type_event(event_queue, event_type, event_data, discard)

            # 无效事件，不处理
            if discard:  return
            # 检查队列中是否存在符合分组条件的事件片段
            group, event_data = check_event_groups(event_queue)
            if event_data:
                process_group_events(text_area, group, event_data, *args)

            statusbar = args[0].get('statusbar', None)
            if statusbar:
                update_cursor_position(None, event, *args)
            text_area.edit_modified(False)
            
        return wrapper
    return decorator
    
def replace_same_type_event(event_queue, event_type, new_event, discard):
    """用新事件替换队列中的同类型旧事件"""
    temp_events = []

    # 遍历队列
    while not event_queue.empty():
        event = event_queue.get()
        if event["type"] != event_type:
            temp_events.append(event)
        else: break

    # 将事件重新放回队列
    temp_events.reverse()
    for event in temp_events:
        event_queue.put(event)

    if not discard:
        event_queue.put(new_event)

def check_event_groups(event_queue):
    """检查队列中是否存在符合任何分组条件的事件片段"""
    # 从队列中取出事件
    event = event_queue.get()
    if QUEUE_EVENT_LOG:
        print(f"check event, event: {event}")

    # 检查所有分组
    for group in EVENT_GROUP:
        edit_events = group["editevent"]
        required_events = group.get("required", [])
        option_events = group.get("option", [])

        if event["type"] in edit_events:
            option_event = retrieve_target_event(event_queue, option_events) if option_events else None
            if not required_events:
                clear_event_queue(event_queue)  # 清空事件队列
                return group, {"editevent": event, "option": option_event}
            if required_events:
                required_event = retrieve_target_event(event_queue, required_events)
                if required_event:
                    clear_event_queue(event_queue)  # 清空事件队列
                    # 如果 required 事件已发生，处理事件组
                    return group, {"editevent": event, "required": required_event, "option": option_event}
                else:
                    event_queue.put(event)
        # 如果事件是 required 事件
        elif event["type"] in required_events:
            # 如果是required事件，按照事件顺序是等待editevent发生，直接放回队列
            event_queue.put(event)
        else:
            # 如果事件不匹配任何分组，重新放回队列
            event_queue.put(event)
    return None, None

def retrieve_target_event(event_queue, target_events):
    """获取对应的 required 事件"""
    # 遍历队列，获取 required 事件
    temp_events = []
    required_event_data = None
    while not event_queue.empty():
        event = event_queue.get()
        temp_events.append(event)
        if event["type"] in target_events:
            required_event_data = event
            break
    # 将事件重新放回队列
    temp_events.reverse()
    for event in temp_events:
        event_queue.put(event)
    return required_event_data

def clear_event_queue(event_queue):
    """清空事件队列"""
    while not event_queue.empty():
        event_queue.get()
    
# 定义事件处理函数
@group_event_decorator(event_type="Modified", debounce_time=10)
def on_modified(text_area, event, argsdict):
    return {}

@group_event_decorator(event_type="paste", debounce_time=0, isbreak=True)
def on_paste(text_area, event, argsdict):
    print("Paste事件触发")

    try:
        text_area.delete("sel.first", "sel.last")
    except Exception as e:
        print(f"Exception: {e}")

    current_index = text_area.index(INSERT)
    print(f"start cursor index: {current_index}")
    start_line = int(current_index.split('.')[0])

    pasted_text = text_area.clipboard_get()
    lines = pasted_text.splitlines()
    #is_endnewl = pasted_text.endswith('\n')

    newlines = len(lines)
    #if is_endnewl: newlines += 1
    linetags = set(text_area.tag_names(current_index))
    insert_index = current_index
    if 'invalidfilltext' in linetags:
        try:
            start = str(text_area.tag_ranges('invalidfilltext')[0])
            #text_area.mark_set('insert', start)
            start_line = int(start.split('.')[0])
            insert_index = start
        except Exception as e:
            print(f"Exception: {e}")
    text_area.insert(insert_index, pasted_text)

    end_index = text_area.index(INSERT)
    print(f"paste end index: {end_index}")

    return {
        'startline': start_line,
        'endline': end_index.split('.')[0],
        'newlines': newlines
    }

@group_event_decorator(event_type="selection", debounce_time=0, isbreak=True)
def on_selection(text_area, event, argsdict):
    if QUEUE_EVENT_LOG: print("Selection事件触发")
    b_remove_selected_tag = False
    try:
        start_index = text_area.index("sel.first")
        end_index = text_area.index("sel.last")
        if QUEUE_EVENT_LOG:
            selected_text = text_area.get("sel.first", "sel.last")
            length = len(selected_text)
            print(f"起始位置: {start_index}, 结束位置: {end_index}, 长度: {length} 字符")
            print(f"选中的文本: '{selected_text}'")
        
        text_area.tag_remove("selected_text", '1.0', 'end')
        text_area.tag_add("selected_text", start_index, end_index)
        
        event_data = { }
        b_remove_selected_tag = start_index == end_index
        
    except Exception as e:
        print(f"Exception: {e}")
        b_remove_selected_tag = True

    if b_remove_selected_tag:
        text_area.tag_remove("selected_text", '1.0', 'end')
        event_data = None

    return event_data
    
@group_event_decorator(event_type="Cut", debounce_time=0)
def on_cut(text_area, event, argsdict):
    return {}
    
@group_event_decorator(event_type="Del", debounce_time=0)
def on_del_back(text_area, event, argsdict):
    return {}
    
@group_event_decorator(event_type="BackSpace", debounce_time=0)
def on_del_head(text_area, event, argsdict):
    return {}

@group_event_decorator(event_type="KeyPress", debounce_time=0)
def on_key_press(text_area, event, argsdict):
    print(f"KeyPress 事件触发")
    print(f"event: {event}")
    
    cursor_index = text_area.index(INSERT)
    if QUEUE_EVENT_LOG:
        print(f"cursor_index: {cursor_index}")
    # 获取按键的字符和键码
    char = event.char
    keysym = event.keysym
    print(f"char: {repr(char)} keysym: {keysym}")
    
    # 定义方向键
    direction_keys = {'Left', 'Right', 'Up', 'Down'}
    
    # 获取修饰键的状态
    # 判断修饰键状态
    shift_pressed = keysym in {'Shift_L', 'Shift_R'} or (event.state & 0x1) != 0  # Shift 键
    ctrl_pressed = keysym in {'Control_L', 'Control_R'} or (event.state & 0x4) != 0  # Control 键
    alt_pressed = keysym in {'Alt_L', 'Alt_R'} or (event.state & 0x8) != 0  # Alt 键

    print(f"shift_pressed: {shift_pressed} ctrl_pressed: {ctrl_pressed} alt_pressed: {alt_pressed}")

    invalidkey = any([
        len(char) == 0,
        shift_pressed or ctrl_pressed or alt_pressed,
        shift_pressed and keysym in direction_keys,
        ctrl_pressed and char in {'c', 'v', 'x'},
        char in {'BackSpace', 'Delete'},
    ])
    print(f"invalidkey: {invalidkey}")
    event_data = {
        "invalidkey": invalidkey,
        "keysym": keysym
    }
    return event_data
    
@group_event_decorator(event_type="arrowmerge", debounce_time=10)
def on_arrow_merge(text_area, event, argsdict):
    print(f"arrowmerge 事件触发")
    print(f"event: {event}")
    
    return None

#@group_event_decorator(event_type="arrowclick", debounce_time=0)
def on_arrow_click(text_area, event, argsdict):
    pass

@group_event_decorator(event_type="refresh", debounce_time=10)
def refresh_compare_F5(text_area, event, argsdict):
    print(f"refresh 事件触发")

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

    line_number_reset(text_line_numbers)
    line_number_reset(tag_line_numbers)
    line_number_reset(lfl)
    line_number_reset(rfl)
    
    text_content = get_area(text_area)
    tag_content = get_area(tag_area)
    text_area_reset(tag_area)
    text_area_reset(text_area)
    text_area.tag_delete(text_area.tag_names())
    tag_area.tag_delete(tag_area.tag_names())

    # 配置显示样式
    configure_tags(text_area)
    configure_tags(tag_area)

    clear_event_queue(text_area.__dict__.get('__eventqueue'))
    clear_event_queue(tag_area.__dict__.get('__eventqueue'))
    
    print("刷新对比内容")
    match_pairs = compare_files(text_content, tag_content)    
    display_results(text_area, tag_area, text_content, tag_content, match_pairs, lfl, rfl)
    
    update_line_numbers(text_area, text_line_numbers, tag_line_numbers)

def on_compare_end(text_area, event, argsdict):
    print(f"compareend 事件触发")

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

    #print(f"text_area.tag_ranges('invalidfilltext'): {text_area.tag_ranges('invalidfilltext')}")
    #print(f"tag_area.tag_ranges('invalidfilltext'): {tag_area.tag_ranges('invalidfilltext')}")

    if False: #MODIFY_REVIEW_LOG:
        messagebox.showerror(title="错误", message="对比结果显示行数不一致")

    print("----------------")
    print(f"on_compare_end--l_text_area.index('end'): {maxtextline}")
    print(f"on_compare_end--r_text_area.index('end'): {maxtagline}")
    print(f"on_compare_end--l_line_numbers.index('end'): {maxlln}")
    print(f"on_compare_end--r_line_numbers.index('end'): {maxrln}")
    print(f"on_compare_end--lfl.index('end'): {maxlfl}")
    print(f"on_compare_end--rfl.index('end'): {maxrfl}")
    print("----------------")

    vs = [text_area, tag_area, lln, rln, lfl, rfl]
    ls = [maxtextline, maxtagline, maxlln, maxrln, maxlfl, maxrfl]
    maxline = max([maxtextline, maxtagline, maxlln, maxrln, maxlfl, maxrfl])
    minline = min([maxtextline, maxtagline, maxlln, maxrln, maxlfl, maxrfl])
    
    print(f"maxline: {maxline} minline: {minline}")
   
    for i in range(minline, maxline):
        for v, maxl in zip(vs, ls):
            if i >= maxl:
                prestate = v.cget('state')
                if prestate == 'disabled':
                    v.config(state='normal')
                v.insert('end', '\n', 'invalidfilltext')
                v.config(state=prestate)
    
    print("----------------")
    print(f"on_compare_end--l_text_area.index('end'): {text_area.index('end')}")
    print(f"on_compare_end--r_text_area.index('end'): {tag_area.index('end')}")
    print(f"on_compare_end--l_line_numbers.index('end'): {lln.index('end')}")
    print(f"on_compare_end--r_line_numbers.index('end'): {rln.index('end')}")
    print(f"on_compare_end--lfl.index('end'): {lfl.index('end')}")
    print(f"on_compare_end--rfl.index('end'): {rfl.index('end')}")
    print("----------------")

    text_area.__dict__['__endline'] = int(text_area.index('end').split('.')[0])
    tag_area.__dict__['__endline'] = int(tag_area.index('end').split('.')[0])

    if DEBUG_TAG:
        import shutil
        print(f"++++ save text tags")
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

def update_cursor_position(text, event, argsdict):
    # print(f"update_cursor_position 事件")
    text = event.widget
    if text == None: return

    tag_area = argsdict.get('tagarea')
    tag_area.tag_remove("selected_text", '1.0', 'end')

    try:
        # 获取光标位置(INSERT标记)
        cursor_pos = text.index(INSERT)
        line, column = map(int, cursor_pos.split('.'))
       
        status_var = argsdict.get('statusbar')
        # 更新状态栏
        status_var.set(
            f"行: {line}, 列: {column}"
        )
    except Exception as e:
        status_var.set(f"错误: {str(e)}")

def on_undo(text_area, e, argsdict):
    print(f"undo 事件")
    modified_count = text_area.__dict__.get('__modifiedCT', 0)
    print(f"modified_count: {modified_count}")

    if modified_count == 0:
        return 'break'
    modified_count -= 1
    text_area.__dict__['__modifiedCT'] = modified_count

# 文本编辑事件处理end

def text_area_bind(text_area, argsdict):
    text_area.bind("<<Selection>>", lambda event: on_selection(text_area, event, argsdict))
    text_area.bind('<<Cut>>', lambda event: on_cut(text_area, event, argsdict))
    text_area.bind("<<Paste>>", lambda event: on_paste(text_area, event, argsdict))
    text_area.bind("<<Modified>>", lambda event: on_modified(text_area, event, argsdict))
    text_area.bind("<Delete>", lambda event: on_del_back(text_area, event, argsdict))
    text_area.bind("<BackSpace>", lambda event: on_del_head(text_area, event, argsdict))
    text_area.bind("<KeyPress>", lambda event: on_key_press(text_area, event, argsdict))

    # 自定义事件
    text_area.bind("<<arrowmerge>>", lambda event: on_arrow_merge(text_area, event, argsdict))
    text_area.bind("<<compareend>>", lambda event: on_compare_end(text_area, event, argsdict))

    # 鼠标事件
    text_area.bind("<Button-1>", lambda e: update_cursor_position(None, e, argsdict))
    # text_area.bind("<FocusOut>", on_focusout)
    # undo、redo事件
    text_area.bind("<Control-z>", lambda e: on_undo(text_area, e, argsdict))         # 撤销 (Ctrl + Z)
    #text_area.bind("<Control-y>", lambda e: redo_event(text_area, e, argsdict))         # 重做 (Ctrl + Y)
    #text_area.bind("<Control-Shift-Z>", lambda e: redo_event(text_area, e, argsdict))   # 重做 (Ctrl + Shift + Z)

#————————————————————————————————
# 文件选择保存栏功能函数
#————————————————————————————————
@log_function('INFO')
def _save_to_path(path, text_area):
    """将内容保存到指定路径"""
    #logger = StructuredLogger()
    try:
        with open(path, 'w', encoding='utf-8') as file:
            contents = get_area(text_area, '1.0', 'end')
            content = ''.join(contents)
            file.write(content)
        logger.info(f"File successfully saved to {path}")
    except Exception as e:
        logger.error(f"Failed to save file to {path}", error=str(e))
        raise

def update_history(path, filepathbox):
    current_values = list(filepathbox['values'])
    new_entry = path
    if new_entry in current_values:
        current_values.remove(new_entry)
        
    # if new_entry not in current_values:
    current_values.insert(0, new_entry)
    filepathbox['values'] = current_values[:10]  # 限制最多保存10条历史记录
    filepathbox.set(new_entry)

def load_file(path_var, text_area, pathbox, argsdict):
    file_path = path_var.get()
    update_history(file_path, pathbox)
    if path_var.__dict__.get('__from__', None) == '__save__':
        return

    print("**路径变化，重新加载文件**")
    tag_area = argsdict.get("tagarea")
    text_line_numbers = argsdict.get('textlines')
    tag_line_numbers = argsdict.get('taglines')
    lfl = argsdict.get('textflines', None)
    rfl = argsdict.get('tagflines', None)
    
    text_area_reset(text_area)
    line_number_reset(text_line_numbers)
    line_number_reset(tag_line_numbers)
    line_number_reset(lfl)
    line_number_reset(rfl)
    
    print(f"file_path: {file_path}")
    if file_path:
        text_content = file_to_lines(file_path)
        text_area.insert('1.0', "".join(text_content))
    """
    print("开始对比文件")
    modified = argsdict.get('modified')
    
    if modified == 'left':
        match_pairs = compare_files(text_content, tag_content)
        display_results(text_area, tag_area, text_content, tag_content, match_pairs, lfl, rfl)
    else:
        match_pairs = compare_files(tag_content, text_content)
        display_results(tag_area, text_area, tag_content, text_content, match_pairs, rfl, lfl)
    """
    update_line_numbers(text_area, text_line_numbers, tag_line_numbers)
    
  
def select_file(path_var):
    file_path = filedialog.askopenfilename(
        title="选择文件",
        filetypes=[("所有文件", "*.*"), ("文本文件", "*.txt"), ("Python 文件", "*.py")],
    )
    if file_path:
        # msgbox.showinfo(title='提示', message=f"选择的文件路径是: {file_path}")
        # 你也可以在这里将文件路径设置到某个控件中，例如 Combobox 或 Entry
        path_var.set(file_path)
        
def save_file(filepath_var, text_area):
    """
    打开文件保存对话框，并返回用户选择的文件路径。
    """
    print("**保存文件**")
    file_path = filepath_var.get()
    if file_path:
        _save_to_path(file_path, text_area)
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
        _save_to_path(file_path, text_area)

# 文件选择保存栏功能函数 end

#————————————————————————————————
# GUI构建
#————————————————————————————————
#++++++++++++++++++++++++++++
# 菜单栏
#++++++++++++++++++++++++++++
def menu(root):
    main_menu = Menu(root)
    root.config(menu=main_menu)
    # 一级菜单
    # 会话
    session_menu = Menu(main_menu, tearoff=False)
    main_menu.add_cascade(label="会话", menu=session_menu)
    # 文件
    file_munu = Menu(main_menu, tearoff=False)
    main_menu.add_cascade(label="文件", menu=file_munu)
    # 编辑
    edit_munu = Menu(main_menu, tearoff=False)
    main_menu.add_cascade(label="编辑", menu=edit_munu)
    # 搜索
    search_menu = Menu(main_menu, tearoff=False)
    main_menu.add_cascade(label="搜索", menu=search_menu)
    # 视图
    view_munu = Menu(main_menu, tearoff=False)
    main_menu.add_cascade(label="视图", menu=view_munu)
    # 工具
    tools_munu = Menu(main_menu, tearoff=False)
    main_menu.add_cascade(label="工具", menu=tools_munu)
    # 帮助
    help_menu = Menu(main_menu, tearoff=False)
    main_menu.add_cascade(label="帮助", menu=help_menu)

    # 会话二级菜单
    session_menu.add_command(label="新建会话",
                comman=lambda:messagebox.showinfo(title='tip', message="maybe wait!"))
    # 菜单栏 end

def main(root):
    # 创建 GUI
    root.title("文本对比工具")    
    #root.title("PyCompare")
    #screen_width = root.winfo_screenwidth()
    #screen_height = root.winfo_screenheight()
    #min_width = screen_width // 3
    #min_height = int(0.8*min_width)
    #root.minsize(min_width, min_height) 
    #root.geometry(f'{screen_width}x{screen_height}')
    root.state('zoomed')

    # 菜单栏
    menu(root)
    
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
            command=lambda *args:sync_scroll(l_text_area, r_text_area, l_line_numbers, r_line_numbers, lfl, rfl, *args))
    scroll_ya.grid(row=0, column=3, sticky=NS)
    scroll_yb = ttk.Scrollbar(text_frame, orient=VERTICAL,
            command=lambda *args:sync_scroll(l_text_area, r_text_area, l_line_numbers, r_line_numbers, lfl, rfl, *args))
    scroll_yb.grid(row=0, column=7, sticky=NS)

    l_text_area.config(yscrollcommand=lambda *args:on_text_scroll(scroll_ya, scroll_yb,             l_text_area, r_text_area, l_line_numbers, r_line_numbers, lfl, rfl, *args))
    r_text_area.config(yscrollcommand=lambda *args:on_text_scroll(scroll_ya, scroll_yb,             l_text_area, r_text_area, l_line_numbers, r_line_numbers, lfl, rfl, *args))
    l_line_numbers.config(yscrollcommand=lambda *args:on_text_scroll(scroll_ya, scroll_yb,             l_text_area, r_text_area, l_line_numbers, r_line_numbers, lfl, rfl, *args))
    r_line_numbers.config(yscrollcommand=lambda *args:on_text_scroll(scroll_ya, scroll_yb,             l_text_area, r_text_area, l_line_numbers, r_line_numbers, lfl, rfl, *args))
    lfl.config(yscrollcommand=lambda *args:on_text_scroll(scroll_ya, scroll_yb, l_text_area, r_text_area, l_line_numbers, r_line_numbers, lfl, rfl, *args))
    rfl.config(yscrollcommand=lambda *args:on_text_scroll(scroll_ya, scroll_yb, l_text_area,r_text_area, l_line_numbers, r_line_numbers, lfl, rfl, *args))

    scroll_xa = ttk.Scrollbar(text_frame, orient=HORIZONTAL, 
            command=lambda *args:sync_scroll_x(l_text_area, r_text_area, *args))
    scroll_xa.grid(row=1, column=2, sticky=EW)
    scroll_xb = ttk.Scrollbar(text_frame, orient=HORIZONTAL, 
            command=lambda *args:sync_scroll_x(l_text_area, r_text_area, *args))
    scroll_xb.grid(row=1, column=6, sticky=EW)
    
    l_text_area.config(xscrollcommand=lambda *args: on_text_scroll_x(scroll_xa, scroll_xb, l_text_area, r_text_area, *args))
    r_text_area.config(xscrollcommand=lambda *args: on_text_scroll_x(scroll_xa, scroll_xb, l_text_area, r_text_area, *args))

    # 配置网格布局
    text_frame.grid_rowconfigure(0, weight=1)
    text_frame.grid_columnconfigure(2, weight=1)
    text_frame.grid_columnconfigure(6, weight=1)
    # 文件对比操作区 end

    #++++++++++++++++++++++++++++
    # 状态栏
    #++++++++++++++++++++++++++++
    statusvar = StringVar()
    statusbar = ttk.Label(root, relief=RAISED, borderwidth=1, textvariable=statusvar)
    statusbar.pack(side=BOTTOM, fill=X)
    # 状态栏end
    
    # 配置显示样式
    configure_tags(l_text_area)
    configure_tags(r_text_area)
    
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
    l_select_button.bind('<Button-1>', lambda *args: select_file(l_path_var))
    l_path_var.trace_add('write', lambda *args: load_file(l_path_var, l_text_area, l_pathbox, l_args))
    r_args = {
        'tagpathvar': l_path_var,
        'tagarea': l_text_area, 
        'textlines': r_line_numbers, 
        'taglines': l_line_numbers,
        'textflines': rfl,
        'tagflines': lfl,
        'modified': 'right'
    }
    r_select_button.bind('<Button-1>', lambda *args: select_file(r_path_var))
    r_path_var.trace_add('write', lambda *args: load_file(r_path_var, r_text_area, r_pathbox, r_args))

    l_save_button.bind('<Button-1>', lambda *args: save_file(l_path_var, l_text_area))
    r_save_button.bind('<Button-1>', lambda *args: save_file(r_path_var, r_text_area))
    
    argsdict = {
        'tagarea': r_text_area, 
        'textlines': l_line_numbers,
        'taglines': r_line_numbers,
        'textflines': lfl,
        'tagflines': rfl,
        'statusbar': statusvar,
        'modified': 'left'
    }
    text_area_bind(l_text_area, argsdict)
    argsdict = {
        'tagarea': l_text_area, 
        'textlines': r_line_numbers,
        'taglines': l_line_numbers,
        'textflines': rfl,
        'tagflines': lfl,
        'statusbar': statusvar,
        'modified': 'right'
    }
    text_area_bind(r_text_area, argsdict)
    l_text_area.__dict__['__eventqueue'] = queue.LifoQueue()
    r_text_area.__dict__['__eventqueue'] = queue.LifoQueue()
    
    argsdict = {
        'textarea': r_text_area,
        'tagarea': l_text_area, 
        'textlines': r_line_numbers,
        'taglines': l_line_numbers,
        'textflines': rfl,
        'tagflines': lfl,
        'modified': 'right'
    }
    rfl.tag_bind("arrow_merge", "<Button-1>", lambda event: on_arrow_click(rfl, event, argsdict))

    argsdict = {
        'textarea': l_text_area,
        'tagarea': r_text_area, 
        'textlines': l_line_numbers,
        'taglines': r_line_numbers,
        'textflines': lfl,
        'tagflines': rfl,
    }
    l_text_area.bind('<F5>', lambda event: refresh_compare_F5(None, event, argsdict))
    r_text_area.bind('<F5>', lambda event: refresh_compare_F5(None, event, argsdict))

    return argsdict

def test(context):
    # 文件路径
    file1 = 'D:\\Desktop\\repo入门使用.txt'
    file2 = 'D:\\Desktop\\repo入门使用1.txt'

    file1 = 'D:\\Desktop\\PyComare\\Application.py'
    file2 = 'D:\\Desktop\\PyComare\\Application.py.bak'

    # 对比文件
    lines1 = tuple(file_to_lines(file1))
    lines2 = tuple(file_to_lines(file2))
    print(f"len(lines1): {len(lines1)} len(lines2): {len(lines2)}")
    match_pairs = compare_files(lines1, lines2)

    # 显示对比结果
    display_results(context['textarea'], context['tagarea'], lines1, lines2, match_pairs, 
                    context['textflines'], context['tagflines'])
    update_line_numbers(context['textarea'], context['textlines'], context['taglines'])

@click.command()
@click.help_option('-h', '--help')
@click.version_option(version=__version__, prog_name='pycompare')
def cli():
    #set_start_method('spawn', force=True)  # 解决Windows兼容性问题

    root = Tk()
    context = main(root)

    # test(context)
    # 运行主循环
    root.mainloop()

if __name__ == "__main__":
    cli()