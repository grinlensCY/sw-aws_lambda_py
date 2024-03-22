# Module Imports
#import pymysql as sql_lib
import MySQLdb as sql_lib

import sys
import datetime
import time
import traceback
from datetime import timezone
import io
import boto3
import base64
from botocore.client import ClientError

DB_USER_NAME="admin"
DB_PASSWROD="HdsMM6EnWPfU9s5PHR4eNGdnYDYctuvm"
#DB_URL="db-baby-monitor.chm9qorasc3x.ap-northeast-1.rds.amazonaws.com"
DB_URL="db-baby-monitor-mysql.chm9qorasc3x.ap-northeast-1.rds.amazonaws.com"

#===========================================================================
#https://github.com/nonbeing/mysqlclient-python3-aws-lambda

#RDS proxy目前只能在VPC內部存取，因此如果要測試proxy，就需要在EC2
#https://aws.amazon.com/tw/premiumsupport/knowledge-center/rds-proxy-connection-issues/
DB_PROXY_URL="proxy-db-baby-monitor-mysql.proxy-chm9qorasc3x.ap-northeast-1.rds.amazonaws.com"
DB_READONLY_PROXY_URL="proxy-db-baby-monitor-mysql-read-only.endpoint.proxy-chm9qorasc3x.ap-northeast-1.rds.amazonaws.com"

#https://stackoverflow.com/questions/37030704/allow-aws-lambda-to-access-rds-database
#lambda無法直接以IP存取到rds proxy，必須准許VPC存許

DEV_TYPE_FATEL_MONITOR=10
DEV_TYPE_BABY_MONITOR=20
STA_TYPE_BABY_MONITOR=30

GENDER_GIRL=0
GENDER_BOY=1
GENDER_OTHER=2

DB_NAME='db_baby_monitor_neo'
USER_TABLE_NAME='user'
BABY_TABLE_NAME='baby'
DEV_TABLE_NAME='dev'
STA_TABLE_NAME='sta'
DEV_BABY_MAP_TABLE_NAME='dev_baby_map'
DEV_USER_MAP_TABLE_NAME='dev_user_map'
STA_USER_MAP_TABLE_NAME='sta_user_map'
EVT_TABLE_NAME='evt'
BILL_TABLE_NAME='bill'
FOOD_TABLE_NAME='food'
FEED_EVT_TABLE_NAME='feed'
RANGE_EVT_TABLE_NAME='revt'
MP3_TABLE_NAME='mp3'
TREND_TABLE_NAME='trend'

ERROR_USER_WIHT_THE_SAME_COGNITOID_NOT_EXIST=-1000
ERROR_ALREADY_HAVE_USER_WITH_THE_SAME_COGNITOID=-1001
ERROR_USER_INSERT_FAIL=-1002
ERROR_USER_INFO_CHANGE_FAIL=-1003
ERROR_READ_USER_INFO_FAIL=-1004
ERROR_DELETE_USER_FAIL=-1005

ERROR_BABY_WIHT_THE_NAME_NOT_EXIST=-2000
ERROR_ALREADY_HAVE_BABY_WITH_THE_SAME_NAME=-2001
ERROR_BABY_INSERT_FAIL=-2002
ERROR_BABY_INFO_CHANGE_FAIL=-2003
ERROR_DELETE_DEV_BABY_MAP_ITEM_FAIL=-2004
ERROR_DELETE_BABY_FAIL=-2005
ERROR_READ_BABY_INFO_FAIL=-2006

ERROR_STA_UDID_IS_ALREADY_EXIST=-3000
ERROR_STA_INSERT_FAIL=-3001
ERROR_STA_WITH_THE_UDID_IS_NOT_EXIST=-3002
ERROR_READ_STA_INFO_FAIL=-3003
ERROR_DEL_STA_INFO_FAIL=-3004
ERROR_STA_UPDATE_FAIL=-3005

ERROR_DEV_UDID_IS_ALREADY_EXIST=-4000
ERROR_DEV_INSERT_FAIL=-4001
ERROR_DEV_WITH_THE_UDID_IS_NOT_EXIST=-4002
ERROR_READ_DEV_INFO_FAIL=-4003
ERROR_DEL_DEV_INFO_FAIL=-4004

ERROR_READ_DEV_BABY_MAP_INFO_FAIL=-5000
ERROR_DELETE_DEV_BABY_MAP_INFO_FAIL=-5001
ERROR_INSERT_DEV_BABY_MAP_INFO_FAIL=-5002
ERROR_NO_RECORD_WITH_THE_DEVID=-5003
ERROR_NO_VALID_DEVID=-5004
ERROR_DEV_IS_OCCUPIED_BY_OTHER_BABY=-5005

ERROR_READ_EVENT_INFO_FAIL=-6000
ERROR_EVENT_INSERT_FAIL=-6001
ERROR_DELETE_EVENT_FAIL=-6002
ERROR_EVENT_CHANGE_FAIL=-6003
ERROR_EVENT_ALEADY_EXIST=-6004

ERROR_READ_STA_USER_MAP_INFO_FAIL=-7000
ERROR_DELETE_STA_USER_MAP_INFO_FAIL=-7001
ERROR_INSERT_STA_USER_MAP_INFO_FAIL=-7002
ERROR_NO_RECORD_WITH_THE_STAID=-7003
ERROR_STA_IS_OCCUPIED_BY_OTHER=-7004

ERROR_READ_DEV_USER_MAP_INFO_FAIL=-7500
ERROR_DELETE_DEV_USER_MAP_INFO_FAIL=-7501
ERROR_INSERT_DEV_USER_MAP_INFO_FAIL=-7502
ERROR_DEV_IS_OCCUPIED_BY_OTHER=-7503
ERROR_USER_DONT_HAVE_THIS_DEV=-7504

ERROR_READ_FOOD_INFO_FAIL=-8000
ERROR_FOOD_NAME_IS_ALREADY_EXIST=-8001
ERROR_FOOD_INSERT_FAIL=-8002
ERROR_FOOD_UPDATE_FAIL=-8003
ERROR_FOOD_NEW_NAME_IS_ALREADY_EXIST=-8004
ERROR_FOOD_DELETE_FAIL=-8005
ERROR_FOOD_IS_NOT_EXIST=-8006

ERROR_READ_FEED_INFO_FAIL=-9000
ERROR_FEED_INSERT_FAIL=-9001
ERROR_FEED_UPDATE_FAIL=-9002
ERROR_FEED_DELETE_FAIL=-9003
ERROR_FEED_ALEADY_EXIST=-9004

ERROR_READ_REVT_INFO_FAIL=-10000
ERROR_REVT_INSERT_FAIL=-10001
ERROR_REVT_UPDATE_FAIL=-10002
ERROR_REVT_DELETE_FAIL=-10003
ERROR_REVT_ALEADY_EXIST=-10004

ERROR_READ_MP3_INFO_FAIL=-11000
ERROR_MP3_ADD_FAIL=-11001
ERROR_MP3_DELETE_FAIL=-11002
ERROR_MP3_ALEADY_EXIST=-11003
ERROR_MP3_ENCODE_ERR=-11004
ERROR_MP3_SLOT_OUT_OF_RANGE=-11005

ERROR_READ_CFG_FAIL=-12000
ERROR_CFG_ADD_FAIL=-12001
ERROR_READ_PHOTO_FAIL=-12002
ERROR_PHOTO_ADD_FAIL=-12003
ERROR_PHOTO_ENCODE_ERR=-12004
ERROR_ODD_ADD_FAIL=-12005

ERROR_READ_TREND_INFO_FAIL=-13000
ERROR_TREND_INSERT_FAIL=-13001
ERROR_DELETE_TREND_FAIL=-13002
ERROR_TREND_CHANGE_FAIL=-13003
ERROR_TREND_ALEADY_EXIST=-13004

ERROR_EMAIL_INVALID_ACT=-20000

