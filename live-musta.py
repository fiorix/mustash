#!/usr/bin/env python
# coding: utf-8

import os
import sys
import time

try:
    import Image
except ImportError:
    print("Could not find PIL. Make sure it is installed and `Image` "
          "module is in PYTHONPATH.")
    sys.exit(1)

try:
    import cv
except ImportError:
    print("Could not find OpenCV. Make sure it is installed and `cv` "
          "module is in PYTHONPATH.")
    sys.exit(1)


class FaceDetection:
    def __init__(self, haar_face, haar_eyes, haar_mouth):
        self.haar_face = cv.Load(haar_face)
        self.haar_eyes = cv.Load(haar_eyes)
        self.haar_mouth = cv.Load(haar_mouth)

        self.cfg = dict(
            scale=4,
            haar_scale=1.6,
            min_neighbors=2,
            haar_flags=0,
            min_size=(10, 10)
        )

    def find(self, img, haar, **kwargs):
        opt = lambda k: kwargs.get(k, self.cfg.get(k))
        return cv.HaarDetectObjects(img, haar,
                                    cv.CreateMemStorage(0),
                                    opt("haar_scale"),
                                    opt("min_neighbors"),
                                    opt("haar_flags"),
                                    opt("min_size"))[:opt("maxobjs")]

    def find_ROI(self, img, haar, ROI, **kwargs):
        cv.SetImageROI(img, tuple(ROI))
        for square, n in self.find(img, haar, **kwargs):
            yield square, n
        cv.ResetImageROI(img)

    def faces(self, img, **kwargs):
        opt = lambda k: kwargs.get(k, self.cfg.get(k))
        size = (cv.Round(img.width / opt("scale")),
                cv.Round(img.height / opt("scale")))
        small_img = cv.CreateImage(size, 8, 1)

        gray = cv.CreateImage((img.width, img.height), 8, 1)
        cv.CvtColor(img, gray, cv.CV_BGR2GRAY)
        cv.Resize(gray, small_img, cv.CV_INTER_LINEAR)
        cv.EqualizeHist(small_img, small_img)

        faces = self.find(small_img, self.haar_face, **kwargs)
        for square, n in faces:
            yield map(lambda v: (cv.Round(v * opt("scale"))), square), n

    def eyes(self, img, ROI, **kwargs):
        return self.find_ROI(img, self.haar_eyes, ROI, **kwargs)

    def mouths(self, img, ROI, **kwargs):
        return self.find_ROI(img, self.haar_mouth, ROI, **kwargs)


def beautify(fd, im, moustache):
    boxes = []

    for facerect, n in fd.faces(im, min_size=(20, 20)):
        x, y, w, h = facerect
        pt1 = (x, y)
        pt2 = (x + w, y + h)
        cv.Rectangle(im, pt1, pt2, cv.RGB(255, 0, 0), 3, 8, 0)

        for eyerect, n in fd.eyes(im, facerect, maxobjs=1, min_size=(40, 30)):
            x, y, w, h = eyerect
            w = x + w
            y = y + h
            cv.Rectangle(im, (x, y), (w, h), cv.RGB(0, 255, 0), 1, 8, 0)

        h = facerect[3]
        facerect[1] += h / 2
        facerect[3] -= h / 2
        for mouthrect, n in fd.mouths(im, facerect,
                                      maxobjs=1, min_size=(40, 30)):
            x, y, w, h = mouthrect
            pt1 = (x, y)
            pt2 = (x + w, y + h)
            cv.Rectangle(im, pt1, pt2, cv.RGB(0, 0, 255), 1, 8, 0)
            boxes.append((facerect[0] + x, facerect[1] + y, w, h))

    pil_im = Image.fromstring("RGB", cv.GetSize(im), im.tostring())
    new_im = cv.CreateImageHeader(pil_im.size, cv.IPL_DEPTH_8U, 3)

    # composite :}
    for (x, y, w, h) in boxes:
        mw, mh = moustache.size
        w = int(w * 1.8)
        x = x - int(w / 5)
        y = int(y / 1.1)
        ratio = mw / float(w)
        h = int(float(mh) / ratio)
        mm = moustache.resize((w, h))
        pil_im.paste(mm, (x, y, x + w, y + h), mm)

    cv.SetData(new_im, pil_im.tostring())
    return new_im


def main():
    fd = FaceDetection("haarcascades/haarcascade_frontalface_alt.xml",
                       "haarcascades/haarcascade_mcs_eyepair_small.xml",
                       "haarcascades/haarcascade_mcs_mouth.xml")

    moustache = Image.open("moustache.png")

    wname = "Moustache Yourself"
    cv.NamedWindow(wname, 1)
    capture = cv.CreateCameraCapture(0)

    fps = 0
    im = None
    t = int(time.time())

    print("Press any key to quit.")
    while 1:
        frame = cv.QueryFrame(capture)
        if not frame:
            print("Nothing else to do.")
            cv.WaitKey(0)
            break

        if not im:
            im = cv.CreateImage((frame.width, frame.height),
                                cv.IPL_DEPTH_8U, frame.nChannels)

        if frame.origin == cv.IPL_ORIGIN_TL:
            cv.Copy(frame, im)
        else:
            cv.Flip(frame, im, 0)

        im = beautify(fd, im, moustache)
        cv.ShowImage(wname, im)

        fps += 1
        nt = int(time.time())
        if t + 1 < nt:
            print("%d fps" % fps)
            fps = 0
            t = nt

        if cv.WaitKey(10) >= 0:
            break

    cv.DestroyWindow(wname)


if __name__ == "__main__":
    main()
