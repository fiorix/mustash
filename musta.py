#!/usr/bin/env python
# coding: utf-8

import BeautifulSoup
import cv
import hashlib
import Image
import os
import random
import sys
import urlparse
from cStringIO import StringIO
from cyclone import web
from cyclone.bottle import run, route
from cyclone.escape import json_encode
from cyclone.httpclient import fetch
from twisted.python import log
from twisted.internet import defer, threads

ROOT="http://musta.sh"


def make_absolute_path(soup, url, tag, opt, prefix=None):
    for k in soup.findAll(tag):
        v = k.get(opt, None)
        if not v or v.startswith("javascript"):
            return

        if not k[opt].startswith("http"):
            k[opt] = urlparse.urljoin(url, k[opt])

        if prefix:
            k[opt] = prefix+k[opt]


@route("/")
@defer.inlineCallbacks
def index(req):
    url = req.get_argument("q", None)
    if url:
        if os.path.exists(req.settings.cache.getpath(url)):
            print 'true???'
            req.redirect("/mustashify?q="+url)
            defer.returnValue(None)
    else:
        req.render("index.html", err={})
        defer.returnValue(None)

    if not url.startswith("http"):
        url = "http://"+url

    try:
        tmp = urlparse.urlparse(url)
        assert tmp.scheme
        assert tmp.netloc
    except:
        req.render("index.html", err={"url":True})
        defer.returnValue(None)

    try:
        response = yield fetch(url, followRedirect=1, maxRedirects=3)
        assert response.code == 200, "Bad response code %s" % response.code
    except Exception, e:
        #log.err()
        req.render("index.html", err={"fetch":True})
        defer.returnValue(None)

    try:
        if response.headers["Content-Type"][0] in req.settings.mumu.supported:
            req.redirect("/mustashify?q="+url)
            defer.returnValue(None)
    except:
        pass

    try:
        soup = BeautifulSoup.BeautifulSoup(response.body)
        make_absolute_path(soup, url, "a", "href")
        make_absolute_path(soup, url, "link", "href")
        make_absolute_path(soup, url, "script", "src")
        make_absolute_path(soup, url, "img", "src", ROOT+"/mustashify?q=")
        body = str(soup)
    except Exception, e:
        #log.err()
        req.render("index.html", err={"html":True})
    else:
        req.finish(body)


@route("/mustashify")
@defer.inlineCallbacks
def mustashify(req):
    url = req.get_argument("q")
    obj = req.settings.cache.get(url)
    if obj:
        content_type, buff = obj.split("\r\n", 1)
        req.set_header("Content-Type", content_type)
        req.write(buff)
        defer.returnValue(None)

    try:
        response = yield fetch(url, followRedirect=1, maxRedirects=3)
    except Exception, e:
        #log.err()
        raise web.HTTPError(404)

    if response.code != 200:
        raise web.HTTPError(response.code)

    try:
        content_type = response.headers.get("Content-Type")[0]
        fmt = req.settings.mumu.supported[content_type]
    except Exception, e:
        #log.err("Invalid content-type: %s" % str(e))
        #req.set_header("Content-Type", content_type)
        #req.write(response.body)
        #defer.returnValue(None)
        raise web.HTTPError(400)

    try:
        im = Image.open(StringIO(response.body))
    except Exception, e:
        #log.err()
        raise web.HTTPError(400)

    try:
        nf, im = yield threads.deferToThread(req.settings.mumu.mustashify, im)
        fd = StringIO()
        im.save(fd, fmt)
        buff = fd.getvalue()
        if nf:
            req.settings.cache.add(url, content_type+"\r\n"+buff)
    except Exception, e:
        #log.err()
        raise web.HTTPError(503)

    req.set_header("Content-Type", content_type)
    req.finish(buff)


@route("/recents")
def recents(req):
    req.set_header("Content-Type", "application/json")
    req.write(json_encode({"recents":req.settings.cache.recents()}))


