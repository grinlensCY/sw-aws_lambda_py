import rest_util as RU
import aws_rds_util

def handle_evt(cur,conn,body):
    req_list=['sta_udid','dev_udid','type','ts']
    res=RU.check_param(body,req_list)
    if(res[0]==False):
        return res
        
    sta_udid=body['sta_udid']
    dev_udid=body['dev_udid']
    type=body['type']
    ts=body['ts']
        
    res=aws_rds_util.addEventByDevUdid(cur,conn,dev_udid,type,ts)

    if(res[0]==False):
      return RU.gen_error_result_by_code(res[1])
      
    return RU.gen_success_result({})