
使用脚本编译，运行程序的时候，总是报错，而纯python运行，代码没有异常，因此编写最小模块进行测试
python -m nuitka --mode=standalone --windows-console-mode=force --zig --include-windows-runtime-dlls=yes test_min_main.py

错误log如下：
pycompare> .\test_min.dist\test_min.exe
Traceback (most recent call last):
  File "F:\PYTHON~1\OWN_PR~1\SHELLC~1\PYCOMP~1\TEST_M~1.DIS\test_min.py", line 1, in <module>
  File "F:\PYTHON~1\OWN_PR~1\SHELLC~1\PYCOMP~1\TEST_M~1.DIS\psutil\__init__.py", line 102, in <module psutil>
  File "F:\PYTHON~1\OWN_PR~1\SHELLC~1\PYCOMP~1\TEST_M~1.DIS\psutil\_pswindows.py", line 29, in <module psutil._pswindows>
ImportError

解决方案：
1.删除已有的使用uv创建的虚拟环境
2.使用python venv创建新的虚拟环境
3.使用uv sync --extra dev安装环境后，重新执行最小打包测试
4.验证通过