import cache_util as CU
import rest_util as RU
import aws_rds_util
import time

AWS_NOTIFY_HR=10	#心率指數異常
AWS_NOTIFY_RR=20	#呼吸指數異常
AWS_NOTIFY_RR_QUALITY=30	#呼吸品質異常
AWS_NOTIFY_CHOKING=40	#嗆奶與阻塞
AWS_NOTIFY_DIARRHEA=50	#大量排泄
AWS_NOTIFY_OBS=55	#鼻涕
AWS_NOTIFY_BS=60	#腸鳴頻率異常
AWS_NOTIFY_TEMPERATURE=70	#腹部溫度異常
AWS_NOTIFY_STA_PREF=1000#station設定變更
AWS_NOTIFY_BABY_PREF=1001#baby設定變更
AWS_NOTIFY_DEV_LIST_PREF=1002#dev list設定變更

AWS_NOTIFY_COMFORT_STATE=2000	
AWS_NOTIFY_ABNORMAL=2001


def handle_notify(cur,body):
    req_list=['sta_udid']

    res=RU.check_param(body,req_list)
    if(res[0]==False):
        return res
    
    sta_udid=body['sta_udid']
        
    res=aws_rds_util.getStaIdByStaUdid(cur,sta_udid)
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])

    sid=res[1]
        
    res=aws_rds_util.getCognitoIdByStaId(cur,sid)
    #(True, ('cbf783b1-86ee-4426-b793-95386cbbe545',))
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])
        
    if(len(res[1])==0):
        return RU.gen_success_result({'has_user':False})
        
    cognito_id=res[1][0]
        
    notify_list=[];
    
    key=CU.PREF_NOTIFY_STA_KEY_HEADER+cognito_id
    info=CU.get_cache_data(key);
    if(info is not None):
        notify_list.append(info)
    #else:#for test
    #    notify_list.append({'type':AWS_NOTIFY_DEV_LIST_PREF,'ts':int(time.time())})
    
    cts=int(time.time())
    max_alarm_time=15*60#15mins
        
    key=CU.PREF_NOTIFY_DEV_LIST_KEY_HEADER+cognito_id
    info=CU.get_cache_data(key);
    if(info is not None):
        notify_list.append(info)
        
    key=CU.PREF_NOTIFY_BABY_KEY_HEADER+cognito_id
    info=CU.get_cache_data(key);
    if(info is not None):
        notify_list.append(info)
    
    key=CU.PREF_NOTIFY_ALARM_HR_KEY_HEADER+cognito_id
    info=CU.get_cache_data(key);
    if(info is not None and cts-info['ts']<max_alarm_time):
        notify_list.append(info)
        
    key=CU.PREF_NOTIFY_ALARM_RR_KEY_HEADER+cognito_id
    info=CU.get_cache_data(key);
    if(info is not None and cts-info['ts']<max_alarm_time):
        notify_list.append(info)
        
    key=CU.PREF_NOTIFY_ALARM_RRQ_KEY_HEADER+cognito_id
    info=CU.get_cache_data(key);
    if(info is not None and cts-info['ts']<max_alarm_time):
        notify_list.append(info)
        
    key=CU.PREF_NOTIFY_ALARM_CHOKING_KEY_HEADER+cognito_id
    info=CU.get_cache_data(key);
    if(info is not None and cts-info['ts']<max_alarm_time):
        notify_list.append(info)
        
    key=CU.PREF_NOTIFY_ALARM_OBSND_KEY_HEADER+cognito_id
    info=CU.get_cache_data(key);
    if(info is not None and cts-info['ts']<max_alarm_time):
        notify_list.append(info)
        
    key=CU.PREF_NOTIFY_ALARM_DIARRHEA_KEY_HEADER+cognito_id
    info=CU.get_cache_data(key);
    if(info is not None and cts-info['ts']<max_alarm_time):
        notify_list.append(info)
        
    key=CU.PREF_NOTIFY_ALARM_BS_KEY_HEADER+cognito_id
    info=CU.get_cache_data(key);
    if(info is not None and cts-info['ts']<max_alarm_time):
        notify_list.append(info)
        
    key=CU.PREF_NOTIFY_ALARM_TEMP_KEY_HEADER+cognito_id
    info=CU.get_cache_data(key);
    if(info is not None and cts-info['ts']<max_alarm_time):
        notify_list.append(info)
        
    key=CU.SLEEP_REQ_COMFORT_KEY_HEADER+cognito_id
    info=CU.get_cache_data(key);
    if(info is not None and cts-info['ts']<max_alarm_time):
        notify_list.append(info)
    #if(info is None):
    #    #若沒有資料則設定為false
    #    info={'type':AWS_NOTIFY_COMFORT_STATE,'state':False,'ts':int(time.time())}
    #notify_list.append(info)

    msg={"notify_list":notify_list,'has_user':True}
    
    return RU.gen_success_result(msg)