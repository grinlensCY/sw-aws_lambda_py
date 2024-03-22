import cache_util as CU
import db_cache as DC
import rest_util as RU
import rest_notify as RN
import aws_rds_util
import time

white_list=['vyyXD7q64qydeiyI','AZKBL1pi0v5R4APm']
req_white_list=False

AWS_NOTIFY_COMFORT_STATE=2000	

def handle_detail_notify(cur,body):
    req_list=['sta_udid']

    res=RU.check_param(body,req_list)
    if(res[0]==False):
        return res
    
    sta_udid=body['sta_udid']
        
    res=aws_rds_util.getStaIdByStaUdid(cur,sta_udid)
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])

    sid=res[1]
        
    #同時要讀取dev清單變更的資訊
    res=aws_rds_util.getCognitoIdByStaId(cur,sid)
    #(True, ('cbf783b1-86ee-4426-b793-95386cbbe545',))
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])
        
    if(len(res[1])==0):
        return RU.gen_success_result({'has_user':False})
        
    cognito_id=res[1][0]
    
    #開始整理事件清單
    
    notify_list=[]
    
    key=CU.PREF_NOTIFY_STA_KEY_HEADER+cognito_id
    info=CU.get_cache_data(key);
    if(info is not None):
        notify_list.append(info)
    
    key=CU.PREF_NOTIFY_DEV_LIST_KEY_HEADER+cognito_id
    info=CU.get_cache_data(key);
    if(info is not None):
        notify_list.append(info)
        
    key=CU.PREF_NOTIFY_BABY_KEY_HEADER+cognito_id
    info=CU.get_cache_data(key);
    if(info is not None):
        notify_list.append(info)
        
    cts=int(time.time())
    max_alarm_time=15*60#15mins
        
    key=CU.SLEEP_REQ_COMFORT_KEY_HEADER+cognito_id
    info=CU.get_cache_data(key);
    if(info is not None and cts-info['ts']<max_alarm_time):
        notify_list.append(info)

    #=========================================================================== 
    if req_white_list:
        if(sta_udid not in white_list):
            return RU.gen_success_result({})
    #===========================================================================
    
    res=DC.get_dev_list_by_sta_udid(cur,sta_udid)
    if(res[0]==False):
        return res
        
    dev_list=res[1]
    for di in dev_list:
        dev_udid=di['udid']
        dn_key=CU.NOTIFY_RES_KEY_HEADER+dev_udid
        notify_res=CU.get_cache_data(dn_key)
        if(notify_res is None):
            continue
        notify_list.append({"type":RN.AWS_NOTIFY_ABNORMAL,"ts":0,'notify':notify_res})
        
    #print('DETAIL NOTIFY',notify_list)

    msg={'notify_list':notify_list,'has_user':True}
    
    return RU.gen_success_result(msg)