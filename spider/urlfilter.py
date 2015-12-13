#!/usr/bin/env python
# coding:utf-8
# manning  2015-1-27
import time
import os
import urlparse
import hashlib
import sys
#sys.path.append("..")

#from config.config import *
#reload(sys)
#sys.setdefaultencoding("utf-8")
from pybloomfilter import BloomFilter

bf = BloomFilter (100000,0.01)
def format(url):
    '''
    策略是构建一个三元组
    第一项为url的netloc
    第二项为path中每项的拆分长度
    第三项为query的每个参数名称(参数按照字母顺序排序，避免由于顺序不同而导致的重复问题)
    '''
    if urlparse.urlparse(url)[2] == '':
        url = url+'/'

    url_structure = urlparse.urlparse(url)
    netloc = url_structure[1]
    path = url_structure[2]
    query = url_structure[4]

    temp = (netloc,tuple([len(i) for i in path.split('/')]),tuple(sorted([i.split('=')[0] for i in query.split('&')])))
    #print temp
    return temp


def check_netloc_is_ip(netloc):
    '''
    如果url的netloc为ip形式
    return True
    否则
    return False
    '''
    flag =0
    t = netloc.split('.')
    for i in t:
        try:
            int(i)
            flag += 1
        except Exception, e:
            break
    if flag == 4:
        return True

    return False

def url_similar_control(url):
    '''
    URL相似性控制

    True url未重复
    False url重复
    '''
    t = format(url)
    if t not in bf:
        bf.add(t)
        return True
    return False

def url_repeat_control(url):
    '''
    URL重复控制

    True url未重复
    False url重复
    '''
    if url not in bf:
        bf.add(url)
        return True
    return False

