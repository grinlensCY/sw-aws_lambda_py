import rest_util as RU
import aws_rds_util
import cache_util as CU

def get_dev_list_by_sta_udid(cur,sta_udid):
    key=CU.STA_UDID_TO_DEV_LIST_KEY_HEADER+sta_udid
    res=CU.get_cache_data(key)
    
    if(res==None):
        res=aws_rds_util.getStaIdByStaUdid(cur,sta_udid)
        if(res[0]==False):
            return RU.gen_error_result_by_code(res[1])
    
        sid=res[1]
        res=aws_rds_util.getDevListByStaId(cur,sid)
        
        if(res[0]==False):
            return RU.gen_error_result_by_code(res[1])
            
        dev_info_raw_list=res[1]
        dev_list=[]
        for item in dev_info_raw_list:
            dev_info={'udid':item[0],'key':item[1],'iv':item[2]}
            dev_list.append(dev_info)

        res=CU.set_cache_data(key,{'dev_list':dev_list},3600)
    else:
        dev_list=res['dev_list']
        
    return (True,dev_list)



def get_cognito_id_by_sta_udid(cur,sta_udid):
    key=CU.STATION_UDID_TO_COGNITO_ID_KEY_HEADER+sta_udid
    res=CU.get_cache_data(key)
    
    if(res==None):
        res=aws_rds_util.getStaIdByStaUdid(cur,sta_udid)
        if(res[0]==False):
            return res
    
        sid=res[1]
            
        res=aws_rds_util.getCognitoIdByStaId(cur,sid)
        #(True, ('cbf783b1-86ee-4426-b793-95386cbbe545',))
        if(res[0]==False):
            return res
            
        if(len(res[1])==0):
            return (True,None)
            
        cognito_id=res[1][0]
        res=CU.set_cache_data(key,{'cid':cognito_id},3600)
    else:
        cognito_id=res['cid']
        
    return (True,cognito_id)
    
def get_tag_cfg(cognito_id,udid):#return default when no data 
    key=CU.PREF_TAG_KEY_HEADER+cognito_id+udid;
    #CU.del_cache_data(key);
    cfg=CU.get_cache_data(key);
    
    if(cfg is None):
        res=aws_rds_util.getTagCfgContent(cognito_id,udid)
        
        if(res[0]==False):
            cfg='{"hrH":130.0,"hrL":80.0,"rrH":50.0,"rrL":15.0,"tempH":37.0,"tempL":33.0,"nHrE":false,"nRrE":false,"nTempE":false}'
        else:
            cfg=res[1]
        
        if(cfg is not None):
            CU.set_cache_data(key,cfg);
            
    return (True,cfg)
    
def load_sta_cfg(cognito_id):
    key=CU.PREF_STA_KEY_HEADER+cognito_id;
    cfg=CU.get_cache_data(key);
    
    if(cfg is None):
        res=aws_rds_util.getStaCfgContent(cognito_id)
        
        if(res[0]==False):
            return res
        
        cfg=res[1]
        
        if(cfg is not None):
            key=CU.PREF_STA_KEY_HEADER+cognito_id;
            CU.set_cache_data(key,cfg);
    return (True,cfg)
    
