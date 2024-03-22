import cache_util as CU
import rest_util as RU
import aws_rds_util
import time

def handle_direct(cur,body):
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
        
    cmd_list=[];
    
    key=CU.REQ_DET_TAG_HEADER+cognito_id+sta_udid
    info=CU.get_cache_data(key);
    if(info is not None):
        cmd_list.append(info)
        CU.del_cache_data(key);
    
    key=CU.REQ_FORGET_WIFI_HEADER+cognito_id+sta_udid
    info=CU.get_cache_data(key);
    if(info is not None):
        cmd_list.append(info)
        CU.del_cache_data(key);
    
    msg={"cmd_list":cmd_list}
    
    return RU.gen_success_result(msg)