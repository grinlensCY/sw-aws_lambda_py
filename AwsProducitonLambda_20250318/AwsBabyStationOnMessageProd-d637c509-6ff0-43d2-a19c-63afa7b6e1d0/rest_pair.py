import rest_util as RU
import aws_rds_util
from hashlib import sha256
import io
import base64
import traceback
import cache_util as CU
import db_cache as DC
import time

def handle_add_dev(cur,conn,body):
    req_list=['sta_udid']
    res=RU.check_param(body,req_list)
    
    if(res[0]==False):
        return res
    
    sta_udid=body['sta_udid']

    dev_udid=body['dev_udid']
    dev_key=body['dev_key']
    dev_iv=body['dev_iv']
    
    res=DC.get_cognito_id_by_sta_udid(cur,sta_udid)

    if(res is None or res[0]==False):
        return RU.gen_error_result_by_code(aws_rds_util.ERROR_READ_USER_INFO_FAIL)
    cognito_id=res[1]
    
    res=aws_rds_util.getDevByUdid(cur,dev_udid)

    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])
    
    ref_key=res[1][2]
    ref_iv=res[1][3]

    if(ref_key!=dev_key or ref_iv!=dev_iv):
        return RU.gen_error_result_by_code(aws_rds_util.ERROR_NO_VALID_DEVID)
        
    res=aws_rds_util.pairUserAndThisDev(cur,conn,cognito_id,dev_udid)
    
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])
        
    return RU.gen_success_result({})