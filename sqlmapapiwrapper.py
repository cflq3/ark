# -*- coding: utf-8 -*-
import requests
import json
import os
import time

#import config

class SqlmapAPIWrapper():

    def __init__(self, payload):
        config={}
        config['smart']= True
        config['risk']=3
        config['level']=3
        config['randomAgent']= True
        #config['forms']=True
        config['batch']= True
        #config['mobile']= True
        #config['tech']='BET'
        self.url = 'http://127.0.0.1:8775'
        self.taskid = None
        self.start_time = time.time()
        #self.filepath = config.save_path + '/' + filename
        #self.options = {'requestFile': self.filepath}
        #传过来的payload跟配置文件的sqlmap参数组合，传给sqlmapapi
        self.options = payload
        self.options.update(config)
        self.headers = {'Content-Type': 'application/json'}

    def settaskid(self, taskid):
        #print taskid
        self.taskid = taskid

    def new(self):
        path = '/task/new'
        r = requests.get(self.url + path, headers=self.headers).json()
        if r['success']:
            self.taskid = r['taskid']
        return r['success']

    def delete(self):
        path = '/task/%s/delete' % self.taskid
        #print 'delete' + path
        r = requests.get(self.url + path, headers=self.headers).json()
        self.taskid = None
        return r['success']

    def scan_start(self):
        #调用new()得到一个taskid
        self.new()
        path = '/scan/%s/start' % self.taskid
        #print 'scan_start' + path
        #print (self.url + path, json.dumps(self.options), self.headers)
        r = requests.post(self.url + path, data=json.dumps(self.options), headers=self.headers).json()
        return r['success']

    def scan_stop(self):
        path = '/scan/%s/stop' % self.taskid
        #print 'scan_stop' + path
        r = requests.get(self.url + path, headers=self.headers).json()
        return r['success']

    def scan_kill(self):
        path = '/scan/%s/kill' % self.taskid
        r = requests.get(self.url + path, headers=self.headers).json()
        return r['success']

    def scan_status(self):
        path = '/scan/%s/status' % self.taskid
        #print 'scan_status' + path
        r = requests.get(self.url + path, headers=self.headers).json()
        if r['success']:
            return r['status']
        else:
            return None

    def scan_data(self):
        path = '/scan/%s/data' % self.taskid
        self.res=json.loads(requests.get(self.url + path, headers=self.headers).text)['data']
        #print r
        #print r['data']
        if len(self.res)==0:
            e='not injection!'
            return e
            #print "r['success']"
        else:
            return self.res

    def terminal(self):
        if self.scan_status() == 'terminated':
            return self.scan_status()

    def vulnerable(self):
        #print "vulnerable()"
        #print len(self.scan_data())
        return len(self.scan_data()) > 0

    def delete_file(self):
        os.remove(self.filepath)

    def clear(self):
        self.scan_stop()
        self.scan_kill()

    def run(self):
        if not self.new():
            return False

        if not self.scan_start():
            return False

        while True:

                if self.scan_status()=='running':
                    time.sleep(5)
                elif self.terminal():
                    break
                elif time.time()-self.start_time>180:
                    self.clear()
                    break

        return self.scan_data()

if __name__ == '__main__':
    t = SqlmapAPIWrapper('http://testphp.vulnweb.com')
    t.run()

