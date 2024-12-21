import json
import random
import re
import subprocess
import sys
import time
from enum import Enum
from urllib.parse import urlparse
from urllib.parse import urlunparse

import requests
from bs4 import BeautifulSoup


from http.cookies import SimpleCookie


class CookieUtil:
    @staticmethod
    def cookies_to_dict(cookies):
        """
        Convert requests.cookies.RequestsCookieJar to dictionary
        """
        cookie_dict = {}
        for key, value in cookies.items():
            cookie_dict[key] = value
        return cookie_dict

    @staticmethod
    def cookies_to_string(cookie_dict):
        """
        Convert cookie dictionary to string
        """
        return '; '.join([f'{key}={value}' for key, value in cookie_dict.items()])

    @staticmethod
    def parse_cookie_string(cookie_str):
        """
        Parse cookie string into dictionary
        """
        cookie = SimpleCookie()
        cookie.load(cookie_str)
        cookies = {}
        for key, morsel in cookie.items():
            cookies[key] = morsel.value
        return cookies

    @staticmethod
    def merge_cookies(cookies1, cookies2):
        """
        Merge two cookie dictionaries
        """
        merged = cookies1.copy()
        merged.update(cookies2)
        return merged


class LivingStatus(Enum):
    Living = 1
    STOP = 2
    ERROR = 3


def generate_did():
    random_number = int(random.random() * 1e9)
    hex_chars = "0123456789ABCDEF"
    random_hex = ''.join(random.choice(hex_chars) for _ in range(7))
    return "web_" + str(random_number) + random_hex

def get_stream_url(user_agent, pc_live_url):
    did = generate_did()
    print("did: \n", did)

    headers = {
        'referer': "https://live.kuaishou.com/",
        'User-Agent': user_agent,
        "Cookie": f"_did={did}",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
    }

    response = requests.get(pc_live_url, headers=headers, allow_redirects=True)

    cookie_dict = CookieUtil.cookies_to_dict(response.cookies)
    cookie_content = CookieUtil.cookies_to_string(cookie_dict)
    print("cookie_content: \n", cookie_content)

    headers['Cookie'] = cookie_content

    response = requests.get(pc_live_url, headers=headers, allow_redirects=True)

    html_str = response.text

    soup = BeautifulSoup(html_str, 'html.parser')
    scripts = soup.find_all('script')

    result = []

    for script in scripts:
        target_str = script.string
        if target_str is not None and "liveStream" in target_str:
            if "undefined," in target_str:
                target_str = target_str.replace("undefined,", '"",')
            match = re.search(r'window\.__INITIAL_STATE__=(.*?);', target_str)

            if match:
                extracted_content = match.group(1)
                print("extracted_content:\n", extracted_content)
                data = json.loads(extracted_content)

                live_room = data['liveroom']
                if live_room is not None:
                    play_list = live_room['playList']
                    if play_list is not None and len(play_list) > 0:
                        play_item = play_list[0]
                        if "errorType" in play_item:
                            error_msg = play_item['errorType']['title']
                            print(error_msg)
                            return [], LivingStatus.ERROR.value
                        if "isLiving" in play_item:
                            status = play_item['isLiving']
                            print("living status: ", status)
                            if not status:
                                print("直播已经结束!")
                                return [], LivingStatus.STOP.value
                        if "liveStream" in play_item:
                            live_stream = play_item['liveStream']
                            if live_stream is not None and "playUrls" in live_stream:
                                play_urls = live_stream['playUrls']
                                if play_urls is not None:
                                    for type_, play_url in play_urls.items():
                                        try:
                                            result.extend(play_url['adaptationSet']['representation'])
                                        except KeyError:
                                            continue
                                    filtered_list = [{'name': item['shortName'], 'url': item['url']} for item in result]
                                    return filtered_list, LivingStatus.Living.value
                                else:
                                    print("play_urls不存在")
                            else:
                                print("live_stream不存在")
                    else:
                        print("play_list不存在")
                else:
                    print("live_room不存在")
            else:
                print("未找到匹配的内容")
    return [], LivingStatus.ERROR.value

def save_video_slice(user_agent, stream_data):
    real_url = stream_data[0]['url']

    analyzeduration = "20000000"
    probesize = "10000000"
    bufsize = "8000k"
    max_muxing_queue_size = "1024"

    ffmpeg_command = [
        'ffmpeg', "-y",
        "-v", "verbose",
        "-rw_timeout", "30000000",
        "-loglevel", "error",
        "-hide_banner",
        "-user_agent", user_agent,
        "-protocol_whitelist", "rtmp,crypto,file,http,https,tcp,tls,udp,rtp",
        "-thread_queue_size", "1024",
        "-analyzeduration", analyzeduration,
        "-probesize", probesize,
        "-fflags", "+discardcorrupt",
        "-i", real_url,
        "-bufsize", bufsize,
        "-sn", "-dn",
        "-reconnect_delay_max", "60",
        "-reconnect_streamed", "-reconnect_at_eof",
        "-max_muxing_queue_size", max_muxing_queue_size,
        "-correct_ts_overflow", "1",
    ]

    now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
    save_file_path = f"{now}_%03d.mp4"
    command = [
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0",
        "-f", "segment",
        "-segment_time", "20",
        "-segment_time_delta", "0.01",
        "-segment_format", "mp4",
        "-reset_timestamps", "1",
        "-pix_fmt", "yuv420p",
        save_file_path,
    ]

    ffmpeg_command.extend(command)
    print("开始拉取数据流...")

    result = ' '.join(ffmpeg_command)
    print("result: \n", result)
    _output = subprocess.check_output(ffmpeg_command, stderr=subprocess.STDOUT)
    # 以下代码理论上不会执行
    print(_output)

if __name__ == '__main__':
    # https://live.kuaishou.com/u/3xf2ed9vrbqzr49
    # url = input('请输入快手直播链接：')
    # url = "https://live.kuaishou.com/u/3xf2ed9vrbqzr49"
    # url = "https://live.kuaishou.com/u/3xj6wf7ksgs2uru"
    # url = "https://live.kuaishou.com/u/DD5221273500"
    # url = "https://live.kuaishou.com/u/haiwangqi"
    url = "https://live.kuaishou.com/u/hy441195"
    parsed_url = urlparse(url)
    # 移除查询参数
    url_without_query = urlunparse(parsed_url._replace(query=""))

    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

    try_times = 0
    while True:
        stream_url_list, ret_flag = get_stream_url(user_agent, url_without_query)
        if ret_flag == LivingStatus.STOP.value:
            print("直播已结束")
            break
        if ret_flag == LivingStatus.Living.value:
            print(stream_url_list)
            break
        try_times = try_times + 1
        if try_times > 10:
            print("获取直播流地址失败")
            sys.exit(-1)

    save_video_slice(user_agent, stream_url_list)

