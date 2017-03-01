# -*- coding: utf-8 -*-
from __future__ import division
from json import *
import sys, getopt, string, os, glob, hashlib, gc, zlib, base64
from  datetime import  datetime
import xlrd, xlsxwriter
import xlwt
from Crypto.Cipher import AES
from binascii import b2a_hex, a2b_hex
from  utils import ReportFormat,ReportType,getValueForKey,deviceNameMap,getNestedValueForKeys
import ConfigParser


class Report(object):
    def __init__(self, reportType, reportFormat):
        super(Report, self).__init__()
        self.reportType = reportType
        self.reportFormat = reportFormat
        self.pin = None
        self.uuid = None
        self.time = None
        self.pagePath = None
        self.osVersion = None
        self.devcieType = None
        self.encryptedCrashString = None
        self.decryptedCrashDict = None
        self.originalData = None
        self.foreground = False
        self.error = None

class AesCrypter(object):
    '''decrypt method'''
    def __init__(self, key, iv, mode):
        self.key = key
        self.iv = iv
        self.mode = mode

    def encrypt(self, data):
        data = self.pkcs7padding(data)
        cipher = AES.new(self.key, self.mode, self.iv)
        encrypted = cipher.encrypt(data)
        return base64.b64encode(encrypted)

    def decrypt(self, data):
        data = base64.b64decode(data)
        cipher = AES.new(self.key, self.mode, self.iv)
        decrypted = cipher.decrypt(data)
        decrypted = self.pkcs7unpadding(decrypted)
        return decrypted

    def pkcs7padding(self, data):
        bs = AES.block_size
        padding = bs - len(data) % bs
        padding_text = chr(padding) * padding
        return data + padding_text

    def pkcs7unpadding(self, data):
        lengt = len(data)
        unpadding = ord(data[lengt - 1])
        return data[0:lengt - unpadding]

def getDeviceModeName(mode):
    modeName = "other"
    if deviceNameMap.has_key(mode):
        modeName = deviceNameMap[mode]
    return modeName

def fileList():
    fl = glob.glob("*.txt")
    return fl


class CrashParser():
    def getCrashReports(self,filePath):
        reportList = []
        try:
            file = open(filePath)
            for line in file:
                infoList = line.split('<|>')
                if len(infoList) < 18:
                    continue
                reportType = int(infoList[0])
                reportFormat = ReportFormat.ZIP_BASE64
                if reportType == ReportType.KS:
                    reportFormat = ReportFormat.ZIP_AES_BASE64

                report = Report(reportType, ReportFormat.ZIP_BASE64)
                #orginal data
                report.originalData = infoList

                # pin、uuid、崩溃时间
                report.pin = infoList[6]
                report.uuid = infoList[7]
                report.time = infoList[2]
                # 系统版本
                report.osVersion = infoList[12]
                # 页面路径
                report.pagePath = infoList[17]
                # 设备型号
                report.devcieType = getDeviceModeName(infoList[9])
                # crash信息
                report.encryptedCrashString = infoList[15]
                #report list
                reportList.append(report)

        except Exception, e:
            print e,filePath
        finally:
            file.close()
        return reportList

    def parseCrashString(self,report):
            crashDict = None
            errorInfo = None
            crashString = report.encryptedCrashString
            if len(crashString) > 0:
                if report.reportType == ReportType.PL:
                    if report.reportFormat == ReportFormat.JSON:
                        try:
                            crashDict = eval(crashString)
                        except Exception, e:
                            errorInfo = unicode("解析 json 失败", 'utf-8')
                    elif report.reportFormat == ReportFormat.ZIP_BASE64:
                        if crashString.find("Crash") != -1:
                            errorInfo = unicode(crashString, 'utf-8')
                        else:
                            try:
                                base64String = base64.b64decode(crashString)
                                crashDict = eval(zlib.decompress(base64String, 16 + zlib.MAX_WBITS))
                            except Exception, e:
                                errorInfo = unicode("解析 base + zip 失败", 'utf-8')

                        report.decryptedCrashDict = crashDict
                        report.error = errorInfo

                elif report.reportType == ReportType.KS:
                    dict = None
                    try:
                        key = 'NSObjectNSString'
                        iv = 16 * '\x00'
                        aes = AesCrypter(key, iv, AES.MODE_CBC)
                        decryptString = aes.decrypt(crashString)
                        jsonString = zlib.decompress(decryptString, 16 + zlib.MAX_WBITS)
                        #print jsonString
                        dict = JSONDecoder().decode(jsonString)

                    except Exception, e:
                        errorInfo = unicode("解析 ZIP + AES + BASE64 失败", 'utf-8')

                    report.decryptedCrashDict = dict
                    report.error = errorInfo
            return report

    def isForeground(self,report):
        report.foreground = getNestedValueForKeys(report.decryptedCrashDict,['system','application_stats','application_in_foreground'])
        return report.foreground

    def getOOMCrashControllerPage(self,report):
        decryptedCrash = report.decryptedCrashDict
        if decryptedCrash:
            user = getValueForKey(decryptedCrash,'user')
            if user:
                pageList = getValueForKey(user,'nav_history')
                if pageList and len(pageList) > 0:
                    return getValueForKey(pageList[-1],'c')


