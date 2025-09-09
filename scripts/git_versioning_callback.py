import logging
import os, sys
import subprocess
from pathlib import Path
from setuptools_git_versioning import (
    get_version, 
    get_branch, 
    get_tag, 
    _tag_filter_factory,
    _tag_formatter_factory,
    _callable_factory
)
try:
    from .logger_config import get_print_logger
except:
    print("python -m scripts.git_versioning_callback [install|file]")
    exit(1)

# --------------------------------------
# project global config
#_______________________________________
g_version_file = Path(__file__).parent.parent / "src" / "pycompare" / "_version.py"
g_git_path = Path(__file__).parent.parent / ".git"
g_config = {
        "enabled": True,
        "starting_version": "0.1.0",
        "template": "{tag}",
        "dev_template": "{tag}.{ccount}",
        "dirty_template": "{tag}.{ccount}+dirty",
        "tag_filter": "^(?P<tag>v\d+\.\d+\.\d+)$", # 过滤符合条件的tag
        "tag_formatter": "^.*?(?P<tag>\d+\.\d+\.\d+).*" # 对tag进行提取，提取出纯粹的版本号：x.y.z
    }
g_post_config = {
        "dev_template": "{tag}.post{ccount}",
        "dirty_template": "{tag}.post{ccount}+dirty",
    }
g_dev_config = {
        "dev_template": "{tag}.dev{ccount}",
        "dirty_template": "{tag}.dev{ccount}+dirty",
    }
# --------------------------------------
# project global config end
#_______________________________________

# logger_third_module("setuptools_git_versioning", setuptools_git_versioning.DEBUG)
logger = get_print_logger(__name__, logging.INFO)
#logger = get_logging_logger(__name__, logging.DEBUG)

def print_func(func):
    def wrapper(*args, **kws):
        logger.debug(f"\nfunc: {func.__name__}")
        res = func(*args, **kws)
        logger.debug(f"func: {func.__name__} end")
        return res
    return wrapper

def singleton(cls):
    instances = {}
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance

class Version():
    def __init__(self, version: str):
        try:
            version = version.lstrip('v')  # 去除可能的'v'前缀
            parts = version.split('.')
            if len(parts) != 3:
                raise ValueError("Version must be in format X.Y.Z")
            self.x, self.y, self.z = map(int, parts)
            self.version = version
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid version string '{version}': {e}")