error_code_msg_map={
ERROR_USER_WIHT_THE_SAME_COGNITOID_NOT_EXIST:'無效的使用者',
ERROR_ALREADY_HAVE_USER_WITH_THE_SAME_COGNITOID:"已經有同ID的使用者",
ERROR_USER_INSERT_FAIL:"無法新增使用者",
ERROR_USER_INFO_CHANGE_FAIL:"修改使用者資料時候出現錯誤",
ERROR_READ_USER_INFO_FAIL:"無法讀取使用者資料",
ERROR_DELETE_USER_FAIL:"無法刪除使用者",

ERROR_BABY_WIHT_THE_NAME_NOT_EXIST:"沒有名字相符的寶寶",
ERROR_ALREADY_HAVE_BABY_WITH_THE_SAME_NAME:"已經有相同名字的寶寶",
ERROR_BABY_INSERT_FAIL:"無法增加寶寶",
ERROR_BABY_INFO_CHANGE_FAIL:"無法修改寶寶資訊",
ERROR_DELETE_DEV_BABY_MAP_ITEM_FAIL:"無法刪除寶寶配對的裝置",
ERROR_DELETE_BABY_FAIL:"無法刪除寶寶",
ERROR_READ_BABY_INFO_FAIL:"無法讀取寶寶資訊",

ERROR_STA_UDID_IS_ALREADY_EXIST:"已經存在該STA UDID",
ERROR_STA_INSERT_FAIL:"無法增加STA",
ERROR_STA_WITH_THE_UDID_IS_NOT_EXIST:"不存在該UDID的STA",
ERROR_READ_STA_INFO_FAIL:"無法讀取STA資料",
ERROR_DEL_STA_INFO_FAIL:"無法刪除STA",
ERROR_STA_UPDATE_FAIL:"無法更新STA",

ERROR_DEV_UDID_IS_ALREADY_EXIST:"已經存在該DEV UDID",
ERROR_DEV_INSERT_FAIL:"無法增加DEV",
ERROR_DEV_WITH_THE_UDID_IS_NOT_EXIST:"不存在該UDID的DEV",
ERROR_READ_DEV_INFO_FAIL:"無法讀取DEV資料",
ERROR_DEL_DEV_INFO_FAIL:"無法刪除DEV",

ERROR_READ_DEV_BABY_MAP_INFO_FAIL:"無法讀取DEV BABY對應表",
ERROR_DELETE_DEV_BABY_MAP_INFO_FAIL:"無法刪除DEV BABY對應表的資料",
ERROR_INSERT_DEV_BABY_MAP_INFO_FAIL:"無法增加DEV BABY對應表資訊",
ERROR_NO_RECORD_WITH_THE_DEVID:"該DEV ID在DEV BABY對應表沒有任何紀錄",
ERROR_NO_VALID_DEVID:"無有效的DEV",
ERROR_DEV_IS_OCCUPIED_BY_OTHER_BABY:"該DEV已經指定給其他BABY",

ERROR_READ_EVENT_INFO_FAIL:"無法讀取事件資料",
ERROR_EVENT_INSERT_FAIL:"無法增加事件",
ERROR_DELETE_EVENT_FAIL:"無法刪除事件",
ERROR_EVENT_CHANGE_FAIL:"無法更新事件",
ERROR_EVENT_ALEADY_EXIST:"該事件已存在",

ERROR_READ_STA_USER_MAP_INFO_FAIL:"無法讀取STA USER對應表的資訊",
ERROR_DELETE_STA_USER_MAP_INFO_FAIL:"無法刪除STA USER對應表的資訊",
ERROR_INSERT_STA_USER_MAP_INFO_FAIL:"無法新增STA USER對應表的資訊",
ERROR_NO_RECORD_WITH_THE_STAID:"沒有該STA ID的資料",
ERROR_STA_IS_OCCUPIED_BY_OTHER:"該STA已被他人使用",

ERROR_READ_DEV_USER_MAP_INFO_FAIL:"無法讀取DEV_USER配對表",
ERROR_DELETE_DEV_USER_MAP_INFO_FAIL:"無法刪除DEV_USER配對",
ERROR_INSERT_DEV_USER_MAP_INFO_FAIL:"無法新增DEV_USER配對",
ERROR_DEV_IS_OCCUPIED_BY_OTHER:"該DEV已被他人使用",
ERROR_USER_DONT_HAVE_THIS_DEV:"使用者沒有該DEV",

ERROR_READ_FOOD_INFO_FAIL:"無法讀取FOOD資訊",
ERROR_FOOD_NAME_IS_ALREADY_EXIST:"該FOOD名稱已經存在",
ERROR_FOOD_INSERT_FAIL:"無法增加FOOD資訊",
ERROR_FOOD_UPDATE_FAIL:"無法更新FOOD資訊",
ERROR_FOOD_NEW_NAME_IS_ALREADY_EXIST:"新的FOOD名稱已經存在",
ERROR_FOOD_DELETE_FAIL:"無法刪除FOOD資訊",
ERROR_FOOD_IS_NOT_EXIST:"無該FOOD資訊",

ERROR_READ_FEED_INFO_FAIL:"無法讀取FEED資訊",
ERROR_FEED_INSERT_FAIL:"無法增加FEED資訊",
ERROR_FEED_UPDATE_FAIL:"無法更新FEED資訊",
ERROR_FEED_DELETE_FAIL:"無法刪除FEED資訊",
ERROR_FEED_ALEADY_EXIST:"該事件已存在",

ERROR_READ_REVT_INFO_FAIL:"無法讀取RangeEvent資訊",
ERROR_REVT_INSERT_FAIL:"無法增加RangeEvent資訊",
ERROR_REVT_UPDATE_FAIL:"無法更新RangeEvent資訊",
ERROR_REVT_DELETE_FAIL:"無法刪除RangeEvent資訊",
ERROR_REVT_ALEADY_EXIST:"該事件已存在",

ERROR_READ_MP3_INFO_FAIL:"無法讀取MP3資訊",
ERROR_MP3_ADD_FAIL:"無法新增MP3",
ERROR_MP3_DELETE_FAIL:"MP3無法刪除",
ERROR_MP3_ALEADY_EXIST:"MP3已經存在",
ERROR_MP3_ENCODE_ERR:"MP3編碼錯誤",
ERROR_MP3_SLOT_OUT_OF_RANGE:"無效的Slot",

ERROR_READ_CFG_FAIL:"無法讀取cfg",
ERROR_CFG_ADD_FAIL:"無法寫入cfg",
ERROR_READ_PHOTO_FAIL:"無法讀取photo",
ERROR_PHOTO_ADD_FAIL:"無法寫入photo",
ERROR_PHOTO_ENCODE_ERR:"圖片base64編碼錯誤",
ERROR_ODD_ADD_FAIL:"無法寫入odd snd",

ERROR_READ_TREND_INFO_FAIL:"無法讀取趨勢資訊",
ERROR_TREND_INSERT_FAIL:"無法增加趨勢資訊",
ERROR_DELETE_TREND_FAIL:"無法刪除趨勢訊",
ERROR_TREND_CHANGE_FAIL:"無法更新趨勢資訊",
ERROR_TREND_ALEADY_EXIST:"該趨勢資訊已存在",

ERROR_EMAIL_INVALID_ACT:"無此指令"

}

EVENT_TYPE_PEE=1
EVENT_TYPE_POOP=2
EVENT_TYPE_CHANGE_DIAPER=3
EVENT_TYPE_MILK=4
EVENT_TYPE_SLEEP_START=5
EVENT_TYPE_SLEEP_END=6
EVENT_TYPE_ACTIVE=7
EVENT_TYPE_CRY=8
EVENT_TYPE_FART=9

EVENT_TYPE_HR_H=101
EVENT_TYPE_HR_L=102
EVENT_TYPE_RR_H=103
EVENT_TYPE_RR_L=104
EVENT_TYPE_TMP_H=105
EVENT_TYPE_TMP_L=106
EVENT_TYPE_RRQ=107
EVENT_TYPE_CHOKIN=108
EVENT_TYPE_DIARRHEA=109
EVENT_TYPE_BS=110
EVENT_TYPE_WAKEUP=111
EVENT_TYPE_OBS=112

EVENT_STR_PEE='pee'
EVENT_STR_POOP='poop'
EVENT_STR_CHANGE_DIAPER='change_diaper'
EVENT_STR_MILK='milk'
EVENT_STR_SLEEP_START='sleep_start'
EVENT_STR_SLEEP_END='sleep_end'
EVENT_STR_ACTIVE='active'
EVENT_STR_CRY='cry'
EVENT_STR_FART='fart'

EVENT_STR_HR_H='hrh'
EVENT_STR_HR_L='hrl'
EVENT_STR_RR_H='rrh'
EVENT_STR_RR_L='rrl'
EVENT_STR_TMP_H='tmph'
EVENT_STR_TMP_L='tmpl'
EVENT_STR_RRQ='rrq'
EVENT_STR_CHOKIN='chokin'
EVENT_STR_DIARRHEA='diarrhea'
EVENT_STR_BS='bs'

EVT_CODE_TO_STR_MAP={
EVENT_TYPE_PEE:EVENT_STR_PEE,
EVENT_TYPE_POOP:EVENT_STR_POOP,
EVENT_TYPE_CHANGE_DIAPER:EVENT_STR_CHANGE_DIAPER,
EVENT_TYPE_MILK:EVENT_STR_MILK,
EVENT_TYPE_SLEEP_START:EVENT_STR_SLEEP_START,
EVENT_TYPE_SLEEP_END:EVENT_STR_SLEEP_END,
EVENT_TYPE_ACTIVE:EVENT_STR_ACTIVE,
EVENT_TYPE_CRY:EVENT_STR_CRY,
EVENT_TYPE_FART:EVENT_STR_FART,

EVENT_TYPE_HR_H:EVENT_STR_HR_H,
EVENT_TYPE_HR_L:EVENT_STR_HR_L,
EVENT_TYPE_RR_H:EVENT_STR_RR_H,
EVENT_TYPE_RR_L:EVENT_STR_RR_L,
EVENT_TYPE_TMP_H:EVENT_STR_TMP_H,
EVENT_TYPE_TMP_L:EVENT_STR_TMP_L,
EVENT_TYPE_RRQ:EVENT_STR_RRQ,
EVENT_TYPE_CHOKIN:EVENT_STR_CHOKIN,
EVENT_TYPE_DIARRHEA:EVENT_STR_DIARRHEA,
EVENT_TYPE_BS:EVENT_STR_BS
}

EVT_STR_TO_CODE_MAP={
EVENT_STR_PEE:EVENT_TYPE_PEE,
EVENT_STR_POOP:EVENT_TYPE_POOP,
EVENT_STR_CHANGE_DIAPER:EVENT_TYPE_CHANGE_DIAPER,
EVENT_STR_MILK:EVENT_TYPE_MILK,
EVENT_STR_SLEEP_START:EVENT_TYPE_SLEEP_START,
EVENT_STR_SLEEP_END:EVENT_TYPE_SLEEP_END,
EVENT_STR_ACTIVE:EVENT_TYPE_ACTIVE,
EVENT_STR_CRY:EVENT_TYPE_CRY,
EVENT_STR_FART:EVENT_TYPE_FART,

EVENT_STR_HR_H:EVENT_TYPE_HR_H,
EVENT_STR_HR_L:EVENT_TYPE_HR_L,
EVENT_STR_RR_H:EVENT_TYPE_RR_H,
EVENT_STR_RR_L:EVENT_TYPE_RR_L,
EVENT_STR_TMP_H:EVENT_TYPE_TMP_H,
EVENT_STR_TMP_L:EVENT_TYPE_TMP_L,
EVENT_STR_RRQ:EVENT_TYPE_RRQ,
EVENT_STR_CHOKIN:EVENT_TYPE_CHOKIN,
EVENT_STR_DIARRHEA:EVENT_TYPE_DIARRHEA,
EVENT_STR_BS:EVENT_TYPE_BS
}

'''
新增喝奶事件
新增換尿布事件
新增睡眠起始事件
新增睡眠結束事件
新增清醒活動事件
新增哭聲事件
新增放屁事件
'''

MANUAL_DEV_UDID='manual_dev'
manual_dev_idx=0

s3 = boto3.client('s3')
S3_BUCKET='awsbabymonitor114454-dev'

#===========================================================================
#cache

class Cache():

    def __init__(self,max_size,max_hold_ts) -> None:
        self.max_hold_ts=max_hold_ts
        self.max_size=max_size

        self.reset()

    def reset(self):
        self.data_map={}
        self.data_map_size=0
        self.data_map_last_ts=0

    def set(self,key,val):
        #寫入的時候檢查內部資料的大小，如果已經太大，就刪除最舊的資料
        cts=time.time()

        if(self.data_map_size>=self.max_size):
            del_item_cnt=0
            eariest_data_ts=-1
            eariest_data_key=None
            for key, info in self.data_map.items():
                if((cts-info[1])>self.max_hold_ts):
                    del self.data_map[key]
                    del_item_cnt+=1
                elif(del_item_cnt==0):
                    if(eariest_data_ts<0 or eariest_data_ts>info[1]):
                        eariest_data_ts=info[1]
                        eariest_data_key=key
                    
            #如果沒刪掉任何資料，就刪除最舊的那筆資料
            if(del_item_cnt==0 and eariest_data_key is not None):
                del self.data_map[eariest_data_key]
                del_item_cnt+=1

            #下面情況不可能發生
            self.data_map_size-=del_item_cnt
            if(self.data_map_size<0):
                self.reset()

        self.data_map[key]=(val,cts)
        self.data_map_size+=1
        self.data_map_last_ts=cts

    def get(self,key):
        #讀取的時候檢查內部資料的時間戳記，如果過時的，救回傳None
        cts=time.time()

        if(key not in self.data_map):
            return None

        info=self.data_map[key]
        
        val=info[0]
        ts=info[1]

        if((cts-ts)>self.max_hold_ts):
            del self.data_map[key]
            val=None
            self.data_map_size-=1

        return val
    
sta_uuid_to_id_cache=Cache(1024,3600)#this mapping is never changing
dev_uuid_to_id_cache=Cache(1024,3600)#this mapping is never changing
dev_uuid_to_baby_id_cache=Cache(1024,300)#5min
baby_name_to_id_cache=Cache(1024,3600)#5min
cognito_id_to_user_id_cache=Cache(1024,3600)#this mapping is never changing

