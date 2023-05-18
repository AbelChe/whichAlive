#!/usr/bin/env python
import argparse
import base64
import codecs
import csv
import datetime
import os
import re
import select
import socket
import sys
import time
import urllib
import urllib.parse
from concurrent.futures import ALL_COMPLETED, ThreadPoolExecutor, wait

import mmh3
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
DEBUG = False


class whichAlive(object):
    def __init__(self, file, THREAD_POOL_SIZE=10, allow_redirect=False, PROXY={}):
        self.script_path = os.path.dirname(__file__)
        self.file = file
        self.timenow = str(time.time()).split(".")[0]
        self.outfilename = f'{self.timenow}.csv'
        self.errorfilename = f'error_{self.timenow}.txt'
        self.urllist = self.__urlfromfile()
        self.tableheader = ['no', 'url', 'ip', 'state',
                            'state_code', 'title', 'cmsfinger', 'server', 'iconhash', 'length', 'other']
        self.HEADER = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36',
        }
        self.THREAD_POOL_SIZE = THREAD_POOL_SIZE
        self.allurlnumber = len(self.urllist)
        self.completedurl = -1
        self.allow_redirect = allow_redirect
        self.PROXY = PROXY
        self.__load_cmsfinger_database()

    def run(self):
        self.completedurl += 1
        self.__writetofile(self.tableheader)
        tasklist = []
        start_time = datetime.datetime.now()
        t = ThreadPoolExecutor(max_workers=self.THREAD_POOL_SIZE)
        for k, url in enumerate(self.urllist):
            tasklist.append(t.submit(self.__scan, url, k+1))
        print(f'total {self.allurlnumber}')
        if wait(tasklist, return_when=ALL_COMPLETED):
            end_time = datetime.datetime.now()
            print(
                f'--------------------------------\nDONE, use {(end_time - start_time).seconds} seconds')
            print(
                f'outfile: {os.path.join(os.path.abspath(os.path.dirname(__file__)), "result", self.outfilename)}')

    def __scan(self, url, no, tryagainflag=False):
        def callback(no, url, ip, state, state_code, title, cmsfinger, server, iconhash, length, other):
            self.completedurl += 1
            thisline = [no, url, ip, state, state_code,
                        title, cmsfinger, server, iconhash, length, other]
            nowpercent = '%.2f' % ((self.completedurl/self.allurlnumber)*100)
            print(f'[{nowpercent}%] {url} {ip} {state} {title} {length} {cmsfinger}')
            self.__writetofile(thisline)

        ip = ''
        state = ''
        state_code = -1
        title = ''
        server = ''
        cmsfinger = ''
        iconhash = ''
        length = -1
        other = ''
        try:
            if DEBUG:
                print(f'[debug] {no} {url}')
            u = urllib.parse.urlparse(url)
            ip = self.__getwebip(u.netloc.split(':')[0])
            if self.allow_redirect:
                r = requests.get(url=url, headers=self.HEADER,
                                 timeout=15, verify=False, proxies=self.PROXY)
                state = 'alive'
                self.__getwebcmsfinger(r)
                state_code = '->'.join([str(i.status_code)
                                       for i in r.history] + [str(r.status_code)])
                title = '->'.join([self.__getwebtitle(i)
                                  for i in r.history] + [self.__getwebtitle(r)])
                length = '->'.join([str(self.__getweblength(i))
                                   for i in r.history] + [str(self.__getweblength(r))])
                server = '->'.join([self.__getwebserver(i)
                                   for i in r.history] + [self.__getwebserver(r)])
                iconhash = '->'.join([self.__get_webiconhash(i)
                                      for i in r.history] + [self.__get_webiconhash(r)])
                cmsfinger = '->'.join([self.__getwebcmsfinger(i)
                                       for i in r.history] + [self.__getwebcmsfinger(r)])
            else:
                r = requests.get(url=url, headers=self.HEADER, allow_redirects=False,
                                 timeout=15, verify=False, proxies=self.PROXY)
                state = 'alive'
                state_code = str(r.status_code)
                title = self.__getwebtitle(r)
                length = str(self.__getweblength(r))
                server = self.__getwebserver(r)
                iconhash = self.__get_webiconhash(r)
                cmsfinger = self.__getwebcmsfinger(r)
            callback(no, url, ip, state, state_code, title,
                     cmsfinger, server, iconhash, length, other)
        except requests.exceptions.ConnectTimeout as e:
            if DEBUG:
                print(f'[ERROR][SCAN][ConnectTimeout] {url} {e}')
            self.__errorreport(str(e))
            state = 'dead'
            callback(no, url, ip, state, state_code, title, cmsfinger,
                     server, iconhash, length, 'ConnectTimeout')
        except requests.exceptions.ReadTimeout as e:
            if DEBUG:
                print(f'[ERROR][SCAN][ReadTimeout] {url} {e}')
            self.__errorreport(str(e))
            state = 'dead'
            callback(no, url, ip, state, state_code,
                     title, cmsfinger, server, iconhash, length, 'ReadTimeout')
        except requests.exceptions.ConnectionError as e:
            if DEBUG:
                print(f'[ERROR][SCAN][ConnectionError] {url} {e}')
            self.__errorreport(str(e))
            state = 'dead'
            callback(no, url, ip, state, state_code, title,
                     server, iconhash, cmsfinger, length, 'ConnectionError')
        except Exception as e:
            if DEBUG:
                print(f'[ERROR][SCAN][other] {no} {url} {e}')
            self.__errorreport(str(e))
            if TRYAGAIN and not tryagainflag:
                self.__scan(url, no, True)
            callback(no, url, ip, state, state_code,
                     title, cmsfinger, server, iconhash, length, 'e')

    def __getwebtitle(self, r) -> str:
        try:
            if r.headers.get('Content-Type'):
                try:
                    if r.headers.get('Content-Type').split('charset=')[1]:
                        charset = r.headers.get(
                            'Content-Type').split('charset=')[1]
                    elif re.findall(r'<meta charset=(.*?)>', r.text)[0].replace('\'', '').replace('"', ''):
                        charset = re.findall(
                            r'<meta charset=(.*?)>', r.text)[0].replace('\'', '').replace('"', '')
                    else:
                        charset = 'utf8'
                except:
                    charset = 'utf8'
            return re.findall(r'<title>(.*?)</title>', r.content.decode(charset))[0]
        except:
            return ''

    def __getwebip(self, domain) -> str:
        try:
            ip = socket.getaddrinfo(domain, 'http')
            return ip[0][4][0]
        except:
            return ''

    def __getweblength(self, r) -> int:
        try:
            return len(r.content)
        except:
            return -1

    def __getwebserver(self, r) -> str:
        try:
            return r.headers.get('server') if r.headers.get('server') else ''
        except:
            return ''

    def __get_webiconhash(self, r) -> str:
        try:
            soup = BeautifulSoup(r.content, 'html.parser')
            soup_iconlink = soup.find_all(
                'link[rel="shortcut icon"], link[rel="icon"]')
            if soup_iconlink:
                _link = soup_iconlink[0]
                if _link.startswith('http://') or _link.startswith('https://'):
                    icon_link = _link
                else:
                    icon_link = urllib.parse.urljoin(r.url, _link)
            else:
                icon_link = urllib.parse.urljoin(r.url, '/favicon.ico')

            r_icon = requests.get(icon_link, headers=self.HEADER,
                                  timeout=15, verify=False, proxies=self.PROXY)
            if r_icon.status_code != 200:
                return ''
            favicon = codecs.lookup('base64').encode(r_icon.content)[0]
            icon_hash = mmh3.hash(favicon)
            if DEBUG:
                print(f'[debug][icon_hash] {icon_link} icon hash:', icon_hash)
            return str(icon_hash)
        except Exception as e:
            if DEBUG:
                print('[ERROR][webiconhash]', e)
            return ''

    def __load_cmsfinger_database(self):
        try:
            import json

            import ahocorasick
            with open(f'{self.script_path}/cmsfinger.json') as f:
                self.j_data = json.load(f)
            self.ac_keyword_body = ahocorasick.Automaton()
            self.ac_keyword_header = ahocorasick.Automaton()
            self.ac_faviconhash_body = ahocorasick.Automaton()
            for j_index, pattern in enumerate(self.j_data.get('fingerprint')):
                method = pattern['method']
                location = pattern['location']
                keywords = pattern['keyword']
                cms = pattern['cms']

                if method == 'keyword':
                    if location == 'body':
                        for k in keywords:
                            self.ac_keyword_body.add_word(
                                k, (j_index, cms, len(keywords))
                            )
                    elif location == 'header':
                        for k in keywords:
                            self.ac_keyword_header.add_word(
                                k, (j_index, cms, len(keywords))
                            )
                elif method == 'faviconhash':
                    for k in keywords:
                        self.ac_faviconhash_body.add_word(
                            k, (j_index, cms, len(keywords))
                        )
            self.ac_keyword_body.make_automaton()
            self.ac_keyword_header.make_automaton()
            self.ac_faviconhash_body.make_automaton()
        except Exception as e:
            if DEBUG:
                print('[ERROR][cmsfinger_database]', e)
            exit(1)

    def __getwebcmsfinger(self, r) -> str:
        try:
            match_result = []
            _matche_r = {
                'keyword': {
                    'header': '\n'.join([': '.join([i, r.headers.get(i)]) for i in r.headers]),
                    'body': r.text
                },
                'faviconhash': {
                    'body': self.__get_webiconhash(r),
                },
            }

            for match_type in _matche_r:
                for match_loc in _matche_r.get(match_type):
                    this_match_num = 0
                    if match_type == 'keyword':
                        if match_loc == 'body':
                            for end_index, matched_cms in self.ac_keyword_body.iter(_matche_r.get(match_type).get(match_loc)):
                                this_match_num += 1
                                if this_match_num == matched_cms[2]:
                                    match_result.append(matched_cms[1])
                        elif match_loc == 'header':
                            for end_index, matched_cms in self.ac_keyword_header.iter(_matche_r.get(match_type).get(match_loc)):
                                this_match_num += 1
                                if this_match_num == matched_cms[2]:
                                    match_result.append(matched_cms[1])
                    elif match_type == 'faviconhash':
                        for end_index, matched_cms in self.ac_faviconhash_body.iter(_matche_r.get(match_type).get(match_loc)):
                            this_match_num += 1
                            if this_match_num == matched_cms[2]:
                                match_result.append(matched_cms[1])
            return ', '.join(set(match_result))
        except Exception as e:
            if DEBUG:
                print(f'[ERROR][cmsfinger] {r.url} {e}')
            return ''

    def __urlfromfile(self) -> str:
        tmp_list = [i.replace('\n', '').replace('\r', '')
                    for i in self.file.readlines()]
        return tmp_list

    def __writetofile(self, data: list):
        f = open(f'{self.script_path}/result/{self.outfilename}', 'a')
        writer = csv.writer(f)
        writer.writerow(data)
        f.close()

    def __errorreport(self, message):
        f = open(f'{self.script_path}/error/{self.errorfilename}', 'a')
        f.write(message+'\n')
        f.close()