# class OOMpercentModel(object):
#     def __init__(self,controller):
#         super(OOMpercentModel,self).__init__()
#         self.controller = controller
#         self.foregroundCount = 0 #maybe repeat by uuid
#         self.backgroundCount = 0 #maybe repeat by uuid
#         self.percent = 0

class OOMFilterRepeatedUUIDModel(object):
    def __init__(self,controller):
        super(OOMFilterRepeatedUUIDModel,self).__init__()
        self.controller = controller
        self.foregroundCount = 0  # maybe repeat by uuid
        self.backgroundCount = 0  # maybe repeat by uuid
        self.percent = 0
        self.uniqUUIDList = []
        self.foregroundRepeatCount = 0
        self.backgroundRepeatCount = 0


class OOMCrashPage(object):
    '''generate reports list based on crash files'''
    def __init__(self):
        super(OOMCrashPage,self).__init__()
        self.pageKVCount = {}
        self.list = fileList()
        self.allCrashCount = 0  # 所有的crash
        self.parsedCrashCount = 0  # 正常解析的数量
        self.unparsedCrashCount = 0  # 字段缺失导致无法正常解析


    #去重原则  UUID，controller 相同，才会认为是重复数据
    def getOOMCrashPageCount(self):
        '''{controlerName:pageCountModel}'''
        index = 0
        crashParser = CrashParser()
        if len(self.list) > 0:
            while(index < len(self.list)):
                reportList =  crashParser.getCrashReports(self.list[index])
                self.allCrashCount = len(reportList)
                if reportList and len(reportList) > 0:
                    for report in reportList:
                        crashParser.parseCrashString(report)
                        # print  report.uuid,report.pin,report.osVersion,report.pagePath
                        if not report.error:
                            vc = crashParser.getOOMCrashControllerPage(report)
                            if vc:
                                self.parsedCrashCount += 1
                                if self.pageKVCount.has_key(vc):
                                    OOMModel = self.pageKVCount[vc]
                                    isForeground = crashParser.isForeground(report)
                                    if isForeground:
                                        OOMModel.foregroundCount += 1
                                    else:
                                        OOMModel.backgroundCount += 1
                                    if  report.uuid in OOMModel.uniqUUIDList:
                                        if isForeground:
                                            OOMModel.foregroundRepeatCount += 1
                                        else:
                                            OOMModel.backgroundRepeatCount += 1
                                    else:
                                        OOMModel.uniqUUIDList.append(report.uuid)
                                else:
                                    OOMModel = OOMFilterRepeatedUUIDModel(vc)
                                    if crashParser.isForeground(report):
                                        OOMModel.foregroundCount += 1
                                    else:
                                        OOMModel.backgroundCount += 1

                                    OOMModel.uniqUUIDList.append(report.uuid)
                                    self.pageKVCount[vc] = OOMModel
                            else:
                                self.unparsedCrashCount += 1
                        else:
                            self.unparsedCrashCount += 1

                index += 1

        return (self.allCrashCount,self.parsedCrashCount,self.unparsedCrashCount, self.pageKVCount)


    def updatePercentAndSort(self,tu):
        '''uuid maybe repeat'''
        pageKVCount = tu[3]
        allCrashCount = tu[0]
        parsedCrashCount = tu[1]
        unparsedCrashCount = tu[2]
        # compute percent
        for key in pageKVCount:
            v = pageKVCount[key]
            v.percent = (v.foregroundCount + v.backgroundCount) / allCrashCount * 100  # 除以已经解析成功的还是所有的
        # sort it
        sortedList = sorted(pageKVCount.items(), key=lambda e: (e[1].percent), reverse=True)
        return (allCrashCount, parsedCrashCount, unparsedCrashCount, sortedList)


    def updatePercentAndSortWithFilterRepeatUUID(self,tu):
        '''uuid maybe repeat'''
        pageKVCount = tu[3]
        allCrashCount = tu[0]
        parsedCrashCount = tu[1]
        unparsedCrashCount = tu[2]

        # compute percent
        for key in pageKVCount:
            v = pageKVCount[key]
            v.percent = (v.foregroundCount - v.foregroundRepeatCount + v.backgroundCount - v.backgroundRepeatCount) / allCrashCount * 100  # 除以已经解析成功的还是所有的

        # sort it
        sortedList = sorted(pageKVCount.items(), key=lambda e: (e[1].percent), reverse=True)
        return (allCrashCount, parsedCrashCount, unparsedCrashCount, sortedList)


