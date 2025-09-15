# PyCompare 文本对比工具文档

## 功能概述
PyCompare 是一个基于 Python 和 Tkinter 的文本对比工具，主要功能包括：

- 并行文本对比
- 差异高亮显示
- 文件历史记录管理
- 行号同步显示
- 支持文件拖拽
- 支持utf-8编码
- 临时修改文件内容，不影响源文件内容

## 核心模块

### 主要类与方法

1. **ParallelMatcher** - 并行相似度计算
   - `get_ratio()`: 计算两行文本的相似度
   - `process_row()`: 并行处理矩阵行

2. **DynamicSharedArray** - 共享内存管理
   - 用于进程间高效数据传递

3. **MatcherConfig** - 配置类
   - 定义相似度计算参数

## 使用示例

![img](assets/images/效果图1.png)

![img](assets/images/效果图2.png)

## 快捷键

- F5: 刷新对比结果
