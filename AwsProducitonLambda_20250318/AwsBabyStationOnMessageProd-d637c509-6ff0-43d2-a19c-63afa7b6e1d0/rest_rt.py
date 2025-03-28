import statistics as STAT
import trend as TREND
import cache_util as CU
import rest_util as RU
import db_cache as DC
import aws_rds_util
import json
import sleep_status as SS
import time
import rest_notify as RN
import boto3
from botocore.exceptions import ClientError

lambda_client = boto3.client('lambda')

warn_title_map_zh={
    'hrH_n':'裝置通知',
    'hrL_n':'裝置通知',
    'rrH_n':'裝置通知',
    'rrL_n':'裝置通知',
    'tmpH_n':'裝置通知',
    'tmpL_n':'裝置通知',
    'choking_n':'裝置通知',
    'obsnd_n':'裝置通知',
    'diarrhea_n':'裝置通知',
    'wakeup_n':'裝置通知',
    'bs_n':'裝置通知',
}

warn_desc01_map_zh={
    'hrH_n':'心跳偏快 ',
    'hrL_n':'心跳偏 慢',
    'rrH_n':'呼吸率偏快 ',
    'rrL_n':'呼吸率偏慢 ',
    'tmpH_n':'腹部溫度偏高 ',
    'tmpL_n':'腹部溫度偏低 ',
    'choking_n':'嗆奶等阻塞 ',
    'obsnd_n':'鼾聲鼻涕聲 ',
    'diarrhea_n':'大量排泄或腹瀉 ',
    'wakeup_n':'寶寶即將清醒 ',
    'bs_n':'腸胃蠕動頻繁或偏低 ',
}

warn_desc02_map_zh={
    'hrH_n':'快去看看寶寶',
    'hrL_n':'快去看看寶寶',
    'rrH_n':'快去看看寶寶',
    'rrL_n':'快去看看寶寶',
    'tmpH_n':'快去看看寶寶',
    'tmpL_n':'快去看看寶寶',
    'choking_n':'快去看看寶寶',
    'obsnd_n':'快去看看寶寶',
    'diarrhea_n':'快去看看寶寶',
    'wakeup_n':'快去看看寶寶',
    'bs_n':'快去看看寶寶',
}

#...............................................................................
warn_title_map_en={
    'hrH_n':'Device Notify',
    'hrL_n':'Device Notify',
    'rrH_n':'Device Notify',
    'rrL_n':'Device Notify',
    'tmpH_n':'Device Notify',
    'tmpL_n':'Device Notify',
    'choking_n':'Device Notify',
    'obsnd_n':'Device Notify',
    'diarrhea_n':'Device Notify',
    'wakeup_n':'Device Notify',
    'bs_n':'Device Notify',
}

warn_desc01_map_en={
    'hrH_n':'Fast Heartbeat ',
    'hrL_n':'Slow Heartbeat ',
    'rrH_n':'Fast Breathing Rate ',
    'rrL_n':'Slow Breathing Rate ',
    'tmpH_n':'High Abdominal Temp. ',
    'tmpL_n':'Low Abdominal Temp. ',
    'choking_n':'Choking ',
    'obsnd_n':'Snore-Like ',
    'diarrhea_n':'Excretion or Diarrhea ',
    'wakeup_n':'About to Wake Up ',
    'bs_n':'Digestive Frequency ',
}

warn_desc02_map_en={
    'hrH_n':'Please check out your baby!',
    'hrL_n':'Please check out your baby!',
    'rrH_n':'Please check out your baby!',
    'rrL_n':'Please check out your baby!',
    'tmpH_n':'Please check out your baby!',
    'tmpL_n':'Please check out your baby!',
    'choking_n':'Please check out your baby!',
    'obsnd_n':'Please check out your baby!',
    'diarrhea_n':'Please check out your baby!',
    'wakeup_n':'Please check out your baby!',
    'bs_n':'Please check out your baby!',
}

warnContinueSameEventCnt=18

def get_msg_maps(lang):
    if(lang=='zh' or lang=='tw'):
        return (warn_title_map_zh,warn_desc01_map_zh,warn_desc02_map_zh) 
    else:
        return (warn_title_map_en,warn_desc01_map_en,warn_desc02_map_en) 
        
def get_warn_info(lang,bn,type,limit):
    title_map,desc01_map,desc02_map=get_msg_maps(lang)
    title=title_map[type]
    desc01=desc01_map[type]
    desc02=desc02_map[type]
    
    #if(limit==None):
    #    body=bn+' '+desc01+desc02
    #else:
    #    body=bn+' '+desc01+"{:.1f}".format(limit)+desc02
    body=bn+' '+desc01+desc02
    return title,body
    
