#!/usr/bin/env python
import argparse
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

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
DEBUG = False

class whichAlive(object):
    def __init__(self, file, THREAD_POOL_SIZE=10, allow_redirect=False, TRYAGAIN=False, PROXY={}, nooutfile=False, timeout=10):
        self.script_path = os.path.dirname(__file__)
        self.file = file
        self.nooutfile = nooutfile
        if not self.nooutfile: self.timenow = time.strftime("%Y%m%d%H%M%S", time.localtime(time.time()))
        if not self.nooutfile: self.outfilename = f'{self.timenow}.csv'
        if not self.nooutfile: self.errorfilename = f'error_{self.timenow}.txt'
        self.urllist = self.__urlfromfile()
        self.tableheader = ['no', 'url', 'ip', 'state',
                            'state_code', 'title', 'server', 'length', 'other']
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
        def callback(no, url, ip, state, state_code, title, server, length, other):
            self.completedurl += 1
            thisline = [no, url, ip, state, state_code,
                        title, server, length, other]
            nowpercent = '%.2f' % ((self.completedurl/self.allurlnumber)*100)
            if state == 'alive':
                print(f'[{nowpercent}%] {url} | {ip} | \033[0;32;40m{state}\033[0m | {title} | {length}')
            else:
                print(f'[{nowpercent}%] {url} | {ip} | \033[0;31;40m{state}\033[0m | {title} | {length}')
            if not self.nooutfile:
                self.__writetofile(thisline)

        ip = ''
        state = ''
        state_code = -1
        title = ''
        server = ''
        length = -1
        other = ''
        try:
            if DEBUG:
                print(f'[debug] {no} {url}')
            if not url.startswith('http://') and not url.startswith('https://'):
                url = 'http://' + url
            u = urllib.parse.urlparse(url)
            ip = self.__getwebip(u.netloc.split(':')[0])
            if self.allow_redirect:
                r = requests.get(url=url, headers=self.HEADER,
                                 timeout=self.timeout, verify=False, proxies=self.PROXY)
                state = 'alive'
                state_code = '->'.join([str(i.status_code)
                                       for i in r.history] + [str(r.status_code)])
                title = '->'.join([self.__getwebtitle(i)
                                  for i in r.history] + [self.__getwebtitle(r)])
                length = '->'.join([str(self.__getweblength(i))
                                   for i in r.history] + [str(self.__getweblength(r))])
                server = '->'.join([self.__getwebserver(i)
                                   for i in r.history] + [self.__getwebserver(r)])
            else:
                r = requests.get(url=url, headers=self.HEADER, allow_redirects=False,
                                 timeout=self.timeout, verify=False, proxies=self.PROXY)
                state = 'alive'
                state_code = str(r.status_code)
                title = self.__getwebtitle(r)
                length = str(self.__getweblength(r))
                server = self.__getwebserver(r)
            callback(no, url, ip, state, state_code, title, server, length, other)
        except requests.exceptions.ConnectTimeout as e:
            if DEBUG:
                print(f'[ERROR][SCAN][ConnectTimeout] {url} {e}')
            self.__errorreport(str(e))
            state = 'dead'
            callback(no, url, ip, state, state_code, title,
                     server, length, 'ConnectTimeout')
        except requests.exceptions.ReadTimeout as e:
            if DEBUG:
                print(f'[ERROR][SCAN][ReadTimeout] {url} {e}')
            self.__errorreport(str(e))
            state = 'dead'
            callback(no, url, ip, state, state_code,
                     title, server, length, 'ReadTimeout')
        except requests.exceptions.ConnectionError as e:
            if DEBUG:
                print(f'[ERROR][SCAN][ConnectionError] {url} {e}')
            self.__errorreport(str(e))
            state = 'dead'
            callback(no, url, ip, state, state_code, title,
                     server, length, 'ConnectionError')
        except Exception as e:
            if DEBUG:
                print(f'[ERROR][SCAN][other] {no} {url} {e}')
            self.__errorreport(str(e))
            if tryagainflag:
                self.__scan(url, no, True)
            callback(no, url, ip, state, state_code,
                     title, server, length, 'e')

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
           __    _      __    ___    ___
 _      __/ /_  (_)____/ /_  /   |  / (_)   _____
| | /| / / __ \/ / ___/ __ \/ /| | / / / | / / _ \\
| |/ |/ / / / / / /__/ / / / ___ |/ / /| |/ /  __/
|__/|__/_/ /_/_/\___/_/ /_/_/  |_/_/_/ |___/\___/  \033[95mFAST\033[0m

\033[90mAbout: https://github.com/abelche/whichalive\033[0m
"""

HELP_MESSAGE = """FAST detect alive targets
  python whichalive-air.py -u url.txt
  cat url.txt | python whichalive-air.py\
"""

if __name__ == '__main__':
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
        PROXY={'http': args.proxy, 'https': args.proxy},
        nooutfile=NOOUTFILE,
        timeout=args.timeout
    )
    w.run()
