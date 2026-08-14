/* PPOCRCapture.app 的主可执行文件（Mach-O）。
 * 作用：作为 App Bundle 被 launchd 直接启动，从而让 TCC（辅助功能授权）
 * 以 com.ppocr.capture 这个 App 身份记账；随后 exec 切换到项目里的 python。
 * 之所以用编译的 Mach-O 而非 shell 脚本：launchd 不肯把脚本当 Bundle 主程序启动。
 *
 * 项目路径由编译期注入，源码里不含任何机器专属路径 —— 否则每个人都得改这个
 * 文件才能跑起来，改完一提交就把自己的路径带进仓库（历史上发生过两次）。
 * 由 install.sh 负责传入，手动编译见 README。
 */
#include <unistd.h>
#include <stdio.h>

#ifndef PROJ_DIR
#error "缺少 PROJ_DIR。请用 install.sh 构建，或手动指定：cc -DPROJ_DIR='\"/path/to/ppocr\"' -O2 -o ppocr-capture launcher.c"
#endif

static const char *PROJ = PROJ_DIR;

int main(void) {
    if (chdir(PROJ) != 0) {
        perror("[launcher] chdir");
        return 70;
    }
    /* 相邻字符串字面量在编译期拼接，因此这里同样不含硬编码用户名。 */
    char *const argv[] = {
        PROJ_DIR "/.venv/bin/python",
        PROJ_DIR "/capture.py",
        NULL,
    };
    execv(argv[0], argv);
    perror("[launcher] execv");   /* 只有 exec 失败才会走到这里 */
    return 71;
}
