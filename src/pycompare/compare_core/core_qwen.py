import difflib
import re
import os
import sys
import uuid
import psutil
import concurrent.futures
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from multiprocessing import shared_memory
from array import array
import struct

from pycompare.config import COMPARE_AUTOJUNK, JUNK_STR_PATTERN
from pycompare.config import COMPARE_RESULT_LOG

import logging
from pycompare.logging_config import setup_logging
logger = setup_logging(logging.DEBUG, log_tag=__name__)

class MatcherConfig:
    SCALE = 1_000_000      # 1e6 (对应1e-6精度)
    MIN_RATIO = 1          # ratio > 1e-6 → scaled > 1

# 缓存大小动态计算
def get_cache_size():
    try:
        total_memory = psutil.virtual_memory().total
        cache_memory = total_memory * 0.01
        item_size = 300
        return max(1000, int(cache_memory / item_size))
    except:
        return 10000

# 预处理正则
pattern = re.compile(f"[{JUNK_STR_PATTERN}]")

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
        separator = '\x1E'
        self.byte_data = f"{separator.join(data_list)}{separator}".encode('utf-8')
        self.shm_name = f"shm_{uuid.uuid4().hex}"
        self.shm = shared_memory.SharedMemory(
            create=True, 
            size=len(self.byte_data),
            name=self.shm_name
        )
        # 使用 memoryview 写入
        mv = memoryview(self.shm.buf)
        mv[:] = self.byte_data

    def get_reader(self) -> str:
        return self.shm_name

    def release(self):
        self.shm.close()
        if sys.platform != 'win32':
            self.shm.unlink()

class Int32Matrix:
    """替代 numpy int32 矩阵"""
    def __init__(self, n, m):
        self.n, self.m = n, m
        self.data = array('i', [0]) * (n * m)  # i = int32

    def __setitem__(self, index, value):
        i, j = index
        self.data[i * self.m + j] = value

    def __getitem__(self, index):
        i, j = index
        return self.data[i * self.m + j]

    def to_2d_list(self):
        return [
            [self.data[i * self.m + j] for j in range(self.m)]
            for i in range(self.n)
        ]

class ParallelMatcher:
    SCALE = MatcherConfig.SCALE
    _shared_cache = None

    @classmethod
    def init_shared_cache(cls):
        if cls._shared_cache is None:
            cls._shared_cache = {}

    @classmethod
    def get_ratio(cls, i, j) -> int:
        a = preprocess(cls.lines1[i])
        b = preprocess(cls.lines2[j])
        key = (hash(a), hash(b))
        if key not in cls._shared_cache:
            ratio = difflib.SequenceMatcher(None, a, b, autojunk=COMPARE_AUTOJUNK).ratio()
            cls._shared_cache[key] = ratio
        return int(round(cls._shared_cache[key] * cls.SCALE))

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
            # 读取 lines1
            shm1 = shared_memory.SharedMemory(name=shm_name1)
            mv = memoryview(shm1.buf)
            byte_data = bytes(mv)
            cls.lines1 = byte_data.decode('utf-8').split('\x1E')[:-1]
            del mv

            # 读取 lines2
            shm2 = shared_memory.SharedMemory(name=shm_name2)
            mv = memoryview(shm2.buf)
            byte_data = bytes(mv)
            cls.lines2 = byte_data.decode('utf-8').split('\x1E')[:-1]
            del mv

            # 写入结果矩阵
            shm_matrix = shared_memory.SharedMemory(name=matrix_shm_name)
            # 使用 memoryview 操作原始 buffer
            mv = memoryview(shm_matrix.buf)
            # 两种写入方案
            # 方案1：行批量写入。效率更高，占用内存更大
            row_data = [cls.get_ratio(i, j) for j in range(m)]
            packed = struct.pack(f'{m}i', *row_data)
            offset = i * m * 4
            mv[offset:offset + m*4] = packed
            # 方案2：逐个写入
            """
            for j in range(m):
                ratio = cls.get_ratio(i, j)
                # 计算偏移：第 i 行，第 j 列
                offset = i * m * 4 + j * 4  # 每个 int32 占 4 字节
                struct.pack_into('i', mv, offset, ratio)
            """

            return i
        finally:
            del mv
            cls.clear_cache()
            for shm in [shm1, shm2, shm_matrix]:
                if shm is not None:
                    try:
                        shm.close()
                    except:
                        logger.warnings(f"释放资源时出错: {str(e)}")

def parallel_sim_matrix(content1, content2):
    arr1 = arr2 = shm_matrix = None
    try:
        arr1 = DynamicSharedArray(content1)
        arr2 = DynamicSharedArray(content2)
        n, m = len(content1), len(content2)

        # 创建结果矩阵共享内存（每个 int32 占 4 字节）
        matrix_size = n * m * 4
        matrix_shm_name = f"matrix_shm_{uuid.uuid4().hex}"
        shm_matrix = shared_memory.SharedMemory(
            create=True,
            size=matrix_size,
            name=matrix_shm_name
        )
    except Exception as e:
        logger.error(f"初始化共享内存失败: {str(e)}")
        raise

    workers = max(2, os.cpu_count() // 2)

    try:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    ParallelMatcher.process_row,
                    i,
                    arr1.get_reader(),
                    arr2.get_reader(),
                    shm_matrix.name,
                    m
                )
                for i in range(n)
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"任务失败: {str(e)}")

        # 从共享内存读取结果
        mv = memoryview(shm_matrix.buf)
        sim_matrix = Int32Matrix(n, m)
        fmt = f'{n * m}i'
        data = struct.unpack(fmt, mv[:n * m * 4])
        for i in range(n):
            for j in range(m):
                sim_matrix[i, j] = data[i * m + j]

        return sim_matrix.to_2d_list()  # 返回二维列表

    except Exception as e:
        logger.error(f"并行计算相似度矩阵时出错: {str(e)}")
        raise
    finally:
        try:
            del mv
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

    if lines1 and lines2:
        sim_matrix = parallel_sim_matrix(lines1, lines2)
    else:
        sim_matrix = [[0] * n for _ in range(m)]

    # 动态规划表（list of list）
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            dp[i][j] = max(
                dp[i-1][j-1] + sim_matrix[i-1][j-1],
                dp[i-1][j],
                dp[i][j-1]
            )

    # 回溯
    match_pairs = []
    i, j = m, n
    while i > 0 and j > 0:
        ratio = sim_matrix[i-1][j-1]
        if abs(dp[i][j] - dp[i-1][j-1] - ratio) < MatcherConfig.MIN_RATIO:
            if ratio > MatcherConfig.MIN_RATIO:
                if COMPARE_RESULT_LOG:
                    matcher = mySequenceMatcher(None, lines1[i-1], lines2[j-1])
                    matches = matcher.get_matching_blocks()
                    common_content = ''.join(
                        lines1[i-1][match.a:match.a + match.size]
                        for match in matches if match.size > 0
                    )
                    match_pairs.append((i-1, j-1, lines1[i-1], lines2[j-1], common_content, ratio))
                else:
                    match_pairs.append((i-1, j-1, "", "", "", ratio))
            i -= 1
            j -= 1
        elif abs(dp[i][j] - dp[i-1][j]) < MatcherConfig.MIN_RATIO:
            i -= 1
        else:
            j -= 1

    match_pairs.reverse()

    if COMPARE_RESULT_LOG:
        for match in match_pairs:
            logger.debug("----------")
            logger.debug(f"{match[0]}-{match[1]} {repr(match[4])} {match[5]}")
            logger.debug(f"{repr(match[2])}-{repr(match[3])}")

    return match_pairs