class CommitMsg():
    MSG_INDEX = 2
    NEW_MAJOR_MSG = "feat!"
    NEW_MINOR_MSG = "newfeat"
    STAGED_MSG_FILE = ".git/COMMIT_EDITMSG"

    def __init__(self, tag: str):
        self.tag = tag

        self.staged_msg = None
        self.all_msg = self._all_msg_from_tag()

        self.b_new_major = None
        self.b_new_minor = None

    def _all_msg_from_tag(self):
        # cmd = 'git log v1.0.0..HEAD --pretty=format:"%h [%an] %ad: %s" --date=format:"%Y-%m-%d-%H:%M:%S"'
        cmd = [
            'git', 
            '-c', 'i18n.logOutputEncoding=utf-8', 
            'log', 
            f'{self.tag}..HEAD',
            '--pretty=format:"%h [%an] %s"'
        ]
        if not self.tag:
            cmd = [
                'git', 
                '-c', 'i18n.logOutputEncoding=utf-8', 
                'log', 
                '--pretty=format:"%h [%an] %s"'
            ]
        
        env = os.environ.copy()
        env['LANG'] = 'zh_CN.UTF-8'  # 关键环境变量
        env['PYTHONIOENCODING'] = 'utf-8'

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.getcwd(),
            env=env,  # 传递修改后的环境变量
            shell=False  # 避免shell的编码干扰
        )
        stdout, stderr = proc.communicate()
        # 尝试多种解码方式
        for encoding in ('utf-8', 'gbk', 'latin1'):
            try:
                lines = stdout.decode(encoding).splitlines()
                return [line.rstrip() for line in lines if line.rstrip()]
            except UnicodeDecodeError:
                continue
        lines = stdout.decode('utf-8', errors='replace').splitlines  # 保底方案
        return [line.rstrip() for line in lines if line.rstrip()]

    def is_null(self):
        return not self.all_msg

    def latest_msg(self):
        return self.all_msg[0] if self.all_msg else None

    def __read_staged_msg(self):
        file_path = os.path.join(os.getcwd(), self.STAGED_MSG_FILE)
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()

    def __check_staged_msg_file_valid(self):
        file_path = os.path.join(os.getcwd(), self.STAGED_MSG_FILE)
        if not os.path.exists(file_path):
            logger.error(f"staged_msg file {file_path} not exist")
            return False
        return True

    def __staged_msg(self):
        if self.staged_msg is None and self.__check_staged_msg_file_valid():
            self.staged_msg = self.__read_staged_msg()
        return self.staged_msg
    
    def _new_major(self, msg=None):
        _msg = msg or self.staged_msg
        return (_msg and _msg.startswith(self.NEW_MAJOR_MSG))

    def _new_minor(self, msg=None):
        _msg = msg or self.staged_msg
        return (_msg and _msg.startswith(self.NEW_MINOR_MSG))

    def _valid_format(self) -> bool:
        if self.staged_msg.startswith(f"{self.NEW_MINOR_MSG}!"):
            logger.error(f"错误：'{self.staged_msg}' 不符合规范，多余的符号'!'")
            return False
        return True
    
    def check_staged_msg_valid(self, staged_msg: str = None) -> bool:
        msg = staged_msg or self.__staged_msg()
        self.staged_msg = msg
        if self.staged_msg is None:
            logger.error("staged_msg is None, the pre-commit hook type must be 'commit-msg'")
            return False

        if not self._valid_format():
            return False
        if not self.all_msg:
            return True
        if self._new_major() and self.has_new_major():
            logger.error("当前大版本未发布，不可以再次升级大版本！")
            return False
        if self._new_minor() and self.has_new_minor():
            logger.error("当前小版本未发布，不可以再次升级小版本！")
            return False
        if self._new_major() and self.has_new_minor():
            logger.warning("当前小版本未发布情况下升级大版本!")
            logger.warning("如需要发布小版本，使用git reset回退版本，发布小版本后再提交升级大版本。")
            return True
        logger.debug(f"_new_minor: {self._new_minor(msg)}")
        logger.debug(f"has_new_minor: {self.has_new_minor()}")
        if self._new_minor() and self.has_new_major():
            logger.debug(f"commit msg: {msg}")
            logger.error("当前大版本未发布。新升级的大版本包含新的小版本，不需要升级小版本。")
            return False
        
        return True

    @staticmethod
    def __up_version(func):
        def wrapper(self, **args):
            res = func(self, **args)
            if func == self.has_new_major:
                self.b_new_major = res
            elif func == self.has_new_minor:
                self.b_new_minor = res
            return res
        return wrapper

    @__up_version
    def has_new_major(self):
        if self.b_new_major is not None:
            return self.b_new_major

        if self.all_msg:
            for line in self.all_msg:
                parts = line.split(' ')
                msg = ' '.join(parts[self.MSG_INDEX:])
                if self._new_major(msg):
                    return True

        return False

    @__up_version
    def has_new_minor(self):
        if self.b_new_minor is not None:
            return self.b_new_minor

        if self.all_msg:
            for line in self.all_msg:
                parts = line.split(' ')
                msg = ' '.join(parts[self.MSG_INDEX:])
                if self._new_minor(msg):
                    return True

        return False

