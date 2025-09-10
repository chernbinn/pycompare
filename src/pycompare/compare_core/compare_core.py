import difflib
import re
import os, sys
import uuid
import psutil
import numpy as np
import concurrent.futures
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from multiprocessing import shared_memory
from pycompare.config import COMPARE_AUTOJUNK, JUNK_STR_PATTERN
from pycompare.config import COMPARE_RESULT_LOG

import logging
from pycompare.logging_config import setup_logging
logger = setup_logging(logging.DEBUG, log_tag=__name__)

class MatcherConfig:
    # 修正后的精度参数
    SCALE = 1_000_000      # 1e6 (对应1e-6精度)
    MIN_RATIO = 1          # ratio > 1e-6 → scaled > 1
    DTYPE = np.int32       # 必须使用32位整数

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
        #logger.debug(f"ratio: {ratio} a: {repr(a)} b: {repr(b)}")
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
        logger.error(f"初始化共享内存失败: {str(e)}")
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
                    logger.error(f"任务失败: {str(e)}")
        #return np.ndarray((n, m), dtype=np.float32, buffer=shm_matrix.buf).copy()
        return np.ndarray((n, m), dtype=MatcherConfig.DTYPE, buffer=shm_matrix.buf).copy()
    except Exception as e:
        logger.error(f"并行计算相似度矩阵时出错: {str(e)}")
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
            logger.error(f"释放资源时出错: {str(e)}")
            

def compare_files(content1, content2):
    lines1 = content1 or []
    lines2 = content2 or []
    m, n = len(lines1), len(lines2)

    # 并行计算相似度矩阵
    if lines1 and lines2:
        sim_matrix = parallel_sim_matrix(lines1, lines2)
    else:
        sim_matrix = np.zeros((len(lines1), len(lines2)), dtype=MatcherConfig.DTYPE)
    #logger.debug(f"sim_matrix: {sim_matrix}")

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
            logger.debug("----------")
            logger.debug(f"{match[0]}-{match[1]} {repr(match[4])} {match[5]}")
            logger.debug(f"{repr(match[2])}-{repr(match[3])}")

    return match_pairs