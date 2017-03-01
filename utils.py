# -*- coding: utf-8 -*-

deviceNameMap = {"iPhone3,1": "iPhone4",
                 "iPhone3,2": "iPhone4",
                 "iPhone3,3": "iPhone4",
                 "iPhone4,1": "iPhone4s",
                 "iPhone5,1": "iPhone5",
                 "iPhone5,2": "iPhone5",
                 "iPhone5,3": "iPhone5c",
                 "iPhone5,4": "iPhone5c",
                 "iPhone6,1": "iPhone5s",
                 "iPhone6,2": "iPhone5s",
                 "iPhone7,1": "iPhone6 Plus",
                 "iPhone7,2": "iPhone6",
                 "iPhone8,1": "iPhone6s Plus",
                 "iPhone8,2": "iPhone6s",
                 "iPhone8,4": "iPhoneSE",
                 "iPhone9,1": "iPhone7",
                 "iPhone9,2": "iPhone7 Plus",
                 "iPhone9,3": "iPhone7",
                 "iPhone9,4": "iPhone7 Plus",
                 "iPad2,1": "iPad2",
                 "iPad2,2": "iPad2",
                 "iPad2,3": "iPad2",
                 "iPad2,4": "iPad2",
                 "iPad2,5": "iPad mini",
                 "iPad2,6": "iPad mini",
                 "iPad2,7": "iPad mini",
                 "iPad3,1": "iPad3",
                 "iPad3,2": "iPad3",
                 "iPad3,3": "iPad3",
                 "iPad3,4": "iPad4",
                 "iPad3,5": "iPad4",
                 "iPad3,6": "iPad4",
                 "iPad4,1": "iPad Air",
                 "iPad4,2": "iPad Air",
                 "iPad4,3": "iPad Air",
                 "iPad4,4": "iPad mini 2",
                 "iPad4,5": "iPad mini 2",
                 "iPad4,6": "iPad mini 2",
                 "iPad4,7": "iPad mini 3",
                 "iPad4,8": "iPad mini 3",
                 "iPad4,9": "iPad mini 3",
                 "iPad5,1": "iPad mini 4",
                 "iPad5,2": "iPad mini 4",
                 "iPad5,3": "iPad Air 2",
                 "iPad5,4": "iPad Air 2",
                 "iPad6,3": "iPad Pro mini",
                 "iPad6,4": "iPad Pro mini",
                 "iPad6,7": "iPad Pro",
                 "iPad6,8": "iPad Pro",
                 "iPod5,1": "iPod Touch5",
                 "iPod7,1": "iPod Touch6"}


class ReportFormat:
    JSON = 1
    ZIP_BASE64 = 2
    ZIP_AES_BASE64 = 3

class ReportType:
    PL = 1
    KS = 2


def getValueForKey(d,key):
    if d and isinstance(d,dict):
        if d.has_key(key):
            return d[key]

def getNestedValueForKeys(d,keys):
    nestDict = d
    if d and isinstance(d,dict) and isinstance(keys,list):
        for key in keys:
            nestDict = getValueForKey(nestDict,key)
            if nestDict is None:
                break
    return nestDict

