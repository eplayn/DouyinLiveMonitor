
# coding:utf-8

import json
import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox
from datetime import datetime, date

import requests

from liveMan import DouyinLiveWebFetcher

CONFIG_FILE = "config.json"


# ==================== 通过 API 获取直播间信息 ====================
def fetch_room_info(rid, cookie=""):
    """通过直播间 ID 获取主播昵称和开播状态，失败返回 None。
    开播状态无需 Cookie；传 Cookie 可额外获取直播流用于播放。
    """
    try:
        session = requests.Session()
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
        session.headers.update({"User-Agent": ua})

        cookie_str = cookie
        if not cookie_str:
            session.get("https://live.douyin.com/", timeout=10)
            ttwid = session.cookies.get("ttwid")
            if not ttwid:
                return None
            cookie_str = f"ttwid={ttwid}"

        url = (
            "https://live.douyin.com/webcast/room/web/enter/?aid=6383"
            "&app_name=douyin_web&live_id=1&device_platform=web&language=zh-CN"
            "&enter_from=page_refresh&cookie_enabled=true"
            "&screen_width=1920&screen_height=1080&browser_language=zh-CN"
            "&browser_platform=Win32&browser_name=Chrome&browser_version=140.0.0.0"
            f"&web_rid={rid}&room_id_str={rid}"
            "&enter_source=&is_need_double_stream=false&insert_task_id=&live_reason="
            "&msToken=" + __import__('random').choice('abcdefghijklmnopqrstuvwxyz0123456789') * 107
        )
        headers = {
            "Referer": f"https://live.douyin.com/{rid}",
            "Cookie": cookie_str,
        }
        resp = session.get(url, headers=headers, timeout=10)
        data = resp.json().get("data", {})
        if not data:
            return None

        user = data.get("user", {})
        room_list = data.get("data", [])
        room = room_list[0] if room_list else {}
        # status == 2 表示正在直播
        is_live = room.get("status") == 2
        return {
            "nickname": user.get("nickname", ""),
            "is_live": is_live,
            "title": room.get("title", ""),
            "user_count": room.get("user_count_str", "0"),
            "streams": extract_streams(room) if is_live else {},
        }
    except Exception:
        return None


def fetch_anchor_name(rid, cookie=""):
    info = fetch_room_info(rid, cookie)
    return info["nickname"] if info and info["nickname"] else None


def extract_streams(room):
    streams = {}
    flv = room.get('stream_url', {}).get('flv_pull_url', {})
    for k, v in flv.items():
        streams[k] = v
    sdk = room.get('stream_url', {}).get('live_core_sdk_data', {})
    data_str = sdk.get('pull_data', {}).get('stream_data', '')
    if data_str:
        try:
            sd = json.loads(data_str).get('data', {})
            o = sd.get('origin', {}).get('main', {}).get('flv')
            a = sd.get('ao', {}).get('main', {}).get('flv')
            if o: streams['origin'] = o
            if a: streams['audio'] = a
        except Exception: pass
    return streams


QUALITY_ORDER = ['origin', 'FULL_HD1', 'HD1', 'SD2', 'SD1', 'audio']
QUALITY_NAMES = {'origin': '原画', 'FULL_HD1': '蓝光', 'HD1': '超清', 'SD2': '高清', 'SD1': '标清', 'audio': '仅音频'}


def play_with_potplayer(url):
    for p in [r"C:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe",
              r"C:\Program Files (x86)\DAUM\PotPlayer\PotPlayerMini.exe",
              r"C:\Program Files\PotPlayer\PotPlayerMini64.exe"]:
        if os.path.exists(p):
            subprocess.Popen([p, url])
            return True
    return False


# ==================== 配置文件操作 ====================
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                if "anchors" not in config:
                    config["anchors"] = {}
                if "cookie" not in config:
                    config["cookie"] = ""
                return config
        except Exception as e:
            print(f"【X】加载 config.json 失败: {e}")
    return {"anchors": {}, "cookie": ""}


