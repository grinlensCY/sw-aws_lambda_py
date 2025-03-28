import rest_util as RU
import aws_rds_util

def handle_revt(cur,conn,body):
    req_list=['dev_udid','type','bts','ets','gauge']
    res=RU.check_param(body,req_list)
    if(res[0]==False):
        return res
        
    dev_udid=body['dev_udid']
    type=body['type']
    bts=body['bts']
    ets=body['ets']
    gauge=body['gauge']
        
    res=aws_rds_util.addRangeEvtByDevUdid(cur,conn,dev_udid,type,bts,ets,gauge)

    if(res[0]==False):
      return RU.gen_error_result_by_code(res[1])

    return RU.gen_success_result({})