def reset_cache():#A
    sta_uuid_to_id_cache.reset()
    dev_uuid_to_id_cache.reset()
    dev_uuid_to_baby_id_cache.reset()
    baby_name_to_id_cache.reset()
    cognito_id_to_user_id_cache.reset()

#===========================================================================

def get_aws_ts():#S
    return int(time.time()*1000)

def connectDb():#S
    global manual_dev_idx
    
    # Connect to MariaDB Platform
    for _ in range(10):
        try:
            conn = sql_lib.connect(
                user=DB_USER_NAME,
                password=DB_PASSWROD,
                host=DB_URL,
                port=3306,
                database=DB_NAME
            )
        except sql_lib.Error as e:
            print(f"Error connecting to MariaDB Platform: {e}")
            
        try:
            cur = conn.cursor()
            manual_dev_info=getDevByUdid(cur,MANUAL_DEV_UDID)
            if(manual_dev_info[0]==False):
                print(manual_dev_info)
            else:
                manual_dev_idx=manual_dev_info[1][0]
            cur.close()
        except:
            pass

        return conn
    return None

def connectDbByProxy():#S
    global manual_dev_idx
    
    # Connect to MariaDB Platform
    for _ in range(10):
        try:
            conn = sql_lib.connect(
                user=DB_USER_NAME,
                password=DB_PASSWROD,
                host=DB_PROXY_URL,
                port=3306,
                database=DB_NAME
            )
        except sql_lib.Error as e:
            print(f"Error connecting to MariaDB Platform: {e}")
            
        try:
            cur = conn.cursor()
            manual_dev_info=getDevByUdid(cur,MANUAL_DEV_UDID)
            if(manual_dev_info[0]==False):
                print(manual_dev_info)
            else:
                manual_dev_idx=manual_dev_info[1][0]
            cur.close()
        except:
            pass

        return conn
    
    return None


def connectDbByReadOnlyProxy():#S
    global manual_dev_idx
    
    # Connect to MariaDB Platform
    for _ in range(10):
        try:
            conn = sql_lib.connect(
                user=DB_USER_NAME,
                password=DB_PASSWROD,
                host=DB_READONLY_PROXY_URL,
                port=3306,
                database=DB_NAME
            )
            
        except sql_lib.Error as e:
            print(f"Error connecting to MariaDB Platform: {e}")
            
        try:
            cur = conn.cursor()
            manual_dev_info=getDevByUdid(cur,MANUAL_DEV_UDID)
            if(manual_dev_info[0]==False):
                print(manual_dev_info)
            else:
                manual_dev_idx=manual_dev_info[1][0]
            cur.close()
        except:
            pass

        return conn
    
    return None

#===========================================================================

def getUserByCognitoId(cur,cognito_id):#A #B for meta data only
    STATE="SELECT user_id,cognito_id,name,vip_level,cfg_ts,photo_ts,cognito_name FROM %s WHERE cognito_id='%s' LIMIT 1"%(USER_TABLE_NAME,cognito_id)

    try:
        cur.execute(STATE)
        res = cur.fetchone()
    except:
        return (False,ERROR_READ_USER_INFO_FAIL)

    if(res==None or len(res)==0):
        return (False,ERROR_USER_WIHT_THE_SAME_COGNITOID_NOT_EXIST)
    return (True,res)

def getUserIdByCognitoId(cur,cognito_id):#A #B
    uid=cognito_id_to_user_id_cache.get(cognito_id)

    if(uid is not None):
        return (True,uid)

    STATE="SELECT user_id FROM %s WHERE cognito_id='%s' LIMIT 1"%(USER_TABLE_NAME,cognito_id)

    try:
        cur.execute(STATE)
        res = cur.fetchone()
    except:
        return (False,ERROR_READ_USER_INFO_FAIL)

    if(res==None or len(res)==0):
        return (False,ERROR_USER_WIHT_THE_SAME_COGNITOID_NOT_EXIST)

    cognito_id_to_user_id_cache.set(cognito_id,res[0])

    return (True,res[0])

#===========================================================================

def getCognitoIdByStaId(cur,sid):#A #B
    VALUES=(USER_TABLE_NAME,STA_USER_MAP_TABLE_NAME,sid)
    STATE='SELECT a.cognito_id FROM %s as a '\
        'JOIN %s as b ON a.user_id=b.user_id '\
        'AND b.sta_id=%d'%VALUES

    try:
        cur.execute(STATE)
        res = cur.fetchone()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_STA_INFO_FAIL)

    if(res==None):
        return (True,[])

    return (True,res)

def getDevListByStaId(cur,sid):#A #B
    VALUES=(DEV_TABLE_NAME,DEV_USER_MAP_TABLE_NAME,DEV_BABY_MAP_TABLE_NAME,BABY_TABLE_NAME,STA_USER_MAP_TABLE_NAME,sid)
    STATE='SELECT a.udid,a.aes_key,a.aes_iv FROM %s as a '\
        'JOIN %s as b ON a.dev_id=b.dev_id '\
        'JOIN %s as c ON c.du_map_id=b.map_id '\
        'JOIN %s as d ON c.baby_id=d.baby_id '\
        'JOIN %s as e ON d.user_id=e.user_id '\
        'AND e.sta_id=%d'%VALUES

    try:
        cur.execute(STATE)
        res = cur.fetchall()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_STA_INFO_FAIL)

    if(res==None or len(res)==0):
        return (True,[])
    
    res_list=[]
    for item in res:
        res_list.append(item)

    return (True,res_list)

def getStaByUdid(cur,udid):#A #B
    STATE="SELECT sta_id,udid,pw,pcb_ver,type,mf_ts FROM %s WHERE udid='%s' LIMIT 1"%(STA_TABLE_NAME,udid)

    try:
        cur.execute(STATE)
        res = cur.fetchone()
    except:
        return (False,ERROR_READ_STA_INFO_FAIL)

    if(res==None or len(res)==0):
        return (False,ERROR_STA_WITH_THE_UDID_IS_NOT_EXIST)
        
    return (True,res)

def getStaIdByStaUdid(cur,udid):#A #B
    sid=sta_uuid_to_id_cache.get(udid)

    if(sid):
        return (True,sid)

    STATE="SELECT sta_id FROM %s WHERE udid='%s' LIMIT 1"%(STA_TABLE_NAME,udid)

    try:
        cur.execute(STATE)
        res = cur.fetchone()
    except:
        return (False,ERROR_READ_STA_INFO_FAIL)

    if(res==None or len(res)==0):
        return (False,ERROR_STA_WITH_THE_UDID_IS_NOT_EXIST)

    sta_uuid_to_id_cache.set(udid,res[0])
    return (True,res[0])
    
def getDevByUdid(cur,udid):#A #B
    STATE="SELECT dev_id,udid,aes_key,aes_iv,pcb_ver,type,mf_ts FROM %s WHERE udid='%s' LIMIT 1"%(DEV_TABLE_NAME,udid)

    try:
        cur.execute(STATE)
        res = cur.fetchone()
    except:
        return (False,ERROR_READ_DEV_INFO_FAIL)

    if(res==None or len(res)==0):
        return (False,ERROR_DEV_WITH_THE_UDID_IS_NOT_EXIST)

    return (True,res)

#===========================================================================

def addDev(cur,conn,udid,aes_key,aes_iv,pcb_ver,type,mf_ts):#B
    res=getDevByUdid(cur,udid)

    if(res[0]):
        return (False,ERROR_DEV_UDID_IS_ALREADY_EXIST)
    if(res[0]==False and res[1]!=ERROR_DEV_WITH_THE_UDID_IS_NOT_EXIST):
        return res
    
    VALUES=(DEV_TABLE_NAME,udid,aes_key,aes_iv,pcb_ver,type,mf_ts)
    STATE="INSERT INTO %s (udid,aes_key,aes_iv,pcb_ver,type,mf_ts) values ('%s','%s','%s',%d,%d,%d)"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_DEV_INSERT_FAIL)

    return (True,cur.lastrowid)

def addSta(cur,conn,udid,pw,pcb_ver,type,mf_ts):#B
    res=getStaIdByStaUdid(cur,udid)
    
    if(res[0]):
        return (False,ERROR_STA_UDID_IS_ALREADY_EXIST)

    if(res[1]!=ERROR_STA_WITH_THE_UDID_IS_NOT_EXIST):
        return res

    VALUES=(STA_TABLE_NAME,udid,pw,pcb_ver,type,mf_ts)
    STATE="INSERT INTO %s (udid,pw,pcb_ver,type,mf_ts,dev_pair_ts) values ('%s','%s',%d,%d,%d,0)"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        return (False,ERROR_STA_INSERT_FAIL)

    return (True,cur.lastrowid)

def notifyStaScanChangeByUserId(cur,conn,user_id):#A #B
    VALUES=(STA_TABLE_NAME,STA_USER_MAP_TABLE_NAME,user_id)
    STATE="UPDATE %s AS s JOIN %s AS usm ON s.sta_id=usm.sta_id AND usm.user_id=%d SET s.dev_pair_ts=CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER)"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        return (False,ERROR_STA_UPDATE_FAIL)

    return (True,0)

def getLastStaScanChangeTsByStaId(cur,sta_id):#A #B
    VALUES=(STA_TABLE_NAME,sta_id)
    STATE="SELECT dev_pair_ts FROM %s WHERE sta_id=%d LIMIT 1"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchall()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_STA_INFO_FAIL)

    if(res==None or len(res)==0):
        return (True,0)

    return (True,res[0][0])

def deleteDev(cur,conn,udid):#B
    VALUES=(DEV_TABLE_NAME,udid)
    STATE="DELETE FROM  %s WHERE udid='%s'"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_DEL_DEV_INFO_FAIL)

    return (True,cur.lastrowid)

def deleteSta(cur,conn,udid):#B
    VALUES=(STA_TABLE_NAME,udid)
    STATE="DELETE FROM  %s WHERE udid='%s'"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_DEL_STA_INFO_FAIL)

    return (True,cur.lastrowid)

#===========================================================================

def getBabyList(cur,cognito_id):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    STATE="SELECT baby_id,user_id,name,gender,birthday,photo_ts,cfg_ts FROM %s WHERE user_id='%s' ORDER BY baby_id ASC"%(BABY_TABLE_NAME,user_id)

    try:
        cur.execute(STATE)
        res = cur.fetchall()
    except:
        return (False,ERROR_READ_BABY_INFO_FAIL)

    if(res==None or len(res)==0):
        return (True,[],user_id)

    res=list(res)
    return (True,res,user_id)

def getBabyNameById(cur,bid):#要注意是不是使用者所屬的baby
    STATE="SELECT name FROM %s WHERE baby_id='%d' LIMIT 1"%(BABY_TABLE_NAME,bid)

    try:
        cur.execute(STATE)
        res = cur.fetchone()
    except:
        return (False,ERROR_READ_BABY_INFO_FAIL)

    if(res==None or len(res)==0):
        return (False,ERROR_READ_BABY_INFO_FAIL)

    return (True,res)

