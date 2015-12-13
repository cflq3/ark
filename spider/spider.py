#!/usr/bin/env python
# coding:utf-8


'''
project_ark:spider @ 2015.10

most coded by pnig0s@20140131

previous name is Vulcan spider

modified by hackerlq @ 2015.10

1.调整同源控制为根目录，便于爬行分站
2.增加自动选择user-agent，提高存活率
3.增加文件过滤种类，避免无效爬取
4.增加url去重，避免重复爬取（采用pybloomfiltermmap，详见urlfilter.py）
5.增加url相似性判断，提高爬行效率（采用pybloomfiltermmap，详见urlfilter.py）
6.增加一个将爬取的url发送到celery任务调度（基于redis），便于分布式利用爬取的url（如sqlmapapi分布式调度）

TODO：
1.添加动态取得代理功能，避免爬虫被封IP
2.因为实测目前性能瓶颈不在爬虫本身，而在后续任务（sqlmapapi，xssscan）等，所以目前不考虑爬虫的分布式
3.目前根据sqlmap的--forms选项自动测试表单，后续将cookie和表单提交的参数自动化发送给celery以及sqlmap
4.自动判断并填写referer
5.爬虫爬取频率控制

基于gevent和多线程模型，支持WebKit引擎的DOM解析动态爬虫框架。
框架由两部分组成：
fetcher:下载器，负责获取HTML，送入crawler。
crawler:爬取器，负责解析并爬取HTML中的URL，送入fetcher。
fetcher和crawler两部分独立工作，互不干扰，通过queue进行链接
fetcher需要发送HTTP请求，涉及到阻塞操作，使用gevent池控制
crawler没有涉及阻塞操作，但为了扩展可以自选gevent池和多线程池两种模型控制

'''

import gevent
from gevent import monkey
from gevent import Greenlet
from gevent import pool
from gevent import queue
from gevent import event
from gevent import Timeout
from gevent import threadpool

from exceptions import *
from plugin import *
from contextlib import closing
from publicsuffixlist import PublicSuffixList
monkey.patch_all()
import re
import os
import sys
sys.setrecursionlimit(10000)
import time
import uuid
import string
import urlparse
import logging
import random
import requests
import chardet
import urlfilter
from Data import UrlCache,UrlData
from utils import HtmlAnalyzer

try:
    from utils import WebKit
except Exception,e:
    pass

def monkey_patch():
    '''
    requests库中文乱码补丁
    '''
    prop = requests.models.Response.content
    def content(self):
        _content = prop.fget(self)
        if self.encoding == 'ISO-8859-1':
            encodings = requests.utils.get_encodings_from_content(_content)
            if encodings:
                self.encoding = encodings[0]
            else:
                self.encoding = self.apparent_encoding
            _content = _content.decode(self.encoding, 'replace').encode('utf8', 'replace')
            self._content = _content
        return _content
    requests.models.Response.content = property(content)

monkey_patch()

def to_unicode(data, charset=None):
    '''
    将输入的字符串转化为unicode对象
    '''
    unicode_data = ''
    if isinstance(data,str):
        if not charset:
            try:
                charset = chardet.detect(data).get('encoding')
            except Exception,e:
                pass
        if charset:
            unicode_data = data.decode(charset,'ignore')
        else:
            unicode_data = data
    else:
        unicode_data = data
    return unicode_data