def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ==================== 添加主播对话框 ====================
class AddAnchorDialog(tk.Toplevel):
    def __init__(self, parent, cookie=""):
        super().__init__(parent)
        self.title("添加主播")
        self.geometry("300x200")
        self.configure(bg="#2d2d2d")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self._fetching = False
        self._cookie = cookie

        self._build_ui()
        self._center(parent)

    def _center(self, parent):
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 300) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 200) // 2
        self.geometry(f"+{x}+{y}")

    def _build_ui(self):
        tk.Label(self, text="直播间ID:", font=("微软雅黑", 10),
                 fg="#cccccc", bg="#2d2d2d").pack(pady=(15, 5))
        self.rid_entry = tk.Entry(self, font=("微软雅黑", 10), bg="#3c3c3c",
                                  fg="#ffffff", insertbackground="#ffffff",
                                  relief=tk.FLAT)
        self.rid_entry.pack(padx=20, fill=tk.X)
        self.rid_entry.focus()

        tk.Label(self, text="主播名称（留空自动获取）:", font=("微软雅黑", 10),
                 fg="#cccccc", bg="#2d2d2d").pack(pady=(10, 5))
        self.name_entry = tk.Entry(self, font=("微软雅黑", 10), bg="#3c3c3c",
                                   fg="#ffffff", insertbackground="#ffffff",
                                   relief=tk.FLAT)
        self.name_entry.pack(padx=20, fill=tk.X)

        self.fetch_hint = tk.Label(self, text="", font=("微软雅黑", 8),
                                   fg="#888888", bg="#2d2d2d")
        self.fetch_hint.pack(pady=(4, 0))

        btn_frame = tk.Frame(self, bg="#2d2d2d")
        btn_frame.pack(pady=12)
        self.confirm_btn = tk.Button(btn_frame, text="确定", font=("微软雅黑", 10),
                                     bg="#007acc", fg="#ffffff", padx=20,
                                     relief=tk.FLAT, cursor="hand2",
                                     command=self._confirm)
        self.confirm_btn.pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", font=("微软雅黑", 10),
                  bg="#3c3c3c", fg="#cccccc", padx=20,
                  relief=tk.FLAT, cursor="hand2",
                  command=self.destroy).pack(side=tk.LEFT, padx=10)

        self.rid_entry.bind("<Return>", lambda e: self.name_entry.focus())
        self.name_entry.bind("<Return>", lambda e: self._confirm())
        self.bind("<Escape>", lambda e: self.destroy())

    def _confirm(self):
        if self._fetching:
            return
        rid = self.rid_entry.get().strip()
        if not rid:
            messagebox.showwarning("提示", "直播间ID不能为空", parent=self)
            return

        name = self.name_entry.get().strip()
        if name:
            # 用户已手动输入名称，直接确认
            self.result = (rid, name)
            self.destroy()
            return

        # 名称留空，自动获取
        self._fetching = True
        self.confirm_btn.config(state=tk.DISABLED, text="获取中...")
        self.fetch_hint.config(text="⏳ 正在获取主播名称...", fg="#888888")
        self.update()

        def do_fetch():
            fetched = fetch_anchor_name(rid, self._cookie)
            self.after(0, lambda: self._on_name_fetched(rid, fetched))

        threading.Thread(target=do_fetch, daemon=True).start()

    def _on_name_fetched(self, rid, name):
        self._fetching = False
        if name:
            self.result = (rid, name)
            self.destroy()
        else:
            self.confirm_btn.config(state=tk.NORMAL, text="确定")
            self.fetch_hint.config(text="⚠️ 获取失败，请手动输入名称", fg="#ffaa00")
            self.name_entry.focus()


