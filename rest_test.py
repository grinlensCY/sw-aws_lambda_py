import rest_util as RU
import aws_rds_util
import io
import base64
import traceback
import cache_util as CU
import db_cache as DC
import time

def handle_reset(cur,conn,body):
    req_list=['sta_udid','dev_udid']
    res=RU.check_param(body,req_list)
    
    if(res[0]==False):
        return res
    
    sta_udid=body['sta_udid']
    dev_udid=body['dev_udid']
    
    res=DC.get_cognito_id_by_sta_udid(cur,sta_udid)
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])
        
    if(len(res[1])==0):
        return RU.gen_success_result({'has_user':False})
        
    cognito_id=res[1][0]
    
    #刪除direct command
    key=CU.REQ_DET_TAG_HEADER+cognito_id+sta_udid
    CU.del_cache_data(key);
    key=CU.REQ_FORGET_WIFI_HEADER+cognito_id+sta_udid
    CU.del_cache_data(key);
    
    #刪除各種通知
    key=CU.PREF_NOTIFY_STA_KEY_HEADER+cognito_id
    CU.del_cache_data(key)
    key=CU.PREF_NOTIFY_DEV_LIST_KEY_HEADER+cognito_id
    CU.del_cache_data(key)
    key=CU.PREF_NOTIFY_BABY_KEY_HEADER+cognito_id
    CU.del_cache_data(key)
    key=CU.SLEEP_REQ_COMFORT_KEY_HEADER+cognito_id
    CU.del_cache_data(key)
    
    
    #早期的
    key=CU.PREF_NOTIFY_ALARM_HR_KEY_HEADER+cognito_id
    CU.del_cache_data(key)
    key=CU.PREF_NOTIFY_ALARM_RR_KEY_HEADER+cognito_id
    CU.del_cache_data(key)
    key=CU.PREF_NOTIFY_ALARM_RRQ_KEY_HEADER+cognito_id
    CU.del_cache_data(key)
    key=CU.PREF_NOTIFY_ALARM_CHOKING_KEY_HEADER+cognito_id
    CU.del_cache_data(key)
    key=CU.PREF_NOTIFY_ALARM_OBSND_KEY_HEADER+cognito_id
    CU.del_cache_data(key)
    key=CU.PREF_NOTIFY_ALARM_DIARRHEA_KEY_HEADER+cognito_id
    CU.del_cache_data(key)
    key=CU.PREF_NOTIFY_ALARM_BS_KEY_HEADER+cognito_id
    CU.del_cache_data(key)
    key=CU.PREF_NOTIFY_ALARM_TEMP_KEY_HEADER+cognito_id
    CU.del_cache_data(key)
    
    #演算法計算相關
    #異常音處理的變數
    key=CU.ODD_SND_RES_KEY_HEADER+dev_udid
    CU.del_cache_data(key)
    key=CU.OBS_VAR_KEY_HEADER+dev_udid
    CU.del_cache_data(key)
    #睡眠階段
    key=CU.STAT_DATA_KEY_HEADER+dev_udid
    CU.del_cache_data(key)
    key=CU.SLEEP_VAR_KEY_HEADER+dev_udid
    CU.del_cache_data(key)
    
    #RT data
    key=CU.REALTIME_DATA_KEY_HEADER+dev_udid
    CU.del_cache_data(key)
    key=CU.NOTIFY_VAR_KEY_HEADER+dev_udid
    CU.del_cache_data(key)
    key=CU.NOTIFY_RES_KEY_HEADER+dev_udid
    CU.del_cache_data(key)
      
    return RU.gen_success_result({'res':'clean all related redis vars'})
    
def handle_get_vars(cur,conn,body):
    req_list=['sta_udid','dev_udid']
    res=RU.check_param(body,req_list)
    
    if(res[0]==False):
        return res
        
    sta_udid=body['sta_udid']
    dev_udid=body['dev_udid']
    
    res=DC.get_cognito_id_by_sta_udid(cur,sta_udid)
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])
        
    if(len(res[1])==0):
        return RU.gen_success_result({'has_user':False})
        
    cognito_id=res[1][0]
    
    vars={}
    
    #刪除direct command
    key=CU.REQ_DET_TAG_HEADER+cognito_id+sta_udid
    vars['direct_cmd']=CU.get_cache_data(key)
    key=CU.REQ_FORGET_WIFI_HEADER+cognito_id+sta_udid
    vars['req_forget_wifi']=CU.get_cache_data(key)
    
    #刪除各種通知
    key=CU.PREF_NOTIFY_STA_KEY_HEADER+cognito_id
    vars['pref_notify_sta']=CU.get_cache_data(key)
    key=CU.PREF_NOTIFY_DEV_LIST_KEY_HEADER+cognito_id
    vars['pref_notify_dev']=CU.get_cache_data(key)
    key=CU.PREF_NOTIFY_BABY_KEY_HEADER+cognito_id
    vars['pref_notify_baby']=CU.get_cache_data(key)
    key=CU.SLEEP_REQ_COMFORT_KEY_HEADER+cognito_id
    vars['sleep_req_comfort']=CU.get_cache_data(key)
    
    
    #早期的
    key=CU.PREF_NOTIFY_ALARM_HR_KEY_HEADER+cognito_id
    vars['alarm_hr']=CU.get_cache_data(key)
    key=CU.PREF_NOTIFY_ALARM_RR_KEY_HEADER+cognito_id
    vars['alarm_rr']=CU.get_cache_data(key)
    key=CU.PREF_NOTIFY_ALARM_RRQ_KEY_HEADER+cognito_id
    vars['alarm_rrq']=CU.get_cache_data(key)
    key=CU.PREF_NOTIFY_ALARM_CHOKING_KEY_HEADER+cognito_id
    vars['alarm_choking']=CU.get_cache_data(key)
    key=CU.PREF_NOTIFY_ALARM_OBSND_KEY_HEADER+cognito_id
    vars['alarm_choking']=CU.get_cache_data(key)
    key=CU.PREF_NOTIFY_ALARM_DIARRHEA_KEY_HEADER+cognito_id
    vars['alarm_diarrhea']=CU.get_cache_data(key)
    key=CU.PREF_NOTIFY_ALARM_BS_KEY_HEADER+cognito_id
    vars['alarm_bs']=CU.get_cache_data(key);
    key=CU.PREF_NOTIFY_ALARM_TEMP_KEY_HEADER+cognito_id
    vars['alarm_temp']=CU.get_cache_data(key)
    
    #演算法計算相關
    #演算法計算結果
    key=CU.ODD_SND_RES_KEY_HEADER+dev_udid
    vars['odd_snd_res']=CU.get_cache_data(key)
    key=CU.OBS_VAR_KEY_HEADER+dev_udid
    vars['obs_vars']=CU.get_cache_data(key)
    #睡眠階段
    key=CU.STAT_DATA_KEY_HEADER+dev_udid
    vars['stat_data']=CU.list_get_range(key,0,-1)#因為是redis list type
    key=CU.SLEEP_VAR_KEY_HEADER+dev_udid
    vars['sleep_vars']=CU.get_cache_data(key)
    
    #RT data
    key=CU.REALTIME_DATA_KEY_HEADER+dev_udid
    vars['rt_data']=CU.get_cache_data(key)
    key=CU.NOTIFY_VAR_KEY_HEADER+dev_udid
    vars['notify_vars']=CU.get_cache_data(key)
    key=CU.NOTIFY_RES_KEY_HEADER+dev_udid
    vars['notify_res']=CU.get_cache_data(key)
        
    return RU.gen_success_result(vars)