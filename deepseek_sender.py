import time
import pyautogui
import pyperclip
from typing import Optional


class DeepSeekWebSender:
    """
    DeepSeek 网页版 RPA 控制器（精简优化版）
    负责模拟键盘鼠标操作，将文本发送到 DeepSeek 网页并复制回复。

    优化点：
        - 剪贴板操作异常时提供备用键入方案（限 ASCII 文本）
        - 固定等待策略：初始静默等待 15 秒后轮询，总超时 600 秒
        - 去掉粘贴后字数验证，加快发送速度
    """

    def __init__(self,
                 empty_input_box: tuple,
                 normal_input_box: tuple,
                 copy_btn: tuple,
                 regen_btn: tuple,
                 new_chat_btn: tuple,
                 expert_btn: tuple,
                 max_retries_per_note: int = 2,
                 poll_interval: int = 3,
                 initial_silent_wait: int = 15,  # 初始静默等待秒数（默认 15 秒）
                 total_timeout: int = 600):  # 总超时秒数
        self.empty_input_box = empty_input_box
        self.normal_input_box = normal_input_box
        self.input_box = empty_input_box
        self.copy_btn = copy_btn
        self.regen_btn = regen_btn
        self.new_chat_btn = new_chat_btn
        self.expert_btn = expert_btn
        self.max_retries_per_note = max_retries_per_note
        self.poll_interval = poll_interval
        self.initial_silent_wait = initial_silent_wait
        self.total_timeout = total_timeout
        self._first_send_done = False

        print("⚠️ 请确保 DeepSeek 网页已打开并保持在前台")
        time.sleep(3)
        pyautogui.FAILSAFE = True

    # ========== 基础操作 ==========
    def _click(self, pos):
        pyautogui.click(pos)
        time.sleep(0.5)

    def _paste_with_fallback(self, text: str):
        """
        尝试用 pyperclip 粘贴，若失败且文本为纯 ASCII，则降级为逐字键入。
        否则抛出异常。
        """
        clipboard_ok = False
        try:
            pyperclip.copy(text)
            clipboard_ok = True
        except Exception as e:
            print(f"    ⚠️ 剪贴板复制异常: {e}")

        if clipboard_ok:
            pyautogui.hotkey('ctrl', 'v')
            return

        # 备用方案：仅支持 ASCII 文本
        if text.isascii():
            print("    降级为 pyautogui.write 逐字键入...")
            pyautogui.write(text, interval=0.01)
        else:
            raise RuntimeError("剪贴板不可用，且文本包含非 ASCII 字符，无法自动键入")

    def _send_message(self, text: str):
        """清空输入框、粘贴文本、按 Enter 发送（无字数验证）"""
        self._click(self.input_box)
        time.sleep(0.3)
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.2)
        pyautogui.press('delete')
        time.sleep(0.2)
        self._click(self.input_box)
        time.sleep(0.2)

        self._paste_with_fallback(text)

        # 直接发送，不验证输入框内容
        pyautogui.press('enter')
        time.sleep(1.0)  # 确保发送完成

    def _try_copy_reply(self) -> str:
        """点击复制按钮，重试最多 3 次，返回剪贴板内容（空字符串表示失败）"""
        try:
            pyperclip.copy("")
        except Exception:
            pass
        time.sleep(0.2)

        for _ in range(3):
            self._click(self.copy_btn)
            time.sleep(0.5)
            try:
                text = pyperclip.paste()
            except Exception as e:
                print(f"    ⚠️ 读取回复剪贴板失败: {e}")
                continue
            if text and len(text.strip()) > 0:
                return text
            time.sleep(0.3)
        return ""

    # ========== 固定等待与轮询 ==========
    def _wait_and_copy(self) -> str:
        """
        固定等待策略：
        1. 静默等待 initial_silent_wait 秒（默认 15 秒）
        2. 总超时 total_timeout 秒（默认 600 秒）
        3. 轮询检测回复，间隔 poll_interval 秒
        """
        silent_wait = self.initial_silent_wait
        total = self.total_timeout
        poll_timeout = max(0, total - silent_wait)

        print(f"    静默等待 {silent_wait}s...", end="", flush=True)
        time.sleep(silent_wait)
        print(" 开始轮询")
        print(f"    轮询最多 {poll_timeout}s（总时限 {total}s）", flush=True)

        start = time.time()
        while time.time() - start < poll_timeout:
            reply = self._try_copy_reply()
            if reply:
                elapsed = silent_wait + int(time.time() - start)
                print(f"    检测到回复（总耗时 {elapsed}s）")
                return reply
            print(f"    未检测到回复，{self.poll_interval}s 后重试...")
            time.sleep(self.poll_interval)

        print("    超过轮询超时，未获取回复")
        return ""

    # ========== 核心发送 ==========
    def send(self, content: str) -> str:
        """
        发送消息并获取回复，失败时在输入框重新发送（最多 max_retries_per_note 次）。
        返回空字符串表示最终失败。
        """
        for attempt in range(1, self.max_retries_per_note + 1):
            try:
                self._send_message(content)
                print(f"    已发送（第{attempt}次），等待回复...")

                reply = self._wait_and_copy()
                if reply:
                    if not self._first_send_done:
                        self.input_box = self.normal_input_box
                        self._first_send_done = True
                    return reply

                print(f"    第{attempt}次尝试未获取回复", end="")
                if attempt < self.max_retries_per_note:
                    print("，2秒后在输入框重新发送...")
                    time.sleep(2)
                else:
                    print("，已达最大尝试次数")

            except Exception as e:
                print(f"    异常: {e}，等待5秒后重试...")
                time.sleep(5)

        return ""

    # ========== 新建对话 + 专家模式 ==========
    def new_chat_with_expert(self):
        if not self.new_chat_btn or not self.expert_btn:
            print("    ⚠️ 未配置新对话/专家模式按钮，跳过新建对话")
            return
        self._click(self.new_chat_btn)
        time.sleep(3)
        self._click(self.expert_btn)
        time.sleep(1)
        self.input_box = self.empty_input_box
        self._first_send_done = False
        self._click(self.input_box)
        time.sleep(0.5)
        print("    🆕 已新建对话并开启专家模式")