def send_push_notification(uid,cur,dev_udid,type,limit):
    print("REST RT AAA NOTIFICATION",dev_udid,type,limit);
    
    res=aws_rds_util.getBabyIdAndDevIdByDevUdidThroughCache(cur,dev_udid)
    
    req_alarm=True
    if(type=='tmpL_n' or type == 'tmpH_n' or type == 'wakeup_n' or type=='obsnd_n' or type=='diarrhea_n' or type=='bs_n'):
        req_alarm=False
        
    
    if(res!=None and res[0]==True):
        baby_id=res[1][0]
        res=aws_rds_util.getBabyNameById(cur,baby_id)
        if(res !=None and res[0]==True):
            bn=res[1][0]
            
            key=CU.USER_PHONE_SET_KEY_HEADER+uid
            tokens=CU.get_set_items(key)
            
            for token in tokens:
                token=token.decode()
                
                lang_key=CU.USER_LANG_KEY_HEADER+token
                lang=CU.get_cache_data(lang_key)
                if(lang==None):
                    lang='en'
                
                title,body=get_warn_info(lang,bn,type,limit)
                
                inputParams = {
                    "token": token,
                    "title":title,
                    "body":body,
                    "data": {'req_alarm':req_alarm},
                }
        
                response = lambda_client.invoke(
                    #FunctionName = 'arn:aws:lambda:ap-northeast-1:227225135945:function:AwsBabyApiV2-PushNotification',
                    FunctionName = 'arn:aws:lambda:ap-northeast-1:227225135945:function:babymonneoApi-Notification',
                    InvocationType = 'RequestResponse',
                    Payload = json.dumps(inputParams)
                )
                
                if response['StatusCode']==200:
                    str=response['Payload'].read()
                    if(str != None):
                        msg=str.decode()
                        jobj=json.loads(msg)
                        if(jobj['statusCode']!=200):
                            print(response)
                            print(jobj)
                            CU.remove_set_item(key,token)
                            CU.del_cache_data(lang_key)
#===============================================================================

'''
def add_data_to_trend_queue(dev_udid,dat):
    cts=dat['ts']
    trend_key=CU.TREND_DATA_QUEUE_KEY_HEADER+dev_udid

    fifo_len=CU.list_append(trend_key,dat)
    if(fifo_len>(3600*4/10+64)):
        CU.list_pop(trend_key)

    #check stat time slot
    first_item=CU.list_get(trend_key,0)
    bts=first_item['ts']
    cts_slot=TREND.cal_time_slot(cts)
    bts_slot=TREND.cal_time_slot(bts)
    if(bts_slot != cts_slot):
        #cal static
        data_list=CU.list_get_range(trend_key,0,fifo_len-1)
        CU.list_trim(trend_key,fifo_len-1,fifo_len)
        res=TREND.cal(data_list)
'''
def get_last_realtime_cache(dev_udid):
    rt_key=CU.REALTIME_DATA_KEY_HEADER+dev_udid
    
    return CU.get_cache_data(rt_key)

def add_data_to_realtime_cache(dev_udid,dat):
    rt_key=CU.REALTIME_DATA_KEY_HEADER+dev_udid
    
    CU.set_cache_data(rt_key,dat,16*60)#只保留15分鐘
    
    #if(dev_udid=='253f5b71be7169bb'):
    #    print(dev_udid,dat)
    
def check_var_limit(vars,val,cl,hv,lv,hc_item,lc_item):
    global warnContinueSameEventCnt
    res_h=False
    res_l=False
    
    if(val!=0 and val>hv and cl>5):
        vars[hc_item]+=1
        vars[lc_item]=0
        if(vars[hc_item]>=warnContinueSameEventCnt):
            vars[hc_item]=warnContinueSameEventCnt
            res_h=True
            
        #print("REST RT AAAAA limit",hc_item,vars[hc_item],val,cl,hv,lv)
            
    elif(val!=0 and val<lv and cl>5):
        vars[lc_item]+=1
        vars[hc_item]=0
        if(vars[lc_item]>=warnContinueSameEventCnt):
            vars[lc_item]=warnContinueSameEventCnt
            res_l=True
            
        #print("REST RT AAAAA limit",lc_item,vars[lc_item],val,cl,hv,lv)
    
    else:
        vars[hc_item]=0
        vars[lc_item]=0
        
    return (res_h,res_l)

def save_event_vars(sta_udid,dev_udid,tmp):
    if tmp[0]:
        evt_idx=tmp[1]

        inputParams = {
            "sta_udid": sta_udid,
            "dev_udid":dev_udid,
            "evt_idx":evt_idx,
        }

        response = lambda_client.invoke(
            FunctionName = 'arn:aws:lambda:ap-northeast-1:227225135945:function:AwsBabyStationSaveEventVars',
            InvocationType = 'Event',
            Payload = json.dumps(inputParams)
        )

    