@singleton
class GitVersioning:
    def __init__(self, version_file, exit_git = True):
        self.__version = None
        self.config = g_config.copy()
        self.version_file = version_file

        # 基础数据获取
        self.file_version = self._load_file_version()
        if exit_git == False:
            logger.warning(f".git not exist, version read from file: {os.path.relpath(self.version_file)}")
            return
        self.tag_version = self.get_tag()

        logger.debug(f"tag_version: {self.tag_version}")
        self.commit_msg = CommitMsg(self.tag_version)
        self.branch = get_branch()

        # 版本对象初始化
        #self.file_xyz = Version(self._tag_formmator(self.file_version))
        if self.tag_version:
            self.tag_xyz = Version(self._tag_formmator(self.tag_version))
        else:
            self.tag_xyz = Version(self.config.get("starting_version", '0.1.0'))

        # 比较结果
        #self.major_upped = self.is_major_upped()
        #self.minor_upped = self.is_minor_upped()

        logger.info("-------------------")
        logger.info(f"file_version: {self.file_version}")
        logger.info(f"tag_version: {self.tag_version}")
        #logger.info(f"file_xyz: {self.file_xyz.version}")
        logger.info(f"tag_xyz: {self.tag_xyz.version}")
        logger.info(f"current branch: {self.branch}")
        logger.info(f"latest_msg: {self.commit_msg.latest_msg()}")
        #logger.info(f"major_upped: {self.major_upped()}")
        #logger.info(f"minor_upped: {self.minor_upped()}")
        logger.info("-------------------")

    @print_func
    def _load_file_version(self)->str:
        try:
            with open(self.version_file, 'r', encoding='utf-8') as f:
                # 读取第一行内容
                return f.readline().split('=')[1].strip().replace('"', '')
        except:
            logger.warning(f"version from version file is not exist! Return default version:{self.config.get('starting_version', '0.1.0')}")
            return self.config.get('starting_version', '0.1.0')

    @print_func
    def get_tag(self):
        filter_callback = None
        if self.config.get("tag_filter"):
            filter_callback = _callable_factory(
                callable_name="tag_filter",
                regexp_or_ref=self.config.get("tag_filter"),
                callable_factory=_tag_filter_factory,
                package_name=None,
                root=None,
            )
        else:
            logger.warning("tag_filter is None")

        tag = get_tag(filter_callback=filter_callback)
        return tag      

    @print_func
    def is_major_upped(self):
        if self.file_xyz.x > self.tag_xyz.x:
            return True
        return False
    
    @print_func
    def is_minor_upped(self):
        if self.file_xyz.y > self.tag_xyz.y:
            return True
        return False

    @print_func
    def _tag_formmator(self, tag: str):
        logger.debug(f"tag: {tag}")
        if self.config.get("tag_formatter"):
            tag_format_callback = _callable_factory(
                callable_name="tag_formatter",
                regexp_or_ref=self.config.get("tag_formatter"),
                callable_factory=_tag_formatter_factory,
                package_name=None,
                root=None,
            )

            tag = tag_format_callback(tag)
        else:
            logger.warning(f"tag_formatter is None, tag: {tag}")
        return tag

    def _is_new_major(self):
        return self.commit_msg._new_major() or self.commit_msg.has_new_major()

    def _is_new_minor(self):
        return self.commit_msg._new_minor() or self.commit_msg.has_new_minor()
    
    @print_func
    def _is_dev(self):
        logger.debug("self.tag_version: ", self.tag_version)
        #logger.debug("self.commit_msg.is_null(): ", self.commit_msg.is_null())
        #logger.debug("self.major_upped: ", self.major_upped)
        #logger.debug("self.minor_upped: ", self.minor_upped)
        logger.debug("_is_new_major(): ", self._is_new_major())
        logger.debug("_is_new_minor(): ", self._is_new_minor())

        return any([
            self.tag_version is None,
            #self.major_upped,
            #self.minor_upped,            
            self._is_new_major(),
            self._is_new_minor(),
        ])
    
    @print_func
    def _is_post(self):
        """
        all([
            self.file_xyz.x == self.tag_xyz.x,
            self.file_xyz.y == self.tag_xyz.y,
            self.file_xyz.z == self.tag_xyz.z,
        ]),
        """
        if any([
            self.branch == self.tag_version,
            self.tag_version is not None and not (self._is_new_major() or self._is_new_minor()),
        ]):
            return True
        return False
    
    @print_func
    def up_major(self):
        #logger.debug("file_xyz.x: ", self.file_xyz.x)
        logger.debug("_is_new_major: ", self._is_new_major())
        #logger.debug("major_upped: ", self.major_upped)

        #return self.file_xyz.x + (1 if (self._is_new_major() and not self.major_upped) else 0)
        return self.tag_xyz.x + (1 if self._is_new_major() else 0)
    
    @print_func
    def up_minor(self):
        #logger.debug("file_xyz.y: ", self.file_xyz.y)
        logger.debug("_is_new_minor: ", self._is_new_minor())
        #logger.debug("minor_upped: ", self.minor_upped)

        #return self.file_xyz.y + (1 if (self._is_new_minor() and not self.minor_upped) else 0)
        return self.tag_xyz.y + (1 if self._is_new_minor() else 0)
    
    @print_func
    def _get_dev_xyz(self):
        if self._is_new_major():
            x = self.up_major()
            y = 0
            z = 0
        else: # self._is_new_minor()
            x = self.up_major()
            y = self.up_minor()
            z = 0
        return f"{x}.{y}.{z}"
    
    @print_func
    def _dev_version(self):
        self.config.update(g_dev_config)
        version = str(get_version(self.config))
        logger.info("the latest original version: ", version)
        xyz = Version(self._tag_formmator(version))
        logger.info("the latest version xyz: ", xyz.version)

        parts = version.split(xyz.version)
        logger.debug(parts)
        prefix = parts[0]+"." if len(parts) > 0 and len(parts[0]) > 0 else ""
        suffix = parts[1] if len(parts) > 1 else ""

        new_xyz = self._get_dev_xyz()
        new_version = f"{prefix}{new_xyz}{suffix}"

        return new_version

    @print_func
    def _post_version(self):
        self.config.update(g_post_config)
        new_version = str(get_version(self.config))
        return new_version

    @print_func
    def save_version(self, version=None):
        version = version or self.__version
        with open(self.version_file, 'w', encoding='utf-8') as f:
            f.write(f"__version__ = \"{version}\"\n")

    @print_func
    def get_version(self):
        logger.info(f"staged_msg: {self.commit_msg.staged_msg}")

        new_version = None
        if self._is_post():
            new_version = self._post_version()
        elif self._is_dev():
            new_version = self._dev_version()
        else:
            new_version = self._post_version()
        
        self.__version = new_version
        return new_version
    
    @print_func
    def check_staged_msg_valid(self, staged_msg=None):
        return self.commit_msg.check_staged_msg_valid(staged_msg)

