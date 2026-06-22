from pynput import keyboard
import time


def hit():
    print(">>> 快捷键触发成功!")


h = keyboard.GlobalHotKeys({
    "<ctrl>+<shift>+6": hit,
    "<cmd>+<shift>+6": hit,
})
h.start()
print("请在 10 秒内按 Ctrl+Shift+6 或 Cmd+Shift+6 ...")
time.sleep(10)
print("结束")
