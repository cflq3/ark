#!/usr/bin/env python
# encoding: utf-8

from celery import Celery
#sys.path.append('..')
from sqlmapapiwrapper import SqlmapAPIWrapper

celery = Celery('task')


class config:


    BROKER_URL = 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'

    CELERY_TASK_SERIALIZER = 'pickle'
    CELERY_ACCEPT_CONTENT = ['pickle']
    CELERY_MESSAGE_COMPRESSION = 'zlib'
    CELERY_DISABLE_RATE_LIMITS = True
  # CELERYD_PREFETCH_MULTIPLIER = 1
    CELERY_TASK_RESULT_EXPIRES = 3600
    CELERY_TIMEZONE = 'US/Pacific'


celery.config_from_object(config)


@celery.task
def sqlmap_spider(url):
    x=url
    t=SqlmapAPIWrapper(x)
    return t.run()

@celery.task
def sqlmap_proxy(payload):
    x=payload
    t=SqlmapAPIWrapper(x)
    return t.run()


