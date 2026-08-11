
# coding:utf-8

# @FileName:    liveMan.py
# @Time:        2024/1/2 21:51
# @Author:      bubu
# @Project:     douyinLiveWebFetcher

import codecs
import gzip
import hashlib
import random
import re
import string
import threading
import time
import execjs
import urllib.parse

import requests
import websocket
from py_mini_racer import MiniRacer

from ac_signature import get__ac_signature
from protobuf.douyin import *

from urllib3.util.url import parse_url


def execute_js(js_file: str):
    """
    执行 JavaScript 文件
    :param js_file: JavaScript 文件路径
    :return: 执行结果
    """
    with open(js_file, 'r', encoding='utf-8') as file:
        js_code = file.read()
    
    ctx = execjs.compile(js_code)
    return ctx



def generateSignature(wss, script_file='sign.js'):
    """
    出现gbk编码问题则修改 python模块subprocess.py的源码中Popen类的__init__函数参数encoding值为 "utf-8"
    """
    params = ("live_id,aid,version_code,webcast_sdk_version,"
              "room_id,sub_room_id,sub_channel_id,did_rule,"
              "user_unique_id,device_platform,device_type,ac,"
              "identity").split(',')
    wss_params = urllib.parse.urlparse(wss).query.split('&')
    wss_maps = {i.split('=')[0]: i.split("=")[-1] for i in wss_params}
    tpl_params = [f"{i}={wss_maps.get(i, '')}" for i in params]
    param = ','.join(tpl_params)
    md5 = hashlib.md5()
    md5.update(param.encode())
    md5_param = md5.hexdigest()
    
    with codecs.open(script_file, 'r', encoding='utf8') as f:
        script = f.read()
    
    ctx = MiniRacer()
    ctx.eval(script)
    
    try:
        signature = ctx.call("get_sign", md5_param)
        return signature
    except Exception as e:
        print(f"【X】generateSignature 失败: {e}")
        return ""


def generateMsToken(length=182):
    """
    产生请求头部cookie中的msToken字段，其实为随机的107位字符
    :param length:字符位数
    :return:msToken
    """
    random_str = ''
    base_str = string.ascii_letters + string.digits + '-_'
    _len = len(base_str) - 1
    for _ in range(length):
        random_str += base_str[random.randint(0, _len)]
    return random_str


