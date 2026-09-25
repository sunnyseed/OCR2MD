"""全局快捷键 Ctrl+Shift+6 / Cmd+Shift+6 的监听，capture.py 与 test_hotkey.py 共用。"""

import Quartz
from pynput import keyboard

# Ctrl 与 Cmd 两个键位都注册，两种手感都能触发（PR #1 引入的做法，此处恢复）。
# 选 6 的依据：本机 Cmd+Shift+2/4/5 已被截图功能占用（2=拷贝选区、4=选区截图、
# 5=截屏选项），6 空闲——系统默认是 Touch Bar 截图，而 Mac14,5 无 Touch Bar。
# 若与第三方工具（Raycast/Magnet 的绑定无法程序化枚举）冲突，改成 7/8/9/0——
# 这几个完全没有系统默认，比 6 少一层依赖假设。
HOTKEY_LABEL = "Ctrl+Shift+6 或 Cmd+Shift+6"
_VK_6 = 22  # kVK_ANSI_6，按物理键位匹配，不受 Shift 后字符变成 ^ 的影响
_MOD_MASK = (
    Quartz.kCGEventFlagMaskCommand
    | Quartz.kCGEventFlagMaskControl
    | Quartz.kCGEventFlagMaskShift
    | Quartz.kCGEventFlagMaskAlternate
)
_WANTED_MODS = {
    Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskShift,
    Quartz.kCGEventFlagMaskControl | Quartz.kCGEventFlagMaskShift,
}


class HotkeyListener(keyboard.Listener):
    """按下 6 时直接看这一个事件上带的修饰键标志，而不是像 GlobalHotKeys 那样
    靠之前收到的 Cmd/Shift 按下事件累计状态。

    Logi Options+ 把鼠标键映射成快捷键时，只合成一个带 Cmd+Shift 标志的「6」
    keyDown，不发单独的修饰键事件，GlobalHotKeys 因此永远凑不齐组合键。
    _handle_message 是 pynput 的内部方法，升级 pynput 后需确认签名未变。
    """

    def __init__(self, callback):
        super().__init__(on_press=self._on_press)
        self._callback = callback
        self._event_mods = 0

    def _handle_message(self, proxy, event_type, event, refcon, *args):
        if event_type == Quartz.kCGEventKeyDown:
            self._event_mods = Quartz.CGEventGetFlags(event) & _MOD_MASK
        return super()._handle_message(proxy, event_type, event, refcon, *args)

    def _on_press(self, key):
        if getattr(key, "vk", None) == _VK_6 and self._event_mods in _WANTED_MODS:
            self._callback()