def getBabyByUserIdAndName(cur,user_id,bn):#a1
    STATE="SELECT baby_id,user_id,name,gender,birthday,photo_ts,cfg_ts FROM %s WHERE user_id='%s' AND name='%s' LIMIT 1"%(BABY_TABLE_NAME,user_id,bn)

    try:
        cur.execute(STATE)
        res = cur.fetchone()
    except:
        return (False,ERROR_READ_BABY_INFO_FAIL)

    if(res==None or len(res)==0):
        return (False,ERROR_BABY_WIHT_THE_NAME_NOT_EXIST)

    return (True,res)

def getBabyByCognitoIdAndName(cur,cognito_id,bn):#B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    res=getBabyByUserIdAndName(cur,user_id,bn)

    if(res[0]==False):
        return res

    return (True,res[1])

def addBaby(cur,conn,cognito_id,name,gender,birthday):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    res=getBabyByUserIdAndName(cur,user_id,name)

    if(res[0]):
        return (False,ERROR_ALREADY_HAVE_BABY_WITH_THE_SAME_NAME)

    if(res[0]==False and res[1]!=ERROR_BABY_WIHT_THE_NAME_NOT_EXIST):
        return res

    VALUES=(BABY_TABLE_NAME,user_id,name,gender,birthday)
    STATE="INSERT INTO %s (user_id,name,gender,birthday,photo_ts,cfg_ts) values (%d,'%s',%d,%d,0,0)"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        return (False,ERROR_BABY_INSERT_FAIL)
        
    return (True,cur.lastrowid)

def changeBabyInfoByBabyId(cur,conn,baby_id,name,gender,birthday):#a1
    VALUES=(BABY_TABLE_NAME,name,gender,birthday,baby_id)
    STATE="UPDATE %s SET name='%s',gender=%d,birthday='%d' WHERE baby_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        return (False,ERROR_BABY_INFO_CHANGE_FAIL)

    return (True,0)

def changeBabyInfo(cur,conn,cognito_id,org_baby_name,name,gender,birthday):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]
    
    res=getBabyByUserIdAndName(cur,user_id,org_baby_name)

    if(res[0]==False):
        return res

    baby_id=res[1][0]

    if(name!=org_baby_name):
        res=getBabyByUserIdAndName(cur,user_id,name)

        if(res[0]):
            return (False,ERROR_ALREADY_HAVE_BABY_WITH_THE_SAME_NAME)

        if(res[0]==False and res[1]!=ERROR_BABY_WIHT_THE_NAME_NOT_EXIST):
            return res
            
    return changeBabyInfoByBabyId(cur,conn,baby_id,name,gender,birthday)

def deleteBabyByBabyId(cur,conn,baby_id):#a1
    VALUES=(BABY_TABLE_NAME,baby_id)
    STATE="DELETE FROM %s WHERE baby_id=%d"%VALUES
    
    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        return (False,ERROR_DELETE_BABY_FAIL)

    return (True,0)
    
def deleteBaby(cur,conn,cognito_id,baby_name):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    res=getBabyByUserIdAndName(cur,user_id,baby_name)

    if(res[0]==False):
        return res

    baby_id=res[1][0]

    return deleteBabyByBabyId(cur,conn,baby_id)

#===========================================================================

def addUser(cur,conn,cognito_id,cognito_name,name,vip_level=0,auth_type=0):#B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]):
        return (False,ERROR_ALREADY_HAVE_USER_WITH_THE_SAME_COGNITOID)

    if(res[0]==False and res[1]!=ERROR_USER_WIHT_THE_SAME_COGNITOID_NOT_EXIST):
        return res

    VALUES=(USER_TABLE_NAME,cognito_id,cognito_name,name,vip_level,auth_type)
    STATE="INSERT INTO %s (cognito_id,cognito_name,name,vip_level,cfg_ts,photo_ts,auth_type) values ('%s','%s','%s',%d,0,0,%d)"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_USER_INSERT_FAIL)

    return (True,cur.lastrowid)

def deleteUser(cur,conn,cognito_id):#B
    VALUES=(USER_TABLE_NAME,cognito_id)
    STATE="DELETE FROM  %s WHERE cognito_id='%s'"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        return (False,ERROR_DELETE_USER_FAIL)

    return (True,cur.lastrowid)

def changeUserInfo(cur,conn,cognito_id,name,vip_level=0):#B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    VALUES=(USER_TABLE_NAME,name,vip_level,user_id)
    STATE="UPDATE %s SET name='%s',vip_level=%d WHERE user_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        return (False,ERROR_USER_INFO_CHANGE_FAIL)

    return (True,0)

#===========================================================================

def checkIfDevOccupiedByBaby(cur,user_dev_pair_id):#A #B
    STATE="SELECT map_id FROM %s WHERE du_map_id='%s' LIMIT 1"%(DEV_BABY_MAP_TABLE_NAME,user_dev_pair_id)

    try:
        cur.execute(STATE)
        res = cur.fetchone()
    except:
        return (False,ERROR_READ_DEV_BABY_MAP_INFO_FAIL)

    if(res==None or len(res)==0):
        return (True,False)

    return (True,True)

def getPairIdAndDevUdidListOfBabyByBabyId(cur,baby_id):#A #B
    VALUES=(DEV_TABLE_NAME,DEV_USER_MAP_TABLE_NAME,DEV_BABY_MAP_TABLE_NAME,baby_id)
    STATE="SELECT dbm.du_map_id,d.udid FROM %s AS d JOIN %s AS dum ON d.dev_id=dum.dev_id JOIN %s AS dbm ON dum.map_id=dbm.du_map_id AND dbm.baby_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchall()
    except:
        return (False,ERROR_READ_DEV_BABY_MAP_INFO_FAIL)

    if(res==None or len(res)==0):
        return (True,[])

    return (True,res)

def getDevUdidListOfBaby(cur,cognito_id,bn):#B
    res=getBabyByCognitoIdAndName(cur,cognito_id,bn)

    if(res[0]==False):
        return res

    baby_id=res[1][0]

    res=getPairIdAndDevUdidListOfBabyByBabyId(cur,baby_id)

    if(res[0]==False):
        return res

    id_list=[]
    for item in res[1]:
        id_list.append(item[1])

    return (True,id_list)

def deleteBabyDevPair(cur,conn,cognito_id,bn,udid):#B
    res=getUserIdAndBabyId(cur,cognito_id,bn)
    
    if(res[0]==False):
        return res

    user_id=res[1][0]
    baby_id=res[1][1]

    res=checkIfUserHasThisDev(cur,user_id,udid)

    if(res[0]==False):
        return res
    
    pair_id=res[1]

    return deleteBabyDevPairByPairId(cur,conn,pair_id,baby_id)

def deleteBabyDevPairByPairId(cur,conn,pair_id,baby_id):#A #B
    VALUES=(DEV_BABY_MAP_TABLE_NAME,pair_id,baby_id)
    STATE="DELETE FROM  %s WHERE du_map_id=%d AND baby_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        return (False,ERROR_DELETE_DEV_BABY_MAP_INFO_FAIL)

    return (True,pair_id)
    

def deleteBabyDevPairAll(cur,conn,baby_id):
    VALUES=(DEV_BABY_MAP_TABLE_NAME,baby_id)
    STATE="DELETE FROM  %s WHERE baby_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        return (False,ERROR_DELETE_DEV_BABY_MAP_INFO_FAIL)

    return (True,-1)

def addBabyDevPairByDevUserMapId(cur,conn,baby_id,du_map_id):#A #B
    VALUES=(DEV_BABY_MAP_TABLE_NAME,baby_id,du_map_id)
    STATE="INSERT INTO %s (baby_id,du_map_id,ts) values (%d,%d,CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER))"%VALUES
    
    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_INSERT_DEV_BABY_MAP_INFO_FAIL)
        
    return (True,cur.lastrowid)

#===========================================================================

def deleteAllStaPairByUserId(cur,conn,user_id):#b1
    VALUES=(STA_USER_MAP_TABLE_NAME,user_id)
    STATE="DELETE FROM  %s WHERE user_id=%d"%VALUES

    try:
        cur.execute(STATE)
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_DELETE_STA_USER_MAP_INFO_FAIL)

    return (True,0)

def deleteAllDevPairByUserId(cur,conn,user_id):#b1
    VALUES=(DEV_USER_MAP_TABLE_NAME,user_id)
    STATE="DELETE FROM  %s WHERE user_id=%d"%VALUES

    try:
        cur.execute(STATE)
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_DELETE_DEV_USER_MAP_INFO_FAIL)

    return (True,0)

def deleteAllDevPairByBabyId(cur,conn,baby_id):#b2
    VALUES=(DEV_BABY_MAP_TABLE_NAME,baby_id)
    STATE="DELETE FROM  %s WHERE baby_id=%d"%VALUES

    try:
        cur.execute(STATE)
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_DELETE_DEV_BABY_MAP_INFO_FAIL)

    return (True,0)

def deleteAllStaPair(cur,conn,cognito_id):#B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    return deleteAllStaPairByUserId(cur,conn,user_id)

def deleteStaPairById(cur,conn,user_id,sta_id):#A #B
    VALUES=(STA_USER_MAP_TABLE_NAME,sta_id,user_id)
    STATE="DELETE FROM  %s WHERE sta_id=%d AND user_id=%d"%VALUES

    try:
        cur.execute(STATE)
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_DELETE_EVENT_FAIL)

    return (True,0)

def deleteStaPair(cur,conn,cognito_id,udid):#B
    res=getStaIdByStaUdid(cur,udid)

    if(res[0]==False):
        return res

    sta_id=res[1]

    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    return deleteStaPairById(cur,conn,user_id,sta_id)



def deleteAllDevPair(cur,conn,cognito_id):#B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    return deleteAllDevPairByUserId(cur,conn,user_id)

def deleteDevPair(cur,conn,cognito_id,udid):#B
    res=getDevIdByUdid(cur,udid)

    if(res[0]==False):
        return res

    dev_id=res[1]

    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    return deleteDevPairById(cur,conn,user_id,dev_id)

def deleteDevPairById(cur,conn,user_id,dev_id):#A #B
    VALUES=(DEV_USER_MAP_TABLE_NAME,dev_id,user_id)
    STATE="DELETE FROM  %s WHERE dev_id=%d AND user_id=%d"%VALUES

    try:
        cur.execute(STATE)
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_DELETE_EVENT_FAIL)

    return (True,0)

#===========================================================================

def getPairedDevMapIdByUdidList(cur,user_id,dev_udid_list):#b2
    VALUES=(DEV_USER_MAP_TABLE_NAME,DEV_TABLE_NAME,user_id,','.join(["'%s'"%(udid) for udid in dev_udid_list]))
    STATE="SELECT dum.map_id,d.udid FROM %s AS dum JOIN %s AS d ON dum.dev_id=d.dev_id AND dum.user_id=%d AND d.udid IN (%s) "%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchall()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_DEV_USER_MAP_INFO_FAIL)

    if(res==None or len(res)==0):
        return (True,[])
    if(res[0]==False):
        return res

    id_list=[]
    for item in res:
        id_list.append(item)
    return (True,id_list)

