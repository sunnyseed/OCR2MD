from pynput import keyboard
import time


def hit():
    print(">>> 快捷键触发成功!")


h = keyboard.GlobalHotKeys({"<cmd>+<shift>+1": hit})
h.start()
print("请在 10 秒内按 Cmd+Shift+1 ...")
time.sleep(10)
print("结束")