# 方案1实现
def setuptools_git_versioning_version():
    from setuptools_git_versioning import get_version, _read_toml
    config = _read_toml()
    return get_version(config)

# 方案2: 代码中获取版本号可以是单独的配置，与pyproject.toml中的配置分离,实现不同的获取方式
# 因此可以结合使用
def check_staged_msg_valid(version_file:str, staged_msg: str=None) -> bool:
    git_versioning = GitVersioning(version_file)
    return git_versioning.check_staged_msg_valid(staged_msg)

def setup_git_versioning_version(version_file):
    git_versioning = GitVersioning(version_file)
    version = git_versioning.get_version()
    git_versioning.save_version()
    return version

def setup_version_from_file(version_file:str):
    git_versioning = GitVersioning(version_file, False)
    return git_versioning.file_version

def ensure_version_file(version_file:str, git_path: Path):
    if not Path(version_file).exists():
        version = None
        if Path(git_path).exists():
            version = setup_git_versioning_version(version_file)
        else:
            version = g_config['starting_version']
        # 创建文件
        with open(version_file, 'w', encoding='utf-8') as f:
            f.write(f"__version__ = \"{version or g_config['starting_version']}\"\n")

# -------------------------------------
# for pre-commit
def commit_update_version():
    ensure_version_file(g_version_file, g_git_path)
    if check_staged_msg_valid(g_version_file):
        return setup_git_versioning_version(g_version_file)
    return None

# for pyproject.toml
def install_version():
    ensure_version_file(g_version_file, g_git_path)
    git_path = g_git_path
    if not git_path or not git_path.exists():
        return setup_version_from_file(g_version_file)
    return setup_git_versioning_version(g_version_file)

def version_from_file():
    ensure_version_file(g_version_file, g_git_path)
    return setup_version_from_file(g_version_file)

# --------------------------------------
# for pre-commit entry
def main():
    version = commit_update_version()
    if not version:
        return 1
    logger.info(f"version: {version}")
    return 0

if __name__ == '__main__':
    logger.debug(f"{__file__}:{__name__}")
    if len(sys.argv) > 1 and sys.argv[1] == 'install':
        logger.info(f"version: {install_version()}")
        sys.exit(0)
    elif len(sys.argv) > 1 and sys.argv[1] == 'file':
        logger.info(f"version: {version_from_file()}")
        sys.exit(0)
    sys.exit(main())