def getDevIdByUdid(cur,dev_udid):#a2
    did=dev_uuid_to_id_cache.get(dev_udid)

    if(did != None):
        return (True,did)

    VALUES=(DEV_TABLE_NAME,dev_udid)
    STATE="SELECT dev_id FROM %s WHERE udid='%s' LIMIT 1"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchall()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_DEV_INFO_FAIL)

    if(res==None or len(res)==0):
        return (False,ERROR_DEV_WITH_THE_UDID_IS_NOT_EXIST)

    did=res[0][0]
    dev_uuid_to_id_cache.set(dev_udid,did)
    return (True,did)

#=========================================================================== 

def checkIfUserHasThisDev(cur,user_id,udid):#A #B
    res=getDevUdidAndPairIdListOfUserByUserId(cur,user_id)

    if(res[0]==False):
        return res
    
    is_udid_belong_to_user=False
    pair_id=-1

    for info in res[1]:
        if(info[0]==udid):
            is_udid_belong_to_user=True
            pair_id=info[1]
            break
  
    if(is_udid_belong_to_user==False):
        return (False,ERROR_USER_DONT_HAVE_THIS_DEV)

    return (True,pair_id)

def pairBabyAndThisDevByBabyId(cur,conn,user_id,baby_id,udid):#A #B

    res=checkIfUserHasThisDev(cur,user_id,udid)

    if(res[0]==False):
        return res
    
    pair_id=res[1]

    res=checkIfDevOccupiedByBaby(cur,pair_id)

    if(res[0]==False):
        return res

    if(res[1]==True):
        return (False,ERROR_DEV_IS_OCCUPIED_BY_OTHER_BABY)
    
    #因為目前一個小孩子只會有一個貼片，因此直接刪除該小孩所有相關貼片
    deleteBabyDevPairAll(cur,conn,baby_id)
    if(res[0]==False):
        return res
    
    #增加貼片
    res=addBabyDevPairByDevUserMapId(cur,conn,baby_id,pair_id)

    if(res[0]==False):
        return res
    
    res=notifyStaScanChangeByUserId(cur,conn,user_id)

    if(res[0]==False):
        return res
    
    return (True,pair_id)

def pairBabyAndThisDev(cur,conn,cognito_id,bn,udid):#B
    res=getUserIdAndBabyId(cur,cognito_id,bn)
    
    if(res[0]==False):
        return res

    user_id=res[1][0]
    baby_id=res[1][1]

    return pairBabyAndThisDevByBabyId(cur,conn,user_id,baby_id,udid)

#=========================================================================== 

def getUserIdAndBabyId(cur,cognito_id,bn):#b1
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    res=getBabyByUserIdAndName(cur,user_id,bn)

    if(res[0]==False):
        return res

    baby_id=res[1][0]

    return (True,(user_id,baby_id))

def getBabyIdAndDevIdByDevUdidThroughCache(cur,udid):#a1
    bid=dev_uuid_to_baby_id_cache.get(udid)
    did=dev_uuid_to_id_cache.get(udid)

    if(did != None and bid != None):
        return (True,(bid,did))

    VALUES=(DEV_BABY_MAP_TABLE_NAME,DEV_USER_MAP_TABLE_NAME,DEV_TABLE_NAME,udid)
    STATE="SELECT dbm.baby_id,d.dev_id FROM %s AS dbm JOIN %s AS dum ON dbm.du_map_id=dum.map_id JOIN %s AS d ON dum.dev_id=d.dev_id AND d.udid='%s' LIMIT 1"%VALUES
    
    try:
        cur.execute(STATE)    
        res=cur.fetchone()
    except:
        return (False,ERROR_READ_DEV_BABY_MAP_INFO_FAIL)

    if(res==None or len(res)==0):
        return res

    dev_uuid_to_baby_id_cache.set(udid,res[0])
    dev_uuid_to_id_cache.set(udid,res[1])
 
    return (True,res)

def addUserDevPairByDevIdWithoutCommit(cur,user_id,dev_id):#a1
    VALUES=(DEV_USER_MAP_TABLE_NAME,user_id,dev_id)
    STATE="INSERT INTO %s (user_id,dev_id,ts) values (%d,%d,CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER))"%VALUES
    
    try:
        cur.execute(STATE)    
    except:
        traceback.print_exc()
        return (False,ERROR_INSERT_DEV_USER_MAP_INFO_FAIL)
        
    return (True,cur.lastrowid)

def addUserStaPairByDevIdWithoutCommit(cur,user_id,dev_id):#a1
    VALUES=(STA_USER_MAP_TABLE_NAME,user_id,dev_id)
    STATE="INSERT INTO %s (user_id,sta_id,ts) values (%d,%d,CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER))"%VALUES
    
    try:
        cur.execute(STATE)    
    except:
        traceback.print_exc()
        return (False,ERROR_INSERT_STA_USER_MAP_INFO_FAIL)
        
    return (True,cur.lastrowid)

def isThisStaValid(cur,dev_udid):#a1
    VALUES=(STA_TABLE_NAME,dev_udid)
    STATE="SELECT sta_id FROM %s WHERE udid='%s' LIMIT 1"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchall()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_STA_INFO_FAIL)

    if(res==None or len(res)==0):
        return (True,False)

    return (True,True)

def filtOccupiedSta(cur,sta_udid_list,user_id):#a1
    VALUES=(STA_TABLE_NAME,STA_USER_MAP_TABLE_NAME,','.join(["'%s'"%(udid) for udid in sta_udid_list]))
    STATE="SELECT sta.udid,map.user_id FROM %s AS sta JOIN %s AS map ON sta.sta_id=map.sta_id WHERE sta.udid IN (%s)"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchall()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_DEV_INFO_FAIL,[])

    if(res==None):
        res=()

    filted_list=list(sta_udid_list)
    paired_list=[]

    for item in res:
        udid=item[0]
        mid=item[1]
        if udid in filted_list:
            if(mid==user_id):
                filted_list.remove(udid)
                paired_list.append(udid)
            else:
                return (False,ERROR_STA_UDID_IS_ALREADY_EXIST,paired_list)

    return (True,filted_list,paired_list)

def filtAssignedDevMapId(cur,dev_map_list,baby_id):#b2
    VALUES=(DEV_BABY_MAP_TABLE_NAME,','.join(["'%d'"%(item[0]) for item in dev_map_list]))
    STATE="SELECT du_map_id,baby_id FROM %s WHERE du_map_id IN (%s)"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchall()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_DEV_INFO_FAIL)

    map_list=[]
    for item in dev_map_list:
        map_list.append(item[0])

    for item in res:
        du_map_id=item[0]
        bid=item[1]
        if du_map_id in map_list:
            if(bid==baby_id):
                map_list.remove(du_map_id)
            else:
                return (False,ERROR_NO_VALID_DEVID)

    filted_list=[]
    for item in dev_map_list:
        if(item[0] in map_list):
            filted_list.append(item)

    return (True,filted_list)

def filtOccupiedDev(cur,dev_udid_list,user_id):#a1
    VALUES=(DEV_TABLE_NAME,DEV_USER_MAP_TABLE_NAME,','.join(["'%s'"%(udid) for udid in dev_udid_list]))
    STATE="SELECT dev.udid,map.user_id,dev.dev_id FROM %s AS dev JOIN %s AS map ON dev.dev_id=map.dev_id AND dev.udid IN (%s)"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchall()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_DEV_INFO_FAIL,[])

    if(res==None):
        res=()

    filted_list=list(dev_udid_list)
    paired_list=[]
        
    for item in res:
        udid=item[0]
        bid=item[1]
        if udid in filted_list:
            if(bid==user_id):
                filted_list.remove(udid)
                paired_list.append(udid)
            else:
                return (False,ERROR_DEV_UDID_IS_ALREADY_EXIST,paired_list)

    return (True,filted_list,paired_list)

def isDevOccupiedByOther(cur,dev_id,user_id):#a1
    VALUES=(DEV_USER_MAP_TABLE_NAME,dev_id)
    STATE="SELECT user_id FROM %s WHERE dev_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchall()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_DEV_INFO_FAIL)

    if(res==None or len(res)==0):
        return (True,False,False)

    already_done=False
    for item in res:
        if(item[0]!=user_id):
            return (True,True,False)
        else:
            already_done=True

    return (True,False,already_done)

def isStaOccupiedByOther(cur,sta_id,user_id):#a1
    VALUES=(STA_USER_MAP_TABLE_NAME,sta_id)
    STATE="SELECT user_id FROM %s WHERE sta_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchall()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_DEV_INFO_FAIL)

    if(res==None or len(res)==0):
        return (True,False,False)

    already_done=False
    for item in res:
        if(item[0]!=user_id):
            return (True,True,False)
        else:
            already_done=True

    return (True,False,already_done)

#==========================================================================

def pairUserAndThisDev(cur,conn,cognito_id,dev_udid):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    res=getDevIdByUdid(cur,dev_udid)
    if(res[0]==False):
        return res

    dev_id=res[1]

    res=isDevOccupiedByOther(cur,dev_id,user_id)
    if(res[0]==False):
        return res
    if(res[1]):
        return (False,ERROR_DEV_IS_OCCUPIED_BY_OTHER)
    if(res[2]):
        return (True,dev_id)

    res=addUserDevPairByDevIdWithoutCommit(cur,user_id,dev_id)
    if(res[0]==False):
        return res

    conn.commit()
    return (True,dev_id)

def getUserDevPair(cur,cognito_id):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    VALUES=(DEV_TABLE_NAME,DEV_USER_MAP_TABLE_NAME,user_id)
    STATE="SELECT d.dev_id,d.udid,d.aes_key,d.aes_iv,d.pcb_ver,d.type,d.mf_ts,usm.ts,usm.map_id FROM %s AS d JOIN %s AS usm ON d.dev_id=usm.dev_id AND usm.user_id=%d ORDER BY d.dev_id ASC"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchall()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_DEV_USER_MAP_INFO_FAIL)

    if(res==None or len(res)==0):
        return (True,[])

    return (True,res)

def getDevUdidAndPairIdListOfUserByUserId(cur,user_id):#A #B
    VALUES=(DEV_TABLE_NAME,DEV_USER_MAP_TABLE_NAME,user_id)
    STATE="SELECT d.udid,dum.map_id FROM %s AS d JOIN %s AS dum ON d.dev_id=dum.dev_id WHERE dum.user_id=%d ORDER BY dum.map_id ASC"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchall()
    except:
        return (False,ERROR_READ_DEV_USER_MAP_INFO_FAIL)

    if(res==None or len(res)==0):
        return (True,[])

    id_list=[]
    for info in res:
        id_list.append([info[0],info[1]])

    return (True,id_list)

def getDevUdidListOfUser(cur,cognito_id):#B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    res=getDevUdidAndPairIdListOfUserByUserId(cur,user_id)

    if(res[0]==False):
        return res

    udid_list=[]
    for item in res[1]:
        udid_list.append(item[0])

    return (True,udid_list)

#==========================================================================

