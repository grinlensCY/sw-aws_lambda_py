import rest_util as RU
import aws_rds_util
import cache_util as CU
import db_cache as DC
import base64
import json
from datetime import datetime

def handle_req_get_pref(cur,body):
    print("qqqqqqqqq", body);
    
    req_list=['sta_udid']

    res=RU.check_param(body,req_list)
    if(res[0]==False):
        return res
    
    sta_udid=body['sta_udid']

    res=DC.get_cognito_id_by_sta_udid(cur,sta_udid)
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])
    elif(res[1]==None):
        return RU.gen_success_result({})
    else:
        cognito_id=res[1]
    
    res=aws_rds_util.getStaCfgContent(cognito_id)
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])
    cfg=res[1]
    
    if(cfg is None):
        return RU.gen_success_result({})
        
    msg={"cfg":cfg,"user_cognito_id":cognito_id}
    return RU.gen_success_result(msg)
    
def handle_req_get_dev_pref(cur,body):

    req_list=['sta_udid','dev_udid']

    res=RU.check_param(body,req_list)

    if(res[0]==False):
        return res
    
    sta_udid=body['sta_udid']
        
    res=DC.get_cognito_id_by_sta_udid(cur,sta_udid)
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])
    elif(res[1]==None):
        return RU.gen_success_result({})
    else:
        cognito_id=res[1]
        
    dev_udid=body['dev_udid']
    #必須每次都從資料庫讀取，因為設定的時候是對baby設定，那時候不見得知道貼片的udid，會造成無法更新cache

    res=aws_rds_util.getDevIdByUdid(cur,dev_udid)

    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])
        
    did=res[1]
    res=aws_rds_util.getBabyBidAndBirthdayByDevId(cur,cognito_id,did)

    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])
    elif res[1]==None:
         return RU.gen_success_result({})
         
    bi=res[1]
    bid=bi[0]
    birthday=bi[1]
    
    res=aws_rds_util.getBabyCfgContent(cognito_id,bid)
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])
        
    #baby_cfg 
    bc_str=res[1]

    try:
        bc=json.loads(bc_str)
    except:
        bc=None

    if(bc is None):
        return RU.gen_success_result({})
        
    id_rgb=[4,0,2]
    if('id_rgb' in bc):
       id_rgb=bc['id_rgb']
       if(len(id_rgb)<3):
           id_rgb=[100,0,0]
  
    #dev_cfg    
    dc=DC.get_tag_cfg(cognito_id,dev_udid)
    #{"hrH":160.0,"hrL":100.0,"rrH":70.0,"rrL":25.0,"tempH":38.5,"tempL":34.5,"nHrE":true,"nRrE":true,"nTempE":true}
    
    #整合出實際的cfg=>從baby cfg取得顏色/年齡，從dev cfg取的參數
    #年齡範圍
    if(birthday>1000000000):#in ms
        birthday=birthday/1000.0
    bbd = datetime.fromtimestamp(birthday)
    now = datetime.now()
    delta=now-bbd
    days=delta.days
    
    alg_old_range=0
    if(days>5*365):
        alg_old_range=50
    elif(days>16*30):
        alg_old_range=40
    elif(days>12*30):
        alg_old_range=30
    elif(days>3*30):
        alg_old_range=20
    elif(days>1*30):
        alg_old_range=10  
    else:
        alg_old_range=0  
        
    print('alg_old_range',alg_old_range);
        
    #計算參數
    alg=bytearray(128)
    alg[0]=1;#ver
    alg[1]=alg_old_range;
    cs=0
    for i in range(127):
        cs+=alg[i]
    alg[127]=cs
        
    alg_b64 = base64.b64encode(alg).decode()
    cfg={'id_r':id_rgb[0],'id_g':id_rgb[1],'id_b':id_rgb[2],'alg':alg_b64}
    
    if(dc[0] and dc[1] is not None):
        try:
            dc_cfg=json.loads(dc[1])
        except:
            dc_cfg=None
        
        if(dc_cfg != None):
        
            req_list=["hrH","hrL","rrH","rrL","tempH","tempL","nHrE","nRrE","nTempE"]
            res=RU.check_param(dc_cfg,req_list)
            if(res[0]):
                cfg['hrH']=dc_cfg['hrH']
                cfg['hrL']=dc_cfg['hrL']
                cfg['rrH']=dc_cfg['rrH']
                cfg['rrL']=dc_cfg['rrL']
                cfg['tempH']=dc_cfg['tempH']
                cfg['tempL']=dc_cfg['tempL']
                cfg['nHrE']=dc_cfg['nHrE']
                cfg['nRrE']=dc_cfg['nRrE']
                cfg['nTempE']=dc_cfg['nTempE']
    
    cfg_str=json.dumps(cfg)
    
    msg={"cfg":cfg_str,"dev_udid":dev_udid}
    
    return RU.gen_success_result(msg)