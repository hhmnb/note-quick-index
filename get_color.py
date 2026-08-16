import pyautogui, time
print("3秒后开始显示鼠标所指像素颜色，Ctrl+C 停止")
time.sleep(3)
try:
    while True:
        x, y = pyautogui.position()
        px = pyautogui.pixel(x, y)
        print(f"({x:4d},{y:4d}) RGB{px}", end='\r')
except KeyboardInterrupt:
    print("\n结束。")