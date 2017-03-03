# -*- coding: utf-8 -*-
from __future__ import division
from json import *
import  getopt, string, os, glob, hashlib, gc, zlib, base64
from  datetime import  datetime
import xlrd, xlsxwriter
import xlwt
from Crypto.Cipher import AES
from binascii import b2a_hex, a2b_hex
from  utils import ReportFormat,ReportType,getValueForKey,deviceNameMap,getNestedValueForKeys
import ConfigParser

import sys
reload(sys)
sys.setdefaultencoding('utf8')


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

class CrashParser(object):
    def __init__(self):
        super(CrashParser,self).__init__()
        self.list = fileList()
        self.reportList = []

    def getCrashReports(self):
        if len(self.list) > 0:
            index = 0
            while (index < len(self.list)):
                filePath = self.list[index]
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
                        report.devcieType = infoList[9]
                        # crash信息
                        report.encryptedCrashString = infoList[15]
                        #report list
                        self.reportList.append(report)

                except Exception, e:
                    print e,filePath
                finally:
                    file.close()
                index += 1
        return self.reportList


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

    def getDecryptedReportList(self):
        reportList = self.getCrashReports()
        if reportList and len(reportList) > 0:
            for report in reportList:
                self.parseCrashString(report)
        return reportList


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

# ==================================================================================================
#                                    根据页面数排序
# ==================================================================================================

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


class OOMCrashBasedOnPage(object):
    '''generate reports list based on crash files'''
    def __init__(self,crashParser):
        super(OOMCrashBasedOnPage,self).__init__()
        self.pageKVCount = {}
        self.allCrashCount = 0  # 所有的crash
        self.parsedCrashCount = 0  # 正常解析的数量
        self.unparsedCrashCount = 0  # 字段缺失导致无法正常解析
        self.parser = crashParser


    #去重原则  UUID，controller 相同，才会认为是重复数据
    def getOOMCrashPageCount(self,reportList):
        '''{controlerName:pageCountModel}'''

        if reportList and len(reportList) > 0:
            self.allCrashCount = len(reportList)
            for report in reportList:
                # print  report.uuid,report.pin,report.osVersion,report.pagePath
                if not report.error:
                    vc = self.parser.getOOMCrashControllerPage(report)
                    if vc:
                        self.parsedCrashCount += 1
                        print report.uuid,report.osVersion,vc
                        if self.pageKVCount.has_key(vc):
                            OOMModel = self.pageKVCount[vc]
                            isForeground = self.parser.isForeground(report)
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
                            if self.parser.isForeground(report):
                                OOMModel.foregroundCount += 1
                            else:
                                OOMModel.backgroundCount += 1

                            OOMModel.uniqUUIDList.append(report.uuid)
                            self.pageKVCount[vc] = OOMModel
                    else:
                        self.unparsedCrashCount += 1
                else:
                    self.unparsedCrashCount += 1

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




# ==================================================================================================
#                                    根据页面 设备 排序 PAGE+UUID 去重
# ==================================================================================================

#pageName:PageAndDeviceListModel{modelList,UUIDlist}
class PageAndDeviceListModel(object):
    def __init__(self):
        super(PageAndDeviceListModel,self).__init__()
        self.detailModelList = []
        self.uuidList = []



class OOMFilterWithPageAndDeviceDetailModel(object):
    def __init__(self,controller,deviceType):
        super(OOMFilterWithPageAndDeviceDetailModel,self).__init__()
        self.controller = controller
        self.deviceType = deviceType

        self.isForeground = 0
        self.uuid = None

class PageAndDeviceWritterModel(object):
    '''用于写入到文件的model'''
    def __init__(self,name):
        super(PageAndDeviceWritterModel,self).__init__()
        self.deviceName = name
        self.foregoundCount = 0
        self.backgroundCount = 0



