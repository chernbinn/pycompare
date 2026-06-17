#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nuitka 构建脚本
用法:
    python build_exe.py              # 构建项目
    python build_exe.py --clean      # 仅清理临时文件
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


def clean_temp(backup_exe: bool = True) -> None:
    """清理构建临时文件，并可选择备份已生成的 exe"""
    print("🧹 Cleaning temporary folders...")

    if backup_exe and DIST_DIR.exists():
        exe_files = list(DIST_DIR.glob("*.exe"))
        if exe_files:
            print(f"📋 Found {len(exe_files)} exe files in dist directory.")
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            for exe in exe_files:
                print(f"📋 Backing up {exe.name} to backup")
                shutil.copy2(exe, BACKUP_DIR / exe.name)

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

def build(release: bool = False):
    """执行 Nuitka 构建"""
    # 清理旧文件
    clean_temp(backup_exe=True)

    # 确保目录存在
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # 确保入口文件
    ensure_main_py(release)

    # 获取版本
    ver = get_git_tag()
    timestamp = time.strftime("%Y%m%d%H%M%S")
    exe_name = f"pycompare-gui-{ver}-{timestamp}.exe"
    opt_exe_name = f"pycompare-gui-{ver}-{timestamp}-opt.exe"

    print(f"Building {exe_name} ...")

    # 清除 Nuitka 缓存
    subprocess.run([sys.executable, "-m", "nuitka", "--clean-cache=all"], check=False)

    console_mode = "attach"
    release_args = []
    if release:
        console_mode = "disable"
        release_args.append("--assume-yes-for-downloads")

    # 构建 Nuitka 命令参数列表
    nuitka_args = [
        sys.executable, "-m", "nuitka",
        *release_args,
        "--standalone",
        "--onefile",
        "--onefile-no-dll",
        "--windows-icon-from-ico=assets/logo.ico",
        f"--windows-console-mode={console_mode}",
        f"--output-dir={DIST_DIR}",
        f"--show-modules-output={DIST_DIR / 'modules.txt'}",
        f"--report={DIST_DIR / 'report.xml'}",
        "--enable-plugin=implicit-imports",
        "--enable-plugin=tk-inter",
        "--enable-plugin=multiprocessing",
        "--enable-plugin=anti-bloat",
        "--enable-plugin=no-qt",
        "--include-package=pycompare",
        "--nofollow-import-to=pycompare.compare_core.compare_core",
        "--nofollow-import-to=numpy",
        "--nofollow-import-to=unittest",
        "--nofollow-import-to=ipaddress",
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
        "--onefile-no-compression",
        "--onefile-as-archive",
        "--clean-cache=all",
        "--cf-protection=none",
        "--lto=yes",
        "--jobs=4",
        "--prefer-source-code",
        "--no-debug-c-warnings",
        "--no-debug-immortal-assumptions",
        "--warn-implicit-exceptions",
        "--warn-unusual-code",
        "--python-flag=-O,no_docstrings,-u,isolated,-P,no_warnings,-S",
        "--no-pyi-stubs",
        "--no-pyi-file",
        "--deployment",
        f"--output-filename={exe_name}",
        "main.py"
    ]


    # 执行 Nuitka
    result = subprocess.run(nuitka_args, cwd=ROOT_DIR)
    if result.returncode != 0:
        print(f"❌ Nuitka build failed with exit code: {result.returncode}")
        sys.exit(result.returncode)

    # 压缩输出
    exe_path = DIST_DIR / exe_name
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
    args = parser.parse_args()

    if args.clean:
        clean_temp(backup_exe=False)
        print("✅ Cleanup completed.")
        sys.exit(0)

    build_mode = "release" if args.release else "debug"
    print(f"Building {build_mode} version...")

    build(True if args.release else False)


if __name__ == "__main__":
    main()