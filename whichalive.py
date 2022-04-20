import argparse
import csv
import datetime
import os
import re
import socket
import time
import urllib
import urllib.parse
from concurrent.futures import ALL_COMPLETED, ThreadPoolExecutor, wait

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
DEBUG = False

class whichAlive(object):
    def __init__(self, file, THREAD_POOL_SIZE=10, allow_redirect=False, PROXY={}):
        self.file = file
        self.filename = ''.join(file.split('/')[-1].split('.')[:-1])
        self.timenow = str(time.time()).split(".")[0]
        self.outfilename = f'{self.filename}{self.timenow}.csv'
        self.errorfilename = f'error_{self.filename}{self.timenow}.txt'
        self.urllist = self.__urlfromfile()
        self.tableheader = ['no', 'url', 'ip', 'state',
                            'state_code', 'title', 'server', 'length', 'other']
        self.HEADER = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36',
        }
        self.THREAD_POOL_SIZE = THREAD_POOL_SIZE
        self.allurlnumber = len(self.urllist)
        self.completedurl = -1
        self.allow_redirect = allow_redirect
        self.PROXY = PROXY

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
            print(f'--------------------------------\nDONE, use {(end_time - start_time).seconds} seconds')
            print(f'outfile: {os.path.join(os.path.abspath(os.path.dirname(__file__)), "result", self.outfilename)}')

    def __scan(self, url, no, tryagainflag=False):
        def callback(no, url, ip, state, state_code, title, server, length, other):
            self.completedurl += 1
            thisline = [no, url, ip, state, state_code, title, server, length, other]
            nowpercent = '%.2f'%((self.completedurl/self.allurlnumber)*100)
            print(f'[{nowpercent}%] {url} {ip} {state} {title} {length}')
            self.__writetofile(thisline)

        ip = ''
        state = ''
        state_code = -1
        title = ''
        server = ''
        length = -1
        other = ''
        try:
            if DEBUG: print(f'[+] {no} {url}')
            u = urllib.parse.urlparse(url)
            ip = self.__getwebip(u.netloc.split(':')[0])
            if self.allow_redirect:
                r = requests.get(url=url, headers=self.HEADER, timeout=15, verify=False, proxies=self.PROXY)
                state = 'alive'
                state_code = '->'.join([str(i.status_code) for i in r.history] + [str(r.status_code)])
                title = '->'.join([self.__getwebtitle(i) for i in r.history] + [self.__getwebtitle(r)])
                length = '->'.join([str(self.__getweblength(i)) for i in r.history] + [str(self.__getweblength(r))])
                server = '->'.join([self.__getwebserver(i) for i in r.history] + [str(self.__getwebserver(r))])
            else:
                r = requests.get(url=url, headers=self.HEADER, allow_redirects=False, timeout=15, verify=False, proxies=self.PROXY)
                state = 'alive'
                state_code = r.status_code
                title = self.__getwebtitle(r)
                length = self.__getweblength(r)
                server = self.__getwebserver(r)
            callback(no, url, ip, state, state_code, title, server, length, other)
        except requests.exceptions.ConnectTimeout as e:
            if DEBUG: print(f'[ConnectTimeout] {url} {e}')
            self.__errorreport(str(e))
            state = 'dead'
            callback(no, url, ip, state, state_code, title, server, length, 'ConnectTimeout')
        except requests.exceptions.ReadTimeout as e:
            if DEBUG: print(f'[ReadTimeout] {url} {e}')
            self.__errorreport(str(e))
            state = 'dead'
            callback(no, url, ip, state, state_code, title, server, length, 'ReadTimeout')
        except requests.exceptions.ConnectionError as e:
            if DEBUG: print(f'[ConnectionError] {url} {e}')
            self.__errorreport(str(e))
            state = 'dead'
            callback(no, url, ip, state, state_code, title, server, length, 'ConnectionError')
        except Exception as e:
            if DEBUG: print(f'[ERROR] {no} {url} {e}')
            self.__errorreport(str(e))
            if TRYAGAIN and not tryagainflag:
                self.__scan(url, no, True)
            callback(no, url, ip, state, state_code, title, server, length, 'e')

    def __getwebtitle(self, r):
        try:
            if r.headers.get('Content-Type').split('charset=')[1]:
                charset = r.headers.get('Content-Type').split('charset=')[1]
            elif re.findall(r'<meta charset=(.*?)>', r.text)[0].replace('\'', '').replace('"', ''):
                charset = re.findall(r'<meta charset=(.*?)>', r.text)[0].replace('\'', '').replace('"', '')
            else:
                charset = 'utf8'
            return re.findall(r'<title>(.*?)</title>', r.content.decode(charset))[0]
        except:
            return ''

    def __getwebip(self, domain):
        try:
            ip = socket.getaddrinfo(domain, 'http')
            return ip[0][4][0]
        except:
            return ''

    def __getweblength(self, r):
        try:
            return len(r.content)
        except:
            return -1

    def __getwebserver(self, r):
        try:
            return r.headers.get('server') if r.headers.get('server') else ''
        except:
            return ''

    def __urlfromfile(self):
        with open(self.file, 'r') as f:
            return [i.replace('\n', '').replace('\r', '') for i in f.readlines()]

    def __writetofile(self, data: list):
        f = open(f'result/{self.outfilename}', 'a')
        writer = csv.writer(f)
        writer.writerow(data)
        f.close()

    def __errorreport(self, message):
        f = open(f'error/{self.errorfilename}', 'a')
        f.write(message+'\n')
        f.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(usage='whichAlive usage')
    parser.add_argument('-f', '--file', default='url.txt', help='URL lists file.')
    parser.add_argument('--proxy', default='', help='Set proxy, such as 127.0.0.1:8080')
    parser.add_argument('-t', '--thread', default=10, type=int, help='Set max threads, default 10')
    parser.add_argument('-d', '--debug', default=False, action='store_true', help='print some debug information')
    parser.add_argument('--try-again', default=False, action='store_true', help='If some error, try again scan that url once', dest='tryagain')
    args = parser.parse_args()

    DEBUG = args.debug
    TRYAGAIN = args.tryagain

    w = whichAlive(
        file=args.file,
        THREAD_POOL_SIZE=args.thread,
        allow_redirect=True,
        PROXY={'http': args.proxy, 'https': args.proxy}
    )
    w.run()
