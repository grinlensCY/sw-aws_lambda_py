import json
import aws_rds_util
import cache_util as CU

ERROR_CODE_MISSING_PARAM=-1
ERROR_CODE_DYNAMODB_ERROR=-100
ERROR_CODE_PATH_API_ERROR=-200
ERROR_CODE_UNKNOWN_EVT=-300
ERROR_CODE_TOKEN_INVALID=-400

AWS_EVT_TYPE_DEV_EVT=1
AWS_EVT_TYPE_RANGE_EVT=2
AWS_EVT_TYPE_REALTIME_DATA=50
AWS_EVT_TYPE_REQ_UDID_LIST=100
AWS_EVT_TYPE_CHK_UDID_LIST_TS=101
AWS_EVT_TYPE_REQ_MP3_LIST=200
AWS_EVT_TYPE_CHK_MP3=201
AWS_EVT_TYPE_GET_MP3=202
AWS_EVT_TYPE_ODD_SND=300
AWS_EVT_TYPE_GET_PREF=400
AWS_EVT_TYPE_GET_DEV_PREF=500
AWS_EVT_TYPE_CHK_FW=900
AWS_EVT_TYPE_GET_FW=901
AWS_EVT_TYPE_GET_NEW_DEV=999

AWS_EVT_TYPE_CFG_UPDATE_NOTIFY=1000
AWS_EVT_TYPE_CFG_UPDATE_DETAIL_NOTIFY=1001
AWS_EVT_TYPE_CFG_GET_DIRECT_CMD=1002
AWS_EVT_TYPE_STA_STATE_INFO=1003

AWS_EVT_TYPE_TEST_PING_PONG=65000
AWS_EVT_TYPE_TEST_RESET=65001
AWS_EVT_TYPE_TEST_GET_VARS=65002

AWS_WS_STA_PKG_TYPE_CHK_UDID_LIST_TS=AWS_EVT_TYPE_CHK_UDID_LIST_TS
AWS_WS_STA_PKG_TYPE_CONFI_UDID=AWS_EVT_TYPE_REQ_UDID_LIST
AWS_WS_STA_PKG_TYPE_MP3_LIST=AWS_EVT_TYPE_REQ_MP3_LIST
AWS_WS_STA_PKG_TYPE_CHK_MP3=AWS_EVT_TYPE_CHK_MP3
AWS_WS_STA_PKG_TYPE_GET_MP3_CXT=AWS_EVT_TYPE_GET_MP3
AWS_WS_STA_PKG_TYPE_GET_PREF=AWS_EVT_TYPE_GET_PREF
AWS_WS_STA_PKG_TYPE_GET_DEV_PREF=AWS_EVT_TYPE_GET_DEV_PREF
AWS_WS_STA_PKG_TYPE_CHK_FW_CXT=AWS_EVT_TYPE_CHK_FW
AWS_WS_STA_PKG_TYPE_GET_FW_CXT=AWS_EVT_TYPE_GET_FW
AWS_WS_STA_PKG_TYPE_CFG_UPDATE_NOTIFY=AWS_EVT_TYPE_CFG_UPDATE_NOTIFY
AWS_WS_STA_PKG_TYPE_CFG_UPDATE_DETAIL_NOTIFY=AWS_EVT_TYPE_CFG_UPDATE_DETAIL_NOTIFY

AUTH_ERROR_RESPONSE={
  'statusCode': 403,
  'body': 'REQ CORRECT NAME AND PASSWORD'
}

SUCCESS_RESPONSE={
  'statusCode': 200,
  'body': 'SUCCESS'
}

SERVER_ERROR_RESPONSE={
  'statusCode': 500,
  'body': 'SERVER ERROR'
}

REFRESH_TOKEN_EXPIRED_RESPONSE={
  'statusCode': 403,
  'body': 'REFRESH TOKEN IS EXPIRED'
}

def check_param(body,req_list):
    for item in req_list:
        if(item not in body):
            msg={"err":'missing %s'%(item),'err_code':ERROR_CODE_MISSING_PARAM}
            return (False,msg)
    return (True,"")
    
def checkStaToken(sta_udid,token):

    key=CU.ACCESS_TOKEN_KEY_HEADER+token
    item=CU.get_cache_data(key)

    if(item is not None):
        udid=item['udid']
        if(udid != sta_udid):
            msg={"err":'sta_udid and token mismatch','err_code':ERROR_CODE_TOKEN_INVALID}
            return (False,msg)
    else:
      msg={"err":'no record in token table','err_code':ERROR_CODE_TOKEN_INVALID}
      return (False,msg)
    
    return (True,'')
    
def get_body_json_from_event(event):
    body=event['body'];
    
    try:
        json_obj=json.loads(body)
    except:
        return None
    return json_obj
  
#這是給api gateway的訊息========================================================
def gen_error_msg(msg):
  return {
    'statusCode': 400,
    'body': json.dumps(msg)
  }
  
def gen_success_msg(msg):
  return {
    'statusCode': 200,
    'body': json.dumps(msg)
  }
  
#這是作為指令輸出的訊息=========================================================  
def gen_success_result(msg):
  json_msg={'err_code':0,'msg':msg}
  return (True,json_msg)
  
def gen_error_result_by_code(code):
  if(code in aws_rds_util.error_code_msg_map):
    err_msg=aws_rds_util.error_code_msg_map[code]
  else:
    err_msg='無此錯誤訊息'
    
  return (False,{'err_code':code,"err":err_msg})
  