#!/usr/bin/env python
# coding:utf-8
# pnig0s@20140216
import sys
sys.path.append('..')

from task import sqlmap_spider


class send_url_to_celery(object):
    '''a plugin let crawled urls send to celery'''
    @classmethod
    def start(cls, urldata):
        '''"start" func is the start point of plugin'''
        payload={'url':urldata.url}
        result=sqlmap_spider.delay(payload)
        result.get()