class OOMCrashBasedOnPageAndDevice(object):
    def __init__(self,crashParser):
        super(OOMCrashBasedOnPageAndDevice,self).__init__()
        self.pageKVCount = {}
        self.allCrashCount = 0  # 所有的crash
        self.parsedCrashCount = 0  # 正常解析的数量
        self.unparsedCrashCount = 0  # 字段缺失导致无法正常解析
        self.parser = crashParser


    def getOOMCrashPageAndDeviceCountMaybeRepeat(self,reportList):
        '''{controlerName:pageCountModel},未根据page + uuid 过滤'''

        if reportList and len(reportList) > 0:
            self.allCrashCount = len(reportList)
            for report in reportList:
                # print  report.uuid,report.pin,report.osVersion,report.pagePath
                if not report.error:
                    vc = self.parser.getOOMCrashControllerPage(report)
                    if vc:
                        self.parsedCrashCount += 1
                        if self.pageKVCount.has_key(vc):
                            listModel = self.pageKVCount[vc]
                            detailModel = OOMFilterWithPageAndDeviceDetailModel(vc,report.devcieType)
                            detailModel.uuid = report.uuid
                            detailModel.isForeground = isForeground = self.parser.isForeground(report)
                            listModel.detailModelList.append(detailModel)
                        else:
                            isForeground = self.parser.isForeground(report)
                            listModel = PageAndDeviceListModel()
                            detailModel = OOMFilterWithPageAndDeviceDetailModel(vc,report.devcieType)
                            detailModel.uuid = report.uuid
                            detailModel.isForeground = isForeground
                            listModel.detailModelList.append(detailModel)
                            self.pageKVCount[vc] = listModel
                    else:
                        self.unparsedCrashCount += 1
                else:
                    self.unparsedCrashCount += 1

        return (self.allCrashCount,self.parsedCrashCount,self.unparsedCrashCount, self.pageKVCount)


    def getOOMCrashPageAndDeviceCountWithNoRepeat(self,reportList):
        if reportList and len(reportList) > 0:
            self.allCrashCount = len(reportList)
            for report in reportList:
                # print  report.uuid,report.pin,report.osVersion,report.pagePath
                if not report.error:
                    vc = self.parser.getOOMCrashControllerPage(report)
                    if vc:
                        self.parsedCrashCount += 1
                        if self.pageKVCount.has_key(vc):
                            listModel = self.pageKVCount[vc]

                            if report.uuid and report.uuid in listModel.uuidList:
                                continue
                            detailModel = OOMFilterWithPageAndDeviceDetailModel(vc, report.devcieType)
                            detailModel.uuid = report.uuid
                            detailModel.isForeground = isForeground = self.parser.isForeground(report)
                            listModel.detailModelList.append(detailModel)
                            listModel.uuidList.append(report.uuid)
                        else:
                            isForeground = self.parser.isForeground(report)
                            listModel = PageAndDeviceListModel()
                            detailModel = OOMFilterWithPageAndDeviceDetailModel(vc, report.devcieType)
                            detailModel.uuid = report.uuid
                            detailModel.isForeground = isForeground
                            listModel.detailModelList.append(detailModel)
                            listModel.uuidList.append(report.uuid)
                            self.pageKVCount[vc] = listModel
                    else:
                        self.unparsedCrashCount += 1
                else:
                    self.unparsedCrashCount += 1

        return (self.allCrashCount, self.parsedCrashCount, self.unparsedCrashCount, self.pageKVCount)


    def getWrittenData(self,pageList):
        '''根据给定的pageList，按照device 分类'''

        i4Model = PageAndDeviceWritterModel('iPhone4')
        i4sModel = PageAndDeviceWritterModel('iPhone4s')
        i5Model = PageAndDeviceWritterModel('iPhone5')
        i5cModel = PageAndDeviceWritterModel('iPhone5c')
        i5sModel = PageAndDeviceWritterModel('iPhone5s')
        i6Model = PageAndDeviceWritterModel('iPhone6')
        i6pModel = PageAndDeviceWritterModel('iPhone6p')
        i6sModel = PageAndDeviceWritterModel('iPhone6s')
        i6spModel = PageAndDeviceWritterModel('iPhone6sp')
        i7Model = PageAndDeviceWritterModel('iPhone7')
        i7pModel = PageAndDeviceWritterModel('iPhone7p')


        allCount = 0
        if pageList and len(pageList) > 0:
            for  pageName in pageList:
                listModel = self.pageKVCount[pageName]
                allCount += len(listModel.detailModelList)
                for model  in listModel.detailModelList:
                    dataMode = None
                    if model.deviceType == 'iPhone3,1' or model.deviceType == 'iPhone3,2' or model.deviceType == 'iPhone3,3':
                        dataMode = i4Model
                    elif model.deviceType == 'iPhone4,1':
                        dataMode = i4sModel
                    elif model.deviceType == 'iPhone5,1' or model.deviceType == 'iPhone5,2':
                        dataMode = i5Model
                    elif model.deviceType == 'iPhone5,3' or model.deviceType == 'iPhone5,4':
                        dataMode = i5cModel
                    elif model.deviceType == 'iPhone6,1' or model.deviceType == 'iPhone6,2':
                        dataMode = i5sModel
                    elif model.deviceType == 'iPhone7,1':
                        dataMode = i6pModel
                    elif model.deviceType == 'iPhone7,2':
                        dataMode = i6Model
                    elif model.deviceType == 'iPhone8,1':
                        dataMode = i6spModel
                    elif model.deviceType == 'iPhone8,2':
                        dataMode = i6sModel
                    elif model.deviceType == 'iPhone9,1' or model.deviceType == 'iPhone9,3':
                        dataMode = i7Model
                    elif model.deviceType == 'iPhone9,2' or model.deviceType == 'iPhone9,4':
                        dataMode = i7pModel

                    if model.isForeground:
                        dataMode.foregoundCount += 1
                    else:
                        dataMode.backgroundCount += 1

        return (allCount,i4Model,i4sModel,i5Model,i5cModel,i5sModel,i6Model,i6pModel,i6sModel,i6spModel,i7Model,i7pModel)



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
                        percent = str('%.2f' % tp[1].percent) + '%'
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

                    percent = str('%.2f' % tp[1].percent) + '%'
                    sheet.write(row, 0, name)
                    sheet.write(row, 1, foregroundCount + backgroundCount - foregroundRepeatCount - backgroundRepeatCount , style)
                    sheet.write(row, 2, foregroundCount - foregroundRepeatCount, style)
                    sheet.write(row, 3, backgroundCount - backgroundRepeatCount, style)
                    sheet.write(row, 4, percent, style)
                    row = row + 1


    def writeAllBasedOnPageAndDeviceWithSecionts(self,sections,cf,pageAndDevie,sheetName):
        '''12 列元素，第一个列是总的数量，后面11项是每种设备的crash 数量，indexOfSection start from 0'''

        sheet = self.wbk.add_sheet(unicode(sheetName, 'utf-8'), cell_overwrite_ok=True)
        today = datetime.today()
        today_date = datetime.date(today)

        titleStyle = xlwt.easyxf("font:bold 1, color black; align: horiz right")
        style = xlwt.easyxf("font:color black; align: horiz right")
        boldStyle = xlwt.easyxf("font:bold 1, color black; align: horiz left")

        for sec in sections:
            indexOfSection = sections.index(sec)
            title = cf.getValueWithKeyInSection(sec,'title')
            controllers = cf.getValueWithKeyInSection(sec,'controllers')

            #拆分controllr
            cArray = controllers.split(',')
            if not cArray or len(cArray) == 0:
                continue

            tu = pageAndDevie.getWrittenData(cArray)
            if len(tu) != 12 or not sections or len(sections) == 0:
                continue

            allCount = tu[0]
            dataIndex = 1
            row = 1
            coulum  =  indexOfSection * 4#each secton has 4 columns

            #all count
            foregroundCount = 0
            backgroundCount = 0
            while dataIndex < len(tu):
                writeModel = tu[dataIndex]
                foregroundCount += writeModel.foregoundCount
                backgroundCount += writeModel.backgroundCount
                dataIndex += 1

            #title
            sheet.write(0, coulum, unicode(title, 'utf-8'), boldStyle)
            sheet.write(0, coulum + 1, unicode('前后台总量','utf-8'), style)
            sheet.write(0, coulum + 2, unicode('前台', 'utf-8'), style)
            sheet.write(0, coulum + 3, unicode('后台', 'utf-8'), style)


            #先写统计
            sheet.write(row + len(tu) - 1, coulum, unicode('总计', 'utf-8'),boldStyle)
            sheet.write(row + len(tu) - 1, coulum + 1,backgroundCount + foregroundCount,style)
            sheet.write(row + len(tu) - 1, coulum + 2, foregroundCount, style)
            sheet.write(row + len(tu) - 1, coulum + 3, backgroundCount, style)


            #写入数据
            dataIndex  = 1
            while dataIndex < len(tu):
                sheet.write(row,coulum,tu[dataIndex].deviceName)
                sheet.write(row,coulum+1,tu[dataIndex].foregoundCount + tu[dataIndex].backgroundCount,style)
                sheet.write(row,coulum+2,tu[dataIndex].foregoundCount,style)
                sheet.write(row,coulum+3,tu[dataIndex].backgroundCount,style)

                sheet.write(row + len(tu), coulum, tu[dataIndex].deviceName)
                if allCount == 0:
                    sheet.write(row + len(tu), coulum + 1,'0.00%',style)
                else:
                    sheet.write(row + len(tu), coulum + 1, str('%.2f'% ((tu[dataIndex].foregoundCount + tu[dataIndex].backgroundCount)/allCount*100)) + '%',style)
                if foregroundCount == 0:
                    sheet.write(row + len(tu), coulum + 2,'0.00%',style)
                else:
                    sheet.write(row + len(tu), coulum + 2, str('%.2f' % ((tu[dataIndex].foregoundCount)/foregroundCount * 100)) + '%',style)
                if backgroundCount == 0:
                    sheet.write(row + len(tu), coulum + 3,'0.00%',style)
                else:
                    sheet.write(row + len(tu), coulum + 3, str('%.2f' % ((tu[dataIndex].backgroundCount)/backgroundCount * 100)) + '%',style)
                row += 1
                dataIndex += 1


    def save(self):
        today = datetime.today()
        today_date = datetime.date(today)
        self.wbk.save('OOM' + str(today_date) + '.xls')



