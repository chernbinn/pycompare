# build_exe.ps1
# Usage:
#   .\release_exe\build_exe.ps1             # 构建项目
#   .\release_exe\build_exe.ps1 --clean     # 清理临时文件

Write-Host "❌ 已废弃，请使用 build_exe.py 构建项目." -ForegroundColor Red
exit 0

# 定义一个清除函数
function Clean-Folder {
    param (
        [string]$FolderPath
    )

    # 如果路径包含通配符（如 *.build），使用 Get-ChildItem 查找
    if ($FolderPath -like "*.build" -or $FolderPath -like "*.dist" -or $FolderPath -like "*.onefile-build") {
        $items = Get-ChildItem -Path . -Filter $FolderPath -Directory -ErrorAction SilentlyContinue
    } else {
        # $items = Get-ChildItem -Path $FolderPath -ErrorAction SilentlyContinue | Where-Object { $_.PSProvider.Name -eq "FileSystem" }
        # 获取路径本身（文件或目录）
        $item = Get-Item -Path $FolderPath -ErrorAction SilentlyContinue
        if ($item -and $item.PSProvider.Name -eq "FileSystem") {
            $items = $item
        }
    }

    if ($items) {
        foreach ($item in $items) {
            Write-Host "🗑️  Deleting $($item.FullName)" -ForegroundColor Yellow
            Remove-Item $item.FullName -Recurse -Force
        }
    } else {
        # Write-Host "✅ No matching path found: $FolderPath" -ForegroundColor Gray
    }
}

# 统一清理函数
function Clean-Temp {
    Write-Host "🧹 Cleaning temporary folders..." -ForegroundColor Yellow    

    # 如果dist目录下存在exe文件，拷贝到dist目录的父目录的backup目录
    if (Test-Path "dist") {
        $exeFiles = Get-ChildItem -Path "dist" -Filter "*.exe" -File
        if ($exeFiles) {
            Write-Host "📋 Found $($exeFiles.Count) exe files in dist directory." -ForegroundColor Cyan
            Write-Host "📋 Backing up exe files to backup directory" -ForegroundColor Cyan
            $backupDir = Join-Path -Path "." -ChildPath "backup"
            if (-not (Test-Path $backupDir)) {
                New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
            }
            foreach ($file in $exeFiles) {
                Write-Host "📋 Copying $($file.FullName) to $backupDir" -ForegroundColor Cyan
                Copy-Item -Path $file.FullName -Destination $backupDir -Force
            }
        }
    }

    # 普通目录
    Clean-Folder -FolderPath "build"
    Clean-Folder -FolderPath "dist"

    # 通配符匹配的临时目录（Nuitka 生成）
    Clean-Folder -FolderPath "*.onefile-build"
    Clean-Folder -FolderPath "*.build"
    Clean-Folder -FolderPath "*.dist"
}

# ========== 清理功能 ==========
if ($args.Count -gt 0 -and ($args[0] -eq 'clean' -or $args[0] -eq '-clean' -or $args[0] -eq '--clean')) {
    Clean-Temp
    Write-Host "✅ Cleanup completed." -ForegroundColor Green
    exit 0
}

# ========== 构建流程开始 ==========
$ver = $(git describe --tags --always)
Write-Host "Building pycompare $ver ..." -ForegroundColor Green

# === 清理旧文件 ===
# 清理临时构建目录
Clean-Temp
$dir = "dist"
if (-not (Test-Path $dir)) {
    New-Item -ItemType Directory -Path $dir
}

# === 创建入口文件 ===
if (-not (Test-Path "main.py")) {
    @"
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from pycompare.pycompare import cli
if __name__ == "__main__":
    cli()
"@ | Out-File -Encoding utf8 main.py
}

# 清除缓存
python -m nuitka --clean-cache=all