class OOMxlsWritter(object):
    def __init__(self):
        super(OOMxlsWritter,self).__init__()
        self.wbk = xlwt.Workbook()

    def writeAllCrashListToXls(self,tuplelist):
        if len(tuplelist)  == 0:
            return
        all = tuplelist[0]
        parsed = tuplelist[1]
        un = tuplelist[2]
        slist = tuplelist[3]

        sheet = self.wbk.add_sheet( unicode('所有未去重','utf-8'), cell_overwrite_ok=True)
        today = datetime.today()
        today_date = datetime.date(today)
        titleStyle = xlwt.easyxf("font:bold 1, color black; align: horiz right")
        style = xlwt.easyxf("font:color black; align: horiz right")
        #we can custom the style
        # style = xlwt.easyxf("pattern: pattern solid, fore_color clear; font: color black; align: horiz right")
        name_col = sheet.col(0)
        all_col = sheet.col(1)
        foreground_col = sheet.col(2)
        background_col = sheet.col(3)
        percent_col = sheet.col(4)

        name_col.width = 256 *50
        percent_col.width = foreground_col.width = background_col.width = all_col.width = 256 * 15

        sheet.write(0, 0, unicode('页面','utf-8'))
        sheet.write(0, 1, unicode('OOM总数','utf-8'),style)
        sheet.write(0, 2, unicode('前台','utf-8'),style)
        sheet.write(0, 3, unicode('后台','utf-8'),style)
        sheet.write(0, 4, unicode('占比','utf-8'), style)
        row = 1
        for tp in slist:
            if tp is not None:
                if len(tp) > 0:
                        name = tp[0]
                        foregroundCount = tp[1].foregroundCount
                        backgroundCount = tp[1].backgroundCount
                        percent = tp[1].percent
                        sheet.write(row, 0, name)
                        sheet.write(row, 1,foregroundCount + backgroundCount,style)
                        sheet.write(row, 2, foregroundCount,style)
                        sheet.write(row, 3, backgroundCount,style)
                        sheet.write(row, 4, percent,style)
                        row = row + 1

    def writeUniqUUIDCrashListToXls(self,tuplelist):
        '''filter the same uuid crash'''
        if len(tuplelist) == 0:
            return
        all = tuplelist[0]
        parsed = tuplelist[1]
        un = tuplelist[2]
        slist = tuplelist[3]

        sheet = self.wbk.add_sheet(unicode('所有去重', 'utf-8'), cell_overwrite_ok=True)
        today = datetime.today()
        today_date = datetime.date(today)

        titleStyle = xlwt.easyxf("font:bold 1, color black; align: horiz right")
        style = xlwt.easyxf("font:color black; align: horiz right")
        # we can custom the style
        # style = xlwt.easyxf("pattern: pattern solid, fore_color clear; font: color black; align: horiz right")
        name_col = sheet.col(0)
        all_col = sheet.col(1)
        foreground_col = sheet.col(2)
        background_col = sheet.col(3)
        percent_col = sheet.col(4)

        name_col.width = 256 * 50
        percent_col.width = foreground_col.width = background_col.width = all_col.width = 256 * 15

        sheet.write(0, 0, unicode('页面', 'utf-8'))
        sheet.write(0, 1, unicode('OOM总数', 'utf-8'), style)
        sheet.write(0, 2, unicode('前台', 'utf-8'), style)
        sheet.write(0, 3, unicode('后台', 'utf-8'), style)
        sheet.write(0, 4, unicode('占比', 'utf-8'), style)
        row = 1
        for tp in slist:
            if tp is not None:
                if len(tp) > 0:
                    name = tp[0]
                    foregroundCount = tp[1].foregroundCount
                    backgroundCount = tp[1].backgroundCount
                    foregroundRepeatCount = tp[1].foregroundRepeatCount
                    backgroundRepeatCount = tp[1].backgroundRepeatCount

                    percent = tp[1].percent
                    sheet.write(row, 0, name)
                    sheet.write(row, 1, foregroundCount + backgroundCount - foregroundRepeatCount - backgroundRepeatCount , style)
                    sheet.write(row, 2, foregroundCount - foregroundRepeatCount, style)
                    sheet.write(row, 3, backgroundCount - backgroundRepeatCount, style)
                    sheet.write(row, 4, percent, style)
                    row = row + 1


    def save(self):
        today = datetime.today()
        today_date = datetime.date(today)
        self.wbk.save('OOM' + str(today_date) + '.xls')

# ==================================================================================================
#                                    配置化模块
# ==================================================================================================
relativePathOfConfigFile = 'config/*.config'
class  ConfigModules(object):
    def __init__(self):
        super(ConfigModules,self).__init__()
        self.cf = ConfigParser.RawConfigParser()
        self.config = {}

    def loadConfigFile(self,path):
        cwd = os.getcwd()
        configPath = os.path.join(cwd,relativePathOfConfigFile)
        if os.path.exists(configPath):
            self.parserConfigFile(configPath)

    def parserConfigFile(self):
        cf.read()

        return

    def setDefaultConfig(self):
        pass




if __name__ == '__main__':
    cp = OOMCrashPage()
    tu =  cp.getOOMCrashPageCount()
    OOMWriter = OOMxlsWritter()
    OOMWriter.writeAllCrashListToXls(cp.updatePercentAndSort(tu))
    OOMWriter.writeUniqUUIDCrashListToXls(cp.updatePercentAndSortWithFilterRepeatUUID(tu))
    OOMWriter.save()