# ==================================================================================================
#                                    配置化模块
# ==================================================================================================
relativePathOfConfigFile = 'config/modules.config'
class  ConfigModules(object):
    def __init__(self):
        super(ConfigModules,self).__init__()
        self.cf = ConfigParser.RawConfigParser()
        self.configPath  = None
        self.sections = None

    def loadConfigFile(self):
        cwd = os.getcwd()
        self.configPath = os.path.join(cwd,relativePathOfConfigFile)
        if os.path.exists(self.configPath):
           return self.parserConfigFile(self.configPath)
        else:
            self.setDefaultConfig()
            self.loadConfigFile()


    def parserConfigFile(self,configPath):
        '''absolute path'''
        try:
            self.cf.read(configPath)
        except Exception,e:
            print e,configPath
        finally:
            pass
        self.sections = self.cf.sections()
        return self.sections

    def getValueWithKeyInSection(self,sec,key):
        return self.cf.get(sec,key)

    def setValueWithKeyInSection(self,sec,key,value):
        self.cf.set(sec,key,value)

    def setDefaultConfig(self):
        '''set default config'''
        dir = os.path.dirname(self.configPath)
        if not os.path.exists(dir):
            os.mkdir(dir)
        fp = open(self.configPath, 'w')
        fp.truncate()

        self.cf.add_section('Search_oom')
        self.cf.set('Search_oom', 'title', unicode('搜索OOM','utf-8'))
        self.cf.set('Search_oom', 'controllers', 'FinalSearchListViewController')

        self.cf.add_section('Cart_oom')
        self.cf.set('Cart_oom', 'title', unicode('购物车OOM', 'utf-8'))
        self.cf.set('Cart_oom', 'controllers', 'SynCartViewController')

        self.cf.add_section('WareInfo_oom')
        self.cf.set('WareInfo_oom', 'title', unicode('商祥OOM', 'utf-8'))
        self.cf.set('WareInfo_oom', 'controllers', 'WareInfoBViewController')

        self.cf.add_section('Web_oom')
        self.cf.set('Web_oom', 'title', unicode('Web页面', 'utf-8'))
        self.cf.set('Web_oom', 'controllers', 'JDWebViewController')
        self.cf.write(fp)