def update_notify(vs,item,curr_state,cts,redis_key,redis_type):
    notify_sep_ts_in_sec=10*60  #10mins
    
    if(item not in vs):
        var={'is_true':False,'ts':0}
        vs[item]=var
    else:
        var=vs[item]

    #只有從false切換為true的情況才會設定redis，並設定var為true
    #若curr state為false，則直接設定var為false=>改為不處理，只要記錄事件的時間即可
    if(curr_state):
        #print('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',var,cts)
        #if( var['is_true']==False or (cts-var['ts'])>notify_sep_ts_in_sec):
        if((cts-var['ts'])>notify_sep_ts_in_sec):
            CU.set_cache_data(redis_key,{'type':redis_type,"ts":cts});
            vs[item]={'is_true':True,'ts':cts}
            return True
    else:
        #vs[item]={'is_true':False,'ts':0}
        return False

def add_evt_idx_info_to_var(vars,item,tmp):
    if tmp[0]:
        evt_id=tmp[1]
        if(vars[item] != None):
            vars[item]['evt_id']=evt_id
    
def check_limit(cognito_id,cur,conn,sta_udid,dev_udid,dat,last_data,get_bs_evt,is_wakeup,is_fatal_alarm):
    msg=dat['msg']
    well_att=msg['well_att']
    if(well_att==False):
        return

    cts_ms=int(time.time()*1000);
    cts=cts_ms/1000
    
    #if last_data is not well_att, set ts of change to well att
    last_msg=last_data['msg']
    if(last_msg['well_att']==False):
        dat['chg_to_well_att_ts']=cts
    else:
        if('chg_to_well_att_ts' in last_data):
            dat['chg_to_well_att_ts']=last_data['chg_to_well_att_ts']
        else:
            dat['chg_to_well_att_ts']=cts

    chg_to_well_att_ts=dat['chg_to_well_att_ts']
    
    #get tag cfg
    res=DC.get_tag_cfg(cognito_id,dev_udid)

    if(res is None or res[0]==False):
        return
    try:
        cfg=json.loads(res[1])
    except:
        return
    
    #get sta cfg
    res=DC.load_sta_cfg(cognito_id)
    
    #from sta cfg
    nHrE=False
    nRrE=False
    nTempE=False
    nDiarrheaE=False
    nChokingE=False 
    nObsndE=False 
    nBsE=False
    nWakeupE=False
    
    if(res is None or res[0]==False):
        pass
    try:
        sta_cfg=json.loads(res[1])
        
        #from sta cfg
        nHrE=sta_cfg['hr']
        nRrE=sta_cfg['rr']
        nTempE=sta_cfg['tmp']
        nDiarrheaE=sta_cfg['exc']
        nChokingE=sta_cfg['rq']
        nObsndE=sta_cfg['ot']
        nBsE=sta_cfg['da']
        nWakeupE=sta_cfg['wu']
    except:
        print('fail to load enable cfg',res)

    #{"hrH":130.0,"hrL":80.0,"rrH":50.0,"rrL":15.0,"tempH":37.0,"tempL":33.0,"nHrE":False,"nRrE":False,"nTempE":False}
    hrH=cfg['hrH']
    hrL=cfg['hrL']
    rrH=cfg['rrH']
    rrL=cfg['rrL']
    tmpH=cfg['tempH']
    tmpL=cfg['tempL']
    #nHrE=cfg['nHrE']
    #nRrE=cfg['nRrE']
    #nTempE=cfg['nTempE']

    #get cur dat
    imu_tmp=msg['imu_tmp']
    hr=msg['hr']
    rr=msg['rr']
    hr_cl=msg['hr_cl']
    rr_cl=msg['rr_cl']
    
    get_hrh_notify=False
    get_hrl_notify=False
    get_rrh_notify=False
    get_rrl_notify=False
    get_tmph_notify=False
    get_tmpl_notify=False
    
    key=CU.NOTIFY_VAR_KEY_HEADER+dev_udid
    if(nTempE or nHrE or nRrE or nDiarrheaE or nChokingE or nObsndE or nBsE):
        vars=CU.get_cache_data(key)
        if(vars is None):
            vars={'hrH_cnt':0,'hrL_cnt':0,'rrH_cnt':0,'rrL_cnt':0,'tmpH_cnt':0,'tmpL_cnt':0,
                'hrH_n':{'is_true':False,'ts':0},
                'hrL_n':{'is_true':False,'ts':0},
                'rrH_n':{'is_true':False,'ts':0},
                'rrL_n':{'is_true':False,'ts':0},
                'tmpH_n':{'is_true':False,'ts':0},
                'tmpL_n':{'is_true':False,'ts':0},
                'choking_n':{'is_true':False,'ts':0},
                'obsnd_n':{'is_true':False,'ts':0},
                'diarrhea_n':{'is_true':False,'ts':0},
                'bs_n':{'is_true':False,'ts':0},
                'wakeup_n':{'is_true':False,'ts':0}
            }
    else:#若沒有啟動，則不需檢查
        return
    
    if(nHrE):
        #print("REST RT BBBBBB",hr,hr_cl,hrH,hrL)
        get_hrh_notify,get_hrl_notify=check_var_limit(vars,hr,hr_cl,hrH,hrL,'hrH_cnt','hrL_cnt')
            
    if(nRrE):
        get_rrh_notify,get_rrl_notify=check_var_limit(vars,rr,rr_cl,rrH,rrL,'rrH_cnt','rrL_cnt')
            
    if(nTempE and (cts-chg_to_well_att_ts)>(5*60)):#如果離切換well att的時間間隔超過五分鐘
        get_tmph_notify,get_tmpl_notify=check_var_limit(vars,imu_tmp,10,tmpH,tmpL,'tmpH_cnt','tmpL_cnt')
        
    req_debug_print=False
    #if(dev_udid=='253f5b71be7169bb'):
    #    req_debug_print=True
    #    print(dev_udid,get_hrh_notify,get_hrl_notify,get_rrh_notify,get_rrl_notify,get_tmph_notify,get_tmpl_notify,vars)
        
    #get lang of user
    '''
    lang='en'
    if(get_hrh_notify or get_hrl_notify or get_rrh_notify or get_rrl_notify or get_tmph_notify or get_tmpl_notify):
        lang_key=CU.USER_LANG_KEY_HEADER+cognito_id
        lang=CU.get_cache_data(lang_key)
        if(lang==None):
            lang='en'
    '''
    
    #===========================================================================
    #test only
    '''
    if(sta_udid=='vyyXD7q64qydeiyI' and req_debug_print):
        lang_key=CU.USER_LANG_KEY_HEADER+cognito_id
        lang=CU.get_cache_data(lang_key)
        if(lang==None):
            lang='en'
        

        send_push_notification(cognito_id,cur,dev_udid,'tmpL_n',tmpL,lang)
    '''
    #===========================================================================
    if(nBsE==False):
        get_bs_evt=False

    res=update_notify(vars,'bs_n',get_bs_evt,cts,
                    CU.PREF_NOTIFY_ALARM_BS_KEY_HEADER+cognito_id,
                    RN.AWS_NOTIFY_BS)
                    
    if(res):
        if(nBsE):
            tmp=aws_rds_util.addEventByDevUdid(cur,conn,dev_udid,aws_rds_util.EVENT_TYPE_BS,cts_ms)
            add_evt_idx_info_to_var(vars,'bs_n',tmp)
            save_event_vars(sta_udid,dev_udid,tmp)
            send_push_notification(cognito_id,cur,dev_udid,'bs_n',None)

        if req_debug_print:
            print(dev_udid,'write bs to db')

    #===========================================================================
    if(nWakeupE==False):
        is_wakeup=False    
    
    res=update_notify(vars,'wakeup_n',is_wakeup,cts,
                    CU.PREF_NOTIFY_ALARM_WAKEUP_KEY_HEADER+cognito_id,
                    RN.AWS_NOTIFY_WAKEUP)
                    
    #print('WWWWWWWWWWWWWWWW00',dev_udid,is_wakeup,'send notification')
                    
    if(res):
        if(nWakeupE):
            #print('WWWWWWWWWWWWWWWW01',dev_udid,'send notification')
            tmp=aws_rds_util.addEventByDevUdid(cur,conn,dev_udid,aws_rds_util.EVENT_TYPE_WAKEUP,cts_ms)
            add_evt_idx_info_to_var(vars,'wakeup_n',tmp)
            save_event_vars(sta_udid,dev_udid,tmp)
            send_push_notification(cognito_id,cur,dev_udid,'wakeup_n',None)

        #print('WWWWWWWWWWWWWWWW02',dev_udid,nWakeupE,is_wakeup)
        
        if req_debug_print:
            print(dev_udid,'write wakeup to db')
    
    #===========================================================================
    
    #odd_alg_res={'ts':esp_ts,'has_poo':has_poo,'has_obs':has_obs,'req_obs_alarm':req_obs_alarm}
    odd_alg_res_key=CU.ODD_SND_RES_KEY_HEADER+dev_udid
    
    get_choking=False
    get_obsnd=False
    get_diarrhea=False
    
    if(nChokingE):
        get_choking=is_fatal_alarm
    
    odd_alg_res=CU.get_cache_data(odd_alg_res_key)
    if(odd_alg_res!=None and 'has_poo' in odd_alg_res and 'req_obs_alarm' in odd_alg_res):
        CU.del_cache_data(odd_alg_res_key)
        
        if(nDiarrheaE):
            get_diarrhea=odd_alg_res['has_poo']
        
        if(nObsndE):
            get_obsnd=odd_alg_res['req_obs_alarm']
            
    #===========================================================================

    #'choking_n':'裝置通知',
    res=update_notify(vars,'choking_n',get_choking,cts,
                    CU.PREF_NOTIFY_ALARM_CHOKING_KEY_HEADER+cognito_id,
                    RN.AWS_NOTIFY_CHOKING)

    if(res):
        if(nChokingE):
            tmp=aws_rds_util.addEventByDevUdid(cur,conn,dev_udid,aws_rds_util.EVENT_TYPE_CHOKIN,cts_ms)
            add_evt_idx_info_to_var(vars,'choking_n',tmp)
            save_event_vars(sta_udid,dev_udid,tmp)
            send_push_notification(cognito_id,cur,dev_udid,'choking_n',None)

        if req_debug_print:
            print(dev_udid,'write choking to db')

    #'obsnd_n':'裝置通知',
    res=update_notify(vars,'obsnd_n',get_obsnd,cts,
                    CU.PREF_NOTIFY_ALARM_OBSND_KEY_HEADER+cognito_id,
                    RN.AWS_NOTIFY_OBS)

    if(res):
        if(nObsndE):
            tmp=aws_rds_util.addEventByDevUdid(cur,conn,dev_udid,aws_rds_util.EVENT_TYPE_OBS,cts_ms)
            add_evt_idx_info_to_var(vars,'obsnd_n',tmp)
            save_event_vars(sta_udid,dev_udid,tmp)
            send_push_notification(cognito_id,cur,dev_udid,'obsnd_n',None)

        if req_debug_print:
            print(dev_udid,'write obsnd to db')
        
    #'diarrhea_n':'裝置通知',
    res=update_notify(vars,'diarrhea_n',get_diarrhea,cts,
                    CU.PREF_NOTIFY_ALARM_DIARRHEA_KEY_HEADER+cognito_id,
                    RN.AWS_NOTIFY_DIARRHEA)
    
    if(res):
        if(nDiarrheaE):
            tmp=aws_rds_util.addEventByDevUdid(cur,conn,dev_udid,aws_rds_util.EVENT_TYPE_DIARRHEA,cts_ms)
            add_evt_idx_info_to_var(vars,'diarrhea_n',tmp)
            save_event_vars(sta_udid,dev_udid,tmp)
            send_push_notification(cognito_id,cur,dev_udid,'diarrhea_n',None)

        if req_debug_print:
            print(dev_udid,'write diarrhea to db')
    
    #hr
    res=update_notify(vars,'hrH_n',get_hrh_notify,cts,
                    CU.PREF_NOTIFY_ALARM_HR_KEY_HEADER+cognito_id,
                    RN.AWS_NOTIFY_HR)
    
    if(res):
        if(nHrE):
            tmp=aws_rds_util.addEventByDevUdid(cur,conn,dev_udid,aws_rds_util.EVENT_TYPE_HR_H,cts_ms)
            add_evt_idx_info_to_var(vars,'hrH_n',tmp)
            save_event_vars(sta_udid,dev_udid,tmp)
            send_push_notification(cognito_id,cur,dev_udid,'hrH_n',hrH)

        if req_debug_print:
            print(dev_udid,'write hrh to db')
                    
    res=update_notify(vars,'hrL_n',get_hrl_notify,cts,
                    CU.PREF_NOTIFY_ALARM_HR_KEY_HEADER+cognito_id,
                    RN.AWS_NOTIFY_HR)
    if(res):
        if(nHrE):
            tmp=aws_rds_util.addEventByDevUdid(cur,conn,dev_udid,aws_rds_util.EVENT_TYPE_HR_L,cts_ms)
            add_evt_idx_info_to_var(vars,'hrL_n',tmp)
            save_event_vars(sta_udid,dev_udid,tmp)
            send_push_notification(cognito_id,cur,dev_udid,'hrL_n',hrL)

        if req_debug_print:
            print(dev_udid,'write hrl to db')
    #rr
    res=update_notify(vars,'rrH_n',get_rrh_notify,cts,
                    CU.PREF_NOTIFY_ALARM_RR_KEY_HEADER+cognito_id,
                    RN.AWS_NOTIFY_RR)
    if(res):
        if(nRrE):
            tmp=aws_rds_util.addEventByDevUdid(cur,conn,dev_udid,aws_rds_util.EVENT_TYPE_RR_H,cts_ms)
            add_evt_idx_info_to_var(vars,'rrH_n',tmp)
            save_event_vars(sta_udid,dev_udid,tmp)
            send_push_notification(cognito_id,cur,dev_udid,'rrH_n',rrH)

        if req_debug_print:
            print(dev_udid,'write rrh to db')        
                    
    res=update_notify(vars,'rrL_n',get_rrl_notify,cts,
                    CU.PREF_NOTIFY_ALARM_RR_KEY_HEADER+cognito_id,
                    RN.AWS_NOTIFY_RR)
    if(res):
        if(nRrE):
            tmp=aws_rds_util.addEventByDevUdid(cur,conn,dev_udid,aws_rds_util.EVENT_TYPE_RR_L,cts_ms)
            add_evt_idx_info_to_var(vars,'rrL_n',tmp)
            save_event_vars(sta_udid,dev_udid,tmp)
            send_push_notification(cognito_id,cur,dev_udid,'rrL_n',rrL)

        if req_debug_print:
            print(dev_udid,'write rrl to db')

    #tmp
    res=update_notify(vars,'tmpH_n',get_tmph_notify,cts,
                    CU.PREF_NOTIFY_ALARM_TEMP_KEY_HEADER+cognito_id,
                    RN.AWS_NOTIFY_TEMPERATURE)
    if(res):
        if(nTempE):
            tmp=aws_rds_util.addEventByDevUdid(cur,conn,dev_udid,aws_rds_util.EVENT_TYPE_TMP_H,cts_ms)
            add_evt_idx_info_to_var(vars,'tmpH_n',tmp)
            save_event_vars(sta_udid,dev_udid,tmp)
            send_push_notification(cognito_id,cur,dev_udid,'tmpH_n',tmpH)

        if req_debug_print:
            print(dev_udid,'write tmph to db')
        
    res=update_notify(vars,'tmpL_n',get_tmpl_notify,cts,
                    CU.PREF_NOTIFY_ALARM_TEMP_KEY_HEADER+cognito_id,
                    RN.AWS_NOTIFY_TEMPERATURE)
                    
    if(res):
        if(nTempE):
            tmp=aws_rds_util.addEventByDevUdid(cur,conn,dev_udid,aws_rds_util.EVENT_TYPE_TMP_L,cts_ms)
            add_evt_idx_info_to_var(vars,'tmpL_n',tmp)
            save_event_vars(sta_udid,dev_udid,tmp)
            send_push_notification(cognito_id,cur,dev_udid,'tmpL_n',tmpL)
            
        if req_debug_print:
            print(dev_udid,'write tmpl to db')
 
    CU.set_cache_data(key,vars,3600)
    
    dn_key=CU.NOTIFY_RES_KEY_HEADER+dev_udid

    dn={}
    dn['dev_udid']=dev_udid
    dn['hrH_n']=vars['hrH_n']
    dn['hrL_n']=vars['hrL_n']
    dn['rrH_n']=vars['rrH_n']
    dn['rrL_n']=vars['rrL_n']
    dn['tmpH_n']=vars['tmpH_n']
    dn['tmpL_n']=vars['tmpL_n']
    
    if('choking_n' in vars):
        dn['choking_n']=vars['choking_n']
    if('obsnd_n' in vars):
        dn['obsnd_n']=vars['obsnd_n']
    if('diarrhea_n' in vars):
        dn['diarrhea_n']=vars['diarrhea_n']
    if('bs_n' in vars):
        dn['bs_n']=vars['bs_n']
    if('wakeup_n' in vars):
        dn['wakeup_n']=vars['wakeup_n']
        
    CU.set_cache_data(dn_key,dn,60*30)
    
