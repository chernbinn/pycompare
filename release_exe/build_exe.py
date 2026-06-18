#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nuitka 构建脚本
用法:
    python .\release_exe\build_exe.py              # 构建项目
    python .\release_exe\build_exe.py --clean      # 仅清理临时文件
    python .\release_exe\build_exe.py --help       # 显示帮助信息
"""

import sys
import shutil
import subprocess
import argparse
from pathlib import Path
import time

# 定义目录常量
ROOT_DIR = Path(__file__).parent.parent.resolve()
DIST_DIR = ROOT_DIR / "dist"
BACKUP_DIR = ROOT_DIR / "backup"


def clean_folder(folder_path: str) -> None:
    """删除匹配的文件夹或通配符模式"""
    # 处理通配符
    if "*" in folder_path:
        items = list(ROOT_DIR.glob(folder_path))
    else:
        item = Path(folder_path)
        if not item.is_absolute():
            item = ROOT_DIR / item
        items = [item] if item.exists() else []

    for p in items:
        if p.exists():
            print(f"🗑️  Deleting {p}")
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink()

def backup_prev_version() -> None:
    """备份上一个版本的 exe 和 report.xml"""
    print("Backup previous version...")
    if DIST_DIR.exists():
        exe_files = list(DIST_DIR.glob("*.exe"))
        if exe_files:
            print(f"📋 Found {len(exe_files)} exe files in dist directory.")
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            for exe in exe_files:
                print(f"📋 Backing up {exe.name} to backup")
                shutil.copy2(exe, BACKUP_DIR / exe.name)

            report_xml = list(DIST_DIR.glob("report-*.xml"))
            if report_xml:
                print(f"📋 Found {len(report_xml)} report.xml files in dist directory.")
                BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                for xml in report_xml:
                    print(f"📋 Backing up {xml.name} to backup")
                    shutil.copy2(xml, BACKUP_DIR / xml.name)

def clean_temp() -> None:
    """清理构建临时文件，并可选择备份已生成的 exe"""
    print("🧹 Cleaning temporary folders...")
    # 删除常见构建目录
    for folder in ["build", "dist"]:
        clean_folder(folder)

    # Nuitka 生成的临时目录
    for pattern in ["*.onefile-build", "*.build", "*.dist"]:
        clean_folder(pattern)

def get_git_tag() -> str:
    """获取最新的 git 标签"""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT_DIR
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "unknown"


def ensure_main_py(release: bool = False) -> None:
    """如果不存在则创建 main.py 入口文件"""
    main_py = ROOT_DIR / "main.py"
    print("📄 Creating main.py")
    diff_code = """import traceback
        with open('pycompare-error.log', 'w') as f:
            traceback.print_exc(file=f)
        raise
    """
    if release:
        diff_code = "pass"
    with open(main_py, "w", encoding="utf-8") as f:
        f.write(
f"""
from pycompare.pycompare import cli

if __name__ == "__main__":
    try:
        cli()
    except Exception as e:
        {diff_code}
