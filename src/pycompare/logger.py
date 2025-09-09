# logger.py
import logging
import logging.handlers
import os, sys
import json
from functools import wraps
import inspect
import threading
import traceback
from functools import lru_cache
from pathlib import Path

_default_config_path = Path.home() / ".cmdbox"/ "pycompare"
class LoggerConfig:
    """日志配置类"""
    DEFAULT_CONFIG = {
        'save_log': True,
        'log_dir': str(_default_config_path / "logs"),
        'log_file': 'pycompare.log',
        'max_bytes': 10 * 1024 * 1024,  # 10MB
        'backup_count': 5,
        'log_level': 'INFO',
        'format': '%(asctime)s [%(levelname)s] %(module)s:%(funcName)s:%(lineno)d - %(message)s',
        'filemode': 'w'  # 文件模式：'w' 覆盖写入，'a' 追加写入
    }

    @classmethod
    @lru_cache()  # 添加缓存
    def load_config(cls, config_file=_default_config_path / "logger_config.json"):
        """从配置文件加载配置"""
        if not os.path.exists(config_file):
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            cls._write_default_config(config_file)
            return cls.DEFAULT_CONFIG

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            if config.get('log_dir') and not os.path.isabs(config['log_dir']):
                config['log_dir'] = os.path.join(_default_config_path, config['log_dir'])
            return {**cls.DEFAULT_CONFIG, **config}
        except json.JSONDecodeError as e:
            logging.warning(f"配置文件 {config_file} 损坏，重建默认配置")
            cls._write_default_config(config_file)
            return cls.DEFAULT_CONFIG
        except Exception as e:
            logging.error(f"加载日志配置失败: {e}, 使用默认配置")
            import traceback
            traceback.print_exc()

            return cls.DEFAULT_CONFIG

    @classmethod
    def _write_default_config(cls, config_file):
        """写入默认配置到文件"""
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(cls.DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        
class CustomLogger(logging.Logger):
    def findCaller(self, stack_info=False, stacklevel=1):
        """精确获取调用者信息"""
        frame = inspect.currentframe()
        try:
            # 基础偏移量：
            # 1. findCaller自身
            # 2. Logger._log
            # 3. Logger.info/debug等
            # 4. StructuredLogger._log
            base_skip = 4
            
            # 总跳过数 = 基础偏移 + 用户指定的stacklevel
            for _ in range(base_skip + stacklevel):
                frame = frame.f_back
                if frame is None:
                    break
            
            # 处理装饰器情况（如果有）
            while frame and frame.f_code.co_name == 'wrapper':
                frame = frame.f_back
            
            if frame:
                return (
                    frame.f_code.co_filename, 
                    frame.f_lineno, 
                    frame.f_code.co_name,
                    None
                )
        finally:
            del frame
        
        return ("unknown", 0, "unknown", None)
    
logging.setLoggerClass(CustomLogger)
class StructuredLogger:
    """结构化日志类"""
    """支持多实例的单例模式日志类（每个name一个实例）"""
    _instances = {}
    _lock = threading.Lock()  # 线程安全
    _config_lock = threading.Lock()

    __slots__ = ('_logger', '_initialized')
    
    def __new__(cls, name):
        """
        单例模式的__new__方法实现。
        确保类只有一个实例被创建,如果实例已存在则返回该实例。
        
        Returns:
            返回类的唯一实例
        """
        with cls._lock:
            if name not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[name] = instance
            return cls._instances[name]

    def __init__(self, name):
        # 创建logger
        if not hasattr(self, '_initialized'):  # 防止重复初始化
            self._logger = logging.getLogger(name)
            self._logger.propagate = False  # 禁用传播
            self._initialized = True
            self._setup_logger()

    def _setup_logger(self):
        with self._config_lock:
            # 清理现有handlers
            for handler in self._logger.handlers[:]:
                self._logger.removeHandler(handler)
            """配置日志记录器"""
            config = LoggerConfig.load_config()

            self._logger.setLevel(getattr(logging, config['log_level']))
            # 控制台处理器
            console_handler = logging.StreamHandler()

            # 设置格式
            formatter = logging.Formatter(config['format'])
            console_handler.setFormatter(formatter)

            # 添加处理器
            self._logger.addHandler(console_handler)

            if config['save_log']:
                # 创建日志目录
                log_dir = config['log_dir']
                os.makedirs(log_dir, exist_ok=True)
                log_path = os.path.join(log_dir, config['log_file'])
                print(f"log_path: {log_path}", file=sys.stdout)
                # 创建Handler
                # 文件处理器(带轮转)
                file_handler = logging.handlers.RotatingFileHandler(
                    log_path,
                    maxBytes=config['max_bytes'],
                    backupCount=config['backup_count'],
                    encoding='utf-8'
                )
                file_handler.setFormatter(formatter)
                self._logger.addHandler(file_handler)

    def _format_message(self, message, *args, **kwargs):
        """格式化非结构化日志消息"""
        if args:
            try:
                message = f'{message} {args}'
            except TypeError:
                message = message % args
        if kwargs:
            message = message + ' ' + ' '.join(f'{k}={v}' for k, v in kwargs.items())
        return message

    # 当参数字典kwargs中存在exception时，会自动将栈异常信息添加到kwargs中
    def _log(self, level, message, *args, structured=False, **kwargs):
        """记录日志的内部方法"""
        logenable = self._logger.isEnabledFor(getattr(logging, level.upper()))
        if not logenable:
            return
        
        if "exception" in kwargs and 'traceback' not in kwargs:
            kwargs.pop("exception")
            kwargs['traceback'] = traceback.format_exc().strip()

        try:
            if structured:
                # 结构化日志
                if args:
                    # 将位置参数转换为命名参数
                    kwargs['positional_args'] = args if len(args) > 1 else args[0]
                log_entry = self._build_log_entry(level, message, **kwargs)
                self._logger.log(
                    getattr(logging, level.upper()),
                    json.dumps(log_entry, ensure_ascii=False, default=str)
                )
                print(f"[LOGGER] {level.upper()} {json.dumps(log_entry, ensure_ascii=False, default=str)}", file=sys.stderr)
            else:
                if args or kwargs:
                    message = self._format_message(message, *args, **kwargs)
                self._logger.log(getattr(logging, level.upper()), message)
                print(f"[LOGGER] {level.upper()} {message}", file=sys.stderr)
        except Exception as e:
            error_trace = traceback.format_exc()
            fallback_msg = f"[LOGGER ERROR]Original log:\n    Message: {message} Args: {args}, Kwargs: {kwargs}\nCurrent exception, Full Traceback:\n{error_trace}"
            if not logging.root.handlers:  # 检查是否已有配置
                logging.basicConfig(stream=sys.stderr)
            logging.error(fallback_msg)  # 使用root logger输出
    
    def _build_log_entry(self, level: str, message: str, **kwargs) -> dict[str, any]:
        """构建结构化日志条目"""
        return {'message': message, **kwargs}
    
    def debug(self, message, *args, **kwargs):
        self._log('debug', message, *args, structured=False, **kwargs)

    def info(self, message, *args, **kwargs):
        self._log('info', message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self._log('warning', message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self._log('error', message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        self._log('critical', message, *args, **kwargs)

def log_function(level='INFO'):
    """函数日志装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = StructuredLogger(func.__module__)
            try:
                logger._log(level, f"Function {func.__name__} called", 
                          structured=True, args=args, kwargs=kwargs)
                result = func(*args, **kwargs)
                logger._log(level, f"Function {func.__name__} completed",
                            structured=True, result=result)
                return result
            except Exception as e:
                logger._log('ERROR', f"Function {func.__name__} failed: {str(e)}",
                          structured=True, exception=str(e), 
                          traceback=traceback.format_exc())
                raise
        return wrapper
    return decorator