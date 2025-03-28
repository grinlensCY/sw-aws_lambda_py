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

#FW_BIN_PATH='fw/sta_fw_neo_20240306pm0517_fw012c.bin'
#STA_LAST_FW_VER=0x012c

#FW_BIN_PATH='fw/sta_fw_neo_20240325am0857_fw012d.bin'
#STA_LAST_FW_VER=0x012d

#FW_BIN_PATH='fw/sta_fw_neo_20240411_fw0130_mp3_first_prod.bin'
#STA_LAST_FW_VER=0x0130

#FW_BIN_PATH='fw/sta_fw_neo_20240514_fw0131_prod.bin'
#STA_LAST_FW_VER=0x0131

#FW_BIN_PATH='fw/sta_fw_neo_20240807_fw0132_prod.bin'
#STA_LAST_FW_VER=0x0132

#FW_BIN_PATH='fw/sta_fw_neo_20240924_fw0133_prod.bin'
#STA_LAST_FW_VER=0x0133

#FW_BIN_PATH='fw/sta_fw_neo_20240926pm0510_fw0134_prod.bin'
#STA_LAST_FW_VER=0x0134

#FW_BIN_PATH='fw/sta_fw_neo_20250107pm0338_fw0137_prod.bin'
#STA_LAST_FW_VER=0x0137

#FW_BIN_PATH='fw/sta_fw_neo_20250207pm0551_fw0138_prod.bin'
#STA_LAST_FW_VER=0x0138

FW_BIN_PATH='fw/sta_fw_neo_20250221am0952_fw0139_prod.bin'
STA_LAST_FW_VER=0x0139

#for exp===================================================
#FW_BIN_PATH_EXP='fw/sta_fw_neo_20241219am1008_fw0137_exp.bin'
#FW_BIN_PATH_EXP='fw/sta_fw_neo_20250107pm0338_fw0137_prod.bin'
#FW_BIN_PATH_EXP='fw/sta_fw_neo_20250207pm0551_fw0138_prod.bin'
FW_BIN_PATH_EXP='fw/sta_fw_neo_20250221am0952_fw0139_prod.bin'
STA_LAST_FW_VER_EXP=0x0139

#需要改為cache，最好timeout 1天
STA_FW_BIN=None
STA_FW_BIN_CS=0
STA_FW_BIN_SHA256=0
STA_FW_BIN_LEN=0

STA_EXP_FW_BIN=None
STA_EXP_FW_BIN_CS=0
STA_EXP_FW_BIN_SHA256=0
STA_EXP_FW_BIN_LEN=0

DEFAULT_STA_FW_INFO=None

white_list=['v9FQ2LuTkCGuoTEn','Wo6HEDDUKs4YYWYE','Osh6XtCo4y7Y8s4u','JbQ1GlB59sMy3Clr','OmcLmx70ixjQsbeU','6w9cjMD6SNYQEh8U','rV1BOF9pTZQBnPMB','nRPuLSw3LvG1eCS6','cf3a639787f5d19e','M7ZHFH7X2sccG4la','JyNqYoYBzkYSAW5I','bMOg3ORYvt9KgSvS','DTOSQOMDaibd8T9D','tOhDgeDEsyciO7Hj','U530rDToDiscEXs9','ZJcpSdwZTdNu9OdG','SX_BABY_STA_0000','SX_BABY_STA_0001','4sdHmjsRsCPryNZc','hQCGSCqqReddkqpp','HYqppUq3Dd2XUIGB','M7ZHFH7X2sccG4la','6jRQQyrqqaxpyJdk','ubM7d67owCmHTMk8','0v3gvIDuuISY0v92','38qEvuuha4ImItOD','5c99f8a4e0fcddfa','WI655sb5aTBziEAx']
#white_list_exp=['v9FQ2LuTkCGuoTEn','Wo6HEDDUKs4YYWYE','Osh6XtCo4y7Y8s4u','JbQ1GlB59sMy3Clr','CvXEx3wAxyD6nCxd','OmcLmx70ixjQsbeU','6w9cjMD6SNYQEh8U','rV1BOF9pTZQBnPMB','nRPuLSw3LvG1eCS6','cf3a639787f5d19e','M7ZHFH7X2sccG4la','JyNqYoYBzkYSAW5I','bMOg3ORYvt9KgSvS','DTOSQOMDaibd8T9D','tOhDgeDEsyciO7Hj','U530rDToDiscEXs9','ZJcpSdwZTdNu9OdG','SX_BABY_STA_0000','SX_BABY_STA_0001','4sdHmjsRsCPryNZc','hQCGSCqqReddkqpp','HYqppUq3Dd2XUIGB','M7ZHFH7X2sccG4la','6jRQQyrqqaxpyJdk','ubM7d67owCmHTMk8','0v3gvIDuuISY0v92','38qEvuuha4ImItOD','5c99f8a4e0fcddfa','WI655sb5aTBziEAx']
#white_list_exp=['1rbpbDRRVdX2ZDFs','mbeUP8Ahoh914mPu','Tb1l538jIJHhsrrg','rV1BOF9pTZQBnPMB','U530rDToDiscEXs9','CvXEx3wAxyD6nCxd','ZJcpSdwZTdNu9OdG','M7ZHFH7X2sccG4la','JbQ1GlB59sMy3Clr','SX_BABY_STA_0000','SX_BABY_STA_0001']
white_list_exp=['SX_BABY_STA_0000','DTOSQOMDaibd8T9D','za9yW6yohNvEvIu5','eqg1vqm6OeMejmqP','U530rDToDiscEXs9','CvXEx3wAxyD6nCxd','ZJcpSdwZTdNu9OdG']