def get_baby_age(cognito_id,cur,dev_udid):
    #要取得baby age
    res=aws_rds_util.getDevIdByUdid(cur,dev_udid)

    if(res==None or res[0]==False):
        return 0,0
        
    did=res[1]#dev id
        
    res=aws_rds_util.getBabyBidAndBirthdayByDevId(cur,cognito_id,did)

    #有可能查不到baby而回傳(True,None)
    if(res==None or res[0]==False or res[1]==None):
        return 0,0
       
    bid,birthday_ts=res[1]
    
    #計算年紀in month
    age_cts=time.time()
    bts=birthday_ts/1000.0#convert to sec
    diff_ts=(age_cts-bts)
    
    if(diff_ts<0):
        #不該發生，未來人
        return 0,0
        
    month=diff_ts/(86400*30.0)#粗略用一個月三十天計算
    return month,bid

def has_multi_active_tag(cur,cognito_id,dev_udid):
    res=aws_rds_util.getDevUdidListOfUser(cur,cognito_id)
    if(res[0]==False):
        print('WWWWWWWWWWWwww01 false')
        return False

    udid_list=res[1]
    if(len(udid_list)<=1):
        print('WWWWWWWWWWWwww02 false')
        return False

    for item in udid_list:
        if(dev_udid==item):
            continue

        last_data=get_last_realtime_cache(item)
        if last_data != None and 'msg' in last_data:
            msg=last_data['msg']
            if 'well_att' in msg and msg['well_att']>0:
                print('WWWWWWWWWWWwww03','has multi active dev',item)
                return True

    print('WWWWWWWWWWWwww04','only one dev')
    return False

