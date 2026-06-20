/* PPOCRCapture.app 的主可执行文件（Mach-O）。
 * 作用：作为 App Bundle 被 launchd 直接启动，从而让 TCC（辅助功能授权）
 * 以 com.ppocr.capture 这个 App 身份记账；随后 exec 切换到项目里的 python。
 * 之所以用编译的 Mach-O 而非 shell 脚本：launchd 不肯把脚本当 Bundle 主程序启动。
 */
#include <unistd.h>
#include <stdio.h>

static const char *PROJ = "/Users/zhuym/Documents/101camp/ppocr";

int main(void) {
    if (chdir(PROJ) != 0) {
        perror("[launcher] chdir");
        return 70;
    }
    char *const argv[] = {
        "/Users/zhuym/Documents/101camp/ppocr/.venv/bin/python",
        "/Users/zhuym/Documents/101camp/ppocr/capture.py",
        NULL,
    };
    execv(argv[0], argv);
    perror("[launcher] execv");   /* 只有 exec 失败才会走到这里 */
    return 71;
}
