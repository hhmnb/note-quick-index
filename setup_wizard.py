import os
import sys
import json
import pyautogui

CONFIG_FILE = "config.json"

def print_step(title):
    print("\n" + "=" * 50)
    print(f"  {title}")
    print("=" * 50)

def wait_for_click(prompt):
    """等待用户将鼠标移到目标位置后按 Enter，记录坐标"""
    print(f"\n🎯 {prompt}")
    print("   将鼠标移动到目标位置，然后回到这个窗口按 Enter...")
    input("   按 Enter 确认坐标 >> ")
    x, y = pyautogui.position()
    print(f"   ✅ 已记录坐标: ({x}, {y})")
    return (x, y)

def main():
    print("\n" + "🧙" * 20)
    print("     DeepSeek 笔记自动化 - 初始化向导")
    print("🧙" * 20)

    config = {}

    # ---- 步骤1: 笔记路径 ----
    print_step("步骤1: 设置笔记仓库路径")
    default_path = os.path.abspath("./_inbox")
    path_input = input(f"   请输入笔记文件夹路径 (直接回车使用默认: {default_path}): ").strip()
    config["notes_folder"] = path_input if path_input else default_path
    if not os.path.exists(config["notes_folder"]):
        print(f"   ⚠️ 文件夹不存在，自动创建: {config['notes_folder']}")
        os.makedirs(config["notes_folder"], exist_ok=True)

    # ---- 步骤2: 采集坐标 ----
    print_step("步骤2: 采集 DeepSeek 网页坐标")
    print("   请确保 DeepSeek 网页已打开并固定在屏幕上。")
    print("   接下来会依次要求你将鼠标移动到各个关键位置。")
    input("   准备好后按 Enter 开始采集坐标 >> ")

    config["coordinates"] = {}

    # 空输入框：用于新对话或专家模式后的首次发送
    print("\n📍 第一步：定位【空输入框】（新对话时没有任何内容的输入框）")
    config["coordinates"]["empty_input_box"] = wait_for_click(
        "将鼠标移到【空输入框的中心位置】（新对话时的输入框），按 Enter"
    )

    # 正常输入框：已有对话记录后的输入框（位置可能偏移）
    print("\n📍 第二步：定位【已有对话时的输入框】")
    config["coordinates"]["normal_input_box"] = wait_for_click(
        "将鼠标移到【已存在对话时的输入框中心位置】（发送一条消息后输入框的位置），按 Enter"
    )

    # 复制按钮：位于最新回复的下方
    config["coordinates"]["copy_btn"] = wait_for_click(
        "将鼠标移到最新回复下方的【复制按钮】上，按 Enter"
    )

    # 可选：重新生成按钮
    use_regen = input("\n   是否需要配置重新生成按钮？(y/n，默认 n): ").strip().lower()
    if use_regen == 'y':
        config["coordinates"]["regen_btn"] = wait_for_click(
            "将鼠标移到【重新生成按钮】上，按 Enter"
        )
    else:
        config["coordinates"]["regen_btn"] = None

    # 自动新建对话 + 专家模式
    use_new_chat = input("\n   是否需要自动新建对话+专家模式？(y/n，默认 y): ").strip().lower()
    if use_new_chat != 'n':
        config["coordinates"]["new_chat_btn"] = wait_for_click(
            "将鼠标移到左侧栏的【新对话按钮】上，按 Enter"
        )
        config["coordinates"]["expert_mode"] = wait_for_click(
            "将鼠标移到【专家模式按钮】上，按 Enter"
        )
    else:
        config["coordinates"]["new_chat_btn"] = None
        config["coordinates"]["expert_mode"] = None

    # ---- 步骤3: 设置运行参数 ----
    print_step("步骤3: 设置运行参数")
    print("   以下参数可直接回车使用默认值")

    # 批量新建对话间隔
    switch_every_str = input("   每处理多少篇笔记后新建一次对话？(默认 100): ").strip()
    config["switch_every"] = int(switch_every_str) if switch_every_str else 100

    # 单篇最大重试次数
    retries_str = input("   单篇笔记最大重试次数 (默认 2): ").strip()
    config["max_retries_per_note"] = int(retries_str) if retries_str else 2

    # 动态等待参数
    char_per_sec_str = input("   理想打字速度 (字/秒，默认 50): ").strip()
    config["char_per_sec"] = float(char_per_sec_str) if char_per_sec_str else 50.0

    slow_char_per_sec_str = input("   保守打字速度 (字/秒，默认 20): ").strip()
    config["slow_char_per_sec"] = float(slow_char_per_sec_str) if slow_char_per_sec_str else 20.0

    min_silent_str = input("   最短静默等待 (秒，默认 5): ").strip()
    config["min_silent"] = int(min_silent_str) if min_silent_str else 5

    max_silent_str = input("   最长静默等待 (秒，默认 30): ").strip()
    config["max_silent"] = int(max_silent_str) if max_silent_str else 30

    min_poll_str = input("   最短轮询超时 (秒，默认 5): ").strip()
    config["min_poll"] = int(min_poll_str) if min_poll_str else 5

    max_poll_str = input("   最长轮询超时 (秒，默认 60): ").strip()
    config["max_poll"] = int(max_poll_str) if max_poll_str else 60

    poll_interval_str = input("   轮询间隔 (秒，默认 5): ").strip()
    config["poll_interval"] = int(poll_interval_str) if poll_interval_str else 5

    # ---- 保存配置 ----
    print_step("配置完成，正在保存...")
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 配置已保存到 {CONFIG_FILE}")
    print("   现在可以直接运行 run_auto.py 开始自动化处理！")
    print("\n" + "=" * 50)

if __name__ == "__main__":
    main()