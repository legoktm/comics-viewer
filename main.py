#!/usr/bin/env python

import jinja2
import json
import logging
import webapp2
import re
from google.appengine.api import mail
from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.ext import ndb

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader('templates/'),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True
)


class WebComic(ndb.Model):
    source = ndb.StringProperty()
    inst = ndb.StringProperty(default='comic')
    last_json = ndb.StringProperty()

    @property
    def last(self):
        try:
            return json.loads(self.last_json)
        except:
            return None

    @last.setter
    def last(self, value):
        self.last_json = json.dumps(value)

    @classmethod
    def get_all(cls):
        return cls.query(cls.inst == 'comic')


def get_latest_xkcd():
    data = memcache.get('xkcd-latest')
    if data is None:
        result = urlfetch.fetch('http://xkcd.com')
        content = result.content
        match = re.search('<div id="comic">\n<img src="(.*?)" title="(.*?)"', content)
        if not match:
            return False
        url = match.group(1)
        alt = match.group(2)
        memcache.set('xkcd-latest', [url, alt], 60*30)
    return data or [url, alt]


def get_latest_jl8():
    num = memcache.get('jl8-latest')
    if num is None:
        result = urlfetch.fetch('http://limbero.org/jl8/')
        url = result.final_url
        num = url.split('/')[-1]
        try:
            num = int(num)
        except ValueError:
            return False
        memcache.set('jl8-latest', num, 60*30)
    return num


def get_latest_smbc():
    url = memcache.get('smbc-latest')
    if url is None:
        result = urlfetch.fetch('http://smbc-comics.com')
        match = re.search('<div id="comicimage">\s*?<img src=\'(.*?)\'>', result.content)
        if not match:
            return False
        url = match.group(1)
        memcache.set('smbc-latest', url, 60*30)
    return url


comic_types = {
    'xkcd': get_latest_xkcd,
    'smbc': get_latest_smbc,
    'jl8': get_latest_jl8,
}

pretty_names = {
    'smbc': 'SMBC',
    'jl8': 'JL8',
}


def trigger_email(kind, args):
    template = JINJA_ENVIRONMENT.get_template(kind + '.html')
    html = template.render(data=args)
    message = mail.EmailMessage(
        sender='legoktm@gmail.com',
        to='legoktm@gmail.com',
        subject='A new %s is here!' % pretty_names.get(kind, kind),
        body='A new %s is here!' % pretty_names.get(kind, kind),
        html=html
    )
    message.send()
    logging.info('Sent %s email.' % kind)


class CronHandler(webapp2.RequestHandler):
    # TODO: Move this into it's own file???
    def get(self):
        comics = list(comic_types)
        query = WebComic.get_all()
        objs = []
        for model in query.fetch(100):
            if model.source in comics:
                comics.remove(model.source)
            objs.append(model)
        for cmc in comics:
            objs.append(WebComic(source=cmc))
        futures = []
        for obj in objs:
            latest = comic_types[obj.source]()
            self.response.write(latest)
            self.response.write(obj.last)
            if latest != obj.last:
                trigger_email(obj.source, latest)
                obj.last = latest
                futures.append(obj.put_async())
        if futures:
            ndb.Future.wait_all(futures)
        self.response.write('Done.')


class MainHandler(webapp2.RequestHandler):
    def get(self):
        self.response.write('Hello world!')


class JL8(webapp2.RequestHandler):
    def get(self):
        template = JINJA_ENVIRONMENT.get_template('jl8.html')
        self.response.write(template.render(data=get_latest_jl8()))


class XKCD(webapp2.RequestHandler):
    def get(self):
        info = get_latest_xkcd()
        template = JINJA_ENVIRONMENT.get_template('xkcd.html')
        self.response.write(template.render(data=info))


class SMBC(webapp2.RequestHandler):
    def get(self):
        template = JINJA_ENVIRONMENT.get_template('smbc.html')
        self.response.write(template.render(data=get_latest_smbc()))

app = webapp2.WSGIApplication([
    ('/', MainHandler),
    ('/jl8', JL8),
    ('/xkcd', XKCD),
    ('/smbc', SMBC),
    ('/cron', CronHandler)
], debug=True)
