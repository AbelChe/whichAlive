#!/usr/bin/env python
import argparse
import codecs
import csv
import datetime
import os
import sys
import re
import socket
import sys
import time
import urllib
import urllib.parse
from concurrent.futures import ALL_COMPLETED, ThreadPoolExecutor, wait

import mmh3
import hashlib
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class whichAlive(object):
    def __init__(self, file, THREAD_POOL_SIZE=10, allow_redirect=False, TRYAGAIN=False, PROXY={}, nooutfile=False, timeout=10, DEBUG=False):
        self.DEBUG = DEBUG
        if self.DEBUG: print('DEBUG mode is on')
        self.script_path = os.path.dirname(__file__)
        self.file = file
        self.nooutfile = nooutfile
        if not self.nooutfile: self.timenow = time.strftime("%Y%m%d%H%M%S", time.localtime(time.time()))
        if not self.nooutfile: self.outfilename = f'{self.timenow}.csv'
        if not self.nooutfile: self.errorfilename = f'error_{self.timenow}.txt'
        self.urllist = self.__urlfromfile()
        self.tableheader = ['no', 'url', 'ip', 'state',
                            'state_code', 'title', 'cmsfinger', 'server', 'iconhash', 'length', 'other']
        self.HEADER = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36',
        }
        self.THREAD_POOL_SIZE = THREAD_POOL_SIZE
        self.TRYAGAIN = TRYAGAIN
        self.allurlnumber = len(self.urllist)
        self.completedurl = -1
        self.allow_redirect = allow_redirect
        self.PROXY = PROXY
        self.timeout = timeout
        self.__load_cmsfinger_database()

    def run(self):
        self.completedurl += 1
        if not self.nooutfile:
            self.__writetofile(self.tableheader)
        tasklist = []
        start_time = datetime.datetime.now()
        t = ThreadPoolExecutor(max_workers=self.THREAD_POOL_SIZE)
        for k, url in enumerate(self.urllist):
            tasklist.append(t.submit(self.__scan, url, k+1, self.TRYAGAIN))
        print(f'total {self.allurlnumber}')
        if wait(tasklist, return_when=ALL_COMPLETED):
            end_time = datetime.datetime.now()
            print(f'--------------------------------\nDONE, use {(end_time - start_time).seconds} seconds')
            if not self.nooutfile:
                print(f'outfile: {os.path.join(os.path.abspath(os.path.dirname(__file__)), "result", self.outfilename)}')

    def __scan(self, url, no, tryagainflag=False):
        def callback(no, url, ip, state, state_code, title, cmsfinger, server, iconhash, length, other):
            self.completedurl += 1
            thisline = [no, url, ip, state, state_code,
                        title, cmsfinger, server, iconhash, length, other]
            nowpercent = '%.2f' % ((self.completedurl/self.allurlnumber)*100)
            if state == 'alive':
                print(f'[{nowpercent}%] {url} | {ip} | \033[0;32;40m{state}\033[0m | {title} | {length} | {cmsfinger} |')
            else:
                print(f'[{nowpercent}%] {url} | {ip} | \033[0;31;40m{state}\033[0m | {title} | {length} | {cmsfinger} |')
            if not self.nooutfile:
                self.__writetofile(thisline)

        ip          = ''
        state       = ''
        state_code  = -1
        title       = ''
        server      = ''
        cmsfinger   = ''
        iconhash    = ''
        length      = -1
        other       = ''
        try:
            if self.DEBUG:
                print(f'[debug] {no} {url}')
            if not url.startswith('http://') and not url.startswith('https://'):
                url = 'http://' + url
            u = urllib.parse.urlparse(url)
            ip = self.__getwebip(u.netloc.split(':')[0])
            if self.allow_redirect:
                req = requests.get(url=url, headers=self.HEADER,
                                 timeout=self.timeout, verify=False, proxies=self.PROXY)
                state = 'alive'
                state_code = '->'.join([str(i.status_code)
                                       for i in req.history] + [str(req.status_code)])
                title = '->'.join([self.__getwebtitle(i)
                                  for i in req.history] + [self.__getwebtitle(req)])
                length = '->'.join([str(self.__getweblength(i))
                                   for i in req.history] + [str(self.__getweblength(req))])
                server = '->'.join([self.__getwebserver(i)
                                   for i in req.history] + [self.__getwebserver(req)])
                # mmh3 hash for fofa
                # md5 hash for hunter
                iconhash = '->'.join([self.__get_webiconhash(i)
                                      for i in req.history] + [self.__get_webiconhash(req)])
                #### Weather iconhash need transmit as a param???? 
                cmsfinger = self.__getwebcmsfinger(url, iconhash)
            else:
                req = requests.get(url=url, headers=self.HEADER, allow_redirects=False,
                                 timeout=self.timeout, verify=False, proxies=self.PROXY)
                state = 'alive'
                state_code = str(req.status_code)
                title = self.__getwebtitle(req)
                length = str(self.__getweblength(req))
                server = self.__getwebserver(req)
                iconhash = self.__get_webiconhash(req)
                cmsfinger = self.__getwebcmsfinger(url, iconhash)
            callback(no, url, ip, state, state_code, title,
                     cmsfinger, server, iconhash, length, other)
        except requests.exceptions.ConnectTimeout as e:
            if self.DEBUG:
                print(f'[ERROR][SCAN][ConnectTimeout] {url} {e}')
            self.__errorreport(str(e))
            state = 'dead'
            callback(no, url, ip, state, state_code, title, cmsfinger,
                     server, iconhash, length, 'ConnectTimeout')
        except requests.exceptions.ReadTimeout as e:
            if self.DEBUG:
                print(f'[ERROR][SCAN][ReadTimeout] {url} {e}')
            self.__errorreport(str(e))
            state = 'dead'
            callback(no, url, ip, state, state_code,
                     title, cmsfinger, server, iconhash, length, 'ReadTimeout')
        except requests.exceptions.ConnectionError as e:
            if self.DEBUG:
                print(f'[ERROR][SCAN][ConnectionError] {url} {e}')
            self.__errorreport(str(e))
            state = 'dead'
            callback(no, url, ip, state, state_code, title,
                     server, iconhash, cmsfinger, length, 'ConnectionError')
        except Exception as e:
            if self.DEBUG:
                print(f'[ERROR][SCAN][other] {no} {url} {e}')
            self.__errorreport(str(e))
            if tryagainflag:
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
                                  timeout=self.timeout, verify=False, proxies=self.PROXY)
            if r_icon.status_code != 200:
                return ''
            favicon = codecs.lookup('base64').encode(r_icon.content)[0]
            icon_hash_mmh3 = mmh3.hash(favicon)
            icon_hash_md5 = hashlib.md5(r_icon.content).hexdigest()
            if self.DEBUG:
                print(f'[debug][icon_hash] {icon_link} icon hash: [', icon_hash_mmh3, icon_hash_md5, ']')
            return '[{}|{}]'.format(str(icon_hash_mmh3), str(icon_hash_md5))
        except Exception as e:
            if self.DEBUG:
                print('[ERROR][webiconhash]', e)
            return ''

    def __load_cmsfinger_database(self):
        """
        Gente "self.finger_request_map" and "self.finger_relation_map"
        """
        try:
            print('[+] Loading Cmsfinger database...', end='')
            import json

            with open(f'{self.script_path}/web_fingerprint_v3.json') as f:
                self.j_data = json.load(f)
            self.finger_request_map = {}
            self.finger_relation_map = {}
            for i in self.j_data:
                this_request_obj = (
                    i.get('path'),
                    i.get('request_method'),
                    i.get('request_headers'),
                    i.get('request_data'),
                )
                request_id = hashlib.md5(str(this_request_obj).encode()).hexdigest()
                if request_id not in self.finger_request_map.keys():
                    self.finger_request_map[request_id] = this_request_obj
                if request_id not in self.finger_relation_map.keys():
                    self.finger_relation_map[request_id] = []
                self.finger_relation_map[request_id].append({
                    'status_code': i.get('status_code'),
                    'headers': i.get('headers'),
                    'keyword': i.get('keyword'),
                    'favicon_hash': i.get('favicon_hash'),
                    'name': i.get('name'),
                    'priority': i.get('priority'),
                })
            print(' Rules:{} Done'.format(len(self.j_data)))
        except Exception as e:
            if self.DEBUG:
                print('[ERROR][cmsfinger_database]', e)
            exit(1)

    def __getwebcmsfinger(self, url, iconhash) -> str:
        try:
            finger = []
            for req_id in self.finger_request_map.keys():
                req = requests.request(
                    method=self.finger_request_map[req_id][1],
                    url=urllib.parse.urljoin(url, self.finger_request_map[req_id][0]),
                    headers=self.HEADER.update(self.finger_request_map[req_id][2]),
                    data=self.finger_request_map[req_id][3],
                    timeout=self.timeout,
                    verify=False,
                    proxies=self.PROXY
                )
                for rule in self.finger_relation_map.get(req_id):
                    # 1. match keywords
                    if rule.get('keyword'):
                        kwd_matched_flag = 0
                        for kwd in rule.get('keyword'):
                            if kwd in req.content.decode():
                                kwd_matched_flag += 1
                        if kwd_matched_flag == len(rule.get('keyword')):
                            finger.append(rule.get('name'))
                    # 2. match headers 
                    #### Weather "status_code" need to be matched here???
                    if rule.get('headers'):
                        for hdr_key in rule.get('headers').keys():
                            if req.headers.get(hdr_key) == rule.get('headers').get(hdr_key):
                                finger.append(rule.get('name'))
                    # 3. match icon hash(md5)
                    matched_iconhash_md5 = []
                    ## mybe iconhash as:
                    ## [-12345678|12345678901234567890123456789012]->[-12345678|12345678901234567890123456789012]
                    if iconhash.replace('->', '') and rule.get('favicon_hash'):
                        if '->' in iconhash:
                            for iconhash_item in iconhash.split('->'):
                                matched_iconhash_md5.append(iconhash_item[1:-1].split('|')[1])
                        else:
                            matched_iconhash_md5.append(iconhash[1:-1].split('|')[1])
                        for i in matched_iconhash_md5:
                            if i in rule.get('favicon_hash'):
                                finger.append(rule.get('name'))
            return ','.join(set(finger))
        except Exception as e:
            if self.DEBUG:
                print(f'[ERROR][cmsfinger] {url} {e}')
            return ''

    def __urlfromfile(self) -> str:
        tmp_list = [i.replace('\n', '').replace('\r', '')
                    for i in self.file.readlines()]
        return tmp_list

    def __writetofile(self, data: list):
        if not self.nooutfile:
            f = open(f'{os.path.join(os.path.abspath(os.path.dirname(__file__)), "result", self.outfilename)}', 'a')
            writer = csv.writer(f)
            writer.writerow(data)
            f.close()

    def __errorreport(self, message):
        if not self.nooutfile:
            f = open(f'{os.path.join(os.path.abspath(os.path.dirname(__file__)), "error", self.errorfilename)}', 'a')
            f.write(message+'\n')
            f.close()


