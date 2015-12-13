## ark-分布式sql扫描框架

集成各种优秀开源项目一款sql注入扫描框架。

参考和使用的项目：

- sqlmap
- celery
- flower
- autosqlmap by [xibijj](https://github.com/xibijj/autoSqlmap)
- vulcanspider by [pnigos](https://github.com/pnigos/vulcan) 

### 特性

- 支持spider和proxy两种工作方式
- 支持get、post方式注入检测，支持ssl(需要导入证书)
- 支持分布式(*celery*)
- 支持结果存储、回显、查询(*redis*和*flower*)
- spider支持多线程和协程两种模型(*gevent*)
- spider支持动态user_agent
- spider支持ajax、javascript爬取(*splinter*和*phtomjs*)
- spider支持域名相似性判断(*pybloomfilter*)、同源性判断(*publicsuffixlist*)、域名过滤、后缀过滤
- 框架式处理，后续增加任务(如xss检测)简单

### 缺点

- 依赖的库较多，部署不方便
- 程序结构不明朗
- 配置麻烦

### 使用说明

- 1.安装依赖(requirements.txt)
- 2.开启redis
- 3.开启sqlmapapi
- 4.开启celery
- 5.开启flower
- 6.开启spider爬虫或者开启代理

### 效果图

![图一](https://raw.githubusercontent.com/cflq3/ark/master/screenshots/ark_1.png)
![图二](https://raw.githubusercontent.com/cflq3/ark/master/screenshots/ark_2.png)







