import rest_util as RU
import aws_rds_util
import json
import cache_util as CU

def handle_chk_udid_list_ts(cur,body):
    req_list=['sta_udid']
    res=RU.check_param(body,req_list)
    if(res[0]==False):
        return res
    
    sta_udid=body['sta_udid']
        
    res=aws_rds_util.getStaIdByStaUdid(cur,sta_udid)
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])

    sid=res[1]
    
    res=aws_rds_util.getLastStaScanChangeTsByStaId(cur,sid)
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])

    update_ts=res[1]

    msg={'update_ts':update_ts}
    return RU.gen_success_result(msg)
    
def handle_req_dev_udid_list(cur,body):
    req_list=['sta_udid']
    res=RU.check_param(body,req_list)
    if(res[0]==False):
        return res
    
    sta_udid=body['sta_udid']

    res=aws_rds_util.getStaIdByStaUdid(cur,sta_udid)
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])

    sid=res[1]
    res=aws_rds_util.getDevListByStaId(cur,sid)
    
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])
        
    dev_info_raw_list=res[1]
    dev_info_list=[]
    for item in dev_info_raw_list:
        dev_info={'udid':item[0],'key':item[1],'iv':item[2]}
        dev_info_list.append(dev_info)
        
    res=aws_rds_util.getLastStaScanChangeTsByStaId(cur,sid)
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])
    update_ts=res[1]
        
    key=CU.STA_UDID_TO_DEV_LIST_KEY_HEADER+sta_udid
    res=CU.set_cache_data(key,{'dev_list':dev_info_list},3600)
        
    
    msg={"udid_list":dev_info_list,'update_ts':update_ts}
    return RU.gen_success_result(msg)