# === 打包 ===
# 当前时间
$now = Get-Date -Format "yyyyMMddHHmmss"
$exe_name = "pycompare-gui-$ver-$now.exe"
$opt_exe_name = "pycompare-gui-$ver-$now-opt.exe"
Write-Host "Building $exe_name ..." -ForegroundColor Green
python -m nuitka `
  --standalone `
  --onefile `
  --onefile-no-dll `
  --windows-icon-from-ico=logo.ico `
  --windows-console-mode=disable `
  --output-dir=dist `
  --show-modules-output=dist/modules.txt `
  --report=dist/report.xml `
  --enable-plugin=implicit-imports `
  --enable-plugin=tk-inter `
  --enable-plugin=multiprocessing `
  --enable-plugin=anti-bloat `
  --enable-plugin=no-qt `
  --include-package=pycompare `
  --nofollow-import-to=pycompare.compare_core.compare_core `
  --nofollow-import-to=numpy `
  --nofollow-import-to=unittest `
  --nofollow-import-to=ipaddress `
  --nofollow-import-to=mailcap `
  --nofollow-import-to=smtplib `
  --nofollow-import-to=ftplib `
  --nofollow-import-to=imaplib `
  --nofollow-import-to=poplib `
  --nofollow-import-to=email `
  --nofollow-import-to=webbrowser `
  --nofollow-import-to=netrc `
  --nofollow-import-to=ssl `
  --nofollow-import-to=colorama `
  --nofollow-import-to=*.tests `
  --nofollow-import-to=*.test `
  --nofollow-import-to=*.testing `
  --nofollow-import-to=*.debug `
  --noinclude-pytest-mode=error `
  --noinclude-unittest-mode=error `
  --noinclude-setuptools-mode=error `
  --noinclude-IPython-mode=error `
  --noinclude-dask-mode=error `
  --noinclude-numba-mode=error `
  --noinclude-pydoc-mode=error `
  --noinclude-data-files=*.pyc `
  --noinclude-data-files=*.pyo `
  --noinclude-data-files=*.txt `
  --noinclude-data-files=*.md `
  --noinclude-data-files=*.rst `
  --noinclude-data-files=*.html `
  --noinclude-data-files=*.log `
  --onefile-no-compression `
  --onefile-as-archive `
  --clean-cache=all `
  --cf-protection=none `
  --lto=yes `
  --jobs=4 `
  --prefer-source-code `
  --no-debug-c-warnings `
  --no-debug-immortal-assumptions `
  --warn-implicit-exceptions `
  --warn-unusual-code `
  --python-flag=-O,no_docstrings,-u,isolated,-P,no_warnings,-S `
  --no-pyi-stubs `
  --no-pyi-file `
  --deployment `
  --output-filename=$exe_name `
  main.py
#upx --best --lzma --compress-icons=0 --compress-exports=1 -9 $exe_name
upx --ultra-brute --lzma --compress-icons=0 --compress-exports=1 dist/$exe_name -o dist/$opt_exe_name

# === 清理临时文件 ===
#if (Test-Path "main.py") {
#    Remove-Item "main.py"
#}

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Done -> $exe_name" -ForegroundColor Green
} else {
    Write-Host "❌ Build failed with exit code: $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

# --no-dependency-walker  不校验依赖
# --windows-icon-from-ico=app.ico 为exe添加图标
# --windows-console-mode=attach  调试使用
# --mingw64 编译c\c++代码相对更优且更省控件；不使用该选项时，默认使用windows自带编译工具
# --module-name-choice=original  不使用相对导入，使启动更快
# --clean-cache=all不使用缓存
# --onefile-as-archive 外部归档方式打包exe，即可解压
# --onefile-no-compression 不压缩
# --enable-plugin=implicit-imports 自动处理隐式导入的模块
# --disable-plugin=implicit-imports 禁用自动处理隐式导入的模块
# --show-modules-output=dist/modules.txt 记录导入的包，用于分析优化打包依赖

#python -m nuitka `
#  --standalone `                    # 启用独立打包
#  --onefile `                       # 打包为单个exe
#  --windows-console-mode=disable `  # 禁用控制台窗口（GUI应用）
#  --enable-plugin=tk-inter `        # 启用Tkinter支持
#  --include-package=pycompare `     # 包含pycompare包
#  --output-file="pycompare-gui-$ver.exe" `  # 使用版本号命名
#  src/pycompare/pycompare.py
#

