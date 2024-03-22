import base64
import struct
import aws_rds_util
import obs_alarm as OA
import odd_snd_alg_aws as OSAA
import cache_util as CU

import io
import boto3
import base64
from botocore.client import ClientError

'''
#define ODD_SND_TYPE_MAIN_ONLY	0	//default
#define ODD_SND_TYPE_ENV_ONLY	1
#define ODD_SND_TYPE_MAIN_ENV	2
'''
ODD_SND_TYPE_MAIN_ONLY=	0
ODD_SND_TYPE_ENV_ONLY =	1
ODD_SND_TYPE_MAIN_ENV =	2

s3 = boto3.client('s3')
S3_BUCKET='awsbabymonitor114454-dev'

def chk_alg():
    #s3_path='odd_snd/poo_wav/test.bin'
    s3_path='odd_snd/obs_wav/test.bin'
    try:
        bio=io.BytesIO()
        
        s3.download_fileobj(S3_BUCKET,s3_path, bio)
    except:
        #traceback.print_exc()
        return (False,ERROR_READ_CFG_FAIL)

    bio.seek(0)
    ba=bio.read()
    
    print('OSAA OBS chk01')
    has_poo,has_obs=OSAA.checkRaw(ba,'test',0)
    print('OSAA OBS chk02',has_poo,has_obs)
    
    obs_proc=OA.ObsAlarm('test_aaa')
    req_obs_alarm=obs_proc.addData('test_aaa',0,has_obs)
    print('OSAA OBS chk03',req_obs_alarm)
    
    
#chk_alg()

def odd_snd_proc(cur,conn,cognito_id,param):
    dev_udid=param['dev_udid']
    esp_ts=param['ts']
    tick=param['tick']
    snd_type=param['snd_type']
    sps=param['sps']
    b64=param['b64']

    try:
        ba=base64.b64decode(b64)
    except:
        return False
        
    #save to s3
    res=aws_rds_util.saveOddSnd(cur,conn,cognito_id,dev_udid,esp_ts,ba)
        
    if(ba==None or len(ba)<10*1024):
        return False
        
    #ba_len=len(ba)
    #item_cnt=ba_len//2;
    #data_set=struct.unpack('<'+'h' * item_cnt,ba)
    has_poo,has_obs=OSAA.checkRaw(ba,dev_udid,tick/32768)
    obs_proc=OA.ObsAlarm(dev_udid)
    req_obs_alarm=obs_proc.addData(dev_udid,esp_ts/1000.0,has_obs)
    
    odd_alg_res={'ts':esp_ts,'has_poo':has_poo,'has_obs':has_obs,'req_obs_alarm':req_obs_alarm}
    odd_alg_res_key=CU.ODD_SND_RES_KEY_HEADER+dev_udid
    CU.set_cache_data(odd_alg_res_key,odd_alg_res)
    
    print('odd_alg_res',odd_alg_res_key,odd_alg_res)
    
    #item_cnt為short資料的筆數
    #snd_type指示了此資料的型態
    #data_set包含指定channel的資料
    #print('odd snd proc',dev_udid,esp_ts,tick,snd_type,sps,len(data_set),data_set[:10],data_set[-10:])
    
    return True