def pairUserAndThisSta(cur,conn,cognito_id,sta_udid):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    res=getStaIdByStaUdid(cur,sta_udid)
    if(res[0]==False):
        return res

    sta_id=res[1]

    res=isStaOccupiedByOther(cur,sta_id,user_id)
    if(res[0]==False):
        return res
    if(res[1]):
        return (False,ERROR_STA_IS_OCCUPIED_BY_OTHER)
    if(res[2]):#already done
        return (True,sta_id)

    res=addUserStaPairByDevIdWithoutCommit(cur,user_id,sta_id)
    if(res[0]==False):
        return res

    conn.commit()
    return (True,sta_id)

def getUserStaPair(cur,cognito_id):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    VALUES=(STA_TABLE_NAME,STA_USER_MAP_TABLE_NAME,user_id)
    STATE="SELECT s.sta_id,s.udid,s.pw,s.pcb_ver,s.type,s.mf_ts,usm.ts FROM %s AS s JOIN %s AS usm ON s.sta_id=usm.sta_id AND usm.user_id=%d ORDER BY s.sta_id ASC"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchall()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_STA_USER_MAP_INFO_FAIL)

    if(res==None or len(res)==0):
        return (True,[])

    return (True,res)

def getStaUdidListOfUser(cur,cognito_id):#B
    res=getUserStaPair(cur,cognito_id)

    if(res[0]==False):
        return res

    id_list=[]
    for info in res[1]:
        id_list.append(info[1])

    return (True,id_list)

#==========================================================================
    
def checkEventExist(cur,dev_id,baby_id,type,ts_ms):#a1
    #SELECT EXISTS(SELECT * FROM evt WHERE dev_id=1 AND baby_id=328 AND type=2 AND rec_ts=1634611101378);
    
    VALUES=(EVT_TABLE_NAME,dev_id,baby_id,type,ts_ms)
    STATE="SELECT EXISTS(SELECT * FROM %s WHERE dev_id=%d AND baby_id=%d AND type=%d AND rec_ts=%d)"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchone()
    except:
        traceback.print_exc()
        return (False,ERROR_EVENT_INSERT_FAIL)

    if(res[0]==1):
        return (True,True)
    else:
        return (True,False)

def addEventByDevUdid(cur,conn,dev_udid,type,ts_ms):#A #B
    res=getBabyIdAndDevIdByDevUdidThroughCache(cur,dev_udid)
    if(res==None):
        return (False,ERROR_NO_RECORD_WITH_THE_DEVID)
    if(res[0]==False):
        return res

    baby_id=res[1][0]
    dev_id=res[1][1]

    #res=checkEventExist(cur,dev_id,baby_id,type,ts_ms)
    #if(res==None):
    #    return (False,ERROR_NO_RECORD_WITH_THE_DEVID)
    #if(res[0]==False):
    #    return res
    res=(True,False)

    if(res[1]==False):
        VALUES=(EVT_TABLE_NAME,dev_id,baby_id,type,ts_ms)
        STATE="INSERT INTO %s (dev_id,baby_id,type,rec_ts,aws_ts) values (%d,%d,%d,%d,CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER))"%VALUES

        try:
            cur.execute(STATE)    
            conn.commit()
        except:
            traceback.print_exc()
            return (False,ERROR_EVENT_INSERT_FAIL,baby_id)
        return (True,cur.lastrowid,baby_id)
    else:
        return (False,ERROR_EVENT_ALEADY_EXIST,baby_id)

def addRangeEvtByDevUdid(cur,conn,dev_udid,rt,bts,ets,gauge):#A #B
    res=getBabyIdAndDevIdByDevUdidThroughCache(cur,dev_udid)
    if(res==None):
        return (False,ERROR_NO_RECORD_WITH_THE_DEVID)
    if(res[0]==False):
        return res

    baby_id=res[1][0]

    return addRangeEvtByBabyId(cur,conn,baby_id,rt,bts,ets,gauge)

def addManualEventByBabyId(cur,conn,baby_id,type,ts_ms):#A #B
    VALUES=(EVT_TABLE_NAME,manual_dev_idx,baby_id,type,ts_ms)
    STATE="INSERT INTO %s (dev_id,baby_id,type,rec_ts,aws_ts) values (%d,%d,%d,%d,CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER))"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_EVENT_INSERT_FAIL)
    return (True,cur.lastrowid)

#==========================================================================

def getEventListByBabyId(cur,baby_id,bts,ets):#A #B
    LIMIT=1000
    STATE="SELECT evt_id,rec_ts,type,aws_ts,del FROM %s WHERE baby_id=%d AND aws_ts BETWEEN %d AND %d LIMIT %d"%(EVT_TABLE_NAME,baby_id,bts,ets,LIMIT)

    try:
        cur.execute(STATE)
        res = cur.fetchall()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_EVENT_INFO_FAIL)

    len_res=len(res)
    res=list(res)

    if(len_res>0):
        last_evt=res[-1]
        ets=last_evt[-2]
    else:
        #no data
        ets=bts

    return (True,bts,ets,res)

def updateEventByBabyIdAndEvtId(cur,conn,baby_id,evt_id,ts,type):#A #B
    
    VALUES=(EVT_TABLE_NAME,ts,type,baby_id,evt_id)
    STATE="UPDATE %s SET rec_ts=%d,type=%d,aws_ts=CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER) WHERE baby_id=%d AND evt_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        return (False,ERROR_EVENT_CHANGE_FAIL)

    return (True,evt_id)

def getEventList(cur,cognito_id,bn,bts,ets):#B
    res=getBabyByCognitoIdAndName(cur,cognito_id,bn)
    if(res==None):
        return ERROR_BABY_WIHT_THE_NAME_NOT_EXIST
    if(res[0]==False):
        return res

    baby_id=res[1][0]

    return getEventListByBabyId(cur,baby_id,bts,ets)
    
def deleteEventByBabyIdAndEvtId(cur,conn,baby_id,evt_id):#A #B
    #VALUES=(EVT_TABLE_NAME,baby_id,evt_id)
    #STATE="DELETE FROM  %s WHERE baby_id=%d AND evt_id=%d"%VALUES
    VALUES=(EVT_TABLE_NAME,baby_id,evt_id)
    STATE="UPDATE %s SET aws_ts=CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER),del=1 WHERE baby_id=%d AND evt_id=%d"%VALUES

    try:
        cur.execute(STATE)
        res = cur.fetchall()
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_DELETE_EVENT_FAIL)

    return (True,evt_id)    

#==========================================================================

def getFoodByFoodIdFast(cur,food_id):#a1
    VALUES=(FOOD_TABLE_NAME,food_id)
    STATE="SELECT food_id,name,description,type,unit FROM %s WHERE food_id=%d LIMIT 1"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchone()
    except:
        return (False,ERROR_READ_FOOD_INFO_FAIL)
        
    if(res==None or len(res)==0):
        return (True,None)

    return (True,res)

def getFoodByFoodId(cur,cognito_id,food_id):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    VALUES=(FOOD_TABLE_NAME,food_id,user_id)
    STATE="SELECT food_id,name,description,type,unit FROM %s WHERE food_id=%d AND user_id=%d ORDER BY food_id ASC"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchone()
    except:
        return (False,ERROR_READ_FOOD_INFO_FAIL)
        
    if(res==None or len(res)==0):
        return (True,[])

    return (True,res)

def getFoodByUserIdAndFoodName(cur,user_id,name):#a1
    VALUES=(FOOD_TABLE_NAME,user_id,name)
    STATE="SELECT food_id,name,description,type,unit FROM %s WHERE user_id=%d AND name='%s' LIMIT 1"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchone()
    except:
        return (False,ERROR_READ_FOOD_INFO_FAIL)
        
    if(res==None or len(res)==0):
        return (True,None)

    return (True,res)

def getFoodListByUserId(cur,user_id):#a1
    VALUES=(FOOD_TABLE_NAME,user_id)
    STATE="SELECT food_id,name,description,type,unit FROM %s WHERE user_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchall()
    except:
        return (False,ERROR_READ_FOOD_INFO_FAIL)
        
    if(res==None or len(res)==0):
        return (True,[])

    return (True,res)

def getFoodList(cur,cognito_id):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]
    return getFoodListByUserId(cur,user_id)

def addFoodByUserId(cur,conn,user_id,name,desc,ft,unit):#a1
    VALUES=(FOOD_TABLE_NAME,user_id,name,desc,ft,unit)
    STATE="INSERT INTO %s (user_id,name,description,type,unit) values (%d,'%s','%s',%d,'%s')"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        return (False,ERROR_FOOD_INSERT_FAIL)

    return (True,cur.lastrowid)
    
def addFood(cur,conn,cognito_id,name,desc,ft,unit):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    res=getFoodByUserIdAndFoodName(cur,user_id,name)
    if(res[0]==False):
        return res

    if(res[1] is not None):
        return (False,ERROR_FOOD_NAME_IS_ALREADY_EXIST)

    return addFoodByUserId(cur,conn,user_id,name,desc,ft,unit)

def updateFoodByFoodId(cur,conn,cognito_id,food_id,new_name,desc,ft,unit):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    res=getFoodByFoodIdFast(cur,food_id)

    if(res[0]==False):
        return res

    if(res[1]==None):
        return (False,ERROR_FOOD_IS_NOT_EXIST)
    
    old_name=res[1][1]
    if(old_name != new_name):
        res=getFoodByUserIdAndFoodName(cur,user_id,new_name)

        if(res[0]==False):
            return res

        if(res[1] is not None):
            return (False,ERROR_FOOD_NEW_NAME_IS_ALREADY_EXIST)

    VALUES=(FOOD_TABLE_NAME,new_name,desc,ft,unit,user_id,food_id)
    STATE="UPDATE %s SET name='%s',description='%s',type=%d,unit='%s' WHERE user_id=%d AND food_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        return (False,ERROR_FOOD_INSERT_FAIL)

    return (True,food_id)

def updateFood(cur,conn,cognito_id,name,new_name,desc,ft,unit):#B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    res=getFoodByUserIdAndFoodName(cur,user_id,name)

    if(res[0]==False):
        return res

    if(res[1] is None):
        return (False,ERROR_FOOD_IS_NOT_EXIST)

    food_id=res[1][0]

    return updateFoodByFoodId(cur,conn,cognito_id,food_id,new_name,desc,ft,unit)

def deleteFoodByFoodId(cur,conn,user_id,food_id):#A #B
    VALUES=(FOOD_TABLE_NAME,user_id,food_id)
    STATE="DELETE FROM  %s WHERE user_id=%d AND food_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_FOOD_DELETE_FAIL)

    return (True,food_id)

def deleteFood(cur,conn,cognito_id,name):#B
    res=getUserIdByCognitoId(cur,cognito_id)
    if(res==None):
        return (False,ERROR_USER_WIHT_THE_SAME_COGNITOID_NOT_EXIST)
    if(res[0]==False):
        return res

    user_id=res[1]

    res=getFoodByUserIdAndFoodName(cur,user_id,name)

    if(res[0]==False):
        return res

    if(res[1] is None):
        return (False,ERROR_FOOD_IS_NOT_EXIST)

    food_id=res[1][0]

    return deleteFoodByFoodId(cur,conn,user_id,food_id)
    
#==========================================================================