class DouyinLiveWebFetcher:

    def __init__(self, live_id, abogus_file='a_bogus.js', on_chat_message=None, on_message=None, cookie=None):
        """
        直播间弹幕抓取对象
        :param live_id: 直播间的直播id
        :param cookie: 登录后的完整 Cookie，用于接收礼物等需要登录的消息
        """
        self.abogus_file = abogus_file
        self.on_chat_message = on_chat_message
        self.on_message = on_message
        self.cookie = cookie or ""
        self.__ttwid = None
        self.__room_id = None
        self.session = requests.Session()
        self.live_id = live_id
        self.host = "https://www.douyin.com/"
        self.live_url = "https://live.douyin.com/"
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0"
        self.headers = {
            'User-Agent': self.user_agent
        }
    
    def start(self):
        self._connectWebSocket()
    
    def stop(self):
        self.ws.keep_running = False
        self.ws.close()
    
    @property
    def ttwid(self):
        """
        产生请求头部cookie中的ttwid字段，访问抖音网页版直播间首页可以获取到响应cookie中的ttwid
        :return: ttwid
        """
        if self.__ttwid:
            return self.__ttwid
        headers = {
            "User-Agent": self.user_agent,
        }
        try:
            response = self.session.get(self.live_url, headers=headers)
            response.raise_for_status()
        except Exception as err:
            print("【X】Request the live url error: ", err)
            return None
        else:
            self.__ttwid = response.cookies.get('ttwid')
            return self.__ttwid
    
    @property
    def room_id(self):
        """
        根据直播间的地址获取到真正的直播间roomId，有时会有错误，可以重试请求解决
        :return:room_id
        """
        if self.__room_id:
            return self.__room_id
        url = self.live_url + self.live_id
        headers = {
            "User-Agent": self.user_agent,
            "cookie": f"ttwid={self.ttwid}&msToken={generateMsToken()}; __ac_nonce=0123407cc00a9e438deb4",
        }
        try:
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
        except Exception as err:
            print("【X】Request the live room url error: ", err)
        else:
            match = re.search(r'roomId\\":\\"(\d+)\\"', response.text)
            if match is None or len(match.groups()) < 1:
                print("【X】No match found for roomId")
                return None

            self.__room_id = match.group(1)
            return self.__room_id
    
    def get_ac_nonce(self):
        """
        获取 __ac_nonce
        """
        resp_cookies = self.session.get(self.host, headers=self.headers).cookies
        return resp_cookies.get("__ac_nonce")
    
    def get_ac_signature(self, __ac_nonce: str = None) -> str:
        """
        获取 __ac_signature
        """
        __ac_signature = get__ac_signature(self.host[8:], __ac_nonce, self.user_agent)
        self.session.cookies.set("__ac_signature", __ac_signature)
        return __ac_signature
    
    def get_a_bogus(self, url_params: dict):
        """
        获取 a_bogus
        """
        url = urllib.parse.urlencode(url_params)
        ctx = execute_js(self.abogus_file)
        _a_bogus = ctx.call("get_ab", url, self.user_agent)
        return _a_bogus
    
    def get_room_status(self):
        """
        获取直播间开播状态:
        room_status: 2 直播已结束
        room_status: 0 直播进行中
        """
        msToken = generateMsToken()
        nonce = self.get_ac_nonce()
        signature = self.get_ac_signature(nonce)
        url = ('https://live.douyin.com/webcast/room/web/enter/?aid=6383'
               '&app_name=douyin_web&live_id=1&device_platform=web&language=zh-CN&enter_from=page_refresh'
               '&cookie_enabled=true&screen_width=5120&screen_height=1440&browser_language=zh-CN&browser_platform=Win32'
               '&browser_name=Edge&browser_version=140.0.0.0'
               f'&web_rid={self.live_id}'
               f'&room_id_str={self.room_id}'
               '&enter_source=&is_need_double_stream=false&insert_task_id=&live_reason=&msToken=' + msToken)
        query = parse_url(url).query
        params = {i[0]: i[1] for i in [j.split('=') for j in query.split('&')]}
        a_bogus = self.get_a_bogus(params)  # 计算a_bogus,成功率不是100%，出现失败时重试即可
        url += f"&a_bogus={a_bogus}"
        headers = self.headers.copy()
        headers.update({
            'Referer': f'https://live.douyin.com/{self.live_id}',
            'Cookie': f'ttwid={self.ttwid};__ac_nonce={nonce}; __ac_signature={signature}',
        })
        resp = self.session.get(url, headers=headers)
        data = resp.json().get('data')
        if data:
            room_status = data.get('room_status')
            user = data.get('user')
            user_id = user.get('id_str')
            nickname = user.get('nickname')
            print(f"【{nickname}】[{user_id}]直播间：{['正在直播', '已结束'][bool(room_status)]}.")
    
    def _connectWebSocket(self):
        """
        连接抖音直播间websocket服务器，请求直播间数据
        """
        wss = ("wss://webcast100-ws-web-lq.douyin.com/webcast/im/push/v2/?app_name=douyin_web"
               "&version_code=180800&webcast_sdk_version=1.0.14-beta.0"
               "&update_version_code=1.0.14-beta.0&compress=gzip&device_platform=web&cookie_enabled=true"
               "&screen_width=1536&screen_height=864&browser_language=zh-CN&browser_platform=Win32"
               "&browser_name=Mozilla"
               "&browser_version=5.0%20(Windows%20NT%2010.0;%20Win64;%20x64)%20AppleWebKit/537.36%20(KHTML,"
               "%20like%20Gecko)%20Chrome/126.0.0.0%20Safari/537.36"
               "&browser_online=true&tz_name=Asia/Shanghai"
               "&cursor=d-1_u-1_fh-7392091211001140287_t-1721106114633_r-1"
               f"&internal_ext=internal_src:dim|wss_push_room_id:{self.room_id}|wss_push_did:7319483754668557238"
               f"|first_req_ms:1721106114541|fetch_time:1721106114633|seq:1|wss_info:0-1721106114633-0-0|"
               f"wrds_v:7392094459690748497"
               f"&host=https://live.douyin.com&aid=6383&live_id=1&did_rule=3&endpoint=live_pc&support_wrds=1"
               f"&user_unique_id=7319483754668557238&im_path=/webcast/im/fetch/&identity=audience"
               f"&need_persist_msg_count=15&insert_task_id=&live_reason=&room_id={self.room_id}&heartbeatDuration=0")
        
        signature = generateSignature(wss)
        wss += f"&signature={signature}"
        
        if self.cookie:
            cookie_str = self.cookie
        else:
            cookie_str = f"ttwid={self.ttwid}"
        headers = {
            "cookie": cookie_str,
            'user-agent': self.user_agent,
        }
        self.ws = websocket.WebSocketApp(wss,
                                         header=headers,
                                         on_open=self._wsOnOpen,
                                         on_message=self._wsOnMessage,
                                         on_error=self._wsOnError,
                                         on_close=self._wsOnClose)
        try:
            self.ws.run_forever()
        except Exception:
            self.stop()
            raise
    
    def _sendHeartbeat(self):
        """
        发送心跳包
        """
        while True:
            try:
                heartbeat = PushFrame(payload_type='hb').SerializeToString()
                self.ws.send(heartbeat, websocket.ABNF.OPCODE_PING)
                pass
            except Exception as e:
                print("【X】心跳包检测错误: ", e)
                break
            else:
                time.sleep(5)
    
    def _wsOnOpen(self, ws):
        """
        连接建立成功
        """
        pass  # 连接成功
        threading.Thread(target=self._sendHeartbeat).start()
    
    def _wsOnMessage(self, ws, message):
        """
        接收到数据
        :param ws: websocket实例
        :param message: 数据
        """
        
        # 根据proto结构体解析对象
        try:
            package = PushFrame().parse(message)
            response = Response().parse(gzip.decompress(package.payload))
        except Exception as e:
            print(f"  [错误] 解析消息包失败: {e}")
            return
        
        # 返回直播间服务器链接存活确认消息，便于持续获取数据
        if response.need_ack:
            ack = PushFrame(log_id=package.log_id,
                            payload_type='ack',
                            payload=response.internal_ext.encode('utf-8')
                            ).SerializeToString()
            ws.send(ack, websocket.ABNF.OPCODE_BINARY)
        
        # 根据消息类别解析消息体
        _method_map = {
            'WebcastChatMessage':             self._parseChatMsg,
            'WebcastGiftMessage':             self._parseGiftMsg,
            'WebcastLikeMessage':             self._parseLikeMsg,
            'WebcastMemberMessage':           self._parseMemberMsg,
            'WebcastSocialMessage':           self._parseSocialMsg,
            'WebcastRoomUserSeqMessage':      self._parseRoomUserSeqMsg,
            'WebcastFansclubMessage':         self._parseFansclubMsg,
            'WebcastEmojiChatMessage':        self._parseEmojiChatMsg,
            'WebcastRoomMessage':             self._parseRoomMsg,
            'WebcastRoomStatsMessage':        self._parseRoomStatsMsg,
            # 'WebcastRoomRankMessage':         self._parseRankMsg,  # 太冗长，暂时禁用
            'WebcastControlMessage':          self._parseControlMsg,
            'WebcastRoomStreamAdaptationMessage': self._parseRoomStreamAdaptationMsg,
        }
        for msg in response.messages_list:
            method = msg.method
            parser = _method_map.get(method)
            if parser:
                try:
                    parser(msg.payload)
                except Exception as e:
                    print(f"  [错误] 处理 {method} 时出错: {e}")
            # 不在映射表中的消息类型静默忽略
    
    def _wsOnError(self, ws, error):
        print("WebSocket error: ", error)
    
    def _wsOnClose(self, ws, *args):
        print("WebSocket connection closed.")

    @staticmethod
    def _fmt_time(ts):
        """安全格式化时间戳，无效时用本地时间"""
        from datetime import datetime
        try:
            if ts and ts > 0:
                return datetime.fromtimestamp(ts).strftime('%H:%M:%S')
        except (OSError, ValueError, OverflowError):
            pass
        return datetime.now().strftime('%H:%M:%S')

    @staticmethod
    def _get_msg_time(msg):
        """从消息中提取时间戳，优先级: event_time/send_time > common.create_time"""
        for attr in ('event_time', 'send_time'):
            if hasattr(msg, attr):
                val = getattr(msg, attr)
                if val and val > 0:
                    return val
        if hasattr(msg, 'common') and msg.common:
            ct = msg.common.create_time
            if ct and ct > 0:
                return ct
        return 0

    def _emit(self, msg_type, time_str, text, **extra):
        """统一回调"""
        if self.on_message:
            self.on_message(msg_type, {"time_str": time_str, "text": text, **extra})
        if msg_type == 'chat' and self.on_chat_message:
            self.on_chat_message(extra.get('user_name', ''), extra.get('content', ''), extra.get('event_time', 0))

    def _parseChatMsg(self, payload):
        message = ChatMessage().parse(payload)
        user_name = message.user.nick_name
        content = message.content
        event_time = message.event_time
        time_str = self._fmt_time(event_time)
        self._emit('chat', time_str, f"[{time_str}] 【弹幕】 {user_name}: {content}",
                   user_name=user_name, content=content, event_time=event_time)

    def _parseGiftMsg(self, payload):
        message = GiftMessage().parse(payload)
        user_name = message.user.nick_name
        gift_name = message.gift.name
        gift_cnt = message.combo_count
        time_str = self._fmt_time(message.send_time)
        self._emit('gift', time_str, f"[{time_str}] 【礼物】 {user_name} 送出 {gift_name} x{gift_cnt}",
                   user_name=user_name, gift_name=gift_name, gift_cnt=gift_cnt)

    def _parseLikeMsg(self, payload):
        message = LikeMessage().parse(payload)
        user_name = message.user.nick_name
        count = message.count
        time_str = self._fmt_time(self._get_msg_time(message))
        self._emit('like', time_str, f"[{time_str}] 【点赞】 {user_name} 点了{count}个赞",
                   user_name=user_name, count=count)

    def _parseMemberMsg(self, payload):
        message = MemberMessage().parse(payload)
        user_name = message.user.nick_name
        user_id = message.user.id
        time_str = self._fmt_time(self._get_msg_time(message))
        self._emit('member', time_str, f"[{time_str}] 【进场】 {user_name} 进入了直播间",
                   user_name=user_name, user_id=user_id)

    def _parseSocialMsg(self, payload):
        message = SocialMessage().parse(payload)
        user_name = message.user.nick_name
        user_id = message.user.id
        time_str = self._fmt_time(self._get_msg_time(message))
        self._emit('social', time_str, f"[{time_str}] 【关注】 {user_name} 关注了主播",
                   user_name=user_name, user_id=user_id)

    def _parseRoomUserSeqMsg(self, payload):
        message = RoomUserSeqMessage().parse(payload)
        current = message.total
        total = message.total_pv_for_anchor
        time_str = self._fmt_time(self._get_msg_time(message))
        self._emit('stats', time_str, f"[{time_str}] 【统计】 当前观看: {current}, 累计观看: {total}",
                   current=current, total=total)

    def _parseFansclubMsg(self, payload):
        message = FansclubMessage().parse(payload)
        content = message.content
        time_str = self._fmt_time(self._get_msg_time(message))
        self._emit('fansclub', time_str, f"[{time_str}] 【粉丝团】 {content}",
                   content=content)

    def _parseEmojiChatMsg(self, payload):
        message = EmojiChatMessage().parse(payload)
        user_name = message.user.nick_name if message.user else ''
        content = message.default_content
        time_str = self._fmt_time(self._get_msg_time(message))
        self._emit('emoji', time_str, f"[{time_str}] 【表情】 {user_name}: {content}",
                   user_name=user_name, content=content)

    def _parseRoomMsg(self, payload):
        message = RoomMessage().parse(payload)
        room_id = message.common.room_id if message.common else ''
        time_str = self._fmt_time(self._get_msg_time(message))
        self._emit('room', time_str, f"[{time_str}] 【房间】 id:{room_id}",
                   room_id=room_id)

    def _parseRoomStatsMsg(self, payload):
        message = RoomStatsMessage().parse(payload)
        display_long = message.display_long
        time_str = self._fmt_time(self._get_msg_time(message))
        self._emit('roomstats', time_str, f"[{time_str}] 【直播】 {display_long}",
                   display_long=display_long)

    def _parseRankMsg(self, payload):
        message = RoomRankMessage().parse(payload)
        time_str = self._fmt_time(self._get_msg_time(message))
        self._emit('rank', time_str, f"[{time_str}] 【排行】 已更新")

    def _parseControlMsg(self, payload):
        message = ControlMessage().parse(payload)
        time_str = self._fmt_time(self._get_msg_time(message))
        if message.status == 3:
            self._emit('control', time_str, f"[{time_str}] 【状态】 直播间已结束")
            self.stop()

    def _parseRoomStreamAdaptationMsg(self, payload):
        message = RoomStreamAdaptationMessage().parse(payload)
        adaptationType = message.adaptation_type
        time_str = self._fmt_time(self._get_msg_time(message))
        self._emit('adaptation', time_str, f"[{time_str}] 【流适配】 adaptation: {adaptationType}")