def add_data_to_stat_buffer(cognito_id,cur,conn,dev_udid,dat):
    cts=dat['ts']
    stat_key=CU.STAT_DATA_KEY_HEADER+dev_udid
    
    alg_cts_ms=int(time.time()*1000)
    alg_cts=int(time.time())
    
    #load data
    #dat={'sta':sta_udid,'msg':msg,'tick':tick,'ts':esp_ts}
    msg=dat['msg']
    hr=msg['hr']
    rr=msg['rr']
    hr_cl=msg['hr_cl']
    rr_cl=msg['rr_cl']
    
    if 'still_cnt' in msg:
        sc=msg['still_cnt']
    else:
        sc=dat['tick'] & 0x00ff;
    
    #cal sleep status
    hrdat=[hr,hr_cl]
    rrdat=[rr,rr_cl]
    
    isAwake=False
    isFatalAlarm=False
    
    sleep_status=0
    
    is_well_att='well_att' in msg and msg['well_att']==1
    
    #=======================================================================
    #要取得baby age
    month,bid=get_baby_age(cognito_id,cur,dev_udid)
    #=======================================================================
    
    ss=SS.SleepStatus_FatalAlarm(dev_udid,month)
    _,_,sleepstages,goComfort,isAwake,isFatalAlarm,_=ss.addData(dev_udid,cts/1000.0,hrdat,rrdat,sc,is_well_att)
    
    if(sleepstages is not None and len(sleepstages)>0):
        #def saveSleepStage(cur,conn,cognito_id,bid,ts,map):
        aws_rds_util.saveSleepStage(cur,conn,cognito_id,bid,alg_cts_ms,sleepstages)
        print('qqqqqqqqqqqqqqqqqqqqq','SS.SleepStatus',cognito_id,bid,alg_cts_ms,sleepstages)

    
    if(is_well_att):
        #檢查goComfort與前次相比是否有改變，如果改變的話，就要送出指令給Esp32
        #20240326 jd: 下面這個key是給sta go comfort指示用的，但在此一併作為保留go comfort與awake狀態的用途
        cf_key=CU.SLEEP_REQ_COMFORT_KEY_HEADER+dev_udid
        
        pre_res=CU.get_cache_data(cf_key)
        
        pre_comfort=False
        pre_go_comfort_ts=0
        
        pre_awake=False
        pre_awake_ts=0
        
        if(pre_res != None):
            pre_comfort=pre_res['state']
            pre_go_comfort_ts=pre_res['go_comfort_ts']
            
            pre_awake=pre_res['is_awake']
            pre_awake_ts=pre_res['is_awake_ts']
        
        #get sta cfg
        req_wakeup_notify=False
        
        res=DC.load_sta_cfg(cognito_id)
        if(res is None or res[0]==False):
            req_wakeup_notify=False
        try:
            sta_cfg=json.loads(res[1])
            req_wakeup_notify=sta_cfg['wu']
        except:
            req_wakeup_notify=False
        
        if(pre_awake==False and isAwake and (pre_awake_ts==0 or (alg_cts-pre_awake_ts)>10*60)):
            #if(req_wakeup_notify):#只要傳給手機就好，sta有其他機制傳送go comfort
            #    send_push_notification(cognito_id,cur,dev_udid,'wakeup_n',None)
            #aws_rds_util.addEventByDevUdid(cur,conn,dev_udid,aws_rds_util.EVENT_TYPE_WAKEUP,alg_cts_ms)
            #因為改由check limit function去間隔10min，pre_awake_ts不再被需要，以後可以去掉
            pre_awake_ts=alg_cts
         
        #for test   
        #if(dev_udid=='SX_BABY_MON_0003'):
        #    goComfort=True
        #    pre_go_comfort_ts=0;
        
        if(pre_comfort==False and goComfort and (pre_go_comfort_ts==0 or (alg_cts-pre_go_comfort_ts)>10*60)):
            aws_rds_util.addEventByDevUdid(cur,conn,dev_udid,aws_rds_util.EVENT_TYPE_GO_COMFORT,alg_cts_ms)

            print('wwwwwwwwwwww',dev_udid,alg_cts,pre_go_comfort_ts,pre_comfort,goComfort)
            pre_go_comfort_ts=alg_cts
            
            notify_key=CU.SLEEP_REQ_COMFORT_KEY_HEADER+cognito_id#注意這個會在rest_detail_notify.py被讀取使用
            notify_data={'type':RN.AWS_NOTIFY_COMFORT_STATE,'ts':int(time.time()),'state':goComfort}
            CU.set_cache_data(notify_key,notify_data,60*60)
            
        #20241218 jd:依照fj的要求，若同時有多個tag活動，則不自動關閉安眠曲
        #            要達到這個目的，若goComfort是false的情況，需檢查貼片數量與狀態
        #            只有一個貼片活動的時候，才能立即更新cache；其他情況要等待cache自動timeout
        
        if(goComfort==False and has_multi_active_tag(cur,cognito_id,dev_udid)):
            pass
        else:
            if(goComfort==False):
                notify_key=CU.SLEEP_REQ_COMFORT_KEY_HEADER+cognito_id#注意這個會在rest_detail_notify.py被讀取使用
                CU.del_cache_data(notify_key)

        cf_data={'ts':cts,'state':goComfort,'go_comfort_ts':pre_go_comfort_ts,'is_awake':isAwake,'is_awake_ts':pre_awake_ts}
        CU.set_cache_data(cf_key,cf_data,16*60)
        
    dat['msg']['sleep_status']=sleep_status

    #cal staistic
    fifo_len=CU.list_append(stat_key,dat) # data will be calculated evey 15 mins
    if(fifo_len>(20*12)):#max 20 min data
        CU.list_pop(stat_key)
        
    #check stat time slot
    first_item=CU.list_get(stat_key,0)
    bts=first_item['ts']
    cts_slot=STAT.cal_time_slot(cts,1)
    bts_slot=STAT.cal_time_slot(bts,1)
    
    get_bs_event=False

    if(cts_slot-bts_slot>=5):
        #cal static
        data_list=CU.list_get_range(stat_key,0,fifo_len-1)

        idx=0
        for item in data_list:
            its=item['ts']
            its_slot=STAT.cal_time_slot(its,1);
            if(cts_slot-its_slot>4):#刪除五分鐘前的資料
                idx+=1
                continue
            break
            
        CU.list_trim(stat_key,idx,fifo_len)

        #20241205 jd:修剪data_list，只計算5min內的資料
        data_list=data_list[idx:]

        res=STAT.cal(data_list)
        print('stat',dev_udid,res)

        hr=res['hr']
        rr=res['rr']
        bs=res['bs']
        sleep=res['sleep_status']
        imu_tmp=res['imu_tmp']
        env_tmp=res['env_tmp']
        bat_level=res['bat_level']
        baby_status=res['baby_status']
        
        if bs>2000:
            get_bs_event=True
        
        if(imu_tmp==0 and env_tmp==0 and bat_level==0):
            #只有沒貼附好，才會因為沒有數據而造成這三項數字都是0
            pass
        else:
            aws_rds_util.addTrendByDevUdid(cur,conn,dev_udid,hr,rr,bs,sleep,imu_tmp,env_tmp,bat_level,baby_status)
            
    return get_bs_event,isAwake,isFatalAlarm
    