class Fetcher(Greenlet):
    """抓取器(下载器)类"""
    def __init__(self,spider):
        Greenlet.__init__(self)
        self.fetcher_id = str(uuid.uuid1())[:8]
        self.TOO_LONG = 2048576 # 1M
        self.spider = spider
        self.fetcher_cache = self.spider.fetcher_cache
        self.crawler_cache = self.spider.crawler_cache
        self.fetcher_queue = self.spider.fetcher_queue
        self.crawler_queue = self.spider.crawler_queue
        self.logger = self.spider.logger

    def _fetcher(self):
        '''
        抓取器主函数
        '''
        self.logger.info("fetcher %s starting...." % (self.fetcher_id,))
        while not self.spider.stopped.isSet():
            try:
                url_data = self.fetcher_queue.get(block=False)
            except queue.Empty,e:
                if self.spider.crawler_stopped.isSet() and self.fetcher_queue.unfinished_tasks == 0:
                    self.spider.stop()
                elif self.crawler_queue.unfinished_tasks == 0 and self.fetcher_queue.unfinished_tasks == 0:
                    self.spider.stop()
                else:
                    gevent.sleep()
            else:
                if not url_data.html:
                    try:
                        if url_data not in set(self.crawler_cache):
                            html = ''
                            with gevent.Timeout(self.spider.internal_timeout,False) as timeout:
                                html = self._open(url_data)
                            if not html.strip():
                                self.spider.fetcher_queue.task_done()
                                continue
                            self.logger.info("fetcher %s get %s " % (self.fetcher_id,url_data))
                            url_data.html = html
                            if not self.spider.crawler_stopped.isSet():
                                self.crawler_queue.put(url_data,block=True)
                            self.crawler_cache.insert(url_data)
                    except Exception,e:
                        import traceback
                        traceback.print_exc()
                self.spider.fetcher_queue.task_done()

    def _open(self,url_data):
        '''
        获取HTML内容
        '''
        human_headers = {
            'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'User-Agent':'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1700.76 Safari/537.36',
            'Accept-Encoding':'gzip,deflate,sdch'
        }
        if self.spider.custom_headers:
            human_headers.update(self.spider.custom_headers)
        try:
            #s=requests.Session()
            #r=s.get(url_data.url,headers=human_headers,stream=True)
             r = requests.get(url_data.url,headers=human_headers,stream=True)
        except Exception,e:
            self.logger.warn("%s %s" % (url_data.url,str(e)))
            return u''
        else:
            if r.headers.get('content-type','').find('text/html') < 0:
                r.close()
                return u''
            if int(r.headers.get('content-length',self.TOO_LONG)) > self.TOO_LONG:
                r.close()
                return u''
            try:
                html = r.content
                html = html.decode('utf-8','ignore')
            except Exception,e:
                self.logger.warn("%s %s" % (url_data.url,str(e)))
            finally:
                r.close()
                if vars().get('html'):
                    return html
                else:
                    return u''

    def _run(self):
        self._fetcher()


