import rest_util as RU
import aws_rds_util
from hashlib import sha256
import io
import base64
import traceback
import boto3
import cache_util as CU
import time

s3 = boto3.client('s3')
S3_BUCKET='awsbabymonitor114454-dev' 

#FW_BIN_PATH='fw/sx_sta_0105.bin'
#STA_LAST_FW_VER=0x0105 

#FW_BIN_PATH='fw/sx_sta_20221209_fw010a.bin'
#STA_LAST_FW_VER=0x010a

#FW_BIN_PATH='fw/sx_sta_20230130_fw010c.bin'
#STA_LAST_FW_VER=0x010c

#FW_BIN_PATH='fw/sx_sta_20230208_fw010e.bin'
#STA_LAST_FW_VER=0x010e

#FW_BIN_PATH='fw/sx_sta_20230208_fw010f.bin'
#STA_LAST_FW_VER=0x010f

#FW_BIN_PATH='fw/sx_sta_20230215_fw0110.bin'
#STA_LAST_FW_VER=0x0110

#FW_BIN_PATH='fw/sx_sta_20230221_fw0111.bin'
#STA_LAST_FW_VER=0x0111

#FW_BIN_PATH='fw/sx_sta_20230221fw0112.bin'
#STA_LAST_FW_VER=0x0112

#FW_BIN_PATH='fw/sx_sta_20230221_fw0113.bin'
#STA_LAST_FW_VER=0x0113

#FW_BIN_PATH='fw/sx_sta_20230221_fw0114.bin'
#STA_LAST_FW_VER=0x0114

#FW_BIN_PATH='fw/sx_sta_20230314_fw0115.bin'
#STA_LAST_FW_VER=0x0115

#FW_BIN_PATH='fw/sx_sta_20230321_fw0116.bin'
#STA_LAST_FW_VER=0x0116

#FW_BIN_PATH='fw/sx_sta_20230411_fw0117.bin'
#STA_LAST_FW_VER=0x0117

#FW_BIN_PATH='fw/sx_sta_20230417_fw0118.bin'
#STA_LAST_FW_VER=0x0118

#FW_BIN_PATH='fw/sx_sta_20230822_china.bin'
#STA_LAST_FW_VER=0x0119

#FW_BIN_PATH='fw/sx_sta_20231120_fw011a.bin'
#STA_LAST_FW_VER=0x011a

#FW_BIN_PATH='fw/sx_sta_20231122_fw011b.bin'
#STA_LAST_FW_VER=0x011b

#FW_BIN_PATH='fw/sx_sta_20231122_fw011c.bin'
#STA_LAST_FW_VER=0x011c

#FW_BIN_PATH='fw/sx_sta_20240117_fw011e.bin'
#STA_LAST_FW_VER=0x011E

#FW_BIN_PATH='fw/sx_sta_20240117_fw011f.bin'
#STA_LAST_FW_VER=0x011F

#FW_BIN_PATH='fw/sx_sta_20240118_fw0120.bin'
#STA_LAST_FW_VER=0x0120

#FW_BIN_PATH='fw/sx_sta_20240119_fw0121.bin'
#STA_LAST_FW_VER=0x0121

#FW_BIN_PATH='fw/sx_sta_20240122_fw0122.bin'
#STA_LAST_FW_VER=0x0122

#FW_BIN_PATH='fw/sx_sta_20240122_fw0123.bin'
#STA_LAST_FW_VER=0x0123

#FW_BIN_PATH='fw/sx_sta_20240122_fw0124.bin'
#STA_LAST_FW_VER=0x0124

#FW_BIN_PATH='fw/sx_sta_20240124_fw0125.bin'
#STA_LAST_FW_VER=0x0125

#FW_BIN_PATH='fw/sta_fw_neo_20240215_fw0127.bin'
#STA_LAST_FW_VER=0x0127

#FW_BIN_PATH='fw/sta_fw_neo_20240216_fw0128.bin'
#STA_LAST_FW_VER=0x0128

#FW_BIN_PATH='fw/sta_fw_neo_20240217_fw0129.bin'
#STA_LAST_FW_VER=0x0129

#FW_BIN_PATH='fw/sta_fw_neo_20240221_fw012a.bin'
#STA_LAST_FW_VER=0x012a

#FW_BIN_PATH='fw/sta_fw_neo_20240226_fw012b.bin'
#STA_LAST_FW_VER=0x012b

FW_BIN_PATH='fw/sta_fw_neo_20240306pm0517_fw012c.bin'
STA_LAST_FW_VER=0x012c


#需要改為cache，最好timeout 1天
STA_FW_BIN=None
STA_FW_BIN_CS=0
STA_FW_BIN_SHA256=0
STA_FW_BIN_LEN=0