class Cache:
    def __init__(self, cache_dir, L1=16, L2=256, mask=0755):
        self.max_items = 20
        self.items = []
        self.cache_dir = cache_dir
        self.L1 = L1
        self.L2 = L2

        if not os.path.exists(cache_dir):
            os.mkdir(cache_dir, mask)

        for x in xrange(L1):
            x = str(x)
            tmp = os.path.join(cache_dir, x)
            if not os.path.exists(tmp):
                os.mkdir(tmp, mask)

            for y in xrange(L2):
                y = str(y)
                tmp = os.path.join(cache_dir, x, y)
                if not os.path.exists(tmp):
                    os.mkdir(tmp, mask)

    def getpath(self, name):
        m = sum([ord(n) for n in name])
        L1 = str(m%self.L1)
        L2 = str(m%self.L2)
        FN = hashlib.new("md5", name).hexdigest()
        return os.path.join(self.cache_dir, L1, L2, FN)

    def get(self, name):
        path = self.getpath(name)
        if os.path.exists(path):
            with open(path) as fd:
                buff = fd.read()
                fd.close()
            return buff

    def add(self, name, content, mask=0755):
        path = self.getpath(name)
        if not os.path.exists(path):
            if name not in self.items:
                self.items.insert(0, name)
                self.items = self.items[:self.max_items]
            with open(path+".tmp", "w", mask) as fd:
                fd.write(content)
                fd.close()
            os.rename(path+".tmp", path)

    def recents(self, max=20):
        n = self.items[:max]
        random.shuffle(n)
        return n


class Mustashify:
    supported = {
        "image/gif": "GIF",
        "image/png": "PNG",
        "image/jpg": "JPEG",
        "image/jpeg": "JPEG",
    }

    def __init__(self, mustache_image, haar_xml):
        try:
            self.im = Image.open(mustache_image)
        except Exception, e:
            #log.err()
            print("Mustache image %s could not be opened" % mustache_image)
            sys.exit(1)

        self.min_size = (20,20)
        self.image_scale = 2
        self.haar_scale = 1.2
        self.min_neighbors = 2
        self.haar_flags = 0
        try:
            self.cascade = cv.Load(haar_xml)
        except Exception, e:
            #log.err()
            print("Haar file %s could not be opened" % haar_xml)
            sys.exit(1)

    def find_face(self, im):
        im = im.convert("RGB")
        cvim = cv.CreateImage(im.size, cv.IPL_DEPTH_8U, 3)
        cv.SetData(cvim, im.tostring())

        # allocate temporary images
        gray = cv.CreateImage((cvim.width, cvim.height), 8, 1)
        small_w = cv.Round(cvim.width/self.image_scale)
        small_h = cv.Round(cvim.height/self.image_scale)
        small_img = cv.CreateImage((small_w, small_h), 8, 1)
        cv.CvtColor(cvim, gray, cv.CV_BGR2GRAY)
        cv.Resize(gray, small_img, cv.CV_INTER_LINEAR)
        cv.EqualizeHist(small_img, small_img)

        #t = cv.GetTickCount()
        faces = cv.HaarDetectObjects(small_img, self.cascade,
                                     cv.CreateMemStorage(0),
                                     self.haar_scale, self.min_neighbors,
                                     self.haar_flags, self.min_size)
        #t = cv.GetTickCount() - t
        adjust = lambda v: v*self.image_scale
        if faces:
            for ((x, y, w, h), n) in faces:
                yield adjust(x), adjust(y), adjust(w), adjust(h)

    def mustashify(self, image):
        faces = 0
        for (x, y, w, h) in self.find_face(image):
            # resize our mustache keeping the aspect ratio
            mw, mh = self.im.size
            w = w-(w*10/100)
            ratio = mw/float(w)
            new_size = (w, int(float(mh)/ratio))
            new_mu = self.im.resize(new_size)

            # composite :}
            x = x+(x*5/100)
            y = (y+h)-new_size[1]-(h*15/100)
            image.paste(new_mu, (x, y, x+new_size[0], y+new_size[1]), new_mu)
            faces += 1

        return faces, image


def path_of(s):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), s)

run(host="127.0.0.1", port=int(os.getenv("PORT", 8888)),
    debug=False,
    template_path=path_of("./"),
    static_path=path_of("./static"),
    cache=Cache(path_of("./cache")),
    mumu=Mustashify(path_of("./static/mustache.png"), path_of("./haar.xml")))