def getFeedEvtListByBabyId(cur,baby_id,bts,ets):#A #B
    LIMIT=1000
    VALUES=(FEED_EVT_TABLE_NAME,baby_id,bts,ets,LIMIT)
    STATE="SELECT feed_id,food_id,bts,ets,quantity,aws_ts,del FROM %s WHERE baby_id=%d AND aws_ts BETWEEN %d AND %d LIMIT %d"%VALUES

    try:
        cur.execute(STATE)
        res = cur.fetchall()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_FEED_INFO_FAIL)

    len_res=len(res)
    res=list(res)

    if(len_res>0):
        last_evt=res[-1]
        ets=last_evt[-2]
    else:
        #no data
        ets=bts

    return (True,bts,ets,res)

def checkFeedEventExist(cur,baby_id,food_id,bts):#a1
    VALUES=(FEED_EVT_TABLE_NAME,baby_id,food_id,bts)
    STATE="SELECT EXISTS(SELECT * FROM %s WHERE baby_id=%d AND food_id=%d AND bts=%d)"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchone()
    except:
        traceback.print_exc()
        return (False,ERROR_EVENT_INSERT_FAIL)

    if(res[0]==1):
        return (True,True)
    else:
        return (True,False)

def addFeedEvtByBabyId(cur,conn,baby_id,food_id,bts,ets,quantity):#A #B
    #res=checkFeedEventExist(cur,baby_id,food_id,bts)
    #if(res==None):
    #    return (False,ERROR_NO_RECORD_WITH_THE_DEVID)
    #if(res[0]==False):
    #    return res
    res=(True,False)

    if(res[1]==False):
        VALUES=(FEED_EVT_TABLE_NAME,baby_id,food_id,bts,ets,quantity)
        STATE="INSERT INTO %s (baby_id,food_id,bts,ets,quantity,aws_ts) values (%d,%d,%d,%d,%d,CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER))"%VALUES

        try:
            cur.execute(STATE)    
            conn.commit()
        except:
            return (False,ERROR_FEED_INSERT_FAIL)
        return (True,cur.lastrowid)
    else:
        return (False,ERROR_FEED_ALEADY_EXIST)

def updateFeedEvtByEvtId(cur,conn,baby_id,evt_id,food_id,bts,ets,quantity):#A #B
    VALUES=(FEED_EVT_TABLE_NAME,food_id,bts,ets,quantity,evt_id,baby_id)
    STATE="UPDATE %s SET food_id=%d,bts=%d,ets=%d,quantity=%d,aws_ts=CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER) WHERE feed_id=%d AND baby_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        return (False,ERROR_FEED_UPDATE_FAIL)

    return (True,evt_id)

def deleteFeedEvtByEvtId(cur,conn,baby_id,feed_id):#A #B
    VALUES=(FEED_EVT_TABLE_NAME,feed_id,baby_id)
    STATE="UPDATE %s SET aws_ts=CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER),del=1 WHERE feed_id=%d AND baby_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_FEED_DELETE_FAIL)

    return (True,feed_id)

#==========================================================================

def getRangeEvtListByBabyId(cur,baby_id,bts,ets):#A #B
    LIMIT=1000
    VALUES=(RANGE_EVT_TABLE_NAME,baby_id,bts,ets,LIMIT)
    STATE="SELECT revt_id,type,bts,ets,gauge,aws_ts,del FROM %s WHERE baby_id=%d AND aws_ts BETWEEN %d AND %d LIMIT %d"%VALUES

    try:
        cur.execute(STATE)
        res = cur.fetchall()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_REVT_INFO_FAIL)

    len_res=len(res)
    res=list(res)

    if(len_res>0):
        last_evt=res[-1]
        ets=last_evt[-2]
    else:
        ets=bts

    return (True,bts,ets,res)

def checkRangeEventExist(cur,baby_id,rt,bts):#a1
    VALUES=(RANGE_EVT_TABLE_NAME,baby_id,rt,bts)
    STATE="SELECT EXISTS(SELECT * FROM %s WHERE baby_id=%d AND type=%d AND bts=%d)"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchone()
    except:
        traceback.print_exc()
        return (False,ERROR_EVENT_INSERT_FAIL)

    if(res[0]==1):
        return (True,True)
    else:
        return (True,False)

def addRangeEvtByBabyId(cur,conn,baby_id,rt,bts,ets,gauge):#A #B
    '''
    res=checkRangeEventExist(cur,baby_id,rt,bts)
    if(res==None):
        return (False,ERROR_NO_RECORD_WITH_THE_DEVID)
    if(res[0]==False):
        return res
    '''
    res=(True,False)

    if(res[1]==False):
        VALUES=(RANGE_EVT_TABLE_NAME,baby_id,rt,bts,ets,gauge)
        STATE="INSERT INTO %s (baby_id,type,bts,ets,gauge,aws_ts) values (%d,%d,%d,%d,%d,CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER))"%VALUES

        try:
            cur.execute(STATE)    
            conn.commit()
        except:
            traceback.print_exc()
            return (False,ERROR_REVT_INSERT_FAIL)
        return (True,cur.lastrowid)
    else:
        return (False,ERROR_REVT_ALEADY_EXIST)
    
def updateRangevtByEvtId(cur,conn,baby_id,evt_id,rt,bts,ets,gauge):#A #B
    VALUES=(RANGE_EVT_TABLE_NAME,rt,bts,ets,gauge,baby_id,evt_id)
    STATE="UPDATE %s SET type=%d,bts=%d,ets=%d,gauge=%d,aws_ts=CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER) WHERE baby_id=%d AND revt_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_REVT_UPDATE_FAIL)

    return (True,evt_id)

def deleteRangeEvtByEvtId(cur,conn,baby_id,revt_id):#A #B
    #VALUES=(RANGE_EVT_TABLE_NAME,baby_id,revt_id)
    #STATE="DELETE FROM  %s WHERE baby_id=%d AND revt_id=%d"%VALUES
    VALUES=(RANGE_EVT_TABLE_NAME,baby_id,revt_id)
    STATE="UPDATE %s SET aws_ts=CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER),del=1 WHERE baby_id=%d AND revt_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_REVT_DELETE_FAIL)

    return (True,revt_id)

#==========================================================================

def checkMp3ExistSlot(cur,user_id,slot):#a1
    VALUES=(MP3_TABLE_NAME,user_id,slot)
    STATE="SELECT EXISTS(SELECT mp3_id FROM %s WHERE user_id=%d AND slot_id=%d)"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchone()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_MP3_INFO_FAIL)

    if(res[0]==1):
        return (True,True)
    else:
        return (True,False)
        
def getGeneralMp3Content(slot):#a1
    try:
        bio=io.BytesIO()
        s3_path='mp3/g%d.mp3'%(slot)
        s3.download_fileobj(S3_BUCKET,s3_path, bio)
    except:
        #traceback.print_exc()
        return (False,None)

    bio.seek(0)
    return (True,bio.read())

def getMp3Content(cognito_id,slot):#a1
    try:
        bio=io.BytesIO()
        s3_path='mp3/%s_slot%d.mp3'%(cognito_id,slot)
        s3.download_fileobj(S3_BUCKET,s3_path, bio)
    except:
        #traceback.print_exc()
        return (False,None)

    bio.seek(0)
    return (True,bio.read())

def getMp3Base64(cognito_id,slot):#A #B
    res=getMp3Content(cognito_id,slot)
    if(res[0]==False):
        return res

    bin=res[1]
    encoded = base64.b64encode(bin)
    return (True,encoded.decode())
    
def addMp3(cur,conn,cognito_id,slot,bin):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    res=checkMp3ExistSlot(cur,user_id,slot)
    if(res[0]!=True):
        return res

    if(res[1]):
        VALUES=(MP3_TABLE_NAME,user_id,slot)
        STATE="UPDATE %s SET aws_ts=CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER),del=0 WHERE user_id=%d AND slot_id=%d"%VALUES

    else:
        VALUES=(MP3_TABLE_NAME,user_id,slot)
        STATE="INSERT INTO %s (user_id,slot_id,aws_ts,del) values (%d,%d,CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER),0)"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_MP3_ADD_FAIL)

    idx=cur.lastrowid

    try:
        bio=io.BytesIO(bin)
        s3.upload_fileobj(bio,S3_BUCKET, 'mp3/%s_slot%d.mp3'%(cognito_id,slot))
    except:
        #if s3 fail, remove record
        VALUES=(MP3_TABLE_NAME,idx)
        STATE="DELETE FROM  %s WHERE mp3_id='%d'"%VALUES

        try:
            cur.execute(STATE)    
            conn.commit()
        except:
            traceback.print_exc()

        return (False,ERROR_MP3_ADD_FAIL)

    return (True,cur.lastrowid)

def listMp3(cur,cognito_id):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    VALUES=(MP3_TABLE_NAME,user_id)
    STATE="SELECT user_id,slot_id,aws_ts,del FROM %s WHERE user_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchall()
    except:
        return (False,ERROR_READ_MP3_INFO_FAIL)
        
    if(res==None or len(res)==0):
        return (True,[])

    return (True,res)

def delMp3(cur,conn,cognito_id,slot):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    res=checkMp3ExistSlot(cur,user_id,slot)
    if(res[0]!=True):
        return res

    if(res[1]):
        VALUES=(MP3_TABLE_NAME,user_id,slot)
        STATE="UPDATE %s SET aws_ts=CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER),del=1 WHERE user_id=%d AND slot_id=%d"%VALUES

        try:
            cur.execute(STATE)    
            conn.commit()
        except:
            traceback.print_exc()
            return (False,ERROR_MP3_ADD_FAIL)

        return (True,cur.lastrowid)

    else:
        return (True,-1)

def getMp3ListBelongToSta(cur,sta_udid):#A #B
    VALUES=(MP3_TABLE_NAME,STA_USER_MAP_TABLE_NAME,STA_TABLE_NAME,sta_udid)
    STATE='SELECT a.slot_id,a.aws_ts,a.del FROM %s as a '\
        'JOIN %s as b ON a.user_id=b.user_id '\
        'JOIN %s as c ON b.sta_id=c.sta_id '\
        'WHERE c.udid="%s"'%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchall()
    except:
        return (False,ERROR_READ_MP3_INFO_FAIL)
        
    if(res==None or len(res)==0):
        return (True,[])

    return (True,res)

def getMp3BelongToSta(cur,sta_udid,slot):#A #B
    VALUES=(USER_TABLE_NAME,STA_USER_MAP_TABLE_NAME,STA_TABLE_NAME,sta_udid)
    STATE='SELECT a.cognito_id FROM %s as a '\
        'JOIN %s as b ON a.user_id=b.user_id '\
        'JOIN %s as c ON b.sta_id=c.sta_id '\
        'WHERE c.udid="%s"'%VALUES

    try:
        cur.execute(STATE)    
        res=cur.fetchone()
    except:
        return (False,ERROR_READ_MP3_INFO_FAIL)
        
    if(res==None or len(res)==0):
        return (True,[])

    cognito_id=res[0]
    return getMp3Content(cognito_id,slot)