#white_list=['vyyXD7q64qydeiyI','0IZd5YFZ4DUHXhS4','8ickEfgM2oMh8Ysq','ibwdkwcbbdmwX7BT','ZJcpSdwZTdNu9OdG']
white_list=['JbQ1GlB59sMy3Clr','OmcLmx70ixjQsbeU','6w9cjMD6SNYQEh8U','rV1BOF9pTZQBnPMB','nRPuLSw3LvG1eCS6','cf3a639787f5d19e','M7ZHFH7X2sccG4la','JyNqYoYBzkYSAW5I','bMOg3ORYvt9KgSvS','DTOSQOMDaibd8T9D','tOhDgeDEsyciO7Hj','U530rDToDiscEXs9','ZJcpSdwZTdNu9OdG','SX_BABY_STA_0000','SX_BABY_STA_0001','4sdHmjsRsCPryNZc','hQCGSCqqReddkqpp','HYqppUq3Dd2XUIGB','M7ZHFH7X2sccG4la','6jRQQyrqqaxpyJdk','ubM7d67owCmHTMk8','0v3gvIDuuISY0v92','38qEvuuha4ImItOD','5c99f8a4e0fcddfa','WI655sb5aTBziEAx']
req_white_list=True

def calCs(bin):
    cs=0
    for v in bin:
        cs+=v;
    cs &= 0x00ffff
    return cs

def get_dfu_cxt():# 
    global STA_FW_BIN,STA_FW_BIN_CS,STA_FW_BIN_LEN,STA_FW_BIN_SHA256
    
    if(STA_FW_BIN != None):
        return(True,STA_FW_BIN,STA_FW_BIN_CS,STA_FW_BIN_LEN,STA_FW_BIN_SHA256)

    try:
        bio=io.BytesIO()
        s3_path=FW_BIN_PATH
        s3.download_fileobj(S3_BUCKET,s3_path, bio)
    except:
        traceback.print_exc()
        return (False,None,0,0,None)

    bio.seek(0)
    
    STA_FW_BIN=bio.read()
    STA_FW_BIN_CS=calCs(STA_FW_BIN)
    STA_FW_BIN_LEN=len(STA_FW_BIN)
    STA_FW_BIN_SHA256=sha256(STA_FW_BIN).hexdigest()
    return (True,STA_FW_BIN,STA_FW_BIN_CS,STA_FW_BIN_LEN,STA_FW_BIN_SHA256)
    

def handle_req_chk_fw(body):
    req_list=['sta_udid','fw_ver']
    res=RU.check_param(body,req_list)
    
    if(res[0]==False):
        return res

    sta_udid=body['sta_udid']
    fw_ver=body['fw_ver']
     
    print('handle_req_chk_fw: ',sta_udid,fw_ver)
        
    fw_key=CU.STA_LAST_FW_KEY_HEADER+sta_udid
    CU.set_cache_data(fw_key,{'fw':fw_ver,'ts':int(time.time())})
        
    if(fw_ver>=STA_LAST_FW_VER):
        return RU.gen_success_result({})
        
    if(req_white_list):
        if(sta_udid not in white_list):
            return RU.gen_success_result({})
        
    print('sta_udid in white list')

    res=get_dfu_cxt()

    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])

    fw_bin=res[1]
    fcs=res[2]
    total=res[3]
    sha=res[4]
    msg={"fw_ver":STA_LAST_FW_VER,"total":total,"fcs":fcs,'sha256':sha}

    return RU.gen_success_result(msg)

def handle_req_get_fw(body):
    req_list=['sta_udid','offset']
    res=RU.check_param(body,req_list)
    if(res[0]==False):
        return res
    
    sta_udid=body['sta_udid']
    offset=body['offset']
        
    res=get_dfu_cxt()

    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])
        
    fw_bin=res[1]
    total=res[3]

    max_pkg_size=20*1024

    pkg_size=total-offset
    if(pkg_size>max_pkg_size):
        pkg_size=max_pkg_size;
        
    pkg_bin=fw_bin[offset:(offset+pkg_size)]
    pcs=calCs(pkg_bin)
    
    next_offset=offset+pkg_size
    if(next_offset==total):
        next_offset=0;
        
    print('req_fw',sta_udid,offset,total)

    b64=base64.b64encode(pkg_bin).decode()#base64.b64encode得到是bytes，需要decode變成string
    msg={"b64_len":len(b64),"bin_len":pkg_size,"offset":offset,"next_offset":next_offset,"total":total,"pcs":pcs,"fw_ver":STA_LAST_FW_VER,"b64":b64}
        
    return RU.gen_success_result(msg)