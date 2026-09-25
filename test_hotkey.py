import time

from hotkey import HOTKEY_LABEL, HotkeyListener


def hit():
    print(">>> 快捷键触发成功!")


h = HotkeyListener(hit)
h.start()
print(f"请在 10 秒内按 {HOTKEY_LABEL}（或映射了该快捷键的鼠标键）...")
time.sleep(10)
print("结束")
