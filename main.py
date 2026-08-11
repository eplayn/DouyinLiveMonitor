
# coding:utf-8

import sys


def run_gui(live_id=None):
    from chat_window import ChatWindow
    window = ChatWindow()
    if live_id:
        if live_id not in window.anchors:
            window.anchors[live_id] = live_id
            window._save_config()
            window._refresh_anchor_list()
        idx = list(window.anchors.keys()).index(live_id)
        window.anchor_listbox.selection_set(idx)
        window.anchor_listbox.see(idx)
        window._on_anchor_select(None)
    window.run()


def run_console(live_id):
    from liveMan import DouyinLiveWebFetcher
    print(f"【控制台模式】正在连接直播间 {live_id} ...")
    DouyinLiveWebFetcher(live_id).start()


def print_usage():
    print("用法:")
    print("  python main.py               启动 GUI")
    print("  python main.py <直播间ID>     启动 GUI（自动连接）")
    print("  python main.py console <ID>  控制台模式")


if __name__ == '__main__':
    args = sys.argv[1:]
    if not args:
        run_gui()
    elif len(args) == 1 and args[0].isdigit():
        run_gui(live_id=args[0])
    elif len(args) >= 2 and args[0] == 'console':
        run_console(args[1])
    else:
        print_usage()
