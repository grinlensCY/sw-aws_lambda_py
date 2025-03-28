
def cal_time_slot(ts_ms,min=5):
    #slot=ts_ms/(1000*60*15)
    slot=ts_ms/(1000*60*min)#做為測試，以每分鐘記錄一次
    return int(slot)

def cal_avg_stat(data_list):
    len_list=len(data_list)
    if(len_list==0):
        return 0;
    
    avg_v=0
    
    for v in data_list:
        avg_v+=v
    
    avg_v/=len_list
    return avg_v
    
def cal_avg_stat_filt_cl(data_list,fcl):
    len_list=len(data_list)
    if(len_list==0):
        return 0;
    
    avg_v=0
    cnt=0
    
    for v_cl_pkg in data_list:
        v,cl=v_cl_pkg
        if(cl>=fcl):
            avg_v+=v
            cnt+=1
    
    if(cnt>0):
        avg_v/=cnt
    return avg_v
    
def cal_max_polling_stat(data_list):
    cur_cl=-1e10
    cur_v=-1
    
    for v_cl_pkg in data_list:
        v,cl=v_cl_pkg
        if(cl>cur_cl):
            cur_v=v
            cl=cur_cl
            
    return cur_v
    
def cal_sum_bs(data_list):
    len_list=len(data_list)
    if(len_list==0):
        return 0;
    
    sum_v=0
    pre_cl=-1
    
    for v_cl_pkg in data_list:
        v,cl=v_cl_pkg
        if(cl != pre_cl):
            sum_v+=v
            pre_cl=cl

    return sum_v
    
def cal(data_list):
    #{'sta':sta_udid,'msg':msg,'tick':tick,'ts':srv_ts}
    #要比對tick，去除重複的資料(在有多個sta的時候可能會發生)
    bts=None
    ets=None
    data_map={}
    for data in data_list:
        ts=data['tick']
        data_map[ts]=data['msg']
        if(bts is None):
            bts=ts
        ets=ts
        
    map_msg_set=data_map.values()
    
    hr_list=[]
    rr_list=[]
    bs_list=[]
    imu_tmp_list=[]
    main_tmp_list=[]
    bat_level_list=[]

    sleep_status_map={}
    status_map={}
    
    for msg in map_msg_set:
        #只計算有貼附好的資料
        if('well_att' not in msg or msg['well_att']==0):
            continue
        
        if('hr' in msg and 'hr_cl' in msg):
            hr_list.append((msg['hr'],msg['hr_cl']))
        if('rr' in msg and 'rr_cl' in msg):
            rr_list.append((msg['rr'],msg['rr_cl']))  
        if('bs' in msg and 'bs_cl' in msg):
            bs_list.append((msg['bs'],msg['bs_cl']))  
        if('imu_tmp' in msg):
            imu_tmp_list.append(msg['imu_tmp'])  
        if('main_tmp' in msg):
            main_tmp_list.append(msg['main_tmp'])  
        if('bat_lvl' in msg):
            bat_level_list.append(msg['bat_lvl'])  
            
        if('sleep_status' in msg):
            status=msg['sleep_status']
            if(status in sleep_status_map):
                sleep_status_map[status]+=1
            else:
                sleep_status_map[status]=1
            
        if('status' in msg):
            status=msg['status']
            if(status in status_map):
                status_map[status]+=1
            else:
                status_map[status]=1
                
    baby_status=0
    max_cnt=0;
    for key, value in status_map.items():
        if(value>max_cnt):
            max_cnt=value;
            baby_status=key
            
    sleep_status=0
    max_cnt=0;
    for key, value in sleep_status_map.items():
        if(value>max_cnt):
            max_cnt=value;
            sleep_status=key
            
    print('baby_status max',baby_status)
            
    hr_stat_res=cal_avg_stat_filt_cl(hr_list,4)#收到的CL是已經x10的數值
    rr_stat_res=cal_avg_stat_filt_cl(rr_list,4)#收到的CL是已經x10的數值
    bs_stat_res=cal_sum_bs(bs_list)
    imu_tmp_avg=cal_avg_stat(imu_tmp_list)
    main_tmp_avg=cal_avg_stat(main_tmp_list)
    bat_level_avg=cal_avg_stat(bat_level_list)
    
    return {
        'ts':int((bts+ets)/2),
        'hr':int(hr_stat_res),
        'rr':int(rr_stat_res),
        'bs':int(bs_stat_res),
        'imu_tmp':imu_tmp_avg,
        'env_tmp':main_tmp_avg,
        'bat_level':int(bat_level_avg),
        'baby_status':baby_status,
        'sleep_status':sleep_status
    }