# ==================== 主窗口 ====================
class ChatWindow:
    """抖音直播弹幕实时聊天窗口"""

    def __init__(self):
        self.fetcher: DouyinLiveWebFetcher = None
        self.msg_queue = queue.Queue()
        self.running = False

        self.config = load_config()
        self.anchors: dict = self.config.setdefault("anchors", {})
        self.cookie: str = self.config.setdefault("cookie", "")
        self._anchor_status: dict = {}   # rid -> {'is_live', 'title', ...}
        self._data_dir = "data"
        self._current_rid = None
        self._current_date = None
        self._pending_rid = None
        self._save_lock = threading.Lock()

        self._build_ui()

    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("抖音直播弹幕")
        self.root.geometry("500x650")
        self.root.configure(bg="#1e1e1e")

        # ---- 主播管理区域 ----
        anchor_frame = tk.LabelFrame(self.root, text="主播列表", font=("微软雅黑", 10, "bold"),
                                     fg="#cccccc", bg="#2d2d2d", relief=tk.GROOVE, bd=2)
        anchor_frame.pack(fill=tk.X, padx=10, pady=(10, 0))

        list_container = tk.Frame(anchor_frame, bg="#2d2d2d")
        list_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))

        scrollbar = tk.Scrollbar(list_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.anchor_listbox = tk.Listbox(list_container, height=3, font=("微软雅黑", 10),
                                         bg="#3c3c3c", fg="#ffffff",
                                         selectbackground="#007acc",
                                         yscrollcommand=scrollbar.set,
                                         relief=tk.FLAT, bd=0,
                                         exportselection=False)
        self.anchor_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.anchor_listbox.yview)
        self._refresh_anchor_list()

        btn_bar = tk.Frame(anchor_frame, bg="#2d2d2d")
        btn_bar.pack(fill=tk.X, padx=8, pady=(0, 8))
        tk.Button(btn_bar, text="➕ 添加", font=("微软雅黑", 9), bg="#3c3c3c", fg="#ffffff",
                  relief=tk.FLAT, cursor="hand2", command=self._add_anchor).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_bar, text="✖ 删除", font=("微软雅黑", 9), bg="#3c3c3c", fg="#ffffff",
                  relief=tk.FLAT, cursor="hand2", command=self._del_anchor).pack(side=tk.LEFT, padx=2)

        self.anchor_listbox.bind('<<ListboxSelect>>', self._on_anchor_select)

        # ---- 控制栏 ----
        control_frame = tk.Frame(self.root, bg="#1e1e1e")
        control_frame.pack(fill=tk.X, padx=10, pady=(6, 0))

        self.check_all_btn = tk.Button(control_frame, text="🔍 一键检测", command=self._check_all_anchors,
                                       bg="#007acc", fg="#ffffff", font=("微软雅黑", 10),
                                       relief=tk.FLAT, padx=10, pady=2,
                                       activebackground="#005a99", activeforeground="#ffffff")
        self.check_all_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.play_btn = tk.Button(control_frame, text="▶ 播放", command=self._play_best,
                                  bg="#3c3c3c", fg="#4ec9ff", font=("微软雅黑", 9),
                                  relief=tk.FLAT, padx=8, pady=1,
                                  activebackground="#3c3c3c", activeforeground="#ffffff")
        self.play_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.play_btn.bind('<Button-3>', self._quality_menu)

        self.cookie_btn = tk.Button(control_frame, text="Cookie", command=self._show_cookie_config,
                                    bg="#3c3c3c", fg="#888888", font=("微软雅黑", 8),
                                    relief=tk.FLAT, padx=6, pady=1,
                                    activebackground="#3c3c3c", activeforeground="#ffffff")
        self.cookie_btn.pack(side=tk.LEFT)

        # ---- 消息过滤栏 ----
        filter_frame = tk.Frame(self.root, bg="#1e1e1e")
        filter_frame.pack(fill=tk.X, padx=10, pady=(2, 0))

        self._msg_filters = {}
        self._filter_vars = {}
        # 根开关
        self._filter_root_var = tk.BooleanVar(value=False)
        root_cb = tk.Checkbutton(filter_frame, text="全部", variable=self._filter_root_var,
                                 bg="#1e1e1e", fg="#cccccc", font=("微软雅黑", 9),
                                 selectcolor="#1e1e1e", relief=tk.FLAT,
                                 activebackground="#1e1e1e", activeforeground="#ffffff",
                                 command=self._on_filter_root_toggle)
        root_cb.pack(side=tk.LEFT, padx=(0, 6))

        # 子开关：类型 -> (显示名, 默认开启)
        _filter_types = [
            ("chat",    "弹幕", True),
            ("gift",    "礼物", False),
            ("like",    "点赞", False),
            ("member",  "进场", False),
            ("social",  "关注", False),
            ("fansclub","粉丝团",False),
            ("emoji",   "表情", False),
        ]
        for ftype, fname, fdefault in _filter_types:
            var = tk.BooleanVar(value=fdefault)
            var.trace_add('write', lambda *a: self._apply_filter_elide())
            cb = tk.Checkbutton(filter_frame, text=fname, variable=var,
                                bg="#1e1e1e", fg="#aaaaaa", font=("微软雅黑", 9),
                                selectcolor="#1e1e1e", relief=tk.FLAT,
                                activebackground="#1e1e1e", activeforeground="#ffffff")
            cb.pack(side=tk.LEFT, padx=2)
            self._msg_filters[ftype] = cb
            self._filter_vars[ftype] = var

        # ---- 分割线 ----
        tk.Frame(self.root, bg="#444444", height=1).pack(fill=tk.X, padx=10, pady=4)

        # ---- 底部状态栏（先 pack，保证缩小窗口时不丢失）----
        status_frame = tk.Frame(self.root, bg="#1e1e1e")
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 6))

        self.viewer_label = tk.Label(status_frame, text="", fg="#ffac33", bg="#1e1e1e",
                                     font=("微软雅黑", 9, "bold"))
        self.viewer_label.pack(side=tk.LEFT)

        self.status_label = tk.Label(status_frame, text="未连接", fg="#888888", bg="#1e1e1e",
                                     font=("微软雅黑", 9), anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, padx=(10, 0))

        # ---- 消息显示区域 ----
        self.chat_area = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            bg="#1e1e1e",
            fg="#d4d4d4",
            font=("微软雅黑", 10),
            relief=tk.FLAT,
            borderwidth=0,
            padx=10,
            pady=10,
            state=tk.DISABLED,
            selectbackground="#264f78",
        )
        self.chat_area.pack(fill=tk.BOTH, expand=True, padx=10)

        # 配置文本标签样式
        self.chat_area.tag_configure("chat", foreground="#e0e0e0")
        self.chat_area.tag_configure("gift", foreground="#ffac33")
        self.chat_area.tag_configure("like", foreground="#f06292")
        self.chat_area.tag_configure("member", foreground="#81c784")
        self.chat_area.tag_configure("social", foreground="#4dd0e1")
        self.chat_area.tag_configure("stats", foreground="#9e9e9e")
        self.chat_area.tag_configure("fansclub", foreground="#ce93d8")
        self.chat_area.tag_configure("emoji", foreground="#fff176")
        self.chat_area.tag_configure("roomstats", foreground="#78909c")
        self.chat_area.tag_configure("control", foreground="#ef5350")
        self.chat_area.tag_configure("system", foreground="#6a9955")

        # ---- 定时检查消息队列 ----
        self._poll_queue()

        # ---- 关闭窗口处理 ----
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # -------------------- 主播管理 --------------------
    def _refresh_anchor_list(self):
        self.anchor_listbox.delete(0, tk.END)
        for rid, name in self.anchors.items():
            status = self._anchor_status.get(rid, {})
            if status.get("is_live"):
                prefix = "[直播] "
            elif status.get("checked"):
                prefix = "[未开] "
            else:
                prefix = ""
            self.anchor_listbox.insert(tk.END, f"{prefix}{name}  ({rid})")

    def _get_selected_rid(self):
        selection = self.anchor_listbox.curselection()
        if not selection:
            return None
        return list(self.anchors.keys())[selection[0]]

    def _on_filter_root_toggle(self):
        """根开关：控制所有子开关勾选状态"""
        enabled = self._filter_root_var.get()
        for var in self._filter_vars.values():
            var.set(enabled)

    def _apply_filter_elide(self):
        """根据子开关隐藏/显示已有消息"""
        for ftype in self._filter_vars:
            hide = not self._filter_vars[ftype].get()
            try:
                self.chat_area.tag_configure(ftype, elide=hide)
            except tk.TclError:
                pass

    def _msg_allowed(self, msg_type):
        """检查消息类型是否被允许显示"""
        var = self._filter_vars.get(msg_type)
        if var is None:
            return True  # 未在过滤列表中的消息类型默认显示
        return var.get()

    def _on_anchor_select(self, event):
        rid = self._get_selected_rid()
        if not rid:
            return
        # 没连接或点自己：正常选中+切换
        if not self._current_rid or rid == self._current_rid:
            self._pending_rid = None
            self._check_status(rid)
            if not self._current_rid:
                self._switch_fetch(rid)
            return
        # 已连接 A，点 B：标蓝+改前缀+检测，不选中不切换
        self._pending_rid = rid
        try:
            idx = list(self.anchors.keys()).index(rid)
            name = self.anchors[rid]
            top = self.anchor_listbox.yview()[0]
            self.anchor_listbox.delete(idx)
            self.anchor_listbox.insert(idx, f"[检测中] {name}  ({rid})")
            self.anchor_listbox.itemconfig(idx, bg="#005a99")
            self.anchor_listbox.yview_moveto(top)
        except (ValueError, tk.TclError):
            pass
        self._check_status(rid)
        self.root.after(1, lambda: self._restore_selection())

    def _restore_selection(self):
        """恢复当前连接主播的选中状态"""
        if self._current_rid and self._current_rid in self.anchors:
            try:
                aidx = list(self.anchors.keys()).index(self._current_rid)
                self.anchor_listbox.selection_clear(0, tk.END)
                self.anchor_listbox.selection_set(aidx)
            except (ValueError, tk.TclError):
                pass

    def _check_status(self, rid):
        """后台检查直播间开播状态"""
        if not self._pending_rid or rid == self._current_rid:
            self._update_status("检测中...")

        def do_check():
            info = fetch_room_info(rid, self.cookie)
            self.root.after(0, lambda: self._on_status_checked(rid, info))

        threading.Thread(target=do_check, daemon=True).start()

    def _on_status_checked(self, rid, info):
        # 处理 pending
        if rid == self._pending_rid:
            self._pending_rid = None
            is_live = info is not None and info["is_live"]
            if info:
                self._anchor_status[rid] = {
                    "checked": True, "is_live": is_live,
                    "title": info["title"], "user_count": info["user_count"],
                    "nickname": info["nickname"], "streams": info.get("streams", {}),
                }
            try:
                idx = list(self.anchors.keys()).index(rid)
                name = self.anchors[rid]
                top = self.anchor_listbox.yview()[0]
                self.anchor_listbox.delete(idx)
                prefix = "[直播] " if is_live else "[未开] "
                self.anchor_listbox.insert(idx, f"{prefix}{name}  ({rid})")
                self.anchor_listbox.yview_moveto(top)
                self.anchor_listbox.itemconfig(idx, bg="#3c3c3c" if not is_live else self.anchor_listbox.cget("bg"))
                if is_live:
                    self.anchor_listbox.selection_clear(0, tk.END)
                    self.anchor_listbox.selection_set(idx)
                    self._switch_fetch(rid)
            except (ValueError, tk.TclError):
                pass
            return

        if info is None:
            if rid == self._get_selected_rid():
                self._update_status("检测失败（可能需要配置 Cookie）")
            return

        is_live = info["is_live"]
        self._anchor_status[rid] = {
            "checked": True,
            "is_live": is_live,
            "title": info["title"],
            "user_count": info["user_count"],
            "nickname": info["nickname"],
            "streams": info.get("streams", {}),
        }
        # 只更新单条，保存滚动位置和选中状态
        try:
            idx = list(self.anchors.keys()).index(rid)
        except ValueError:
            idx = -1
        if idx >= 0:
            name = self.anchors[rid]
            prefix = "[直播] " if is_live else "[未开] "
            top = self.anchor_listbox.yview()[0]
            sel = self.anchor_listbox.curselection()
            self.anchor_listbox.unbind('<<ListboxSelect>>')
            self.anchor_listbox.delete(idx)
            self.anchor_listbox.insert(idx, f"{prefix}{name}  ({rid})")
            self.anchor_listbox.yview_moveto(top)
            for s in sel:
                self.anchor_listbox.selection_set(s)
            self.anchor_listbox.bind('<<ListboxSelect>>', self._on_anchor_select)

        # 状态栏：只显示当前连接的主播，或未连接时显示选中的
        if rid == self._current_rid or (not self._current_rid and rid == self._get_selected_rid()):
            if is_live:
                count = info["user_count"]
                self._update_status(f"● 直播中 | {count} 人观看 | {info['title']}")
            else:
                self._update_status("○ 未开播")

    def _add_anchor(self):
        dialog = AddAnchorDialog(self.root, self.cookie)
        self.root.wait_window(dialog)
        if not dialog.result:
            return
        rid, name = dialog.result
        if rid in self.anchors:
            messagebox.showwarning("提示", f"主播「{self.anchors[rid]}」已存在")
            return
        self.anchors[rid] = name
        self._save_config()
        self._refresh_anchor_list()
        self.anchor_listbox.update_idletasks()
        idx = list(self.anchors.keys()).index(rid)
        self.anchor_listbox.selection_clear(0, tk.END)
        self.anchor_listbox.selection_set(idx)
        self.anchor_listbox.see(idx)
        self._check_status(rid)

    def _del_anchor(self):
        rid = self._get_selected_rid()
        if not rid:
            messagebox.showwarning("提示", "请先选择一个主播")
            return
        name = self.anchors[rid]
        if messagebox.askyesno("确认", f"确定要删除主播「{name}」吗？"):
            del self.anchors[rid]
            self._save_config()
            self._refresh_anchor_list()

    def _save_config(self):
        self.config["anchors"] = self.anchors
        self.config["cookie"] = self.cookie
        save_config(self.config)

    def _show_cookie_config(self):
        win = tk.Toplevel(self.root)
        win.title("Cookie 配置")
        win.geometry("620x400")
        win.configure(bg="#2d2d2d")
        win.transient(self.root)
        win.grab_set()
        win.update_idletasks()
        x = (win.winfo_screenwidth() - 620) // 2
        y = (win.winfo_screenheight() - 400) // 2
        win.geometry(f"620x400+{x}+{y}")

        tk.Label(win, text="Cookie 配置", font=("微软雅黑", 14, "bold"),
                 fg="#007acc", bg="#2d2d2d").pack(pady=12)
        tips = ("1. 浏览器登录抖音网页版 live.douyin.com\n"
                "2. 按 F12 → 控制台(Console)\n"
                "3. 输入 document.cookie 并回车\n"
                "4. 复制完整结果粘贴到下方\n"
                "（用于接收礼物消息和获取直播流，可不填）")
        tk.Label(win, text=tips, font=("微软雅黑", 9), fg="#aaaaaa", bg="#2d2d2d",
                 justify=tk.LEFT).pack(pady=5)

        text = scrolledtext.ScrolledText(win, font=("Consolas", 9), height=10,
                                         bg="#3c3c3c", fg="#ffffff", wrap=tk.WORD)
        text.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        if self.cookie:
            text.insert("1.0", self.cookie)

        btn_frame = tk.Frame(win, bg="#2d2d2d")
        btn_frame.pack(pady=12)

        def save():
            cookie = text.get("1.0", tk.END).strip()
            self.cookie = cookie
            self._save_config()
            if cookie:
                self.cookie_btn.config(fg="#6a9955")
            else:
                self.cookie_btn.config(fg="#888888")
            win.destroy()

        tk.Button(btn_frame, text="保存", font=("微软雅黑", 10), bg="#007acc", fg="#ffffff",
                  padx=25, relief=tk.FLAT, cursor="hand2", command=save).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", font=("微软雅黑", 10), bg="#3c3c3c", fg="#cccccc",
                  padx=25, relief=tk.FLAT, cursor="hand2", command=win.destroy).pack(side=tk.LEFT, padx=10)

    # -------------------- 弹幕抓取 --------------------
    def _check_all_anchors(self):
        """一键检测所有主播（不带 Cookie）"""
        self.check_all_btn.config(text="⏳ 检测中...", state=tk.DISABLED)
        rids = list(self.anchors.keys())
        if not rids:
            self.check_all_btn.config(text="🔍 一键检测", state=tk.NORMAL)
            return
        def do():
            for rid in rids:
                info = fetch_room_info(rid)
                self.root.after(0, lambda r=rid, i=info: self._on_status_checked(r, i))
            self.root.after(0, lambda: self.check_all_btn.config(text="🔍 一键检测", state=tk.NORMAL))
        threading.Thread(target=do, daemon=True).start()

    def _switch_fetch(self, live_id):
        """切换抓取目标"""
        if self.running:
            self.stop_fetch()
        self.start_fetch(live_id)

    def start_fetch(self, live_id):
        self.running = True
        self._current_rid = live_id
        self._current_date = date.today().isoformat()
        self._append_system(f"⏳ 正在连接直播间 {live_id} ...")
        def on_message(msg_type, data):
            self.msg_queue.put({"type": msg_type, **data})
        threading.Thread(target=self._run_fetcher, args=(live_id, on_message), daemon=True).start()

    def _run_fetcher(self, live_id, on_message):
        try:
            self.fetcher = DouyinLiveWebFetcher(live_id, on_message=on_message, cookie=self.cookie)
            self.msg_queue.put({"type": "connected"})
            self.fetcher.start()
        except Exception as e:
            self.msg_queue.put({"type": "error", "msg": str(e)})

    def stop_fetch(self):
        self.running = False
        if self.fetcher:
            try: self.fetcher.stop()
            except Exception: pass
            self.fetcher = None
        self._update_status("已断开")
        self._append_system("⏹ 已停止")

    def _on_close(self):
        self.stop_fetch()
        self.root.destroy()

    def _poll_queue(self):
        try:
            while True:
                data = self.msg_queue.get_nowait()

                msg_type = data.get("type")
                if msg_type == "connected":
                    self._append_system("✅ 已连接到直播间，开始接收弹幕...")
                    self._update_status("● 直播中")
                    continue
                elif msg_type == "error":
                    self._append_system(f"❌ 连接失败: {data['msg']}")
                    self._update_status("连接失败")
                    self.root.after(0, self.stop_fetch)
                    continue

                # 所有消息都保存，不受过滤开关影响
                self._save_message(data)

                if msg_type in ("room", "adaptation", "rank"):
                    continue  # 不显示
                elif msg_type == "stats":
                    current = data.get("current", 0)
                    self.viewer_label.config(text=f"👁 {current} 人观看")
                elif msg_type == "roomstats":
                    pass
                else:
                    if not self._msg_allowed(msg_type):
                        continue
                    text = data.get("text", "")
                    tag = msg_type if msg_type in (
                        "chat", "gift", "like", "member", "social",
                        "fansclub", "emoji", "control"
                    ) else "chat"
                    self._append_line(text, tag)

        except queue.Empty:
            pass

        self.root.after(200, self._poll_queue)

    def _at_bottom(self):
        return self.chat_area.yview()[1] >= 1.0

    def _append_line(self, text, tag="chat"):
        at_bottom = self._at_bottom()
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, text + "\n", tag)
        self.chat_area.config(state=tk.DISABLED)
        if at_bottom:
            self.chat_area.see(tk.END)

    def _append_system(self, text):
        at_bottom = self._at_bottom()
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, f"{text}\n", "system")
        self.chat_area.config(state=tk.DISABLED)
        if at_bottom:
            self.chat_area.see(tk.END)

    def _update_status(self, text):
        self.status_label.config(text=text)

    def _save_message(self, data):
        """将消息保存到 data/{rid（昵称）}/{date}.jsonl"""
        rid = self._current_rid
        if not rid:
            return
        name = self.anchors.get(rid, rid)
        folder = f"{name}（{rid}）"
        # 去掉 text 中重复的时间戳前缀
        text = data.get("text", "")
        ts = data.get("time_str", "")
        if ts and text.startswith(f"[{ts}] "):
            text = text[len(ts) + 3:]
        record = {
            "time": ts,
            "type": data.get("type", "?"),
            "text": text,
        }
        try:
            with self._save_lock:
                dir_path = os.path.join(self._data_dir, folder)
                os.makedirs(dir_path, exist_ok=True)
                file_path = os.path.join(dir_path, f"{self._current_date}.jsonl")
                with open(file_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 保存失败不影响主流程

    def _get_streams(self):
        rid = self._get_selected_rid()
        return self._anchor_status.get(rid, {}).get("streams", {}) if rid else {}

    def _play_best(self):
        streams = self._get_streams()
        if not streams:
            messagebox.showwarning("提示", "未获取到直播流，请先一键检测或选中主播")
            return
        for q in QUALITY_ORDER:
            if q in streams:
                self._do_play(streams[q])
                return

    def _quality_menu(self, event):
        streams = self._get_streams()
        if not streams:
            return
        menu = tk.Menu(self.root, tearoff=0, bg="#2d2d2d", fg="#cccccc",
                       font=("微软雅黑", 10), activebackground="#007acc")
        for q in QUALITY_ORDER:
            if q in streams:
                url = streams[q]
                name = QUALITY_NAMES.get(q, q)
                sub = tk.Menu(menu, tearoff=0, bg="#2d2d2d", fg="#cccccc",
                              font=("微软雅黑", 10), activebackground="#007acc")
                sub.add_command(label="▶ 播放", command=lambda u=url: self._do_play(u))
                sub.add_command(label="📋 复制直链", command=lambda u=url: self._copy_url(u))
                menu.add_cascade(label=f"{name}  ({q})", menu=sub)
        menu.post(event.x_root, event.y_root)

    def _copy_url(self, url):
        self.root.clipboard_clear()
        self.root.clipboard_append(url)

    def _do_play(self, url):
        if not play_with_potplayer(url):
            if messagebox.askyesno("提示", "未找到 PotPlayer，是否复制直链？"):
                self.root.clipboard_clear(); self.root.clipboard_append(url)

    def run(self):
        self.root.mainloop()
