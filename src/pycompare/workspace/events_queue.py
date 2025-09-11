
from tkinter import *
from pycompare.config import QUEUE_EVENT_LOG

import logging
from pycompare.logging_config import setup_logging
logger = setup_logging(logging.DEBUG, log_tag=__name__)

EVENT_GROUP = {}

def set_event_group(event_group):
    global EVENT_GROUP
    EVENT_GROUP = event_group

def update_cursor_position(text, event, argsdict):
    # logger.debug(f"update_cursor_position 事件")
    text = event.widget
    if text == None or text.cget('state') == 'disabled': return

    tag_area = argsdict.get('tagarea')
    tag_area.tag_remove("selected_text", '1.0', 'end')

    try:
        # 获取光标位置(INSERT标记)
        cursor_pos = text.index(INSERT)
        line, column = map(int, cursor_pos.split('.'))
    
        status_var = argsdict.get('statusbar')
        # 更新状态栏
        status_var.set(
            f"行: {line}, 列: {column}"
        )
    except Exception as e:
        status_var.set(f"错误: {str(e)}")

# 防抖装饰器, isbreak==True，直接返回'break'，终止底层默认操作
def debounce(wait, isbreak=False):
    root = None
    def decorator(func):
        def wrapper(text_area, event=None, *args):
            nonlocal root
            if wait == 0 or not text_area:
                if QUEUE_EVENT_LOG: logger.debug("exec right now!")
                func(text_area, event, *args)
                if isbreak: return 'break'
                else: return
            # 获取事件或编辑区的唯一标识
            event_key = (event.widget, func.__name__) if event else func.__name__
            
            if not root: root = text_area.winfo_toplevel()
            # 取消之前的定时器（如果存在）
            if hasattr(wrapper, '_timers'):
                if event_key in wrapper._timers:
                    root.after_cancel(wrapper._timers[event_key])

            # 设置新的定时器
            wrapper._timers[event_key] = root.after(wait, func, text_area, event, *args)
            if isbreak: return 'break'

        # 初始化 _timers 字典
        if not hasattr(wrapper, '_timers'):
            wrapper._timers = {}
        return wrapper
    return decorator

# 装饰函数工厂（结合防抖）
def group_event_decorator(event_type, debounce_time, isbreak=False):
    """创建一个装饰函数，用于捕获事件并更新组内状态"""
    def decorator(func):
        @debounce(debounce_time, isbreak)  # 应用防抖
        def wrapper(text_area, event=None, *args):
            if QUEUE_EVENT_LOG: logger.debug(f"event_type: {event_type}")
            # current_time = time.time()
            # 获取事件数据
            event_data = {
                "type": event_type  # 事件类型
            }

            event_data1 = None
            if func:
                event_data1 = func(text_area, event, *args)
            if not text_area: return

            discard = any([
                event_data1 == None,
                event_type == "KeyPress" and event_data1.get("invalidkey"),
            ])

            if event_data1 and not discard: event_data.update(event_data1)

            event_queue = text_area.__dict__.get('__eventqueue')
            # 将事件添加到队列且相同事件替换或删掉无效的事件
            replace_same_type_event(event_queue, event_type, event_data, discard)

            # 无效事件，不处理
            if discard:  return
            # 检查队列中是否存在符合分组条件的事件片段
            group, event_data = check_event_groups(event_queue)
            if event_data:
                process_group_events(text_area, group, event_data, *args)

            statusbar = args[0].get('statusbar', None)
            if statusbar:
                update_cursor_position(None, event, *args)
            text_area.edit_modified(False)
            
        return wrapper
    return decorator
    
def replace_same_type_event(event_queue, event_type, new_event, discard):
    """用新事件替换队列中的同类型旧事件"""
    temp_events = []

    # 遍历队列
    while not event_queue.empty():
        event = event_queue.get()
        if event["type"] != event_type:
            temp_events.append(event)
        else: break

    # 将事件重新放回队列
    temp_events.reverse()
    for event in temp_events:
        event_queue.put(event)

    if not discard:
        event_queue.put(new_event)

def check_event_groups(event_queue):
    """检查队列中是否存在符合任何分组条件的事件片段"""
    # 从队列中取出事件
    event = event_queue.get()
    if QUEUE_EVENT_LOG:
        logger.debug(f"check event, event: {event}")

    # 检查所有分组
    for group in EVENT_GROUP:
        edit_events = group["editevent"]
        required_events = group.get("required", [])
        option_events = group.get("option", [])

        if event["type"] in edit_events:
            option_event = retrieve_target_event(event_queue, option_events) if option_events else None
            if not required_events:
                clear_event_queue(event_queue)  # 清空事件队列
                return group, {"editevent": event, "option": option_event}
            if required_events:
                required_event = retrieve_target_event(event_queue, required_events)
                if required_event:
                    clear_event_queue(event_queue)  # 清空事件队列
                    # 如果 required 事件已发生，处理事件组
                    return group, {"editevent": event, "required": required_event, "option": option_event}
                else:
                    event_queue.put(event)
        # 如果事件是 required 事件
        elif event["type"] in required_events:
            # 如果是required事件，按照事件顺序是等待editevent发生，直接放回队列
            event_queue.put(event)
        else:
            # 如果事件不匹配任何分组，重新放回队列
            event_queue.put(event)
    return None, None

def retrieve_target_event(event_queue, target_events):
    """获取对应的 required 事件"""
    # 遍历队列，获取 required 事件
    temp_events = []
    required_event_data = None
    while not event_queue.empty():
        event = event_queue.get()
        temp_events.append(event)
        if event["type"] in target_events:
            required_event_data = event
            break
    # 将事件重新放回队列
    temp_events.reverse()
    for event in temp_events:
        event_queue.put(event)
    return required_event_data

def clear_event_queue(event_queue):
    """清空事件队列"""
    while not event_queue.empty():
        event_queue.get()