BANNER = """\
\033[95m           __    _      __    ___    ___
\033[94m _      __/ /_  (_)____/ /_  /   |  / (_)   _____
\033[93m| | /| / / __ \/ / ___/ __ \/ /| | / / / | / / _ \\
\033[92m| |/ |/ / / / / / /__/ / / / ___ |/ / /| |/ /  __/
\033[91m|__/|__/_/ /_/_/\___/_/ /_/_/  |_/_/_/ |___/\___/  \033[1mPRO\033[0m

\033[90mAbout: https://github.com/abelche/whichalive\033[0m
"""

HELP_MESSAGE = """\
FULL detect alive targets with more information(Iconhash, CMSFinger)
  python whichalive-pro.py -u url.txt
  cat url.txt | python whichalive-pro.py\
"""

def main():
    print(BANNER)
    parser = argparse.ArgumentParser(usage=HELP_MESSAGE)
    parser.add_argument('-f', '--file', metavar='FILE', nargs='?',
                        type=argparse.FileType('r'), default=sys.stdin, help='URL lists file.')
    parser.add_argument('--proxy', default='',
                        help='Set proxy, such as http://127.0.0.1:8080 or socks5://127.0.0.1:7777')
    parser.add_argument('-t', '--thread', default=20,
                        type=int, help='Set max threads, default 20')
    parser.add_argument('--timeout', default=10,
                        type=int, help='Set request timeout value, default 10s')
    parser.add_argument('-d', '--debug', default=False,
                        action='store_true', help='print some debug information')
    parser.add_argument('--no-redirect', default=False,
                        action='store_true', help='Set to disallow redirect', dest='noredirect')
    parser.add_argument('--try-again', default=False, action='store_true',
                        help='If some error, try again scan that url once', dest='tryagain')
    parser.add_argument('--no-outfile', default=False, action='store_true',
                        help='Set to NOT output results to file', dest='nooutfile')
    args = parser.parse_args()

    # Check whether the TTY has standard input.
    if args.file == sys.stdin and sys.stdin.isatty():
        parser.print_help()
        sys.exit()

    DEBUG = args.debug
    TRYAGAIN = args.tryagain
    NOOUTFILE = args.nooutfile

    w = whichAlive(
        file=args.file,
        THREAD_POOL_SIZE=args.thread,
        allow_redirect=(not args.noredirect),
        TRYAGAIN=TRYAGAIN,
        PROXY={'http': args.proxy, 'https': args.proxy},
        nooutfile=NOOUTFILE,
        timeout=args.timeout,
        DEBUG=DEBUG
    )
    w.run()

if __name__ == '__main__':
    main()