# ==================================================================================================
#                                    配置化模块 END
# ==================================================================================================

def  main():
    # config
    cm = ConfigModules()
    sections = cm.loadConfigFile()

    # 获取所有的reportList
    cp = CrashParser()
    reportList = cp.getDecryptedReportList()

    # 根据ctonroller 计算比例，同一个页面，同一个uuid 才算是数据重复
    pageCP = OOMCrashBasedOnPage(cp)
    tu = pageCP.getOOMCrashPageCount(reportList)

    # 根据页面 拆分
    OOMWriter = OOMxlsWritter()
    OOMWriter.writeAllCrashListToXls(pageCP.updatePercentAndSort(tu))
    OOMWriter.writeUniqUUIDCrashListToXls(pageCP.updatePercentAndSortWithFilterRepeatUUID(tu))

    # 根据模块 device 拆分
    pageAndDevie = OOMCrashBasedOnPageAndDevice(cp)
    pageAndDevie.getOOMCrashPageAndDeviceCountMaybeRepeat(reportList)
    OOMWriter.writeAllBasedOnPageAndDeviceWithSecionts(sections, cm, pageAndDevie, '根据设备未去重')

    # #根据模块 device 拆分,去重
    pageAndDevieFilterRepeat = OOMCrashBasedOnPageAndDevice(cp)
    pageAndDevieFilterRepeat.getOOMCrashPageAndDeviceCountWithNoRepeat(reportList)
    OOMWriter.writeAllBasedOnPageAndDeviceWithSecionts(sections, cm, pageAndDevieFilterRepeat, '根据设备已去重')

    #保存数据
    OOMWriter.save()


if __name__ == '__main__':
    main()