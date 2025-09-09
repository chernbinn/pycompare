import logging
import inspect
import os, sys
import io
from functools import lru_cache
from typing import Dict, Optional

# 确保 UTF-8 输出
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 打开第三方模块
def logger_third_module(module_name:str, log_level = logging.DEBUG):
    if not module_name:
        return
    logger = logging.getLogger(f"{module_name}")
    logger.setLevel(log_level)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False  # 关闭传播，避免重复输出

# ------------------------------------
# 日志方案
# ------------------------------------
# 方案1：基于logging实现log输出
def get_logging_logger(module_name, log_level):
    logger = logging.getLogger(module_name)
    logger.setLevel(log_level)

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False  # 关闭传播，避免重复输出

    return logger

# 方案2：基于print实现log输出
# 模块日志级别缓存
_module_log_levels: Dict[str, int] = {}
_default_log_level = logging.WARNING

def _set_module_log_level(module: str, log_level: int):
    """设置特定模块的日志级别"""
    _module_log_levels[module] = log_level

def _parse_log_level_from_file(file_path: str):
    """从源文件解析日志级别设置"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过注释和空行
                if not line or line.startswith('#'):
                    continue
                
                # 匹配 _log_level 赋值语句
                if line.startswith('_log_level'):
                    log_level_str = line.split("=", 1)[1].strip()
                    log_level_name = log_level_str.split('logging.')[0]
                    log_level = logging.getLevelNamesMapping().get(log_level_name, _default_log_level)
                    return log_level
    except (OSError, UnicodeDecodeError):
        pass
    return _default_log_level

@lru_cache(maxsize=32)
def _get_caller_module() -> str:
    """获取调用者模块名(带缓存优化)"""
    try:
        caller_frame = inspect.stack()[2]  # 跳过装饰器和DEBUG函数本身
        caller_file = caller_frame.filename
        caller_file = os.path.normpath(caller_file)
        caller_module = os.path.splitext(os.path.basename(caller_file))[0]
        if caller_module not in _module_log_levels:
            log_level = _parse_log_level_from_file(caller_file)
            _set_module_log_level(caller_module, log_level)
        return caller_module
    except (IndexError, AttributeError):
        return "unknown"

def _should_log(level: int) -> bool:
    """判断是否应该记录日志"""
    module = _get_caller_module()
    module_level = _module_log_levels.get(module, _default_log_level)

    return level >= module_level

def _print_log(level: int, *args, **kwargs):
    """实际打印日志的底层函数"""
    kwargs.setdefault("file", sys.stderr)
    print(f"[{logging.getLevelName(level)}]", *args, **kwargs)

def myprint(*args, **kws):
    _print_log(logging.INFO, *args, **kws)

def DEBUG(*args, **kws):    
    if _should_log(logging.DEBUG):
        _print_log(logging.DEBUG, *args, **kws)

def INFO(*args, **kws):
    if _should_log(logging.INFO):
        _print_log(logging.INFO, *args, **kws)

def ERROR(*args, **kws):
    if _should_log(logging.ERROR):
        _print_log(logging.ERROR, *args, **kws)


# 方案3：自定义print logger, 目的是在某些情况下代替logging，可以最大自由度客制化输出方式
class PrintLogger:
    def __init__(self, module_name:str, log_level = logging.DEBUG):
        self.module_name = module_name
        self.log_level = log_level

    def __should_log(self, level):
        return level >= self.log_level

    @staticmethod
    def __print_log(*args, **kwargs):
        """实际打印日志的底层函数"""
        kwargs.setdefault("file", sys.stderr)
        kwargs["flush"] = True  # 强制刷新
        level = kwargs.pop('level')
        if not level:
            level = logging.INFO
        print(f"[{logging.getLevelName(level)}]", *args, **kwargs)
    
    def log(self, *args, **kws):
        self.__print_log(*args, **kws, level=level)

    def debug(self, *args, **kws):
        if self.__should_log(logging.DEBUG):
            self.__print_log(*args, **kws, level=logging.DEBUG)

    def info(self, *args, **kws):
        if self.__should_log(logging.INFO):
            self.__print_log(*args, **kws, level=logging.INFO)

    def warning(self, *args, **kws):
        if self.__should_log(logging.WARNING):
            self.__print_log(*args, **kws, level=logging.WARNING)

    def error(self, *args, **kws):
        if self.__should_log(logging.ERROR):
            self.__print_log(*args, **kws, level=logging.ERROR)

def get_print_logger(name, log_level):
    logger = PrintLogger(name, log_level)
    return logger