def updateUserCfg(cur,conn,cognito_id,json_str):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    try:
        bio=io.BytesIO(json_str.encode('utf-8'))
        s3.upload_fileobj(bio,S3_BUCKET, 'user_cfg/%s_cfg.txt'%(cognito_id))
    except:
        return (False,ERROR_CFG_ADD_FAIL)

    VALUES=(USER_TABLE_NAME,user_id)
    STATE="UPDATE %s SET cfg_ts=CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER) WHERE user_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_CFG_ADD_FAIL)

    return (True,cur.lastrowid)

def getUserCfgContent(cognito_id):#A #B
    try:
        bio=io.BytesIO()
        s3_path='user_cfg/%s_cfg.txt'%(cognito_id)
        s3.download_fileobj(S3_BUCKET,s3_path, bio)
    except:
        #traceback.print_exc()
        return (False,ERROR_READ_CFG_FAIL)

    bio.seek(0)
    return (True,bio.read().decode('utf-8'))
    

def updateUserPhoto(cur,conn,cognito_id,bin):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    try:
        bio=io.BytesIO(bin)
        s3.upload_fileobj(bio,S3_BUCKET, 'user_photo/%s_photo.jpg'%(cognito_id))
    except:
        return (False,ERROR_PHOTO_ADD_FAIL)

    VALUES=(USER_TABLE_NAME,user_id)
    STATE="UPDATE %s SET photo_ts=CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER) WHERE user_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_PHOTO_ADD_FAIL)

    return (True,cur.lastrowid)


def getUserPhotoContent(cognito_id):#a1
    try:
        bio=io.BytesIO()
        s3_path='user_photo/%s_photo.jpg'%(cognito_id)
        s3.download_fileobj(S3_BUCKET,s3_path, bio)
    except:
        #traceback.print_exc()
        return (False,ERROR_READ_PHOTO_FAIL)

    bio.seek(0)
    return (True,bio.read())

def getUserPhotoBase64(cognito_id):#A #B
    res=getUserPhotoContent(cognito_id)
    if(res[0]==False):
        return res

    bin=res[1]
    encoded = base64.b64encode(bin)
    return (True,encoded.decode())

def updateBabyPhoto(cur,conn,cognito_id,bid,bin):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    try:
        bio=io.BytesIO(bin)
        s3.upload_fileobj(bio,S3_BUCKET, 'baby_photo/%s_baby_%d_photo.jpg'%(cognito_id,bid))
    except:
        return (False,ERROR_PHOTO_ADD_FAIL)

    VALUES=(BABY_TABLE_NAME,user_id,bid)
    STATE="UPDATE %s SET photo_ts=CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER) WHERE user_id=%d AND baby_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_PHOTO_ADD_FAIL)

    return (True,cur.lastrowid)

def getBabyPhotoContent(cognito_id,bid):#a1
    try:
        bio=io.BytesIO()
        s3_path='baby_photo/%s_baby_%d_photo.jpg'%(cognito_id,bid)
        s3.download_fileobj(S3_BUCKET,s3_path, bio)
    except:
        #traceback.print_exc()
        return (False,ERROR_READ_PHOTO_FAIL)

    bio.seek(0)
    return (True,bio.read())

def getBabyPhotoBase64(cognito_id,bid):#A #B
    res=getBabyPhotoContent(cognito_id,bid)
    if(res[0]==False):
        return res

    bin=res[1]
    encoded = base64.b64encode(bin)
    return (True,encoded.decode())



def updateBabyCfg(cur,conn,cognito_id,bid,json_str):#A #B
    res=getUserIdByCognitoId(cur,cognito_id)

    if(res[0]==False):
        return res

    user_id=res[1]

    try:
        bio=io.BytesIO(json_str.encode('utf-8'))
        s3.upload_fileobj(bio,S3_BUCKET, 'baby_cfg/%s_baby_%d_cfg.txt'%(cognito_id,bid))
    except:
        return (False,ERROR_CFG_ADD_FAIL)

    VALUES=(BABY_TABLE_NAME,user_id,bid)
    STATE="UPDATE %s SET cfg_ts=CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER) WHERE user_id=%d AND baby_id=%d"%VALUES

    try:
        cur.execute(STATE)    
        conn.commit()
    except:
        traceback.print_exc()
        return (False,ERROR_CFG_ADD_FAIL)

    return (True,cur.lastrowid)

def getBabyCfgContent(cognito_id,bid):#a1
    try:
        bio=io.BytesIO()
        s3_path='baby_cfg/%s_baby_%d_cfg.txt'%(cognito_id,bid)
        s3.download_fileobj(S3_BUCKET,s3_path, bio)
    except:
        #traceback.print_exc()
        return (False,ERROR_READ_CFG_FAIL)

    bio.seek(0)
    return (True,bio.read().decode('utf-8'))

def getBabyBidAndBirthdayByDevId(cur,cognito_id,did):
    VALUES=(BABY_TABLE_NAME,DEV_BABY_MAP_TABLE_NAME,DEV_USER_MAP_TABLE_NAME,did)
    STATE='SELECT a.baby_id,a.birthday FROM %s as a '\
        'JOIN %s as b ON a.baby_id=b.baby_id '\
        'JOIN %s as c ON b.du_map_id=c.map_id '\
        'AND c.dev_id=%d'%VALUES

    try:
        cur.execute(STATE)
        res = cur.fetchone()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_BABY_INFO_FAIL)

    if(res==None):
        return (True,None)

    return (True,res)

def getBabyCfgContentByDevId(cur,cognito_id,did):
    VALUES=(BABY_TABLE_NAME,DEV_BABY_MAP_TABLE_NAME,DEV_USER_MAP_TABLE_NAME,did)
    STATE='SELECT a.baby_id FROM %s as a '\
        'JOIN %s as b ON a.baby_id=b.baby_id '\
        'JOIN %s as c ON b.du_map_id=c.map_id '\
        'AND c.dev_id=%d'%VALUES

    try:
        cur.execute(STATE)
        res = cur.fetchone()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_BABY_INFO_FAIL)

    if(res==None):
        return (True,None)

    bid=res[0]
    return getBabyCfgContent(cognito_id,bid)

#==========================================================================

def addTrendByDevUdid(cur,conn,dev_udid,hr,rr,bs,sleep,imu_tmp,env_tmp,bat_level,baby_status):#A #B
    res=getBabyIdAndDevIdByDevUdidThroughCache(cur,dev_udid)
    if(res==None):
        return (False,ERROR_NO_RECORD_WITH_THE_DEVID)
    if(res[0]==False):
        return res

    baby_id=res[1][0]
    dev_id=res[1][1]

    #res=checkEventExist(cur,dev_id,baby_id,type,ts_ms)
    #if(res==None):
    #    return (False,ERROR_NO_RECORD_WITH_THE_DEVID)
    #if(res[0]==False):
    #    return res
    res=(True,False)

    if(res[1]==False):
        VALUES=(TREND_TABLE_NAME,baby_id,hr,rr,bs,sleep,imu_tmp,env_tmp,bat_level,baby_status)
        STATE="INSERT INTO %s (baby_id,hr,rr,bs,sleep,imu_tmp,env_tmp,bat_level,baby_status,aws_ts) values (%d,%d,%d,%d,%d,%f,%f,%d,%d,CAST(1000*UNIX_TIMESTAMP(current_timestamp(3)) AS UNSIGNED INTEGER))"%VALUES

        try:
            cur.execute(STATE)    
            conn.commit()
        except:
            traceback.print_exc()
            return (False,ERROR_TREND_INSERT_FAIL)
        return (True,cur.lastrowid)
    else:
        return (False,ERROR_TREND_ALEADY_EXIST)


def getTrendListByBabyId(cur,baby_id,bts,ets):
    LIMIT=1000
    STATE="SELECT trend_id,hr,rr,bs,sleep,imu_tmp,env_tmp,bat_level,baby_status,aws_ts FROM %s WHERE baby_id=%d AND aws_ts BETWEEN %d AND %d LIMIT %d"%(TREND_TABLE_NAME,baby_id,bts,ets,LIMIT)

    try:
        cur.execute(STATE)
        res = cur.fetchall()
    except:
        traceback.print_exc()
        return (False,ERROR_READ_TREND_INFO_FAIL)

    len_res=len(res)
    res=list(res)

    if(len_res>0):
        last_evt=res[-1]
        ets=last_evt[-1]
    else:
        #no data
        ets=bts

    return (True,bts,ets,res)

#==========================================================================

def getStaCfgContent(cognito_id):
    try:
        bio=io.BytesIO()
        s3_path='sta_cfg/%s_sta_cfg.txt'%(cognito_id)
        s3.download_fileobj(S3_BUCKET,s3_path, bio)
    except:
        #traceback.print_exc()
        #return (False,ERROR_READ_CFG_FAIL)
        return (True,"{}")#20230920，對於尚未設定cfg的情況，給予空Map

    bio.seek(0)
    return (True,bio.read().decode('utf-8'))

def updateStaCfg(cur,conn,cognito_id,json_str):
    try:
        bio=io.BytesIO(json_str.encode('utf-8'))
        s3.upload_fileobj(bio,S3_BUCKET, 'sta_cfg/%s_sta_cfg.txt'%(cognito_id))
    except:
        return (False,ERROR_CFG_ADD_FAIL)

    return (True,cur.lastrowid)

#==========================================================================

def getTagCfgContent(cognito_id,udid):
    try:
        bio=io.BytesIO()
        s3_path='tag_cfg/%s_%s_tag_cfg.txt'%(cognito_id,udid)
        s3.download_fileobj(S3_BUCKET,s3_path, bio)
    except:
        #traceback.print_exc()
        return (False,ERROR_READ_CFG_FAIL)

    bio.seek(0)
    return (True,bio.read().decode('utf-8'))

def updateTagCfg(cur,conn,cognito_id,udid,json_str):
    try:
        bio=io.BytesIO(json_str.encode('utf-8'))
        s3.upload_fileobj(bio,S3_BUCKET, 'tag_cfg/%s_%s_tag_cfg.txt'%(cognito_id,udid))
    except:
        return (False,ERROR_CFG_ADD_FAIL)

    return (True,cur.lastrowid)


#==========================================================================

def saveOddSnd(cur,conn,cognito_id,dev_udid,ts,ba):
    try:
        bio=io.BytesIO(ba)
        s3.upload_fileobj(bio,S3_BUCKET, 'odd_snd/%s/%s/%d.bin'%(cognito_id,dev_udid,ts))
    except:
        traceback.print_exc()
        return (False,ERROR_ODD_ADD_FAIL)

    return (True,cur.lastrowid)
    
#==========================================================================

def getSysNotifyContent(sys_type,language_code): 
    if(sys_type is not None and language_code is not None):
        s3_path='sys/sys_notify_%s_%s.json'%(sys_type,language_code)
    else:
        s3_path='sys/sys_notify.json'

    try:
        bio=io.BytesIO()
        
        s3.download_fileobj(S3_BUCKET,s3_path, bio)
    except:
        #traceback.print_exc()
        return (False,ERROR_READ_CFG_FAIL)

    bio.seek(0)
    return (True,bio.read().decode('utf-8'))