import rest_util as RU
import aws_rds_util
from hashlib import sha256
import base64

white_list=['vyyXD7q64qydeiyI','AZKBL1pi0v5R4APm','ZJcpSdwZTdNu9OdG','HTGtFxz2liVEqzyy','dhDes7q7Wwr9oLDr']
req_white_list=False

MP3_CACHE=aws_rds_util.Cache(32,300)

def calCs(bin):
    cs=0
    for v in bin:
        cs+=v;
    cs &= 0x00ffff
    return cs
    
def handle_req_mp3_list_dummy(cur,body):
    req_list=['sta_udid']
    res=RU.check_param(body,req_list)
    if(res[0]==False):
        return res
    
    sta_udid=body['sta_udid']
        
    mp3_info_list=[]
    #1669786002
    mp3_info_list.append({'slot':1,'ts':1669786024,'del':0})
    mp3_info_list.append({'slot':2,'ts':1669786024,'del':0})
    mp3_info_list.append({'slot':3,'ts':1669786025,'del':0})
    mp3_info_list.append({'slot':4,'ts':1669786024,'del':0})
    mp3_info_list.append({'slot':5,'ts':1669786024,'del':0})
    msg={"mp3_list":mp3_info_list}

    return RU.gen_success_result(msg)
        
def get_mp3_cxt_dummy(cur,sta_udid,slot):
    global MP3_CACHE
    
    key="g_mp3_key_%02d"%(slot)
    info=MP3_CACHE.get(key)
    
    if(info != None):
        return(True,info['bin'],info['cs'],info['len'],info['sha'])
    
    res=aws_rds_util.getGeneralMp3Content(slot)

    if(res[0]==False):
        return res

    bin=res[1]
    
    info={}
    info['bin']=bin;
    info['cs']=calCs(bin);
    info['len']=len(bin);
    info['sha']=sha256(bin).hexdigest();
    
    MP3_CACHE.set(key,info)

    return(True,info['bin'],info['cs'],info['len'],info['sha'])
        
#==============================================================================
        
def handle_req_mp3_list(cur,body):
    req_list=['sta_udid']
    res=RU.check_param(body,req_list)
    if(res[0]==False):
        return res
    
    sta_udid=body['sta_udid']
        
    #===========================================================================
    #針對指定的sta，使其讀取共同的mp3，for test only，日後會置換過去
    if(req_white_list):
        if(sta_udid in white_list):
            return handle_req_mp3_list_dummy(cur,body)
    else:
        return handle_req_mp3_list_dummy(cur,body)
    #===========================================================================

    res=aws_rds_util.getMp3ListBelongToSta(cur,sta_udid)
    
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])

    mp3_info_raw_list=res[1]
    mp3_info_list=[]
    for item in mp3_info_raw_list:
        mp3_info={'slot':item[0],'ts':int(item[1]/1000),'del':item[2]}#convert ms to sec
        mp3_info_list.append(mp3_info)
    msg={"mp3_list":mp3_info_list}

    return RU.gen_success_result(msg)
    

def get_mp3_cxt(cur,sta_udid,slot):
    global MP3_CACHE
    
    #===========================================================================
    #針對指定的sta，使其讀取共同的mp3，for test only，日後會置換過去
    if(req_white_list):
        if(sta_udid in white_list):
            return get_mp3_cxt_dummy(cur,sta_udid,slot)
    else:
        return get_mp3_cxt_dummy(cur,sta_udid,slot)
    #===========================================================================
    
    key="%s#%02d"%(sta_udid,slot)
    info=MP3_CACHE.get(key)
    
    if(info != None):
        return(True,info['bin'],info['cs'],info['len'],info['sha'])

    res=aws_rds_util.getMp3BelongToSta(cur,sta_udid,slot)

    if(res[0]==False):
        return res

    bin=res[1]
    
    info={}
    info['bin']=bin;
    info['cs']=calCs(bin);
    info['len']=len(bin);
    info['sha']=sha256(bin).hexdigest();

    return(True,info['bin'],info['cs'],info['len'],info['sha'])
    

def handle_req_chk_mp3(cur,body):
    req_list=['sta_udid','slot']
    res=RU.check_param(body,req_list)
    if(res[0]==False):
        return res
    
    sta_udid=body['sta_udid']
    slot=body['slot']
        
    res=get_mp3_cxt(cur,sta_udid,slot)
    
    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])

    bin=res[1]
    fcs=res[2]
    total=res[3]
    sha=res[4]
    msg={"slot":slot,"total":total,"fcs":fcs,'sha256':sha}

    return RU.gen_success_result(msg)

def handle_req_get_mp3(cur,body):
    req_list=['sta_udid','slot','offset']
    res=RU.check_param(body,req_list)
    if(res[0]==False):
        return res
    
    sta_udid=body['sta_udid']
    slot=body['slot']
    offset=body['offset']
        
    res=get_mp3_cxt(cur,sta_udid,slot)

    if(res[0]==False):
        return RU.gen_error_result_by_code(res[1])

    bin=res[1]
    total=res[3]

    max_pkg_size=16*1024

    pkg_size=total-offset
    if(pkg_size>max_pkg_size):
        pkg_size=max_pkg_size;
        
    pkg_bin=bin[offset:(offset+pkg_size)]
    pcs=calCs(pkg_bin)
    
    next_offset=offset+pkg_size
    if(next_offset==total):
        next_offset=0;

    b64=base64.b64encode(pkg_bin).decode()#base64.b64encode得到是bytes，需要decode變成string
    msg={"b64_len":len(b64),"bin_len":pkg_size,"offset":offset,"next_offset":next_offset,"total":total,"pcs":pcs,"slot":slot,"b64":b64}
    
    return RU.gen_success_result(msg)