class Spider(object):
    """爬虫主类"""
    logger = logging.getLogger("spider")



    def __init__(self, concurrent_num=10, crawl_tags=[], custom_headers={}, plugin=['send_url_to_celery'], depth=10,
                 max_url_num=3000000, internal_timeout=20, spider_timeout=6*3600,
                 crawler_mode=1, same_origin=True, dynamic_parse=True):
        """
        concurrent_num    : 并行crawler和fetcher数量
        crawl_tags        : 爬行时收集URL所属标签列表
        custom_headers    : 自定义HTTP请求头
        plugin            : 自定义插件列表
        depth             : 爬行深度限制
        max_url_num       : 最大收集URL数量
        internal_timeout  : 内部调用超时时间
        spider_timeout    : 爬虫超时时间
        crawler_mode      : 爬取器模型(0:多线程模型,1:gevent模型)
        same_origin       : 是否限制相同域下
        dynamic_parse     : 是否使用WebKit动态解析
        """
        USER_AGENTS = [
    "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1; AcooBrowser; .NET CLR 1.1.4322; .NET CLR 2.0.50727)",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0; Acoo Browser; SLCC1; .NET CLR 2.0.50727; Media Center PC 5.0; .NET CLR 3.0.04506)",
    "Mozilla/4.0 (compatible; MSIE 7.0; AOL 9.5; AOLBuild 4337.35; Windows NT 5.1; .NET CLR 1.1.4322; .NET CLR 2.0.50727)",
    "Mozilla/5.0 (Windows; U; MSIE 9.0; Windows NT 9.0; en-US)",
    "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Win64; x64; Trident/5.0; .NET CLR 3.5.30729; .NET CLR 3.0.30729; .NET CLR 2.0.50727; Media Center PC 6.0)",
    "Mozilla/5.0 (compatible; MSIE 8.0; Windows NT 6.0; Trident/4.0; WOW64; Trident/4.0; SLCC2; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR 3.0.30729; .NET CLR 1.0.3705; .NET CLR 1.1.4322)",
    "Mozilla/4.0 (compatible; MSIE 7.0b; Windows NT 5.2; .NET CLR 1.1.4322; .NET CLR 2.0.50727; InfoPath.2; .NET CLR 3.0.04506.30)",
    "Mozilla/5.0 (Windows; U; Windows NT 5.1; zh-CN) AppleWebKit/523.15 (KHTML, like Gecko, Safari/419.3) Arora/0.3 (Change: 287 c9dfb30)",
    "Mozilla/5.0 (X11; U; Linux; en-US) AppleWebKit/527+ (KHTML, like Gecko, Safari/419.3) Arora/0.6",
    "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.8.1.2pre) Gecko/20070215 K-Ninja/2.1.1",
    "Mozilla/5.0 (Windows; U; Windows NT 5.1; zh-CN; rv:1.9) Gecko/20080705 Firefox/3.0 Kapiko/3.0",
    "Mozilla/5.0 (X11; Linux i686; U;) Gecko/20070322 Kazehakase/0.4.5",
    "Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.0.8) Gecko Fedora/1.9.0.8-1.fc10 Kazehakase/0.5.6",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/535.11 (KHTML, like Gecko) Chrome/17.0.963.56 Safari/535.11",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_3) AppleWebKit/535.20 (KHTML, like Gecko) Chrome/19.0.1036.7 Safari/535.20",
    "Opera/9.80 (Macintosh; Intel Mac OS X 10.6.8; U; fr) Presto/2.9.168 Version/11.52",
]

        self.logger.setLevel(logging.DEBUG)
        hd = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        hd.setFormatter(formatter)
        self.logger.addHandler(hd)

        self.stopped = event.Event()
        self.internal_timeout = internal_timeout
        self.internal_timer = Timeout(internal_timeout)

        self.crawler_mode = crawler_mode #爬取器模型
        self.concurrent_num = concurrent_num
        self.fetcher_pool = pool.Pool(self.concurrent_num)
        if self.crawler_mode == 0:
            self.crawler_pool = threadpool.ThreadPool(min(50,self.concurrent_num))
        else:
            self.crawler_pool = pool.Pool(self.concurrent_num)

        #self.fetcher_queue = queue.JoinableQueue(maxsize=self.concurrent_num*100)
        self.fetcher_queue = threadpool.Queue(maxsize=self.concurrent_num*10000)
        self.crawler_queue = threadpool.Queue(maxsize=self.concurrent_num*10000)

        self.fetcher_cache = UrlCache()
        self.crawler_cache = UrlCache()

        self.default_crawl_tags = ['a','base','iframe','frame','object','framset']
        self.ignore_ext = ['cab', 'ico', 'swf', 'rar', 'zip', 'tar', 'gz', 'js','7z', 'bz2', 'iso', 'nrg', 'uif', 'exe', 'rpm', 'deb', 'dmg', 'jar', 'jad', 'bin', 'apk', 'run', 'msi', 'xls', 'xlsx', 'ppt', 'pptx', 'pdf', 'doc', 'docx', 'odf', 'rtf', 'odt', 'mkv', 'avi', 'mp4', 'flv', 'WebM', 'mov', 'wmv', '3gp', 'mpg', 'mpeg', 'mp3', 'wav', 'ss3','ogg', 'mp4a', 'wma', 'png', 'jpeg', 'jpg', 'xpm', 'gif', 'tiff', 'css', 'bmp', 'svg', 'exif', 'thmx',  'xml', 'txt']
        self.crawl_tags = list(set(self.default_crawl_tags)|set(crawl_tags))
        self.same_origin = same_origin
        self.depth = depth
        self.max_url_num = max_url_num
        self.dynamic_parse = dynamic_parse
        if self.dynamic_parse:
            self.webkit = WebKit()
        self.crawler_stopped = event.Event()

        self.plugin_handler = plugin #注册Crawler中使用的插件
        self.custom_headers = {'User-Agent': random.choice(USER_AGENTS)}

    def _start_fetcher(self):
        '''
        启动下载器
        '''
        for i in xrange(self.concurrent_num):
            fetcher = Fetcher(self)
            self.fetcher_pool.start(fetcher)

    def _start_crawler(self):
        '''
        启动爬取器
        '''
        for _ in xrange(self.concurrent_num):
            self.crawler_pool.spawn(self.crawler)

    def start(self):
        '''
        主启动函数
        '''
        self.logger.info("spider starting...")

        if self.crawler_mode == 0:
            self.logger.info("crawler run in multi-thread mode.")
        elif self.crawler_mode == 1:
            self.logger.info("crawler run in gevent mode.")

        self._start_fetcher()
        self._start_crawler()

        self.stopped.wait() #等待停止事件置位

        try:
            self.internal_timer.start()
            self.fetcher_pool.join(timeout=self.internal_timer)
            if self.crawler_mode == 1:
                self.crawler_pool.join(timeout=self.internal_timer)
            else:
                self.crawler_pool.join()
        except Timeout:
            self.logger.error("internal timeout triggered")
        finally:
            self.internal_timer.cancel()

        self.stopped.clear()
        if self.dynamic_parse:
            self.webkit.close()
        self.logger.info("crawler_cache:%s fetcher_cache:%s" % (len(self.crawler_cache),len(self.fetcher_cache)))
        self.logger.info("spider process quit.")

    def crawler(self,_dep=None):
        '''
        爬行器主函数
        '''
        while not self.stopped.isSet() and not self.crawler_stopped.isSet():
            try:
                self._maintain_spider() #维护爬虫池
                url_data = self.crawler_queue.get(block=False)
            except queue.Empty,e:
                if self.crawler_queue.unfinished_tasks == 0 and self.fetcher_queue.unfinished_tasks == 0:
                    self.stop()
                else:
                    if self.crawler_mode == 1:
                        gevent.sleep()
            else:
                pre_depth = url_data.depth
                curr_depth = pre_depth+1
                link_generator = HtmlAnalyzer.extract_links(url_data.html,url_data.url,self.crawl_tags)
                link_list = [ url for url in link_generator]
                if self.dynamic_parse:
                    link_generator = self.webkit.extract_links(url_data.url)
                    link_list.extend([ url for url in link_generator])
                link_list = list(set(link_list))
                for index,link in enumerate(link_list):
                    if not self.check_url_usable(link):
                        continue
                    # 增加url相似性判断，详见urlfilter.py
                    if not self.check_url_similar(link):
                        continue
                    # 增加url重复判断,详见urlfilter.py
                    if not self.check_url_repeat(link):
                        continue
                    if curr_depth > self.depth:   #最大爬行深度判断
                        if self.crawler_stopped.isSet():
                            break
                        else:
                            self.crawler_stopped.set()
                            break

                    if len(self.fetcher_cache) == self.max_url_num:   #最大收集URL数量判断
                        if self.crawler_stopped.isSet():
                            break
                        else:
                            self.crawler_stopped.set()
                            break
                    link = to_unicode(link)
                    url = UrlData(link,depth=curr_depth)
                    self.fetcher_cache.insert(url)
                    self.fetcher_queue.put(url,block=True)

                for plugin_name in self.plugin_handler: #循环动态调用初始化时注册的插件
                    try:
                        plugin_obj = eval(plugin_name)()
                        plugin_obj.start(url_data)
                    except Exception,e:
                        import traceback
                        traceback.print_exc()

                self.crawler_queue.task_done()

    def check_url_usable(self,link):
        '''
        检查URL是否符合可用规则
        '''
        if link in self.fetcher_cache:
            return False

        if not link.startswith("http"):
            return False

        if self.same_origin:
            if not self._check_same_origin(link):
                return False

        link_ext = os.path.splitext(urlparse.urlsplit(link).path)[-1][1:]
        if link_ext in self.ignore_ext:
            return False

        return True

    def check_url_similar(self,link):
        '''
        检查url相似性，并去重
        '''
        if urlfilter.url_similar_control(link)==True:
            return True
        else:
            return False

    def check_url_repeat(self,link):
        '''
        检查url是否重复
        '''
        if urlfilter.url_repeat_control(link)==True:
            return True
        else:
            return False



    def feed_url(self,url):
        '''
        设置初始爬取URL
        '''
        if isinstance(url,basestring):
            url = to_unicode(url)
            url = UrlData(url)

        if self.same_origin:
            url_part = urlparse.urlparse(unicode(url))
            psl = PublicSuffixList()
            self.origin = psl.privatesuffix(url_part.netloc)

        self.fetcher_queue.put(url,block=True)

    def stop(self):
        '''
        终止爬虫
        '''
        self.stopped.set()

    def _maintain_spider(self):
        '''
        维护爬虫池:
        1)从池中剔除死掉的crawler和fetcher
        2)根据剩余任务数量及池的大小补充crawler和fetcher
        维持爬虫池饱满
        '''
        if self.crawler_mode == 1:
            for greenlet in list(self.crawler_pool):
                if greenlet.dead:
                    self.crawler_pool.discard(greenlet)
            for i in xrange(min(self.crawler_queue.qsize(),self.crawler_pool.free_count())):
                self.crawler_pool.spawn(self.crawler)

        for greenlet in list(self.fetcher_pool):
            if greenlet.dead:
                self.fetcher_pool.discard(greenlet)
        for i in xrange(min(self.fetcher_queue.qsize(),self.fetcher_pool.free_count())):
            fetcher = Fetcher(self)
            self.fetcher_pool.start(fetcher)

    def _check_same_origin(self,current_url):
        '''
        检查两个URL是否同源
        '''
        current_url = to_unicode(current_url)
        url_part = urlparse.urlparse(current_url)
        #url_part_list=url_part.netloc.split('.')
        psl2 = PublicSuffixList()
        url_origin = psl2.privatesuffix(url_part.netloc)
        return url_origin == self.origin

if __name__ == '__main__':
    spider = Spider(concurrent_num=10,depth=10,max_url_num=300000,crawler_mode=1,dynamic_parse=True)
    url = sys.argv[1]
    spider.feed_url(url)
    spider.start()
