import rest_dev as DEV
import rest_dfu as DFU
import rest_evt as EVT
import rest_mp3 as MP3
import rest_odd_snd as ODD
import rest_pref as PREF
import rest_revt as REVT
import rest_rt as RT
import rest_notify as RN
import rest_detail_notify as RDN
import rest_util as RU
import rest_pair as RP
import rest_direct as RD
import rest_sta_state as RSS
import rest_test as RTEST

import aws_rds_util

import boto3
import json
import aws_rds_util
import base64
import time 
import io
import cache_util as CU

endpoint_url='https://t6pix2l6yg.execute-api.ap-northeast-1.amazonaws.com/production'
lambda_client = boto3.client('lambda')

conn=None
cur=None

def checkConn(cur,conn):
    if(conn is None or cur is None):
        return False
    
    sq = "SELECT NOW()"
    try:
        cur.execute( sq )
    except:
        return False
    return True
    
def checkStaAndUpdateLastAccessTs(body):
    req_list=['sta_udid','token']
    res=RU.check_param(body,req_list)
    if(res[0]==False):
        return res
        
    sta_udid=body['sta_udid']
    token=body['token']
    res=RU.checkStaToken(sta_udid,token)
    if(res[0]==False):
        return res
        
    alive_key=CU.STA_LAST_ALIVE_KEY_HEADER+sta_udid
    msg={'last_access_ts':int(time.time())}#以秒為單位
    CU.set_cache_data(alive_key,msg,5*60)#只保留五分鐘
    
    #print(sta_udid,msg)
    return (True,'')
    
def send_msg_by_api_gateway(url,cid,msg):
    #when working in VPC, use another lambda to access api-gateway's connection api
    inputParams = {
        "url": url,
        "cid": cid,
        "msg": msg
    }

    response = lambda_client.invoke(
        FunctionName = 'arn:aws:lambda:ap-northeast-1:227225135945:function:AwsBabyStationOnMessage_SendBackToStation',
        InvocationType = 'RequestResponse',
        Payload = json.dumps(inputParams)
    )

    return True

def lambda_handler(event, context):
    global conn,cur
    if(checkConn(cur,conn)==False):
        conn=aws_rds_util.connectDbByProxy()
        cur = conn.cursor()
    else:
        conn.commit();
        
    #print(event)
    '''
    {'requestContext': {'routeKey': '$default', 'messageId': 'PjN_GfNUNjMCJcQ=', 'eventType': 'MESSAGE', 'extendedRequestId': 'PjN_GHmENjMFWEA=', 
    'requestTime': '07/Dec/2023:02:12:09 +0000', 'messageDirection': 'IN', 'stage': 'production', 'connectedAt': 1701915123555, 
    'requestTimeEpoch': 1701915129962, 'identity': {'userAgent': 'ESP32 Websocket Client', 'sourceIp': '111.250.74.102'}, 'requestId': 'PjN_GHmENjMFWEA=', 
    'domainName': 't6pix2l6yg.execute-api.ap-northeast-1.amazonaws.com', 'connectionId': 'PjN-GfL3tjMCJcQ=', 'apiId': 't6pix2l6yg'}, 
    'body': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaabbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 'isBase64Encoded': False}
    '''
    
    requestContext=event['requestContext']
    requestTimeEpoch=requestContext['requestTimeEpoch']#in ms
    cid=requestContext['connectionId']
    stage =requestContext['stage']
    eventType=requestContext['eventType']
        
    #return gen_success_msg('success')

    body_str=event['body']
    #print('body_str len',len(body_str),eventType)
    
    if(eventType=='MESSAGE'):#get tokens
        body=json.loads(body_str)
    
        if('evt_type' in body):
            res=checkStaAndUpdateLastAccessTs(body)
            if(res[0]==False):#token過期
                msg=res[1]
                send_msg_by_api_gateway(endpoint_url,cid,json.dumps(msg))
                return RU.gen_success_msg('success')
            
            evt_type=body['evt_type']
            res=lambda_handler_single_item(cur,conn,body,evt_type)
            
            msg=res[1]
            msg['msg_type']=evt_type;
            if(res[0]):
                send_msg_by_api_gateway(endpoint_url,cid,json.dumps(msg))
                return RU.gen_success_msg('success')
            else:
                send_msg_by_api_gateway(endpoint_url,cid,json.dumps(msg))
                return RU.gen_error_msg('fail')
                
        elif('evt_list' in body):
            evt_list=body['evt_list']
            res_list=[]
            
            if(len(evt_list)>0):
                res=checkStaAndUpdateLastAccessTs(evt_list[0])
                if(res[0]==False):#token過期
                    msg=res[1]
                    send_msg_by_api_gateway(endpoint_url,cid,json.dumps(msg))
                    return RU.gen_success_msg('success')
            
            for item in evt_list:
                if('evt_type' in item):
                    evt_type=item['evt_type']
                    res=lambda_handler_single_item(cur,conn,item,evt_type)
                else:
                    evt_type=RU.ERROR_CODE_UNKNOWN_EVT
                    res=(False,{'err_code':RU.ERROR_CODE_MISSING_PARAM,"err":"missing evt_type"})
            
                msg=res[1]
                msg['msg_type']=evt_type;
                
                res_list.append(msg)
                
            msg={"res_list":res_list}
            send_msg_by_api_gateway(endpoint_url,cid,json.dumps(msg))
            return RU.gen_success_msg('success')
            
        else:
            msg={'err_code':RU.ERROR_CODE_MISSING_PARAM,"err":"missing evt_type"}
            send_msg_by_api_gateway(endpoint_url,cid,json.dumps(msg))
            return RU.gen_error_msg('fail')
            
    msg={'err_code':RU.ERROR_CODE_PATH_API_ERROR,"err":"invalid path or method"}
    send_msg_by_api_gateway(endpoint_url,cid,json.dumps(msg))
    return RU.gen_error_msg('fail')

        