"""
            )

def build(release: bool = False, trace: bool = False, 
          zig: bool = False,
          backup: bool = False):
    """执行 Nuitka 构建"""
    # 获取版本
    ver = get_git_tag()
    timestamp = time.strftime("%Y%m%d%H%M%S")
    exe_name = f"pycompare-gui-{ver}-{timestamp}.exe"
    opt_exe_name = f"pycompare-gui-{ver}-{timestamp}-opt.exe"
    # 记录成功编译的report.xml文件，用于在不同设备上复刻虚拟环境
    # nuitka --create-environment-from-report=report.xml
    report_xml = f"report-{ver}-{timestamp}.xml"
    
    # --mingw64 mingw64编译链,gcc编译，性能最好
    # --zig zig编译链，nuitka提供编译链，编译链文件小，自动下载，环境搭建快捷，跨平台性好
    # --msvc msvc编译链，性能一般，但是兼容性好，适合windows平台
    # --clang clang编译链，性能一般，但是兼容性好，适合macos平台和linux平台
    compile_args = []
    if zig:
        compile_args = ["--zig"]
    else:
        compile_args = ["--mingw64"]
    # 
    if release:
        compile_args.append("--mode=onefile")
        console_mode = "disable"
        compile_args.append("--assume-yes-for-downloads")
        # --no-deployment-flag=FLAG --deployment模式下的白名单配置，打开一些特殊flag，flag从log中分析获取
        compile_args.append("--deployment")
        compile_args.append("--onefile-no-compression")
        compile_args.append("--onefile-as-archive")
        compile_args.append("--python-flag=-O,no_docstrings,-u,isolated,-P,no_warnings,-S,static_hashes")
        # --onefile-no-dll 只会影响onefile模式下运行时解压的结果形态，不影响打包的大小。使用该选项可以避免一些杀毒软件的误报，但不使用稳定性更好
        # compile_args.append("--onefile-no-dll")
        # 以下两个选项可以提高onefile模式下的启动速度，第一次启动后，会缓存解压结果，后续启动时直接从缓存中读取
        # --onefile-tempdir-spec='{CACHE_DIR}/{COMPANY}/{PRODUCT}/{VERSION}'
        # --onefile-cache-mode=cached
        # 链接优化
        if not zig:
            compile_args.append("--lto=yes")   
        
        # 静态链接python库，会增加打包大小，但是不依赖运行时库。如果不打开，没有安装python的环境可能无法使用
        # 可以考虑编译不同的版本，依赖本地已经安装python静态库
        # compile_args.append("--static-libpython=yes")
        # --cf-protection=none  GCC 编译器专属，关闭cf保护，开启有一定的性能损失，但是会增加安全性，防止被攻击
        if "--mingw64" in compile_args:
            compile_args.append("--cf-protection=auto")
    else:
        console_mode = "force"
        compile_args.append("--mode=standalone")
        compile_args.append("--debug")
        compile_args.append("--unstripped")
        # --python-debug  开启调试模式，指使用python的debug版本，因此会增加很多的调试信息，增加打包的大小，一般情况都是安装release版本的python
        # 谨慎使用，可能需要额外安装debug版本的python
        # compile_args.append("--python-debug")
        # --full-compat  开启全兼容模式，可以避免一些与旧版本python不兼容的问题。用于特殊情况调试，比如莫名的异常
        # compile_args.append("--full-compat")
        # --trace-execution  开启执行跟踪，可以调试一些异常情况。莫名奇妙异常的利器，一般不要开启，日志会很多且执行很慢
        if trace:
            compile_args.append("--trace-execution")
        #compile_args.append(f"--force-stdout-spec={'pycompare_stdout.txt'}")
        #compile_args.append(f"--force-stderr-spec={'pycompare_stderr.txt'}")

    # 构建 Nuitka 命令参数列表
    nuitka_args = [
        sys.executable, "-m", "nuitka",
        *compile_args,        
        "--windows-icon-from-ico=assets/logo.ico",
        f"--windows-console-mode={console_mode}",        
        "--enable-plugin=implicit-imports",
        "--enable-plugin=tk-inter",
        "--enable-plugin=multiprocessing",
        "--enable-plugin=anti-bloat",
        "--enable-plugin=no-qt",
        "--include-package=pycompare",
        "--nofollow-import-to=pycompare.compare_core.core_ds",        
        "--nofollow-import-to=unittest",
        "--nofollow-import-to=mailcap",
        "--nofollow-import-to=smtplib",
        "--nofollow-import-to=ftplib",
        "--nofollow-import-to=imaplib",
        "--nofollow-import-to=poplib",
        "--nofollow-import-to=email",
        "--nofollow-import-to=webbrowser",
        "--nofollow-import-to=netrc",
        "--nofollow-import-to=ssl",
        "--nofollow-import-to=colorama",
        "--nofollow-import-to=*.tests",
        "--nofollow-import-to=*.test",
        "--nofollow-import-to=*.testing",
        "--nofollow-import-to=*.debug",
        "--noinclude-pytest-mode=error",
        "--noinclude-unittest-mode=error",
        "--noinclude-setuptools-mode=error",
        "--noinclude-IPython-mode=error",
        "--noinclude-dask-mode=error",
        "--noinclude-numba-mode=error",
        "--noinclude-pydoc-mode=error",
        "--noinclude-data-files=*.pyc",
        "--noinclude-data-files=*.pyo",
        "--noinclude-data-files=*.txt",
        "--noinclude-data-files=*.md",
        "--noinclude-data-files=*.rst",
        "--noinclude-data-files=*.html",
        "--noinclude-data-files=*.log",        
        "--jobs=4",
        "--no-debug-c-warnings",
        "--no-debug-immortal-assumptions",
        "--warn-implicit-exceptions",
        "--warn-unusual-code",
        f"--output-dir={DIST_DIR}",
        f"--verbose-output={DIST_DIR / 'verbose.txt'}",
        f"--show-modules-output={DIST_DIR / 'modules.txt'}",
        f"--output-filename={exe_name}",
        f"--report={DIST_DIR / report_xml}",
        f"--xml={DIST_DIR / 'build.xml'}",        
        "main.py"
    ]

    print(f"nuitka_args: {nuitka_args}\n")

    if backup and "--mode=onefile" in nuitka_args:
        backup_prev_version()
    # 清理旧文件
    clean_temp()
    # 确保目录存在
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    # 确保入口文件
    ensure_main_py(release)
    # 清除 Nuitka 缓存
    subprocess.run([sys.executable, "-m", "nuitka", "--clean-cache=all"], check=False)
    print(f"\nBuilding {exe_name} ...")
    # 执行 Nuitka
    result = subprocess.run(nuitka_args, cwd=ROOT_DIR)
    if result.returncode != 0:
        print(f"❌ Nuitka build failed with exit code: {result.returncode}")
        sys.exit(result.returncode)

    # 压缩输出
    exe_path = None
    exes = list(DIST_DIR.rglob(exe_name))
    print(f"Found exes: {exes}")
    if exes:
        exe_path = exes[0]
    else:
        print(f"❌ Expected exe not found: {exe_name}")
        sys.exit(1)
    opt_exe_path = DIST_DIR / opt_exe_name
    if not release:
        print(f"✅ Done -> {exe_name}")
        print(f"\nOutput:\n{exe_path}")
        sys.exit(0)

    if exe_path.exists() and release:
        print(f"📦 Compressing with UPX...")
        try:
            subprocess.run(
                ["upx", "--ultra-brute", "--lzma", "--compress-icons=0", 
                 "--compress-exports=1", str(exe_path), "-o", str(opt_exe_path)],
                check=True,
                cwd=ROOT_DIR
            )
            print(f"✅ Done -> {opt_exe_name}")
            print(f"\nOutput:\n{exe_path}\n{opt_exe_path}")
        except FileNotFoundError:
            print("⚠️  UPX not found, skipping compression.")
            print(f"✅ Done -> {exe_name}")
        except subprocess.CalledProcessError as e:
            print(f"⚠️  UPX compression failed: {e}")
            print(f"✅ Done -> {exe_name}")        
    else:
        print(f"❌ Expected exe not found: {exe_path}")


def main():
    parser = argparse.ArgumentParser(description="Build pycompare with Nuitka")
    parser.add_argument("--clean", action="store_true", help="Clean temporary files and exit")
    parser.add_argument("--release", action="store_true", help="编译发布版本")
    parser.add_argument("--backup", action="store_true", help="备份上一个版本的 exe 文件，仅对--mode=onefile有效。")
    parser.add_argument("--trace", action="store_true", 
                         help="开启执行跟踪，可以调试一些异常情况。一般不要开启，日志会很多且执行很慢, 仅在开发环境下开启")
    parser.add_argument("--zig", action="store_true", help="使用zig编译链")
    args = parser.parse_args()

    backup = args.backup
    if args.clean:
        clean_temp(backup)
        print("✅ Cleanup completed.")
        sys.exit(0)
    
    if args.backup:
        backup_prev_version()
        sys.exit(0)

    build_mode = "release" if args.release else "debug"
    print(f"Building {build_mode} version...")

    build(True if args.release else False, args.trace, args.zig, True)


if __name__ == "__main__":
    main()