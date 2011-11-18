#!/usr/bin/env python
# coding: utf-8

import cv
import BeautifulSoup
import Image
import os
import sys
import urlparse
from cStringIO import StringIO
from cyclone import web
from cyclone.bottle import run, route
from cyclone.httpclient import fetch
from twisted.python import log
from twisted.internet import defer, threads

ROOT="http://localhost:8888"


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
    if not url:
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

    if response.headers.get("Content-Type", [""])[0] in req.settings.mumu.supported:
        req.redirect("/mustashify?q="+url)
        defer.returnValue(None)

    try:
        prefix=ROOT+"/mustashify?q="
        soup = BeautifulSoup.BeautifulSoup(response.body)
        make_absolute_path(soup, url, "a", "href")
        make_absolute_path(soup, url, "link", "href")
        make_absolute_path(soup, url, "script", "src")
        make_absolute_path(soup, url, "img", "src", prefix)
        body = str(soup)
    except Exception, e:
        #log.err()
        req.render("index.html", err={"html":True})
        defer.returnValue(None)

    req.finish(body)


@route("/mustashify")
@defer.inlineCallbacks
def mustashify(req):
    url = req.get_argument("q")
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
        req.set_header("Content-Type", content_type)
        req.write(response.body)
        defer.returnValue(None)

    try:
        im = Image.open(StringIO(response.body))
    except Exception, e:
        #log.err()
        raise web.HTTPError(400)

    try:
        im = yield threads.deferToThread(req.settings.mumu.mustash_it, im)
        fd = StringIO()
        im.save(fd, fmt)
    except Exception, e:
        #log.err()
        raise web.HTTPError(503)

    req.set_header("Content-Type", content_type)
    req.finish(fd.getvalue())


def path_of(s):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), s)

class Mustashify:
    supported = {
        "image/png": "PNG",
        "image/jpg": "JPEG",
        "image/jpeg": "JPEG",
    }

    def __init__(self, mustache_image):
        try:
            self.im = Image.open(mustache_image)
        except Exception, e:
            #log.err()
            print("Mustache image could not be opened")
            sys.exit(1)

        self.min_size = (20,20)
        self.image_scale = 2
        self.haar_scale = 1.2
        self.min_neighbors = 2
        self.haar_flags = 0
        try:
            self.cascade = cv.Load(path_of("./haar.xml"))
        except Exception, e:
            #log.err()
            print("Please symlink haar cascade to haar.xml")
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

    def mustash_it(self, image):
        for (x, y, w, h) in self.find_face(image):
            # resize our mustache keeping the aspect ratio
            mw, mh = self.im.size
            w = w-(w*10/100)
            ratio = mw/float(w)
            new_size = (w, int(float(mh)/ratio))
            new_mu = self.im.resize(new_size)

            # composite :}
            x = x-(x*5/100)
            y = (y+h)-new_size[1]-(h*10/100)
            image.paste(new_mu, (x, y, x+new_size[0], y+new_size[1]), new_mu)

        return image


run(host="127.0.0.1", port=8888,
    debug=True,
    template_path=path_of("./"),
    static_path=path_of("./static"),
    mumu=Mustashify(path_of("./static/mustache.png")))
