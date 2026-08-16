import pyautogui
import time

print("3秒后开始持续打印鼠标所在像素颜色，按 Ctrl+C 停止...")
print("请将鼠标移到【复制按钮】上")
time.sleep(3)

try:
    while True:
        x, y = pyautogui.position()
        px = pyautogui.pixel(x, y)
        print(f"坐标:({x:4d},{y:4d})  颜色: RGB{px}", end='\r')
except KeyboardInterrupt:
    print("\n记录结束。")