req_white_list=False
req_white_list_exp=False

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
    
def get_dfu_cxt_exp():# 
    global STA_EXP_FW_BIN,STA_EXP_FW_BIN_CS,STA_EXP_FW_BIN_LEN,STA_EXP_FW_BIN_SHA256
    
    if(STA_EXP_FW_BIN != None):
        return(True,STA_EXP_FW_BIN,STA_EXP_FW_BIN_CS,STA_EXP_FW_BIN_LEN,STA_EXP_FW_BIN_SHA256)

    try:
        bio=io.BytesIO()
        s3_path=FW_BIN_PATH_EXP
        s3.download_fileobj(S3_BUCKET,s3_path, bio)
    except:
        traceback.print_exc()
        return (False,None,0,0,None)

    bio.seek(0)
    
    STA_EXP_FW_BIN=bio.read()
    STA_EXP_FW_BIN_CS=calCs(STA_EXP_FW_BIN)
    STA_EXP_FW_BIN_LEN=len(STA_EXP_FW_BIN)
    STA_EXP_FW_BIN_SHA256=sha256(STA_EXP_FW_BIN).hexdigest()
    return (True,STA_EXP_FW_BIN,STA_EXP_FW_BIN_CS,STA_EXP_FW_BIN_LEN,STA_EXP_FW_BIN_SHA256)
    

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
    
    req_exp_fw=False
    
    if(req_white_list_exp and sta_udid in white_list_exp and fw_ver<STA_LAST_FW_VER_EXP):
        req_exp_fw=True
        print('AAAAAAAAAAAAAA EXPPPPPPPPPPPPPPPPPPPPPPPPP')
    
    else:
        if(fw_ver>=STA_LAST_FW_VER):
            return RU.gen_success_result({})
            
        if(req_white_list):
            if(sta_udid not in white_list):
                return RU.gen_success_result({})
        
    print('sta_udid in white list')
    
    res=[False,None]
    if(req_exp_fw):
        res=get_dfu_cxt_exp()
        fw_ver=STA_LAST_FW_VER_EXP
    else:
        res=get_dfu_cxt()
        fw_ver=STA_LAST_FW_VER

    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])

    fw_bin=res[1]
    fcs=res[2]
    total=res[3]
    sha=res[4]
    msg={"fw_ver":fw_ver,"total":total,"fcs":fcs,'sha256':sha}

    return RU.gen_success_result(msg)

def handle_req_get_fw(body):
    req_list=['sta_udid','offset']
    res=RU.check_param(body,req_list)
    if(res[0]==False):
        return res
    
    sta_udid=body['sta_udid']
    offset=body['offset']
        
    if(req_white_list_exp and sta_udid in white_list_exp):
        res=get_dfu_cxt_exp()
        fw_ver=STA_LAST_FW_VER_EXP
    else:
        res=get_dfu_cxt()
        fw_ver=STA_LAST_FW_VER

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
    msg={"b64_len":len(b64),"bin_len":pkg_size,"offset":offset,"next_offset":next_offset,"total":total,"pcs":pcs,"fw_ver":fw_ver,"b64":b64}
        
    return RU.gen_success_result(msg)