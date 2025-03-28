import rest_util as RU
import aws_rds_util
import odd_snd_handler as OSP
import db_cache as DC
import rest_util as RU

def handle_odd_snd(cur,conn,body):
    #{'action': 'onmsg', 'sta_udid': 'SX_BABY_STA_0024', 'token': '7TS42EAIWEPG2OHD4NF9F54DVYX3JNSX', 'dev_udid': '253f5b71be7169bb', 'evt_type': 300, 'snd_type': 0, 'sps': 1068650488, 'ts': 43204, 'tick:': 1409024, 'b64':
    
    req_list=['sta_udid','dev_udid','ts','tick','b64','snd_type','sps']
    res=RU.check_param(body,req_list)
    
    if(res[0]==False):
        return res
        
    print('handle_odd_snd',body)
    
    sta_udid=body['sta_udid']
        
    res=DC.get_cognito_id_by_sta_udid(cur,sta_udid)
    if(res[0]):
        cognito_id=res[1]
        res=OSP.odd_snd_proc(cur,conn,cognito_id,body)
        if(res==False):
            return (False,{'err_code':RU.ERROR_CODE_PATH_API_ERROR,"err":'can not send by path api'})

    return RU.gen_success_result({})