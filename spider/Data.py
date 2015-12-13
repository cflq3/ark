#!/usr/bin/env python
# coding:utf-8
# code by pnig0s@20140131


class UrlData(object):
    '''URL对象类'''
    def __init__(self, url, html=None, depth=0):
        self.url = url
        self.html = html
        self.depth = depth
        self.params = {}
        self.fragments = {}
        self.post_data = {}
        
    def __str__(self):
        return self.url
    
    def __repr__(self):
        return '<Url data: %s>' % (self.url,)
    
    def __hash__(self):
        return hash(self.url)
    

class UrlCache(object):
    '''URL缓存类'''
    def __init__(self):
        self.__url_cache = {}
        
    def __len__(self):
        return len(self.__url_cache)
    
    def __contains__(self,url):
        return hash(url) in self.__url_cache.keys()
    
    def __iter__(self):
        for url in self.__url_cache:
            yield url
    
    def insert(self,url):
        if isinstance(url,basestring):
            url = UrlData(url)
        if url not in self.__url_cache:
            self.__url_cache.setdefault(hash(url),url)