BANNER = """\
           __    _      __    ___    ___
 _      __/ /_  (_)____/ /_  /   |  / (_)   _____
| | /| / / __ \/ / ___/ __ \/ /| | / / / | / / _ \\
| |/ |/ / / / / / /__/ / / / ___ |/ / /| |/ /  __/
|__/|__/_/ /_/_/\___/_/ /_/_/  |_/_/_/ |___/\___/
"""

HELP_MESSAGE = """\
whichalive.py -u url.txt\
"""

if __name__ == '__main__':
    print(BANNER)
    parser = argparse.ArgumentParser(usage=HELP_MESSAGE)
    parser.add_argument('-f', '--file', metavar='FILE', nargs='?',
                        type=argparse.FileType('r'), default=sys.stdin, help='URL lists file.')
    parser.add_argument('--proxy', default='',
                        help='Set proxy, such as 127.0.0.1:8080')
    parser.add_argument('-t', '--thread', default=20,
                        type=int, help='Set max threads, default 20')
    parser.add_argument('-d', '--debug', default=False,
                        action='store_true', help='print some debug information')
    parser.add_argument('--try-again', default=False, action='store_true',
                        help='If some error, try again scan that url once', dest='tryagain')
    args = parser.parse_args()

    if args.file == sys.stdin and not select.select([sys.stdin, ], [], [], 0.0)[0]:
        parser.print_help()
        sys.exit()

    DEBUG = args.debug
    TRYAGAIN = args.tryagain

    w = whichAlive(
        file=args.file,
        THREAD_POOL_SIZE=args.thread,
        allow_redirect=True,
        PROXY={'http': args.proxy, 'https': args.proxy}
    )
    w.run()
