import json
import pickle
from redis import Redis
#from rediscluster import RedisCluster

STATION_INFO_KEY_HEADER='sta_'
ACCESS_TOKEN_KEY_HEADER='atkn_'
REFRESH_TOKEN_KEY_HEADER='rtkn_'

REALTIME_DATA_KEY_HEADER='rtd_'
STAT_DATA_KEY_HEADER='stat_'
TREND_DATA_QUEUE_KEY_HEADER='trnd_'

STATION_STATE_KEY_HEADER='sta_state_'

REQ_DET_TAG_HEADER='req_det_tag_'
REQ_FORGET_WIFI_HEADER='req_fog_wifi_'

STA_LAST_ALIVE_KEY_HEADER='sta_alive_'
STA_LAST_FW_KEY_HEADER='sta_fw_'

OBS_VAR_KEY_HEADER='obs_var01_'
ODD_SND_RES_KEY_HEADER='odd_snd_res01_'

SLEEP_VAR_KEY_HEADER='slp_var02_'
SLEEP_REQ_COMFORT_KEY_HEADER='slp_level_'

NOTIFY_VAR_KEY_HEADER='notify_var02_'
NOTIFY_RES_KEY_HEADER='notify_res_'

STA_UDID_TO_DEV_LIST_KEY_HEADER='sta_to_dk_'
USER_LANG_KEY_HEADER='user_lang_'
USER_PHONE_SET_KEY_HEADER='user_phone_set_'

STATION_UDID_TO_COGNITO_ID_KEY_HEADER='sta_to_cid_'
PREF_STA_KEY_HEADER='pref_sta_'
PREF_TAG_KEY_HEADER='pref_tag_'
PREF_BABY_KEY_HEADER='pref_baby_'
PREF_SYS_NOTIFY_HEADER='sys_notify_'

PREF_NOTIFY_STA_KEY_HEADER='notify_sta_'
PREF_NOTIFY_DEV_LIST_KEY_HEADER='notify_dev_list_'
PREF_NOTIFY_BABY_KEY_HEADER='notify_baby_'
PREF_NOTIFY_ALARM_HR_KEY_HEADER='notify_alarm_hr_'
PREF_NOTIFY_ALARM_RR_KEY_HEADER='notify_alarm_rr_'
PREF_NOTIFY_ALARM_RRQ_KEY_HEADER='notify_alarm_rrq_'
PREF_NOTIFY_ALARM_CHOKING_KEY_HEADER='notify_alarm_choking_'
PREF_NOTIFY_ALARM_OBSND_KEY_HEADER='notify_alarm_obsnd_'
PREF_NOTIFY_ALARM_DIARRHEA_KEY_HEADER='notify_alarm_diarrhea_'
PREF_NOTIFY_ALARM_BS_KEY_HEADER='notify_alarm_bs_'
PREF_NOTIFY_ALARM_TEMP_KEY_HEADER='notify_alarm_temp_'

redis = Redis(host='awsbaby-cache.sxqkww.ng.0001.apne1.cache.amazonaws.com', port=6379)
#redis = RedisCluster(startup_nodes=[{"host": "awsbaby-cache-cluster.sxqkww.clustercfg.apne1.cache.amazonaws.com","port": "6379"}], decode_responses=True,skip_full_coverage_check=True)
                
def set_cache_data(key,dat,timeout=2592000):#2592000=30days
    str = json.dumps(dat)
    redis.set(key, str, ex=timeout)
    
def get_cache_data(key):
    str=redis.get(key)
    if(str is None):
        return str
    return json.loads(str)
    
def del_cache_data(key):
    return redis.delete(key)
    
#=================================================================
    
#redis list op
def list_append(key,dat):
    ba = json.dumps(dat)
    list_len=redis.rpush (key, ba)
    return list_len
    
def list_pop(key):
    ba=redis.lpop(key)
    return json.loads(ba)
    
def list_get(key,idx):
    ba=redis.lindex(key,idx)
    return json.loads(ba)
    
def list_get_range(key,start,stop):
    ba_list=redis.lrange(key,start,stop)
    res=[]
    for ba in ba_list:
        res.append(json.loads(ba))
    return res
    
def list_size(key):
    return redis.llen(key)
    
def list_trim(key,keep_start,keep_stop):
    return redis.ltrim(key,keep_start,keep_stop)

#=================================================================

def add_set_item(set_key,item):
    redis.sadd(set_key,item)

def remove_set_item(set_key,item):
    redis.srem(set_key,item)
    
def get_set_items(set_key):
    return redis.smembers(set_key)