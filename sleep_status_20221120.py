import os
import numpy as np
from scipy import signal
import time
import json
import cache_util as CU

class SleepStatus():
    def __init__(self, udid, ver=20221120, scaled=True):
        self.imusr = 104
        self.broadcast_intvl = 5

        scale = 244 if scaled else 1    # True if deploy to AWS
        self.sleep_stat_stillCnt_th = 1.5*60*self.imusr//scale  # 睡眠狀態的stillCnt門檻
        self.lightsleep_stat_stillCnt_th = 6*60*self.imusr//scale
        self.baseline_start_stillCnt = 55000/104*self.imusr//scale 
        self.baseline_end_stillCnt = 55000/104*self.imusr//scale

        self.sleep_sec_th = 30*60  # 至少累積連續30min的睡眠狀態資料才開始進行BL/睡眠階段計算 與 可以進入REM狀態
        self.rem_sleep_sec_th = 30*60  # 至少距離 最後一次清醒多久 才可以進入REM狀態
        self.baseline_seg_sec_th = 600  # 要累積用來計算的baseline片段，每段至少要10min
        self.baseline_duration_th = [20*60,30*60]  # 若baseline seg有2段以下/3段，至少累積20min/30min的靜態睡眠狀態資料才進行BL/睡眠階段計算
        self.clear_BL_sec = 3*24*60*60  # 每三天重新計算一次baseline

        self.storage_sec = 50*60  # 50min之前的資料就不要了
        self.status_storage_len = 5*60//self.broadcast_intvl  # 啟動安撫要間隔上次啟動多少個訊息

        self.movi_sum_len = 60  # 類似移動平均，把最近的movi_sum_len個的hr_devi加總，當作判斷趨勢的參考 大約60*5=300秒
        self.invalid_cnt_th = 180//self.broadcast_intvl # 3min沒有movi_sum就reset last_devi_movi_sum

        self.goComfort_accu_deep_cnt_th = 4*60//self.broadcast_intvl    # 5min內累積多少的deep_sleep訊息 才能啟動安撫 
        self.quitComfort_accu_deep_cnt_th = 4*60//self.broadcast_intvl    # 5min內累積多少的deep_sleep訊息 才能關閉安撫

        # self.over_BL_th_ratio = [0.15, 0.15]
        self.configfn_prefix = './configfn'    # 本地端測試用
        
        # === default
        #self.init_vars=None
        
        '''
        self.debugVars = {  # only for debug on local, remove it if deploying on AWS
            'ts_list':[],   
            'sc_list': [],  
            'hr_list': [],
            'BL_timeslot': [],
            'hr_devi_ts_list': [],
            'hr_devi_list':[],  # 也許不需要，就直接做movi_sum
            'hr_devi_movi_sum_list':[],
            'hr_devi_rising_score_list': [],
            'hr_invalid_cnt_list':[],

            'rr_list': [],
            'rr_devi_ts_list': [],
            'rr_devi_list':[],  # 也許不需要，就直接做movi_sum
            'rr_devi_movi_sum_list':[], 
            'rr_devi_rising_score_list': [],
            'rr_invalid_cnt_list':[],

            'status_list': [],
            'light_cnt_list': [],
            'comfort_ts_list': [],
            'comfortOn_ts_list': [],
            'comfortOff_ts_list': [],
        }
        '''

        #self.vars = self.init_vars.copy()
        #self.save_context(udid, self.vars)

    def hhmmss(self,sec=None, hms='',outType=3):
        if sec is not None:
            h, r = divmod(sec, 3600)
            m, r = divmod(r, 60)
            s = r
            if outType == 0:
                if h:
                    ans = f'{h:02.0f}:{m:02.0f}:{s:02.0f}'
                elif m:
                    ans = f'{m:02.0f}:{s:02.0f}'
                else:        
                    ans = f'{s:04.1f}'
            elif outType == 1:   # for tag time slot in the exported tag file
                ans = f'{h:02.0f}:{m:02.0f}:{s:09.6f}'
            elif outType == 2:  # for update self.ti
                return h,m,s
            elif outType == 3:
                ans = f'{h:02.0f}:{m:02.0f}:{s:04.1f}'
            elif outType == 4:
                ans = f'{h:02.0f}_{m:02.0f}_{s:04.1f}'
        elif hms:
            tmp = hms.split(':')
            if len(tmp)==3:
                ans = float(tmp[-1])+60*float(tmp[-2])+60*60*float(tmp[-3])
            elif len(tmp)==2:
                ans = float(tmp[-1])+60*float(tmp[-2])
        return ans

    def load_context(self,udid):
        #try:
        #    with open(f"{self.configfn_prefix}_{udid}.json", 'r', newline='') as jf:
        #        res= json.loads(jf.read())
        #except:
        #    res=None

        sleep_var_key=CU.SLEEP_VAR_KEY_HEADER+udid
        res=CU.get_cache_data(sleep_var_key)
        
        if(res is None):
            res= {
            'ts_list':[],   # 有保存期限 or 可以用hr, rr devi計算出status
            'sc_list': [],  # 有保存期限 or 可以用hr, rr devi計算出status
            'BL_got': False,    # 需要定期reset
            'update_BL_timeslot_hr': True,  # 是否因計算hr devi的需求，更新baseline timeslot
            'update_BL_timeslot_rr': True,
            'sleep_tstart': None,   # 得到BL就reset
            'BL_tstart': None,  # 隨著BL_got 定期reset
            'BL_ti': 0,         # 確認baseline是否過期
            'BL_idx_chked': 0,  # 得到BL就reset
            'BL_timeslot':[],   # 得到BL就reset
            'BL_duration': 0,   # 得到BL就reset
            'BL_cnt': 0,        # 得到BL就reset
            
            'hr_list': [],  # 有保存期限 or 可以用hr, rr devi計算出status
            'hr_BL_list': [],   # 計算出hr_BL就可以reset
            'update_hr_BL': True,   # 是否要進行hr baseline計算
            'hr_withinCnt': 0,  # 計算出hr_BL就可以reset
            'hr_BL': None,      # 需要定期reset    
            'hr_devi_chk_idx': 0,
            'hr_devi_proc_seg':[],
            'hr_devi_movi_sum': None,
            'last_valid_hr_devi_movi_sum': None,
            'hr_invalid_cnt': 0,
            'hr_devi_rising_score': None,
            'last_valid_hr_devi_rising_score': None,

            'rr_list': [],  # 有保存期限 or 可以用hr, rr devi計算出status
            'rr_BL_list': [],   # 計算出rr_BL就可以reset
            'update_rr_BL': True,   # 是否要進行rr baseline計算
            'rr_withinCnt': 0,  # 計算出rr_BL就可以reset
            'rr_BL': None,  # 需要定期reset
            'rr_devi_chk_idx': 0,
            'rr_devi_proc_seg':[],
            'rr_devi_movi_sum': None,
            'last_valid_rr_devi_movi_sum': None,
            'rr_invalid_cnt': 0,
            'rr_devi_rising_score': None,
            'last_valid_rr_devi_rising_score': None,

            'status_list': [],
            'light_cnt': 0,
            'REM_cnt':0,
            'deep_cnt':0,
            'goComfort': False,
            'last_awake_ts': time.time(),
            'last_deep_ts': time.time()
            }
        return res
        

    def save_context(self, udid, vars={}):
        #with open(f"{self.configfn_prefix}_{udid}.json", 'w', newline='') as jout:
        #    json.dump(vars, jout, ensure_ascii=False)

        sleep_var_key=CU.SLEEP_VAR_KEY_HEADER+udid
        res=CU.set_cache_data(sleep_var_key,vars,86400)#資料中斷超過一天就沒意義
        
        #self.vars = vars
    
    def resetBL(self, vars, typ, res=True):
        #print(self.hhmmss(vars['ts_list'][-1]),'resetBL typ=',typ,'res',res)
        if typ == 'justGotBLTimeSlot':
            vars['BL_ti'] = vars["BL_timeslot"][0][0]   # for checking if baseline data expired
            vars['sleep_tstart'] = None   # 得到BL就reset
            # vars['BL_idx_chked'] = 0  # 得到BL就reset
            vars['BL_duration'] = 0   # 得到BL就reset
            vars['BL_cnt'] = 0        # 得到BL就reset
            vars['BL_tstart'] = None
            vars['update_hr_BL'] = True if vars['update_BL_timeslot_hr'] else False     # 可以進行計算hr baseline了
            vars['update_rr_BL'] = True if vars['update_BL_timeslot_rr'] else False     # 可以進行計算rr baseline了
            vars['update_BL_timeslot_hr'] = False
            vars['update_BL_timeslot_rr'] = False
            vars['BL_got'] = True
        elif typ == 'expired':  # 3天以上
            vars['BL_ti'] = 0
            vars['update_BL_timeslot_hr'] = True
            vars['update_BL_timeslot_rr'] = True
        elif typ == 'hr':
            vars['update_hr_BL'] = False
            vars['hr_BL_list'] = []
            vars['hr_withinCnt'] = 0
            if not res:
                vars['update_BL_timeslot_hr'] = True
            if not vars['update_rr_BL']:
                vars['BL_timeslot'] = []   # 也不需要update rr BL才reset BL_timeslot
                #print('\treset BL_timeslot  update_BL_timeslot_hr=',vars['update_BL_timeslot_hr'])
        elif typ == 'rr':
            vars['rr_BL_list'] = []
            vars['rr_withinCnt'] = 0
            vars['update_rr_BL'] = False
            if not res:
                vars['update_BL_timeslot_rr'] = True
            # if not vars['update_hr_BL']:
            vars['BL_timeslot'] = []   # 流程上已經是跑過 update_hr_BL, 所以就直接reset BL_timeslot
            #print('\treset BL_timeslot  update_BL_timeslot_hr=',vars['update_BL_timeslot_hr'],'update_BL_timeslot_rr=',vars['update_BL_timeslot_rr'])
    
    def clear_expired_data(self,ts,vars): # 超過storage_sec的資料 與 超過status_storage_len的status_list
        if len(vars['status_list']) > self.status_storage_len: # 5min
            del vars['status_list'][0]

        # = reset BL periodically (3 days)
        if vars['BL_ti'] and ts - vars['BL_ti'] > self.clear_BL_sec:
            self.resetBL(vars, 'expired')
        
        while (len(vars["BL_timeslot"]) and ts-vars["BL_timeslot"][0][0] > self.storage_sec):
            #print(f'clear BL_timeslot[0], {vars["BL_timeslot"][0]}={self.hhmmss({vars["BL_timeslot"][0]})}')
            del vars["BL_timeslot"][0]

        step = 1    #12    # 約 5*12=60 sec(如果都有收到廣播)
        idx = 0
        while idx < len(vars['ts_list']) and ts - vars['ts_list'][idx] > self.storage_sec: # 50min
            idx += step
        if idx:
            del vars['ts_list'][:idx]
            del vars['sc_list'][:idx]
            del vars['hr_list'][:idx]
            del vars['rr_list'][:idx]
            vars['hr_devi_chk_idx'] -= idx
            vars['rr_devi_chk_idx'] -= idx
            vars['BL_idx_chked'] -= idx
    
    def find_BL_timeslot(self,vars):
        idx0 = vars['BL_idx_chked']
        for t,sc in zip(vars['ts_list'][idx0:],vars["sc_list"][idx0:]):
            vars['BL_idx_chked'] += 1
            duration = t-vars['BL_tstart'] if vars['BL_tstart'] is not None else 0
            # == a new baseline start
            if sc >= self.baseline_start_stillCnt and vars['BL_tstart'] is None:
                vars['BL_tstart'] = t
                vars["BL_cnt"] = 1
                #print(f"a new tstart={vars['BL_tstart']}={self.hhmmss(t)}  stillCnt={sc}")
            # == remove seg that is not long enough
            elif sc < self.baseline_end_stillCnt and vars['BL_tstart'] is not None and duration < self.baseline_seg_sec_th:
                #print(f"duration={duration:.0f} < {self.baseline_seg_sec_th} ==> remove tstart={vars['BL_tstart']}  stillCnt={sc}  t={t}")
                vars['BL_tstart'] = None
                vars["BL_cnt"] = 0
            # == a new confirmed baseline seg that is long enough and has high enough data density
            elif vars['BL_tstart'] is not None:
                # = stillCnt < self.baseline_end_stillCnt(開始有比較多動作), seg length >= baseline_seg_sec_th, data density > 0.9
                c0 = (sc < self.baseline_end_stillCnt
                        and duration >= self.baseline_seg_sec_th)
                # = stillCnt >= self.baseline_start_stillCnt(一直靜態), seg length >= baseline_duration_th, data density > 0.9
                c1 = not c0 and (sc >= self.baseline_start_stillCnt
                                    and duration >= self.baseline_duration_th[0])
                if (c0 or c1) and duration/self.broadcast_intvl/vars["BL_cnt"] > 0.9:
                    vars["BL_timeslot"].append([vars['BL_tstart'],t])
                    #self.debugVars['BL_timeslot'].append([vars['BL_tstart'],t])
                    vars["BL_duration"] += duration
                    #print(f'updated timeslot={vars["BL_timeslot"]}  stillCnt={sc}  BL_cnt={vars["BL_cnt"]}')
                    #[print(f'baseline timeslot={self.hhmmss(i)} ~ {self.hhmmss(f)}') for i,f in vars["BL_timeslot"]]
                    vars['BL_tstart'] = None
                    vars["BL_cnt"] = 0
                else:
                    # == accumulate baseline data count for data density calculation
                    vars["BL_cnt"] += 1
            else:
                # == accumulate baseline data count for data density calculation
                vars["BL_cnt"] += 1
            # == found enough reliable BL timeslot
            if (len(vars["BL_timeslot"])
                    and ((len(vars["BL_timeslot"]) < 3 and vars["BL_duration"] >= self.baseline_duration_th[0])
                        or (len(vars["BL_timeslot"]) >= 3 and vars["BL_duration"] >= self.baseline_duration_th[1]))) :
                # vars['BL_got'] = True
                self.resetBL(vars, 'justGotBLTimeSlot')
                break
            # == maybe not good data (too many seg)
            elif (len(vars["BL_timeslot"]) > 3):
                del vars["BL_timeslot"][0]
        #if vars["BL_timeslot"]:
        #    print(f'baseline timeslot={vars["BL_timeslot"]}  BL_duration={vars["BL_duration"]}')

    def get_hr_BL(self,vars):
        # print('start to get hr baseline')
        tEnd = vars["BL_timeslot"][-1][1]
        quit = False    # debug
        for t,[hr,cl] in zip(vars['ts_list'],vars['hr_list']):
            lastTS = t  # debug
            if t > tEnd:
                # print(f"\trr lastTS_{self.hhmmss(t)} is beyond baseline timeslot_{self.hhmmss(tEnd)} --> quit")
                quit = True
                break
            for timeslot in vars["BL_timeslot"]:
                if timeslot[0] <= t <= timeslot[1]:
                    vars["hr_withinCnt"] += 1
                    if hr and cl > 0.5:
                        vars['hr_BL_list'].append(hr)
        #if quit:
        #    print(f"\thr lastTS_{self.hhmmss(lastTS)} is beyond baseline timeslot[1]_{self.hhmmss(tEnd)} --> quit")
        #print(f"\tlen(vars['hr_BL_list'])/vars['hr_withinCnt']={len(vars['hr_BL_list'])}/{vars['hr_withinCnt']}={len(vars['hr_BL_list'])/vars['hr_withinCnt']:.2f} > 0.9?")
        if len(vars['hr_BL_list'])/vars['hr_withinCnt'] > 0.9:
            vars['hr_BL'] = np.median(vars['hr_BL_list']) 
            #print(f"\tlastTS_{self.hhmmss(lastTS)}:update_hr_BL={vars['update_hr_BL']}  hr_BL={vars['hr_BL']:.2f}   len(hr_BL_list)/withinCnt={len(vars['hr_BL_list'])/vars['hr_withinCnt']:.3f}")
            self.resetBL(vars,'hr')
        else:
            self.resetBL(vars,'hr',False)
        #     print(f"\tlastTS_{self.hhmmss(lastTS)}:update_hr_BL={vars['update_hr_BL']}  hr_BL={vars['hr_BL']}   len(hr_BL_list)/withinCnt={len(vars['hr_BL_list'])/vars['hr_withinCnt']}")
   
    def get_rr_BL(self,vars):
        # print('start to get rr baseline')
        tEnd = vars["BL_timeslot"][-1][1]
        quit = False
        for t,[rr,cl] in zip(vars['ts_list'],vars['rr_list']):
            lastTS = t  # debug
            if t > tEnd:
                # print(f"\trr lastTS_{self.hhmmss(t)} is beyond baseline timeslot_{self.hhmmss(tEnd)} --> quit")
                quit = True
                break
            for timeslot in vars["BL_timeslot"]:
                if timeslot[0] <= t <= timeslot[1]:
                    vars["rr_withinCnt"] += 1
                    if rr and cl > 0.5:
                        vars['rr_BL_list'].append(rr)
        #if quit:
        #    print(f"\trr lastTS_{self.hhmmss(lastTS)} is beyond baseline timeslot[1]_{self.hhmmss(tEnd)} --> quit")
        #print(f"\tlen(vars['rr_BL_list'])/vars['rr_withinCnt']={len(vars['rr_BL_list'])}/{vars['rr_withinCnt']}={len(vars['rr_BL_list'])/vars['rr_withinCnt']:.2f} > 0.9?")
        if len(vars['rr_BL_list'])/vars["rr_withinCnt"] > 0.9:
            vars['rr_BL'] = np.median(vars['rr_BL_list'])
            #print(f'rr lastTS_{self.hhmmss(lastTS)}:update_rr_BL={vars["update_rr_BL"]}  rr_BL={vars["rr_BL"]:.2f}   len(rr_BL_list)/withinCnt={len(vars["rr_BL_list"])/vars["rr_withinCnt"]:.3f}')
            self.resetBL(vars,'rr')
        else:
            self.resetBL(vars,'rr',False)
        #     print(f'lastTS_{self.hhmmss(lastTS)}:update_rr_BL={vars["update_rr_BL"]}  rr_BL={vars["rr_BL"]}   len(rr_BL_list)/withinCnt={len(vars["rr_BL_list"])/vars["rr_withinCnt"]}')

    def get_devi_from_baseline(self,ts_list,r_list,bl,devi_proc_seg,last_valid_devi_movi_sum,last_valid_devi_rising_score,invalid_cnt):
        devi_list = []  # debug
        devi_movi_sum = None
        devi_rising_score = last_valid_devi_rising_score
        devi_movi_sum_list = []   # debug
        devi_rising_score_list = []  # debug
        invalid_cnt_list = []   # debug
        for t,[r,cl] in zip(ts_list,r_list):
            islowCL = False
            if cl > 0.5:
                devi_list.append([t,r-bl])
                devi_proc_seg.append(r-bl)
            else:
                islowCL = True
            if len(devi_proc_seg) >= self.movi_sum_len:   # 有累積足夠多的資料
                if islowCL:
                    devi_movi_sum = None
                    devi_rising_score = None
                    invalid_cnt += 1
                else:
                    devi_movi_sum = np.sum(devi_proc_seg)
                    if last_valid_devi_movi_sum is not None:
                        diff = devi_movi_sum - last_valid_devi_movi_sum
                        if last_valid_devi_rising_score is None:
                            devi_rising_score = diff if diff > 0 else 0
                        else:
                            devi_rising_score = (last_valid_devi_rising_score + diff if diff > 0
                                                     else last_valid_devi_rising_score - last_valid_devi_rising_score//2)
                        last_valid_devi_rising_score = devi_rising_score
                    else:
                        devi_rising_score = None
                    if devi_movi_sum:
                        last_valid_devi_movi_sum = devi_movi_sum
                        invalid_cnt -= invalid_cnt//2 if invalid_cnt > 0 else 0
                        # invalid_cnt = 0
                    elif invalid_cnt > self.invalid_cnt_th:   # 連續太久沒有有效的devi_movi_sum，就reset last_valid_devi_movi_sum
                        last_valid_devi_movi_sum = None
                        last_valid_devi_rising_score = None
                    else:
                        invalid_cnt += 1
                del devi_proc_seg[0]
            else:
                devi_movi_sum = None
                devi_rising_score = None
                invalid_cnt += 1 if len(ts_list) == 1 else 0
            devi_movi_sum_list.append(devi_movi_sum)   # debug
            devi_rising_score_list.append(devi_rising_score)    # debug
            # if devi_movi_sum is None and t > 60*180:
            #     print(f"{self.hhmmss(t)}: devi_movi_sum is None  invalid_cnt={invalid_cnt}")
            invalid_cnt_list.append(invalid_cnt)
        return len(r_list), devi_proc_seg, devi_movi_sum, last_valid_devi_movi_sum, devi_rising_score, last_valid_devi_rising_score, invalid_cnt, devi_list, devi_movi_sum_list, devi_rising_score_list, invalid_cnt_list
        
    def get_status(self,vars,scdat,devi_dat,devi_rising_score_dat,ts):
        status = None
        if vars['BL_got']:
            if (not vars['hr_BL'] and not vars['rr_BL']) or (devi_dat[0] is None and devi_dat[1] is None):
                # 沒有 hr與rr的baseline 或 hr與rr都是0
                if len(vars['status_list']):
                    status = vars['status_list'][-1]
                elif scdat <= self.sleep_stat_stillCnt_th:
                    status = 'awake'
                    vars['last_awake_ts'] = ts
                elif scdat <= self.lightsleep_stat_stillCnt_th:
                    status = 'light'
                else:
                    status = 'deep'
                    vars['last_deep_ts'] = ts
            else:
                if scdat <= self.sleep_stat_stillCnt_th:
                    status = 'awake'
                    vars['last_awake_ts'] = ts
                else:   # sleep status
                    c0 = scdat >= self.lightsleep_stat_stillCnt_th
                    notets = [60*0,60*0]    # debug

                    # hr 
                    c10 = devi_dat[0] is not None and devi_rising_score_dat[0] is not None
                    c101 = vars['hr_invalid_cnt'] < 3
                    # # moving sum
                    # c11 = c10 and devi_dat[0] <= 300
                    # c12 = c10 and not c11
                    # rising score
                    c31 = c10 and devi_rising_score_dat[0] <= 130
                    c32 = c10 and not c31
                    c33 = c32 and devi_rising_score_dat[0] > 200    # larger light_cnt step
                    c34 = c31 and vars['light_cnt'] > 0 and devi_rising_score_dat[0] > 60
                    #if notets[0] < ts < notets[1]:  # debug
                    #    msg = f"{self.hhmmss(ts)}: c10_{c10}  c31_{c31} c32_{c32} c33_{c33} c34_{c34} light_cnt={vars['light_cnt']}  "
                    #    msg += f"hr_invalid_cnt={vars['hr_invalid_cnt']}  "
                    #    if devi_rising_score_dat[0]:
                    #        msg += f"devi_rising_score_dat[0]={devi_rising_score_dat[0]}"
                    #    print(msg)

                    # rr
                    c20 = devi_dat[1] is not None and devi_rising_score_dat[1] is not None
                    c201 = vars['rr_invalid_cnt'] < 3
                    # moving sum
                    c21 = c20 and devi_dat[1] <= 150
                    c22 = c20 and not c21
                    # rising score
                    c41 = c20 and devi_rising_score_dat[1] <= 120
                    c42 = c20 and not c41
                    #if notets[0] < ts < notets[1]:
                    #    msg = f"\tc20_{c20} c21_{c21} c22_{c22} c41_{c41} c42_{c42}  "
                    #    msg += f"rr_invalid_cnt={vars['rr_invalid_cnt']}  "
                    #    if devi_rising_score_dat[1]:
                    #        msg += f"devi_rising_score_dat[1]={devi_rising_score_dat[1]:7.1f}"
                    #    print(msg)

                    light_score = 1 if c0 else 0
                    score_str = f"{light_score}"    # debug
                    light_score += 1 if c32 else 0  #c12 or c32 else 0
                    score_str += f"_{light_score}"      # debug
                    light_score += 1 if c22 or c42 else 0
                    score_str += f"_{light_score}"    # debug
                    light_score += 1 if not c10 and c101 and not vars['update_BL_timeslot_hr'] and (np.array(vars['status_list'][-3:])=='light').all() else 0
                    score_str += f"_{light_score}"    # debug
                    light_score += 1 if light_score > 0 and c34 else 0
                    score_str += f"_{light_score}"    # debug
                    #if notets[0] < ts < notets[1]:
                    #    print(f"\tlight_score={light_score}  score_str={score_str}  c10={c10}  vars['status_list'][-3:]={vars['status_list'][-3:]}")
                    if not c0:
                        # = 需要距離awake 30min 以上，且曾經有過 deep
                        if ts - vars['last_awake_ts'] > self.rem_sleep_sec_th and vars['last_awake_ts'] < vars['last_deep_ts']:
                            status = 'REM'
                        else:
                            status = 'light'
                    elif light_score > 1:
                        vars['light_cnt'] += 1 if c33 or c34 else 0.5
                        if vars['light_cnt'] > 2:
                            status = 'light'
                        else:
                            status = vars['status_list'][-1]
                    else:
                        deep_score = 1 if c0 else 0
                        deep_score += 1 if c31 else 0
                        deep_score += 1 if c41 else 0
                        if vars['light_cnt'] > 0:
                            vars['light_cnt'] -= 1
                        if deep_score > 1 and vars['light_cnt'] < 3:
                            # 1. stillCnt >= lightsleep_stat_stillCnt_th 
                            # 2. hr_devi_movi_sum <= 125 or rr_devi_movi_sum <= 50
                            # 3. hr_devi_rising <= 110 or rr_devi_rising <= 100
                            status = 'deep'
                            vars['last_deep_ts'] = ts
                            # if 60*87 < ts < 60*93:
                            #     print(f"{self.hhmmss(ts)} deep status={status} light_cnt={vars['light_cnt']}")
                        else:
                            status = vars['status_list'][-1]
                            # if 60*87 < ts < 60*93:
                            #     print(f"{self.hhmmss(ts)} status={status} light_cnt={vars['light_cnt']}  vars['status_list'][-1]={vars['status_list'][-1]}")
                #self.debugVars['light_cnt_list'].append([ts,vars['light_cnt']])
                                
            # == comfort event detection only after baseline is confirmed
            # == 還有一種情況 已經在第一次得到baseline，但換到其他次睡眠  設計另外一個類似 find_BL_timeslot 來找穩定期??
            # if 60*175 < ts < 60*180:
            #     print(f"{self.hhmmss(ts)}: status={status} goComfort={vars['goComfort']} REM_cnt={vars['REM_cnt']} deep_cnt={vars['deep_cnt'] } ")
            if status == 'REM' and not vars['goComfort']:
                # deepCnt = np.count_nonzero(np.array(vars['status_list']) == 'deep')
                # if deepCnt: # and deepCnt > self.goComfort_accu_deep_cnt_th:
                vars['REM_cnt'] += 1
                # tmp = 0     # debug
                if vars['REM_cnt'] > 4: # 至少維持25秒再啟動
                    vars['goComfort'] = True
                    vars['deep_cnt'] = 0
                    #self.debugVars['comfortOn_ts_list'].append(ts)
                    # tmp = 1     # debug
            elif vars['goComfort'] and status == 'deep':
                vars['REM_cnt'] -= 1 if vars['REM_cnt'] > 0 else 0
                vars['deep_cnt'] += 1
                # tmp = 2     # debug
                # = 也要累積一段時間的deep再關
                # deepCnt = np.count_nonzero(np.array(vars['status_list']) == 'deep')
                # if deepCnt and deepCnt > self.quitComfort_accu_deep_cnt_th:
                if vars['deep_cnt'] > self.quitComfort_accu_deep_cnt_th:
                    vars['goComfort'] = False
                    vars['deep_cnt'] = 0
                    #self.debugVars['comfortOff_ts_list'].append(ts)
                    # tmp = 3     # debug
            else:
                vars['REM_cnt'] -= 1 if vars['REM_cnt'] > 0 else 0
                # tmp = 4          # debug
            # if 60*175 < ts < 60*180:
            #     print(f"{self.hhmmss(ts)}: case_{tmp}")
        else:   # 先由stillCnt給出 sleep status
            if scdat <= self.sleep_stat_stillCnt_th:
                status = 'awake'
                vars['last_awake_ts'] = ts
            elif scdat <= self.lightsleep_stat_stillCnt_th:
                status = 'light'
            else:
                status = 'deep'
                vars['last_deep_ts'] = ts
        return status
    
    def addData(self,udid,ts,hrdat,rrdat,scdat):
        #vars = self.vars    # 暫時用於本地端的加速(讀寫那個dict有點慢)  之後要加回去
        vars = self.load_context(udid)  # 用於AWS
        vars['ts_list'].append(ts)
        vars['sc_list'].append(scdat)
        vars['hr_list'].append(hrdat)
        vars['rr_list'].append(rrdat)

        #self.debugVars['ts_list'].append(ts)
        #self.debugVars['sc_list'].append(scdat)
        #self.debugVars['hr_list'].append(hrdat)
        #self.debugVars['rr_list'].append(rrdat)

        if vars['update_BL_timeslot_hr'] or vars['update_BL_timeslot_rr']:
            if vars['sleep_tstart'] is None and scdat >= self.sleep_stat_stillCnt_th:    # a new start of sleep status
                vars['sleep_tstart'] = ts
                #print(f'a sleep starts at {ts}={self.hhmmss(ts)}')
            elif vars['sleep_tstart'] is not None and scdat < self.sleep_stat_stillCnt_th:   # end of sleep status
                vars['sleep_tstart'] = None
                #print(f'a sleep stops at {ts}={self.hhmmss(ts)}')
            elif vars['sleep_tstart'] is not None and ts - vars['sleep_tstart'] > self.sleep_sec_th:  # a long enough sleep status
                self.find_BL_timeslot(vars)

        devi_dat = [None, None]
        devi_rising_score_dat = [None, None]
        if vars['BL_got']:  # 可以計算hr rr的偏差 與 推論睡眠狀態
            devi_dat = [0,0]    # hr devi, rr devi
            devi_rising_score_dat = [None, None]
            if vars['update_hr_BL']:
                self.get_hr_BL(vars)
            if vars['hr_BL']:
                datlen, devi_proc_seg, devi_movi_sum, last_valid_devi_movi_sum, devi_rising_score, last_valid_devi_rising_score, invalid_cnt, devilist, devi_movi_sum_list, devi_rising_score_list, invalid_cnt_list \
                    = self.get_devi_from_baseline(vars['ts_list'][vars['hr_devi_chk_idx']:],
                                                    vars['hr_list'][vars['hr_devi_chk_idx']:],
                                                    vars['hr_BL'],
                                                    vars['hr_devi_proc_seg'],
                                                    vars['last_valid_hr_devi_movi_sum'],
                                                    vars['last_valid_hr_devi_rising_score'],
                                                    vars['hr_invalid_cnt'])
                vars['hr_devi_chk_idx'] += datlen
                vars['hr_devi_proc_seg'] = devi_proc_seg
                vars['hr_devi_movi_sum'] = devi_dat[0] = devi_movi_sum
                vars['last_valid_hr_devi_movi_sum'] = last_valid_devi_movi_sum
                vars['hr_devi_rising_score'] = devi_rising_score_dat[0] = devi_rising_score
                vars['last_valid_hr_devi_rising_score'] = last_valid_devi_rising_score
                vars['hr_invalid_cnt'] = invalid_cnt
                #self.debugVars['hr_devi_ts_list'].extend(vars['ts_list'][vars['hr_devi_chk_idx']-datlen:])
                #self.debugVars['hr_devi_list'].extend(devilist)
                #self.debugVars['hr_devi_movi_sum_list'].extend(devi_movi_sum_list)
                #self.debugVars['hr_devi_rising_score_list'].extend(devi_rising_score_list)
                #self.debugVars['hr_invalid_cnt_list'].extend(invalid_cnt_list)
            if vars['update_rr_BL']:
                self.get_rr_BL(vars)
            if vars['rr_BL']:
                datlen, devi_proc_seg, devi_movi_sum, last_valid_devi_movi_sum, devi_rising_score, last_valid_devi_rising_score, invalid_cnt, devilist, devi_movi_sum_list, devi_rising_score_list, invalid_cnt_list \
                    = self.get_devi_from_baseline(vars['ts_list'][vars['rr_devi_chk_idx']:],
                                                    vars['rr_list'][vars['rr_devi_chk_idx']:],
                                                    vars['rr_BL'],
                                                    vars['rr_devi_proc_seg'],
                                                    vars['last_valid_rr_devi_movi_sum'],
                                                    vars['last_valid_rr_devi_rising_score'],
                                                    vars['rr_invalid_cnt'])
                vars['rr_devi_chk_idx'] += datlen
                vars['rr_devi_proc_seg'] = devi_proc_seg
                vars['rr_devi_movi_sum'] = devi_dat[1] = devi_movi_sum
                vars['last_valid_rr_devi_movi_sum'] = last_valid_devi_movi_sum
                vars['rr_devi_rising_score'] = devi_rising_score_dat[1] = devi_rising_score
                vars['last_valid_rr_devi_rising_score'] = last_valid_devi_rising_score
                vars['rr_invalid_cnt'] = invalid_cnt
                #self.debugVars['rr_devi_ts_list'].extend(vars['ts_list'][vars['rr_devi_chk_idx']-datlen:])
                #self.debugVars['rr_devi_list'].extend(devilist)
                #self.debugVars['rr_devi_movi_sum_list'].extend(devi_movi_sum_list)
                #self.debugVars['rr_devi_rising_score_list'].extend(devi_rising_score_list)
                #self.debugVars['rr_invalid_cnt_list'].extend(invalid_cnt_list)
        status = self.get_status(vars, scdat, devi_dat, devi_rising_score_dat, ts)    
        vars['status_list'].append(status)
        #self.debugVars['status_list'].append(status)

        # = keep data size within UL    50min
        self.clear_expired_data(ts, vars)

        #self.vars = vars    # 暫時用於本地端的加速(讀寫那個dict有點慢)  之後要加回去
        self.save_context(udid,vars)      # 用於AWS
        return udid,vars,status,vars['goComfort']    # 暫時用於本地端的加速(讀寫那個dict有點慢)  之後要加回去

        # self.save_context(udid,vars)      # 用於AWS
        # return status,vars['goComfort']     # 用於AWS，但不確定要回傳甚麼，就先只回傳睡眠狀態


if __name__ == "__main__":
    import os, csv, time, sys, json, threading
    import queue
    # import soundfile as sf
    import numpy as np
    import tkinter as tk
    from tkinter import filedialog
    import pandas as pd


    hrfn="./sleepstate_2022-08-12-23-20-52/2022-08-12-23-20-52-syncHR_v20220728_age15_0-29932sec_500sps.csv"
    rrfn="./sleepstate_2022-08-12-23-20-52/2022-08-12-23-20-52-RR_v20211005_zf_[0.2, 1.0].csv"
    stillCntfn="./sleepstate_2022-08-12-23-20-52/2022-08-12-23-20-52-pose_activity_v20221020.csv"
    #print('hrfn:',hrfn)
    #print('rrfn:',rrfn)
    #print('stillCntfn:',stillCntfn)

    # get hr from broadcast which was upated every 5sec
    ts = None
    data = pd.read_csv(hrfn, header=[0],skiprows=[],quotechar="'")
    hrData = data.to_numpy()
    cnt = 1
    hr_list = []
    hr = None
    prehr = None
    precl = None
    for dat in hrData:
        tbc = cnt*5
        if dat[0] <= tbc:
            ts = dat[0]
            hr = dat[1]
            hrCL = dat[2]
        elif ts:    # dat[0] > tbc
            while ts > tbc:
                if len(hr_list):
                    hr_list.append([tbc,hr_list[-1][1],hr_list[-1][2]])
                tbc += 5
                cnt += 1
            hr_list.append([tbc,hr,hrCL])
            ts = dat[0]
            hr = dat[1]
            hrCL = dat[2]
            cnt += 1
        else:
            ts = dat[0]
            hr = dat[1]
            hrCL = dat[2]
            hr_list.append([tbc,0,0])
            cnt += 1
    
    # get rr from broadcast which was upated every 5sec
    ts = None
    data = pd.read_csv(rrfn, header=[0],skiprows=[],quotechar="'")
    rrData = data.to_numpy()
    cnt = 1
    rr_list = []
    for dat in rrData:
        tbc = cnt*5
        if dat[0] <= tbc:
            ts = dat[0]
            rr = dat[-2]
            rrCL = dat[2]
        elif ts:
            while ts > tbc:
                if len(rr_list):
                    rr_list.append([tbc,rr_list[-1][1],rr_list[-1][2]])
                else:
                    rr_list.append([tbc,0,0])
                tbc += 5
                cnt += 1
            rr_list.append([tbc,rr,rrCL])
            ts = dat[0]
            rr = dat[-2]
            rrCL = dat[2]
            cnt += 1
        else:
            ts = dat[0]
            rr = dat[-2]
            rrCL = dat[2]
            rr_list.append([tbc,0,0])
            cnt += 1

    # get stillcnt from broadcast which was upated every 5sec
    ts = None
    data = pd.read_csv(stillCntfn, header=[0],skiprows=[],quotechar="'")
    stillData = data.to_numpy()
    cnt = 1
    stillCnt_list = []
    for dat in stillData:
        tbc = cnt*5
        if dat[0] <= tbc:
            ts = dat[0]
            stillCnt = dat[-1]
        elif ts:
            while ts > tbc:
                if len(stillCnt_list):
                    stillCnt_list.append([tbc,stillCnt_list[-1][1],stillCnt_list[-1][2]])
                tbc += 5
                cnt += 1
            stillCnt_list.append([tbc,stillCnt])
            ts = dat[0]
            stillCnt = dat[-1]
            cnt += 1
        else:   # dat[0](ts) > tbc
            ts = dat[0]
            stillCnt = dat[-1]
            stillCnt_list.append([tbc,0])
            cnt += 1

    udid = "123"

    sleep_stat = SleepStatus(udid=udid)
    # sleep_stat.save_context(udid)   # init

    # = simulation of receiving broadcast data
    len_hrlist = len(hr_list)
    len_rrlist = len(rr_list)
    len_stillCntlist = len(stillCnt_list)
    # idx_hrlist = 0
    # idx_rrlist = 0
    # idx_stillCntlist = 0
    idx_bc = 0  # broadcase index
    tbc = 5
    go = gohr = gorr = gostill = True
    # while idx_hrlist < len_hrlist or idx_rrlist < len_rrlist or idx_stillCntlist < len_stillCntlist:
    while idx_bc < len_hrlist and idx_bc < len_rrlist and idx_bc < len_stillCntlist:
        ts = tbc
        hrts = hr_list[idx_bc][0]
        rrts = rr_list[idx_bc][0]
        stillCntts = stillCnt_list[idx_bc][0]
        if not (hrts == rrts and rrts == stillCntts):  # 若確認無誤，dat就可以移除ts
            print('ts does not match!',ts,hrts,rrts,stillCntts)

        udid,vars,status,goComfort = sleep_stat.addData(udid,ts,hr_list[idx_bc][1:],rr_list[idx_bc][1:],stillCnt_list[idx_bc][1])
        print(status,goComfort)
        idx_bc += 1
        
        tbc += sleep_stat.broadcast_intvl

        # if sleep_stat.vars['rr_BL'] and sleep_stat.vars['hr_BL']:
        #     break
    
    sleep_stat.save_context(udid,vars)      # 暫時看看能不能 不要每次都存 來加速開發，正式版不能這樣