# build_exe.ps1
# Usage:
#   .\release_exe\build_exe.ps1             # 构建项目
#   .\release_exe\build_exe.ps1 --clean     # 清理临时文件

# 定义一个清除函数
function Clean-Folder {
    param (
        [string]$FolderPath
    )

    # 如果路径包含通配符（如 *.build），使用 Get-ChildItem 查找
    if ($FolderPath -like "*.build" -or $FolderPath -like "*.dist" -or $FolderPath -like "*.onefile-build") {
        $items = Get-ChildItem -Path . -Filter $FolderPath -Directory -ErrorAction SilentlyContinue
    } else {
        $items = Get-ChildItem -Path $FolderPath -ErrorAction SilentlyContinue | Where-Object { $_.PSProvider.Name -eq "FileSystem" }
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
$exeName = "pycompare-gui-$ver.exe"
if (Test-Path $exeName) {
    Remove-Item $exeName
    Write-Host "🗑️  Removed old exe: $exeName" -ForegroundColor Yellow
}

# 清理临时构建目录
Clean-Temp

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


# === 打包 ===
python -m nuitka `
  --standalone `
  --onefile `
  --windows-console-mode=attach `
  --enable-plugin=tk-inter `
  --include-package=pycompare `
  --output-file="pycompare-gui-$ver.exe" `
  main.py

# === 清理临时文件 ===
#if (Test-Path "main.py") {
#    Remove-Item "main.py"
#}

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Done -> pycompare-gui-$ver.exe" -ForegroundColor Green
} else {
    Write-Host "❌ Build failed with exit code: $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

# --no-dependency-walker \
# --windows-icon-from-ico=app.ico

#python -m nuitka `
#  --standalone `                    # 启用独立打包
#  --onefile `                       # 打包为单个exe
#  --windows-console-mode=disable `  # 禁用控制台窗口（GUI应用）
#  --enable-plugin=tk-inter `        # 启用Tkinter支持
#  --include-package=pycompare `     # 包含pycompare包
#  --output-file="pycompare-gui-$ver.exe" `  # 使用版本号命名
#  src/pycompare/pycompare.py
#