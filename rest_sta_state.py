import cache_util as CU
import rest_util as RU
import aws_rds_util
import time

def handle_sta_state(cur,body):
    req_list=['sta_udid']

    res=RU.check_param(body,req_list)
    if(res[0]==False):
        return res
    
    sta_udid=body['sta_udid']
        
    del body['sta_udid']
    del body['token']
    del body['evt_type']
    body['ts']=int(time.time()*1000)
    
    key=CU.STATION_STATE_KEY_HEADER+sta_udid
    CU.set_cache_data(key,body);
    '''
    if 'fw_ver' in body:
        fw_key=body['fw_ver']
        fw_key=CU.STA_LAST_FW_KEY_HEADER+sta_udid
        CU.set_cache_data(fw_key,{'fw':fw_ver,'ts':int(time.time())})
    '''

    
    msg={"result":'update done'}
    return RU.gen_success_result(msg)