def handle_realtime_data(cur,conn,body):
    req_list=['sta_udid','dev_udid','tick','ts',
    'hr','rr','bs','vhr',
    'hr_cl','rr_cl','bs_cl',
    'main_tmp','imu_tmp','bat_lvl',
    'pose','act','status','bat_status',
    'att','well_att','rssi']
    res=RU.check_param(body,req_list)


    if(res[0]==False):
        return res
        
    esp_ts=body['ts']#already in ms
    #srv_ts=int(time.time()*1000)
    #print('esp_ts',esp_ts)
    #print('srv_ts',srv_ts)
    #print('diff ts', esp_ts-srv_ts)
        
    sta_udid=body['sta_udid']
        
    res=DC.get_cognito_id_by_sta_udid(cur,sta_udid)
    if(res is None or res[0]==False):
        return
    cognito_id=res[1]
 
    dev_udid=body['dev_udid']
    tick=body['tick']#patch's data tick
    
    #print('check sta and dev udid',sta_udid,dev_udid)
    
    #compare last data's tick，若有多個station有可能出現這種情況
    last_data=get_last_realtime_cache(dev_udid)
    last_tick=0
    
    if(last_data is not None ):
        last_tick=last_data['tick']
        if(last_tick==tick):
            #is the same data, skip it
            return RU.gen_success_result({})
        
    #如果tick是比較舊的，也宜並忽略，但如果是tag reset造成，則須處理
    if(last_tick>tick):
        if(last_tick-tick < (32768*30)):#舊的資料，不處理
            return RU.gen_success_result({})
    
    msg={}
    msg['hr']=body['hr']
    msg['rr']=body['rr']
    msg['bs']=body['bs']
    msg['vhr']=body['vhr']
    msg['hr_cl']=body['hr_cl']
    msg['rr_cl']=body['rr_cl']
    msg['bs_cl']=body['bs_cl']
    msg['main_tmp']=body['main_tmp']
    msg['imu_tmp']=body['imu_tmp']
    msg['bat_lvl']=body['bat_lvl']
    msg['pose']=body['pose']
    msg['act']=body['act']
    msg['status']=body['status']
    msg['bat_status']=body['bat_status']
    msg['att']=body['att']
    msg['well_att']=body['well_att']
    msg['rssi']=body['rssi']
    
    if 'still_cnt' in body:
        msg['still_cnt']=body['still_cnt']

    dat={'sta':sta_udid,'msg':msg,'tick':tick,'ts':esp_ts}
    
    get_bs_evt,is_wakeup,is_fatal_alarm=add_data_to_stat_buffer(cognito_id,cur,conn,dev_udid,dat)
    
    if(last_data !=None):
        check_limit(cognito_id,cur,conn,sta_udid,dev_udid,dat,last_data,get_bs_evt,is_wakeup,is_fatal_alarm)
    
    #add_data_to_trend_queue(dev_udid,dat)
    add_data_to_realtime_cache(dev_udid,dat)#should be called after check_limit
    
    #add_data_to_stat_buffer(cognito_id,cur,conn,dev_udid,dat)

    return RU.gen_success_result({})