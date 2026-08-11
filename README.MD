# DouyinLiveTool — 抖音直播监控 + 弹幕捕获

实时捕获抖音直播间弹幕、礼物、点赞、进场等消息，支持直播流播放，深色主题 GUI。

## 功能

- **主播管理** — 添加/删除主播，自动获取昵称，列表持久化
- **一键检测** — 批量检测所有主播开播状态
- **13 种消息类型** — 弹幕 / 礼物 / 点赞 / 进场 / 关注 / 粉丝团 / 统计 / 表情 / 直播间 / 流适配 / 状态 ……
- **消息过滤** — 复选框开关，即时隐藏/显示各类消息
- **数据存档** — 自动保存为 JSONL，按主播 + 日期分文件
- **直播流播放** — 提取多清晰度直链，一键 PotPlayer 播放
- **Cookie 配置** — 登录后获取礼物等完整消息

## 环境要求

- Windows 10 / 11
- Python 3.7+
- Node.js（mini_racer 依赖）

## 安装

```bash
git clone https://github.com/你的用户名/仓库名.git
cd 仓库名
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 使用

```bash
python main.py                    # 启动 GUI
python main.py <直播间ID>          # 自动连接指定直播间
```

### 配置 Cookie（获取礼物消息必需）

1. 浏览器打开 https://live.douyin.com 并登录
2. F12 → 控制台 → 输入 `document.cookie` 回车
3. 复制完整结果
4. 在 GUI 中点击 **Cookie** 按钮 → 粘贴 → 保存

## 项目结构

```
├── main.py               # 入口
├── chat_window.py         # GUI 窗口
├── liveMan.py             # WebSocket 弹幕引擎
├── sign.js                # WebSocket 签名
├── protobuf/
│   ├── douyin.proto       # 协议定义
│   ├── douyin.py          # 生成的 Python 类
│   └── __init__.py
├── requirements.txt
└── .gitignore
```

## 数据格式

存档在 `data/主播名（ID）/日期.jsonl`，每行一条：

```json
{"time": "21:17:40", "type": "chat", "text": "【弹幕】 用户: 内容"}
{"time": "21:17:42", "type": "gift", "text": "【礼物】 用户 送出 小心心 x10"}
```

## 致谢

- 基于 [saermart/DouyinLiveWebFetcher](https://github.com/saermart/DouyinLiveWebFetcher)
- 消息协议逆向来自社区贡献

## 声明

本项目仅用于学习研究，严禁用于商业谋利、破坏系统、盗取个人信息等行为。
侵权或涉及相关利益请联系原作者。