def lambda_handler_single_item(cur,conn,body,evt_type):

    if(evt_type==RU.AWS_EVT_TYPE_DEV_EVT):
        return EVT.handle_evt(cur,conn,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_RANGE_EVT):
        return REVT.handle_revt(cur,conn,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_REALTIME_DATA):
        return RT.handle_realtime_data(cur,conn,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_CHK_UDID_LIST_TS):
        return DEV.handle_chk_udid_list_ts(cur,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_REQ_UDID_LIST):
        return DEV.handle_req_dev_udid_list(cur,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_REQ_MP3_LIST):
        return MP3.handle_req_mp3_list(cur,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_CHK_MP3):
        return MP3.handle_req_chk_mp3(cur,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_GET_MP3):
        return MP3.handle_req_get_mp3(cur,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_ODD_SND):
        return ODD.handle_odd_snd(cur,conn,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_GET_PREF):
        return PREF.handle_req_get_pref(cur,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_GET_DEV_PREF):
        return PREF.handle_req_get_dev_pref(cur,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_CHK_FW):
        return DFU.handle_req_chk_fw(body)

    elif(evt_type==RU.AWS_EVT_TYPE_GET_FW):
        return DFU.handle_req_get_fw(body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_GET_NEW_DEV):
        return RP.handle_add_dev(cur,conn,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_CFG_UPDATE_NOTIFY):
        return RN.handle_notify(cur,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_CFG_GET_DIRECT_CMD):
        return RD.handle_direct(cur,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_CFG_UPDATE_DETAIL_NOTIFY):
        return RDN.handle_detail_notify(cur,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_STA_STATE_INFO):
        return RSS.handle_sta_state(cur,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_TEST_PING_PONG):
        return RU.gen_success_result({'len': len(json.dumps(body))})
        #return RU.gen_success_result(body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_TEST_RESET):
        return RTEST.handle_reset(cur,conn,body)
        
    elif(evt_type==RU.AWS_EVT_TYPE_TEST_GET_VARS):
        return RTEST.handle_get_vars(cur,conn,body)
        
    else:
        return (False,{'err_code':RU.ERROR_CODE_UNKNOWN_EVT,"err":'unknow evt_type'})
        