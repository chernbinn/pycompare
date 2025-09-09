# build_exe.ps1
if (Test-Path "nuitka_test.log") {
    Remove-Item -Path "nuitka_test.log"
}

python -m nuitka `
  --standalone `
  --onefile `
  --enable-plugin=tk-inter `
  --windows-console-mode=attach `
  --output-file="test-gui.exe" `
  test_gui.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Done -> test-gui-$ver.exe" -ForegroundColor Green
} else {
    Write-Host "❌ Build failed with exit code: $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

# --no-dependency-walker \
# --windows-icon-from-ico=app.ico

#  --include-data-dir="C:/Program Files/Python311/tcl=tcl" `
# 经验证，打包exe时，有没有该配置都可以正常启动图形界面。--enable-plugin=tk-inter是必须要有的

#python -m nuitka `
#  --standalone `                    # 启用独立打包
#  --onefile `                       # 打包为单个exe
#  --windows-console-mode=disable `  # 禁用控制台窗口（GUI应用）
#  --enable-plugin=tk-inter `        # 启用Tkinter支持
#  --include-package=pycompare `     # 包含pycompare包
#  --output-file="pycompare-gui-$ver.exe" `  # 使用版本号命名
#  src/pycompare/pycompare.py
#