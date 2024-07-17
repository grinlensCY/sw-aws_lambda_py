import os
import numpy as np
# from scipy import signal
import time
import json
import enum
import copy
import cache_util as CU

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.bool_):
            return bool(obj)
        return json.JSONEncoder.default(self, obj)


class Sleep(enum.IntEnum):
    NONE = 0
    AWAKE = 1
    REM = 2
    LIGHT = 3
    DEEP = 4
    NREM = 5


class SleepStatus_FatalAlarm():
    def __init__(self, udid, age, ver=20240712, scaledSC=True):
        self.ver = ver
        self.imusr = 104
        self.broadcast_intvl = 5
        self.age = age

        #self.scaledSC = scaledSC    # debug
        scale = 244 if scaledSC else 1    # True if deploy to AWS
        # == note: self.max_still_cnt = 10*60*sr => stillCnt最高10min
        self.sleep_stillCnt_LL = (3.5 if self.age > 6 else 1.5)*60*self.imusr//scale  # 睡眠狀態的stillCnt門檻
        self.awake_stillCnt_UL = self.sleep_stillCnt_LL - 5*self.imusr//scale  # 睡眠狀態的stillCnt門檻
        self.light_stillCnt_UL = (8 if self.age > 6 else 6)*60*self.imusr//scale  # light/deep的stillCnt界線
        self.close_sleep_LL_sec = 1800 if self.age <= 6 else 2400    # 要連續睡眠多久才能 給出睡眠階段
        self.enable_awakeAlarm_sleeplong = 1200     # 要連續睡眠多久才能啟動awakeAlarm

        self.calcBL_data_long_LL_sec = 1800     # 至少要30min的資料來計算baseline
        self.calcBL_stride_sec = 1200    # 每Nmin根據過去30min更新一次baeline
        self.calcBL_step_sec = 300    # 好資料不足的情況下，平移Nmin，再根據過去30min找一次baeline
        self.calcBL_stillCnt_LL = 7*60*self.imusr//scale    # 可以用來計算baseline的stillCnt下限

        self.stage_long_LL_sec = 120    # scale_REM的時候，兩旁stage最短的長度

        if age < 4:
            self.rem_ratio_target = 0.5
        elif age < 12:
            self.rem_ratio_target = 0.5 + (0.3 - 0.5)/(12 - 4)*(age - 4)
        elif age < 24:
            self.rem_ratio_target = 0.3 + (0.25 - 0.3)/(24 - 12)*(age - 12)
        else:
            self.rem_ratio_target = 0.225
        
        # === fatal alarm
        if age < 12:
            self.rr_UL = 60
            self.rr_LL = 25
            self.hr_LL = 90
            self.hr_UL = 220
        elif age < 36:
            self.rr_UL = 55
            self.rr_LL = 19
            self.hr_LL = 81
            self.hr_UL = 170
        elif age < 72:
            self.rr_UL = 40
            self.rr_LL = 17
            self.hr_LL = 72
            self.hr_UL = 150
        elif age < 120:
            self.rr_UL = 30
            self.rr_LL = 12 # 這已經超出目前hr/rr演算法的可偵測下限
            self.hr_LL = 62
            self.hr_UL = 130
        else:
            self.rr_UL = 29
            self.rr_LL = 10 # 這已經超出目前hr/rr演算法的可偵測下限
            self.hr_LL = 50 # 這已經超出目前hr/rr演算法的可偵測下限
            self.hr_UL = 110
        self.expired_min = 1800 # 大幅變化的註記多久之後就可以拋棄
        self.ratio_to_pre_UL = [1.1, 1.15]    # hr/rr ratio UL   if ratio to pre_val > UL => skip this
        self.ratio_to_pre_LL = [0.85, 0.85]
        self.ratio_to_ref_UL = [1.75, 1.7]
        self.ratio_to_ref_LL = [0.85, 0.8]

        '''
        self.debugVars = {  # only for debug on local, remove it if deploying on 
            # input
            't0':None,
            'ts_list':[],   
            'sc_list': [],
            'hr_list': [],  # [[hr,cl],...]
            'rr_list': [],  # [[rr,cl],...]
            'isWellAttach_list':[],
            'draft_status_list': [],  # draft_sleepstatus所產出的sleep status

            'calcBL_data_list':[],  # 用於計算baseline的資料，也順便確認是否能與 前面的ts_list等等重疊  [[ts,hr,rr,sc],...]

            # attach
            'justWellAttachAfterLongDetach_tslist':[],  # 很久沒貼附之後，還在剛貼附的時間
            'unWellAttach_timespans':[],    # 未貼附的時段

            # status
            'scDrop_info':[],   # [[ts,scDrop_bts,scDrop_ets,scDropSum],...]

            'sleep_bts_list':[],    # 入睡時間點
            'awakeAlarm_ts_list':[],

            'comfortOn_ts_list': [],
            'comfortOff_ts_list': [],

            # baseline
            'low_data_density_infos':[],
            'low_highSC_density_infos':[],
            'low_highHRCL_density_infos':[],
            'low_highRRCL_density_infos':[],
            'hr_baseline':[],   # [[ti,tf,bl],...]
            'rr_baseline':[],
            'hr_baseline_50th':[],
            'hr_baseline_30th':[],
            'rr_baseline_50th':[],
            'rr_baseline_30th':[],

            # fatel alarm
            "hr_alarm_UL_list":[],  # [[ti,hr],...]
            "hr_alarm_LL_list":[],
            'rr_alarm_UL_list':[],
            "rr_alarm_LL_list":[],
            'fatal_alarm_ts_list':[],
            
            'hr_rising_cnt_list': [],
            'hr_falling_cnt_list': [],  # [[ts,cnt],...]
            'rt_ref_hr_list': [],   # [[ts,hr],...]
            'hr_rising_start_list': [], # [[ts,hr],...]
            'hr_falling_start_list': [],    # [[ts,hr],...]
            'hr_has_sharp_rising_list':[],   # [[ts0,hr0],[ts1,hr1],.........]
            'hr_has_sharp_falling_list':[],   # [[ts0,hr0],[ts1,hr1],.........]
            'bigChange_hr_list':[],     #[[ts,hr],...]

            'rr_rising_cnt_list': [],
            'rr_falling_cnt_list': [],  # [[ts,cnt],...]
            'rt_ref_rr_list': [],   # [[ts,rr],...]
            'rr_rising_start_list': [], # [[ts,rr],...]
            'rr_falling_start_list': [],    # [[ts,rr],...]
            'rr_has_sharp_rising_list':[],  # [[ts0,rr0],[ts1,rr1],.........]
            'rr_has_sharp_falling_list':[],     # [[ts0,rr0],[ts1,rr1],.........]
            'bigChange_rr_list':[],     #[[ts,hr],...]

            # stage
            'rem_timespans': [],
            'rem_long_sum_list': [],
            'sleep_stages': [],    # 最終的sleep stages
        }
        '''

        # self.vars = self.init_vars.copy()
        # self.save_context(udid, self.vars)
        # self.vars = self.load_context(udid, True)
        # self.mx_vars_size = sys.getsizeof(self.vars)

        # self.msg = ''   # debug


    # def formatValList(self,msg,typ='f3'):
    #     ''' only for debug'''
    #     if msg is None:
    #         return msg
    #     msg = np.array(msg)
    #     if typ[0] == 'f':
    #         return np.around(msg,int(typ[1])).tolist()
    #     elif typ[0] == 'e':
    #         str_list = []
    #         for i in msg:
    #             str_list.append(f"{np.format_float_scientific(i,int(typ[1]))}")
    #         return str_list
    
    # def aMsg(self,msg,pre=0,post=0):
    #     ''' only for debug'''
    #     for i in range(pre):
    #         self.msg += '\t'
    #     for i in range(post):
    #         msg += '\t'
    #     self.msg += msg+'\n'

    # def hhmmss(self,sec=None, hms='',outType=3):    # 好像是沒用到
    #     if sec is not None:
    #         h, r = divmod(sec, 3600)
    #         m, r = divmod(r, 60)
    #         s = r
    #         if outType == 0:
    #             if h:
    #                 ans = f'{h:02.0f}:{m:02.0f}:{s:02.0f}'
    #             elif m:
    #                 ans = f'{m:02.0f}:{s:02.0f}'
    #             else:
    #                 ans = f'{s:04.1f}'
    #         elif outType == 1:   # for tag time slot in the exported tag file
    #             ans = f'{h:02.0f}:{m:02.0f}:{s:09.6f}'
    #         elif outType == 2:  # for update self.ti
    #             return h,m,s
    #         elif outType == 3:
    #             ans = f'{h:02.0f}:{m:02.0f}:{s:04.1f}'
    #         elif outType == 4:
    #             ans = f'{h:02.0f}_{m:02.0f}_{s:04.1f}'
    #     elif hms:
    #         tmp = hms.split(':')
    #         if len(tmp)==3:
    #             ans = float(tmp[-1])+60*float(tmp[-2])+60*60*float(tmp[-3])
    #         elif len(tmp)==2:
    #             ans = float(tmp[-1])+60*float(tmp[-2])
    #     return ans

    def load_context(self,udid):
        sleep_var_key=CU.SLEEP_VAR_KEY_HEADER+udid
        res=CU.get_cache_data(sleep_var_key)
        
        if(res is None):
            res = {
                # input
                'ts_list': [],
                'hr_list':[],
                'rr_list':[],
                'sc_list': [],
                'pre_stillCnt':0,
                'pre2_ts':None,
                'pre2_hr':None,
                'pre2_rr':None,
                'pre_ts':None,
                'pre_hr':None,
                'pre_rr':None,

                # attach
                'unWellAttach_bts':None,
                'unWellAttach_ets':None,
                # status
                'scDropSum':0,
                'scDrop_bts':None,
                'scDrop_ets':None,

                'sleep_bts':None,
                'sleep_duration':0,
                'had_deep':False,
                'deep_bts':None,
                'light_bts':None,

                'goComfort':False,
                'comfort_bts':None,

                'awakeAlarm_ts':0,
                # baseline
                'hr_baseline':[],
                'rr_baseline':[],
                # stage
                'sleep_stages': [],
                'last_sleep_stages': [],

                # === fatal alarm
                'last_hr_bigChange_ts':0,   # sharp_xxx_ts 要距離bigChange 11秒(兩次廣播)以上
                'last_rr_bigChange_ts':0,   # sharp_xxx_ts 要距離bigChange 11秒(兩次廣播)以上
                "hr_baseline_alarm_UL":None,    # 從baseline推算的limit
                "hr_baseline_alarm_LL":None,
                "rr_baseline_alarm_UL":None,
                "rr_baseline_alarm_LL":None,
                "hr_alarm_UL":None,    # 比較上升起點 x ratio 與 baseline_limit之後的 limit
                "hr_alarm_LL":None,
                "rr_alarm_UL":None,
                "rr_alarm_LL":None,

                'zero_hr_cnt': 0,   # 遇到無效的hr
                'same_hr_cnt': 0,   # 連續一樣的hr
                'rt_ref_hr': 0,     # real time ref hr(和 sleepstage的baseline不同，這是用來即時判斷上升還是下降的)
                'hr_rising_bts':0,
                'hr_rising_cnt':0,
                'hr_falling_blvl': 0,
                'hr_falling_bts':0,
                'hr_falling_cnt':0,
                'hr_has_sharp_falling_ts_list':[],
                'hr_has_sharp_rising_ts_list':[],
                'last_overUL_hr_ts': None,   # 最近一個超過UL的 [頂點時間,開始上升高度]，若下降點也很接近，下降的LL要以上升起點的高度當參考
                'last_overUL_hr_blvl': None,   # 最近一個超過UL的 [頂點時間,開始上升高度]，若下降點也很接近，下降的LL要以上升起點的高度當參考
                'last_overUL_hr_lvl': None, # debug
                
                'zero_rr_cnt': 0,
                'same_rr_cnt': 0,
                'rt_ref_rr': 0,
                'rr_rising_bts':0,
                'rr_rising_cnt':0,
                'rr_falling_blvl': 0,
                'rr_falling_bts':0,
                'rr_falling_cnt':0,
                'rr_has_sharp_falling_ts_list':[],
                'rr_has_sharp_rising_ts_list':[],
                'last_overUL_rr_ts': None,
                'last_overUL_rr_blvl': None,
                'last_overUL_rr_lvl': None, # debug

                'fatal_alram_mute_ets':0,   # alaram之後的10min都不再發出
                'last3_fatalalarm_ts': [],    # 單純是為了能在即時收錄的時候記錄到fatalalarm

            }
        # else:
        #     # with open(f"sleepstat_{udid}.json", 'r', newline='') as jf:
        #     #     res = json.loads(jf.read())
        #     res = self.vars # 因為讀取檔案會很慢，為了加速開發，改用這樣的方式
        return res
    
    def clear_vars(self,vars):  #,udid,saveJson=False):
        # if saveJson:
        #     cnt = 1
        #     fn = f"sleepstat_{udid}_vars_mxsize_{cnt}.json"
        #     while os.path.exists(fn):
        #         cnt += 1
        #         fn = f"sleepstat_{udid}_vars_mxsize_{cnt}.json"
        #     with open(fn, 'w', newline='') as jout:
        #         json.dump(vars, jout, ensure_ascii=False, cls=NumpyEncoder)

        vars['ts_list'] = []
        vars['hr_list'] = []
        vars['rr_list'] = []
        vars['sc_list'] = []
        vars['hr_baseline'] = []
        vars['rr_baseline'] = []

        vars['sleep_stages'] = [] if vars['sleep_stages'][-1][0] != Sleep.AWAKE else [vars['sleep_stages'][-1]]
        vars['sleep_bts'] = None
        vars['sleep_duration'] = 0
        vars['had_deep'] = False
        vars['deep_bts'] = None
        vars['light_bts'] = None

        vars['goComfort'] = False
        vars['comfort_bts'] = None

        vars['scDropSum'] = 0
        vars['scDrop_bts'] = None
        vars['scDrop_ets'] = None

    def save_context(self, udid, vars={}):
        sleep_var_key=CU.SLEEP_VAR_KEY_HEADER+udid
        res=CU.set_cache_data(sleep_var_key,vars,86400)#資料中斷超過一天就沒意義
        
    def getAwakeAlarm(self,vars,ts):    # awake狀態 才去計算
        # self.aMsg(f"\ngetAwakeAlarm: ts={ts}")
        sleep_long = ts - vars['sleep_bts'] if vars['sleep_bts'] is not None else 0
        # self.aMsg(f"sleep_long={sleep_long}",1)
        if (sleep_long > self.enable_awakeAlarm_sleeplong):    # 已經保持入睡一段時間(20min)
            # vars['sleep_duration'] = sleep_long
            # self.debugVars['awakeAlarm_ts_list'].append(ts)
            return ts
        else:
            return 0
    
    def goCalcSS(self,vars,ts,afterLongLoss=False):    # awake狀態 或 空白很久(ts-pre_ts)才去計算
        # self.aMsg(f"\ngoCalcSS: ts={ts}  afterLongLoss={afterLongLoss}")
        if afterLongLoss:
            ts = vars['pre_ts']
        sleep_long = ts - vars['sleep_bts'] if vars['sleep_bts'] is not None else 0
        # self.aMsg(f"sleep_long={sleep_long}",1)
        if (sleep_long > self.close_sleep_LL_sec):    # 已經保持入睡一段時間
            vars['sleep_duration'] = sleep_long
            return True
        else:
            return False
        
    def update_draft_sleep_stages(self,vars,ts,status):
        '''
        stages = [0:type, 1:ti, 2:tf]
        在這階段會有 light / deep / None / Awake
        '''
        stageCnt = len(vars['sleep_stages'])
        if stageCnt:
            if status == vars['sleep_stages'][-1][0]:
                vars['sleep_stages'][-1][2] = ts
            else:
                if vars['sleep_stages'][-1][2] - vars['sleep_stages'][-1][1] < 12 and stageCnt > 2:    # 前一段太短 + 前一段不是第一段 -> 合併
                    del vars['sleep_stages'][-1]
                    if status == vars['sleep_stages'][-1][0]:
                        vars['sleep_stages'][-1][2] = ts
                    else:
                        vars['sleep_stages'].append([status, vars['sleep_stages'][-1][2], ts])
                else:
                    vars['sleep_stages'].append([status, vars['sleep_stages'][-1][2], ts])
        else:
            vars['sleep_stages'].append([status, vars['pre_ts'], ts])
    
    def update_unWellAttach_info(self,vars,ts,reset=False):
        if reset:
            vars['unWellAttach_bts'] = vars['unWellAttach_ets'] = None
        elif vars['unWellAttach_bts'] is not None:
            vars['unWellAttach_ets'] = ts
            # self.debugVars['unWellAttach_timespans'][-1][1] = ts
        else:
            vars['unWellAttach_bts'] = vars['pre_ts']
            vars['unWellAttach_ets'] = ts
            # self.debugVars['unWellAttach_timespans'].append([vars['pre_ts'],ts])

    def is_justWellAttachAfterLongDetach(self,vars,ts):
        '''
        為了避免小孩熟睡，但中途戴上去後呈現 awake 的型態
        會進來這裡，是在貼附狀態
            如果3min內有 連續20分鐘以上的未貼附 且 剛貼附不到3min分鐘，就不產出這段時間的睡眠階段
        '''
        if (vars['unWellAttach_bts'] is not None    # 有過未貼附，且還沒確認(justAttach)完畢
                and vars['unWellAttach_ets'] - vars['unWellAttach_bts'] >= 1200     # 夠長的未貼附=>極可能是未配戴
                and ts - vars['unWellAttach_ets'] <= 180):      # 剛貼附的3min內
            # self.debugVars['justWellAttachAfterLongDetach_tslist'].append(ts)
            return True
        self.update_unWellAttach_info(vars,ts,reset=True)
        return False

    def chkGoComfort(self,vars,ts,isDeep=False):
        if isDeep and vars['goComfort'] and ts - vars['deep_bts'] > 180:    # deep超過3min就解除goComfort
            vars['goComfort'] = False
            vars['comfort_bts'] = None
            # self.debugVars['comfortOff_ts_list'].append(ts)
        elif not isDeep:
            if vars['goComfort']:
                if ts - vars['comfort_bts'] >= 600:    # goComfort不超過10min
                    vars['goComfort'] = False
                    vars['comfort_bts'] = None
                    # self.debugVars['comfortOff_ts_list'].append(ts)
            elif vars['had_deep'] and ts - vars['sleep_bts'] > 1800 and ts - vars['light_bts'] > 25:    # 還沒goComfort, 有過deep, 已經睡了30min以上 且 進入light 25sec以上
                vars['goComfort'] = True
                vars['comfort_bts'] = ts
                # self.debugVars['comfortOn_ts_list'].append(ts)

    def isStillCntDropFreqt(self,vars,ts,sc):
        # 計算scDrop，若在頻繁(3min內有drop的情況下)，改以 sc - scDropSum 的結果來評估是否為 light/deep
        if sc < vars['pre_stillCnt']:   # 下降
            vars['scDropSum'] += vars['pre_stillCnt'] - sc  # 累積下降量
            vars['scDrop_ets'] = ts
            if vars['scDrop_bts'] is None:
                vars['scDrop_bts'] = ts # 目前似乎沒用到
            # self.debugVars['scDrop_info'].append([ts,vars['scDrop_bts'],vars['scDrop_ets'],vars['scDropSum']])
        elif vars['scDropSum'] and ts - vars['scDrop_ets'] >= 180:   # 上升連續3min以上, reset scDrop
            vars['scDropSum'] = 0
            vars['scDrop_bts'] = vars['scDrop_ets'] = None
        # 根據scDrop來再次判斷 sleep status
        if vars['scDropSum'] and sc - vars['scDropSum'] <= self.light_stillCnt_UL:
            return True
        
        return False
                
    def isLightSleep(self,vars,ts,sc):
        status = Sleep.LIGHT
        if sc > self.light_stillCnt_UL: # maybe deep
            if not self.isStillCntDropFreqt(vars,ts,sc):
                status = Sleep.DEEP
                vars['had_deep'] = True
                vars['light_bts'] = None    # 用於 chkGoComfort
                if vars['deep_bts'] is None:
                    vars['deep_bts'] = ts   # 用於 chkGoComfort
                self.chkGoComfort(vars,ts,isDeep=True)
        if status == Sleep.LIGHT:
            if vars['light_bts'] is None:
                vars['light_bts'] = ts
            vars['deep_bts'] = None
            self.chkGoComfort(vars,ts,isDeep=False)
        
        return status

    def draft_sleepstatus(self,vars,ts,hrDat,rrDat,sc,isWellAttached):
        status = Sleep.NONE
        if sc <= self.awake_stillCnt_UL:
            status = Sleep.AWAKE

        if isWellAttached:
            if self.is_justWellAttachAfterLongDetach(vars,ts): # 若很可能是未配戴情況，忽略貼附上去之後的前幾分鐘
                status = Sleep.NONE
            elif status == Sleep.NONE:  # 非awake
                if vars['sleep_bts'] is None:   # 之前有加一個 awake後兩分鐘 的限制，暫時先移除
                    vars['sleep_bts'] = ts
                    # self.debugVars['sleep_bts_list'].append(ts)
                    # self.aMsg(f"\nsleep starts at {ts}")
                
                vars['ts_list'].append(ts)
                vars['hr_list'].append(hrDat)
                vars['rr_list'].append(rrDat)
                vars['sc_list'].append(sc)
                # self.debugVars['calcBL_data_list'].append([ts,hrDat[0],rrDat[0],sc])

                status = self.isLightSleep(vars,ts,sc)
        else:
            self.update_unWellAttach_info(vars,ts)
        
        return status
    
    def get_NsecLong_Idx(self,ts_list,duration):
        arr = np.array(ts_list)
        tmp = np.nonzero(arr - arr[0] >= duration)[0]
        if len(tmp):
            return tmp[0]
        else:
            return None
    
    def stride_data(self,tsData,scData,hrData,rrData,stride_sec,lcf):
        lcf2 = self.get_NsecLong_Idx(tsData[lcf:],stride_sec)
        if not lcf2:
            return [lcf2,[]]
        lci = self.get_NsecLong_Idx(tsData[:lcf],stride_sec)
        tsData = tsData[lci:]
        scData = scData[lci:]
        hrData = hrData[lci:]
        rrData = rrData[lci:]
        lcf = lcf - lci + lcf2
        return [lcf,[tsData,scData,hrData,rrData]]
    
    def extend_last_BL_timespan(self, vars, ti, tf):
        if len(vars['hr_baseline']):    # 沿用上一段的baseline
            vars['hr_baseline'][-1][1] = tf
        else:
            vars['hr_baseline'].append([ti,tf,-1])

        if len(vars['rr_baseline']):
            vars['rr_baseline'][-1][1] = tf
        else:
            vars['rr_baseline'].append([ti,tf,-1])
    
    def getBaseline(self,vars,tsData,lcf):
        # self.aMsg(f"\ngetBaseline")
        scData = np.array(vars['sc_list'])
        hrData = np.array(vars['hr_list'])
        rrData = np.array(vars['rr_list'])
        hasBL = False

        while lcf < tsData.size:
            # self.aMsg(f"calc BL in timeslot:{tsData[[0,lcf]]}")
            # check received data density
            data_density = tsData[:lcf].size / ((tsData[lcf] - tsData[0])/5)
            # self.aMsg(f"data_density={data_density:.3f}",1)
            if data_density < 0.8:
                # self.debugVars['low_data_density_infos'].append([int(tsData[0]),int(tsData[lcf]),data_density])
                self.extend_last_BL_timespan(vars,tsData[0],tsData[lcf])
                lcf, datalist = self.stride_data(tsData,scData,hrData,rrData,self.calcBL_step_sec,lcf)
                if not lcf:
                    break
                tsData,scData,hrData,rrData = datalist
                # self.aMsg(f"stride data to:{tsData[[0,lcf]]}",2)
                continue
            # check high stillCnt density 
            highSC_density = np.count_nonzero(scData[:lcf] >= self.calcBL_stillCnt_LL) / lcf
            # self.aMsg(f"highSC_density={highSC_density:.3f}",1)
            if highSC_density < 0.8:
                # self.debugVars['low_highSC_density_infos'].append([int(tsData[0]),int(tsData[lcf]),highSC_density])
                self.extend_last_BL_timespan(vars,tsData[0],tsData[lcf])
                lcf, datalist = self.stride_data(tsData,scData,hrData,rrData,self.calcBL_step_sec,lcf)
                if not lcf:
                    break
                tsData,scData,hrData,rrData = datalist
                # self.aMsg(f"stride data to:{tsData[[0,lcf]]}",2)
                continue
            # check high CL density
            highHRCL_density = np.count_nonzero(hrData[:lcf,1] >= 5) / lcf
            highRRCL_density = np.count_nonzero(rrData[:lcf,1] >= 5) / lcf
            # self.aMsg(f"highHRCL_density={highHRCL_density:.3f}  highRRCL_density={highRRCL_density:.3f}",1)
            if highHRCL_density < 0.5 and highRRCL_density < 0.5:
                # if highHRCL_density < 0.5:
                #     self.debugVars['low_highHRCL_density_infos'].append([int(tsData[0]),int(tsData[lcf]),highHRCL_density])
                # if highRRCL_density < 0.5:
                #     self.debugVars['low_highRRCL_density_infos'].append([int(tsData[0]),int(tsData[lcf]),highRRCL_density])
                self.extend_last_BL_timespan(vars,tsData[0],tsData[lcf])
                lcf, datalist = self.stride_data(tsData,scData,hrData,rrData,self.calcBL_step_sec,lcf)
                if not lcf:
                    break
                tsData,scData,hrData,rrData = datalist
                # self.aMsg(f"stride data to:{tsData[[0,lcf]]}",2)
                continue
            # update baseline
            hasBL = True
            # if vars['hr_baseline']:
            #     self.aMsg(f"last hr_baseline={vars['hr_baseline'][-1]}",1)
            # else:
            #     self.aMsg(f"no hr_baseline",1)
            if len(vars['hr_baseline']) and vars['hr_baseline'][-1][2] != -1:
                vars['hr_baseline'][-1][1] = tsData[0]  # 因為是stride，所以改變上一個baseline的結尾，讓新的時段套用新的baseline
                mask = hrData[:lcf,0] < vars['hr_baseline'][-1][2]*1.3  # screen data those > 1.3X lastest baseline
                # perc50 = np.percentile(hrData[:lcf,0][mask],50) # debug
                perc40 = np.percentile(hrData[:lcf,0][mask],40)
                # perc30 = np.percentile(hrData[:lcf,0][mask],30) # debug

                if perc40 < 55:
                    vars['hr_baseline'][-1][1] = tsData[-1]
                    # self.aMsg(f"bad perc40 => extend last hr_baseline:{vars['hr_baseline'][-1]}",1)
                    # self.debugVars['hr_baseline'][-1][1] = int(tsData[-1])
                else:
                    vars['hr_baseline'][-1][1] = tsData[0]
                    vars['hr_baseline'].append([tsData[0],tsData[-1],round(perc40,2)])
                    # self.aMsg(f"update last two hr_baseline:{vars['hr_baseline'][-2:]}",1)
                    # self.debugVars['hr_baseline'][-1][1] = int(tsData[0])
                    # self.debugVars['hr_baseline'].append([int(tsData[0]),int(tsData[-1]),float(perc40)])
                
                # self.debugVars['hr_baseline_50th'][-1][1] = int(tsData[0])
                # self.debugVars['hr_baseline_30th'][-1][1] = int(tsData[0])
                # self.debugVars['hr_baseline_50th'].append([int(tsData[0]),int(tsData[-1]),float(perc50)])
                # self.debugVars['hr_baseline_30th'].append([int(tsData[0]),int(tsData[-1]),float(perc30)])
                # self.aMsg(f"50th percentile={perc50}",2)
                # self.aMsg(f"40th percentile={perc40}",2)
                # self.aMsg(f"30th percentile={perc30}",2)
            else:
                # perc50 = np.percentile(hrData[:lcf,0],50)   # debug
                perc40 = np.percentile(hrData[:lcf,0],40)
                # perc30 = np.percentile(hrData[:lcf,0],30)   # debug

                if perc40 >= 55:
                    vars['hr_baseline'].append([tsData[0],tsData[-1],round(perc40,2)])
                    # self.debugVars['hr_baseline'].append([int(tsData[0]),int(tsData[-1]),float(perc40)])
                    # self.aMsg(f"append new hr_baseline:{vars['hr_baseline'][-1]}",1)
                else:
                    vars['hr_baseline'].append([tsData[0],tsData[-1],-1])
                    # self.debugVars['hr_baseline'].append([int(tsData[0]),int(tsData[-1]),-1])
                    # self.aMsg(f"bad perc40",1)

                # self.debugVars['hr_baseline_50th'].append([int(tsData[0]),int(tsData[-1]),float(perc50)])
                # self.debugVars['hr_baseline_30th'].append([int(tsData[0]),int(tsData[-1]),float(perc30)])
                # self.aMsg(f"50th percentile={perc50}",2)
                # self.aMsg(f"40th percentile={perc40}",2)
                # self.aMsg(f"30th percentile={perc30}",2)
            
            # if vars['rr_baseline']:
            #     self.aMsg(f"last rr_baseline={vars['rr_baseline'][-1]}",1)
            # else:
            #     self.aMsg(f"no rr_baseline",1)
            if len(vars['rr_baseline']) and vars['rr_baseline'][-1][2] != -1:
                mask = rrData[:lcf,0] < vars['rr_baseline'][-1][2]*1.3  # screen data those > 1.3X lastest baseline
                # perc50 = np.percentile(rrData[:lcf,0][mask],50) # debug
                perc40 = np.percentile(rrData[:lcf,0][mask],40)
                # perc30 = np.percentile(rrData[:lcf,0][mask],30) # debug

                if perc40 < 10:
                    vars['rr_baseline'][-1][1] = tsData[-1]
                    # self.aMsg(f"bad perc40 => extend last rr_baseline:{vars['rr_baseline'][-1]}",1)
                    # self.debugVars['rr_baseline'][-1][1] = int(tsData[-1])
                else:
                    vars['rr_baseline'][-1][1] = tsData[0]
                    vars['rr_baseline'].append([tsData[0],tsData[-1],round(perc40,2)])
                    # self.aMsg(f"update last two rr_baseline:{vars['rr_baseline'][-2:]}",1)
                    # self.debugVars['rr_baseline'][-1][1] = int(tsData[0])
                    # self.debugVars['rr_baseline'].append([int(tsData[0]),int(tsData[-1]),float(perc40)])

                # self.debugVars['rr_baseline_50th'][-1][1] = int(tsData[0])
                # self.debugVars['rr_baseline_30th'][-1][1] = int(tsData[0])
                # self.debugVars['rr_baseline_50th'].append([int(tsData[0]),int(tsData[-1]),float(perc50)])
                # self.debugVars['rr_baseline_30th'].append([int(tsData[0]),int(tsData[-1]),float(perc30)])
                # self.aMsg(f"update last two rr_baseline:{vars['rr_baseline'][-2:]}",1)
                # self.aMsg(f"50th percentile={perc50}",2)
                # self.aMsg(f"40th percentile={perc40}",2)
                # self.aMsg(f"30th percentile={perc30}",2)
            else:
                # perc50 = np.percentile(rrData[:lcf,0],50)   # debug
                perc40 = np.percentile(rrData[:lcf,0],40)
                # perc30 = np.percentile(rrData[:lcf,0],30)   # debug

                if perc40 >= 10:
                    vars['rr_baseline'].append([tsData[0],tsData[-1],round(perc40,2)])
                    # self.debugVars['rr_baseline'].append([int(tsData[0]),int(tsData[-1]),float(perc40)])
                    # self.aMsg(f"append new rr_baseline:{vars['rr_baseline'][-1]}",1)
                else:
                    vars['rr_baseline'].append([tsData[0],tsData[-1],-1])
                    # self.debugVars['rr_baseline'].append([int(tsData[0]),int(tsData[-1]),-1])
                    # self.aMsg(f"bad perc40",1)

                # self.debugVars['rr_baseline_50th'].append([int(tsData[0]),int(tsData[-1]),float(perc50)])
                # self.debugVars['rr_baseline_30th'].append([int(tsData[0]),int(tsData[-1]),float(perc30)])
                # self.aMsg(f"50th percentile={perc50}",2)
                # self.aMsg(f"40th percentile={perc40}",2)
                # self.aMsg(f"30th percentile={perc30}",2)

            lcf, datalist = self.stride_data(tsData,scData,hrData,rrData,self.calcBL_stride_sec,lcf)
            if not lcf:
                break
            tsData,scData,hrData,rrData = datalist
            # self.aMsg(f"stride data to:{tsData[[0,lcf]]}",2)
        self.extend_last_BL_timespan(vars,tsData[0],tsData[-1])

        if hasBL:
            # update hr/rr limit
            vars['hr_baseline_alarm_UL'] = min(np.median(vars['hr_baseline']) * self.ratio_to_ref_UL[0], self.hr_UL)
            vars['hr_baseline_alarm_LL'] = max(np.median(vars['hr_baseline']) * self.ratio_to_ref_LL[0], self.hr_LL)
            vars['rr_baseline_alarm_LL'] = max(np.median(vars['rr_baseline']) * self.ratio_to_ref_LL[1], self.rr_LL)

            # self.aMsg(f"update hr/rr limit by baseline: hr={vars['hr_baseline_alarm_UL']} ~ {vars['hr_baseline_alarm_LL']}  rr={vars['rr_baseline_alarm_LL']}")

        return hasBL
    
    def draft_REM(self,vars):
        msg = ""
        rem_long_sum = 0

        # self.aMsg(f"\nsleep stages before REM: age={self.age}")

        if self.age < 4:
            # for ss in vars['sleep_stages']:
            #     self.aMsg(f"{ss}  {time.strftime('%Y%m%d_%H%M%S',ss[1])}, {time.strftime('%Y%m%d_%H%M%S',ss[2])}",1)

            for i,info in enumerate(vars['sleep_stages']):
                if info[0] == Sleep.LIGHT:
                    vars['sleep_stages'][i][0] = Sleep.REM
                    rem_long_sum += vars['sleep_stages'][i][2] - vars['sleep_stages'][i][1]
                elif info[0] == Sleep.DEEP:
                    vars['sleep_stages'][i][0] = Sleep.NREM
        else:
            rem_bts_LL = vars['sleep_bts'] + 1200   # 20min之後才能有REM
            rem_hr_ratio = 1.1
            rem_rr_ratio = 1.1

            tsData = np.array(vars['ts_list'])
            # get baseline
            lcf = self.get_NsecLong_Idx(tsData,self.calcBL_data_long_LL_sec)
            if not lcf:
                # self.aMsg(f"fail to get baseline to infer REM: insufficient data")
                return "fail to get baseline to infer REM: insufficient data",rem_long_sum
            if not self.getBaseline(vars,tsData,lcf):
                # self.aMsg(f"fail to get baseline to infer REM: insufficient GOOD data")
                return "fail to get baseline to infer REM: insufficient good data",rem_long_sum
            
            # === find REM timespan
            rem_timespan = []
            rem_like_bts = None
            hrBL_idx = 0
            hrBL_idx_UL = len(vars['hr_baseline'])-1
            hrBL_bts,hrBL_ets,hrBL_val = vars['hr_baseline'][hrBL_idx]  # 是否有hr_baseline已經在前面檢查
            rrBL_idx = 0
            rrBL_idx_UL = len(vars['rr_baseline'])-1
            if rrBL_idx_UL+1:
                rrBL_bts,rrBL_ets,rrBL_val = vars['rr_baseline'][rrBL_idx]
            
            rightafter_rem_bts_LL = False
            lowPeriod = 0
            for i,ts in enumerate(vars['ts_list']):
                if ts < rem_bts_LL:   # 20min之後才能有REM
                    continue
                if not rightafter_rem_bts_LL:
                    # self.aMsg(f"{ts} is just after rem_bts_LL({rem_bts_LL} {time.strftime('%Y%m%d %H:%M:%S',time.localtime(ts))})")
                    rightafter_rem_bts_LL = True
                hr = vars['hr_list'][i][0]
                rr = vars['rr_list'][i][0]
                while hrBL_idx < hrBL_idx_UL and (hrBL_val == -1 or hrBL_ets < ts):
                    hrBL_idx += 1
                    hrBL_bts,hrBL_ets,hrBL_val = vars['hr_baseline'][hrBL_idx]
                    # self.aMsg(f"change hr BL:{hrBL_bts}({time.strftime('%Y%m%d %H:%M:%S',time.localtime(hrBL_bts))}) ~ "
                    #           f"{hrBL_ets}({time.strftime('%Y%m%d %H:%M:%S',time.localtime(hrBL_ets))}) "
                    #           f"{hrBL_val}",1)
                while rrBL_idx < rrBL_idx_UL and (rrBL_val == -1 or rrBL_ets < ts):
                    rrBL_idx += 1
                    rrBL_bts,rrBL_ets,rrBL_val = vars['rr_baseline'][rrBL_idx]
                    # self.aMsg(f"change rr BL:{rrBL_bts}({time.strftime('%Y%m%d %H:%M:%S',time.localtime(rrBL_bts))}) ~ "
                    #           f"{rrBL_ets}({time.strftime('%Y%m%d %H:%M:%S',time.localtime(rrBL_ets))}) "
                    #           f"{rrBL_val}",1)

                if ((hrBL_bts <= ts and hr >= rem_hr_ratio*hrBL_val) or (rrBL_bts <= ts and rr >= rem_hr_ratio*rrBL_val)):
                    if rem_like_bts is None:
                        rem_like_bts = ts
                        # self.aMsg(f"new rem_like_bts = {rem_like_bts} {time.strftime('%Y%m%d %H:%M:%S',time.localtime(ts))}",1)
                    # elif ts - rem_like_bts >= 60:  # 有rem_like_bts,持續1min
                    #     if rem_timespan[-1][0] == rem_like_bts:
                    #         rem_timespan[-1][1] = ts
                    #     else:
                    #         rem_timespan.append([rem_like_bts,ts])
                elif rem_like_bts is not None and ts - rem_like_bts >= 90:  # 沒有比baseline高了, 且已持續高 1.5min以上 => REM
                    rem_timespan.append([rem_like_bts, ts])
                    rem_long_sum += ts - rem_like_bts
                    rem_like_bts = None
                    # self.aMsg(f"new rem_span = {rem_timespan[-1]}"
                    #           f"({time.strftime('%Y%m%d %H:%M:%S',time.localtime(rem_timespan[-1][0]))} ~ "
                    #           f"{time.strftime('%Y%m%d %H:%M:%S',time.localtime(rem_timespan[-1][1]))}) "
                    #           f"sum={rem_long_sum}",1)
                elif rem_like_bts is not None:  # 沒有比baseline高了
                    lowPeriod += ts - vars['ts_list'][i-1]
                    if lowPeriod > 30:
                        # self.aMsg(f"ts={ts}={time.strftime('%Y%m%d %H:%M:%S',time.localtime(ts))}",2)
                        # self.aMsg(f"(hrBL_bts({hrBL_bts}) <= ts({ts})? and hr({hr}) >= {rem_hr_ratio}*hrBL_val({rem_hr_ratio*hrBL_val})?)",3)
                        # self.aMsg(f"(rrBL_bts({rrBL_bts}) <= ts and rr({rr}) >= {rem_rr_ratio}*rrBL_val({rem_rr_ratio*rrBL_val})?)",3)
                        # self.aMsg(f"ts - rem_like_bts = ({ts - rem_like_bts}) >= 90?",3)
                        rem_like_bts = None
                        lowPeriod = 0
                
                # 超出有baseline, sleep_stages時間了
                if ((hrBL_idx == hrBL_idx_UL and hrBL_ets < ts) and (rrBL_idx == rrBL_idx_UL and rrBL_ets < ts)):
                        # or (ss_idx == ss_idx_UL and vars['sleep_stages'][ss_idx][2] <= rem_like_bts)):
                    # self.aMsg(f"no more BL: "
                    #           f"hrBL_idx{hrBL_idx} == {hrBL_idx_UL} and "
                    #           f"hrBL_ets({hrBL_ets}) < {ts}({time.strftime('%Y%m%d %H:%M:%S',time.localtime(ts))})",1)
                    break
            
            # self.aMsg(f"\ncurrent sleep stages")
            # for ss in vars['sleep_stages']:
            #     self.aMsg(f"{ss}  {time.strftime('%Y%m%d_%H%M%S',time.localtime(ss[1]))}, {time.strftime('%Y%m%d_%H%M%S',time.localtime(ss[2]))}",1)
            
            # === merge REM into draft sleep stages
            if len(rem_timespan):   # 因為中間插入改list很麻煩，所以還是最後再來處理
                # self.debugVars['rem_timespans'].extend(copy.deepcopy(rem_timespan))
                # self.debugVars['rem_long_sum_list'].append(rem_long_sum)

                rem_idx = len(rem_timespan)-1
                rem_bts, rem_ets = rem_timespan[rem_idx]
                # rem_long = rem_ets - rem_bts

                rev_ss = copy.deepcopy(vars['sleep_stages'][::-1])
                # max_rev_ss_idx = len(rev_ss) - 1
                max_ss_idx = orig_max_ss_idx = len(vars['sleep_stages']) - 1
                
                # self.aMsg(f"\nmerge REM into draft sleep stages")
                for i,(typ,bts,ets) in enumerate(rev_ss):
                    # self.aMsg(f"{i}({orig_max_ss_idx - i:02d}) {typ}: {bts} ~ {ets}"
                    #           f"({time.strftime('%Y%m%d-%H:%M:%S',time.localtime(bts))} ~ {time.strftime('%Y%m%d-%H:%M:%S',time.localtime(ets))})  "
                    #           f"{typ}  rem: {rem_idx}  {rem_bts} ~ {rem_ets}"
                    #           f"({time.strftime('%Y%m%d-%H:%M:%S',time.localtime(rem_bts))} ~ {time.strftime('%Y%m%d-%H:%M:%S',time.localtime(rem_ets))})  ")
                    # 找出對應的sleep stage
                    if bts >= rem_ets:
                        continue
                    ss_orig_idx = orig_max_ss_idx - i
                    next_ss_orig_idx = ss_orig_idx + 1

                    # === 找出rem開頭在這個睡眠階段內的 (rem_bts會對應到有hr/rr/sc資料的，所以不會是Sleep.NONE)
                    while rem_idx >= 0 and rem_bts >= bts and rem_bts < ets:    # 持續把該睡眠時段內的rem_span加入
                        vars['sleep_stages'][ss_orig_idx][2] = rem_bts
                        # self.aMsg(f"update stage{ss_orig_idx:02d} ets:{vars['sleep_stages'][ss_orig_idx]}",1)

                        isNextNone = False
                        # == 如果rem_span橫跨多個睡眠時段(rem_ets > next_stage_ets)(通常比較不會), 去找到最後一段
                        while next_ss_orig_idx <= max_ss_idx and rem_ets > vars['sleep_stages'][next_ss_orig_idx][2]:
                            # self.aMsg(f"next_stage: idx_{next_ss_orig_idx}  "
                            #           f"{vars['sleep_stages'][next_ss_orig_idx]}=>  rem_ets > next_stage_ets",1)
                            if vars['sleep_stages'][next_ss_orig_idx][0] == Sleep.NONE:    # 跳過NONE
                                isNextNone = True
                                next_ss_orig_idx += 1
                                # self.aMsg(f"change next_ss_orig_idx={next_ss_orig_idx:02d}",2)
                                continue

                            # self.aMsg(f"del {vars['sleep_stages'][next_ss_orig_idx]}",1)
                            del vars['sleep_stages'][next_ss_orig_idx]
                            max_ss_idx = len(vars['sleep_stages']) - 1
                            # self.aMsg(f"update max_ss_idx={max_ss_idx}",1)

                        next_ss_orig_idx = ss_orig_idx + 1  # 因為有可能因為在前面處理時跳到下N個
                        if rem_ets > ets:   # 橫跨到後面的階段(要繞過NONE)
                            # self.aMsg(f"rem_ets > ets: next_ss_orig_idx({next_ss_orig_idx:02d}) <= max_ss_idx({max_ss_idx})? "
                            #           f"and nextSS is not None?{not isNextNone}",1)
                            if next_ss_orig_idx <= max_ss_idx and not isNextNone: # 有下一段
                                vars['sleep_stages'][next_ss_orig_idx][1] = rem_ets
                                # self.aMsg(f"update bts of next sleep_stage({next_ss_orig_idx:02d})={vars['sleep_stages'][next_ss_orig_idx]}",2)
                                # vars['sleep_stages'][ss_orig_idx][2] = rem_bts
                                # vars['sleep_stages'].insert(next_ss_orig_idx,[Sleep.REM,rem_bts,rem_ets])
                            # else:
                                # vars['sleep_stages'][ss_orig_idx][2] = rem_bts
                                # vars['sleep_stages'].append([Sleep.REM,rem_bts,rem_ets])
                        # elif rem_ets == ets:
                            # vars['sleep_stages'][ss_orig_idx][2] = rem_bts
                            # vars['sleep_stages'].insert(next_ss_orig_idx,[Sleep.REM,rem_bts,rem_ets])
                        elif rem_ets != ets:
                            # vars['sleep_stages'][ss_orig_idx][2] = rem_bts
                            vars['sleep_stages'].insert(next_ss_orig_idx,[typ,rem_ets,ets])
                            # self.aMsg(f"insert {typ} at next sleep_stage({next_ss_orig_idx:02d})={vars['sleep_stages'][next_ss_orig_idx]}",1)
                            # vars['sleep_stages'].insert(next_ss_orig_idx,[Sleep.REM,rem_bts,rem_ets])
                        vars['sleep_stages'].insert(next_ss_orig_idx,[Sleep.REM,rem_bts,rem_ets])
                        # self.aMsg(f"insert REM at next sleep_stage({next_ss_orig_idx:02d})={vars['sleep_stages'][next_ss_orig_idx]}",1)

                        # self.aMsg(f"chk sleep stages:",1)
                        # for ss in vars['sleep_stages'][max(0,ss_orig_idx-1):ss_orig_idx+3]:
                        #     self.aMsg(f"{ss}",2)

                        rem_idx -= 1
                        if rem_idx < 0:
                            break
                        ets = rem_bts   # 這段的ets已經變更了
                        rem_bts, rem_ets = rem_timespan[rem_idx]
                        # self.aMsg(f"\nmerge another REM {rem_bts} ~ {rem_ets}"
                        #           f"({time.strftime('%Y%m%d-%H:%M:%S',time.localtime(rem_bts))} ~ {time.strftime('%Y%m%d-%H:%M:%S',time.localtime(rem_ets))})",1)
            else:
                msg = "NO REM"
        # self.aMsg(f"\nsleep stages after draft_REM")
        # for i,ss in enumerate(vars['sleep_stages']):
        #     self.aMsg(f"{ss}  "
        #               f"{time.strftime('%Y%m%d_%H%M%S',time.localtime(ss[1]))}, "
        #               f"{time.strftime('%Y%m%d_%H%M%S',time.localtime(ss[2]))}  "
        #               f"{ss[1] == vars['sleep_stages'][i-1][2]}  "
        #               f"{ss[1] < ss[2]}",1)
        
        # self.aMsg(f"draft_REM end: rem_long_sum={rem_long_sum}  msg={msg}  ")
        return msg,rem_long_sum
        
    def scale_REM(self,vars,rem_long_sum):
        # self.aMsg(f"\nscale_REM (developing!)")
        if not rem_long_sum:
            return False
        
        gain = self.rem_ratio_target / (rem_long_sum / vars['sleep_duration']) - 1

        rev_ss = copy.deepcopy(vars['sleep_stages'][::-1])
        # max_rev_ss_idx = len(rev_ss) - 1
        max_ss_idx = orig_max_ss_idx = len(vars['sleep_stages']) - 1
        
        # self.aMsg(f"\nscaling REM to meet the requirement of rem_ratio_target={self.rem_ratio_target}  gain={gain}")
        for i,(typ,bts,ets) in enumerate(rev_ss):
            # self.aMsg(f"{i}({orig_max_ss_idx - i:02d}): {bts} ~ {ets}  {typ}")
            if typ != Sleep.REM:
                continue
            ss_orig_idx = orig_max_ss_idx - i
            next_ss_orig_idx = ss_orig_idx + 1
            pre_ss_orig_idx = ss_orig_idx - 1
            add_REM_long = (vars['sleep_stages'][ss_orig_idx][2] - vars['sleep_stages'][ss_orig_idx][1]) * gain
            # self.aMsg(f"target of add_REM_long={add_REM_long}",1)
            if (i and vars['sleep_stages'][next_ss_orig_idx][0] != Sleep.AWAKE):    # 還有下一段 且 不是awake
                # self.aMsg(f"")
                new_rem_ets = int(max(min(vars['sleep_stages'][next_ss_orig_idx][2] - self.stage_long_LL_sec,   # 確保 這個與下一段 都有保留到
                                          ets + add_REM_long),
                                    min(ets,bts + self.stage_long_LL_sec)))
                add_REM_long -= new_rem_ets - ets
                # self.aMsg(f"modify next stage: new_rem_ets={new_rem_ets}  update add_REM_long={add_REM_long}",2)
            else:
                next_ss_orig_idx = None
                new_rem_ets = ets
                # self.aMsg(f"no next stage: new_rem_ets=ets  add_REM_long={add_REM_long}",2)

            if (pre_ss_orig_idx >= 0 and vars['sleep_stages'][pre_ss_orig_idx][0] != Sleep.AWAKE):  # 有前一段 且 不是awake
                new_rem_bts = int(min(max(vars['sleep_stages'][pre_ss_orig_idx][1] + self.stage_long_LL_sec,    # 確保 這個與前一段 都有保留到
                                      bts - add_REM_long),
                                    max(bts,new_rem_ets - self.stage_long_LL_sec)))
                # self.aMsg(f"modify previous stage: new_rem_bts={new_rem_bts}  update add_REM_long={add_REM_long}",2)
            else:
                pre_ss_orig_idx = None
                new_rem_bts = bts
                # self.aMsg(f"no previous stage: new_rem_bts=bts  add_REM_long={add_REM_long}",2)

            if new_rem_ets != ets:
                vars['sleep_stages'][next_ss_orig_idx][1] = new_rem_ets
                vars['sleep_stages'][ss_orig_idx][2] = new_rem_ets
                # self.aMsg(f"new_rem_ets({new_rem_ets}) != ets({ets})",1)
                # self.aMsg(f"chk sleep stages:",1)
                # for ss in vars['sleep_stages'][max(0,ss_orig_idx-1):ss_orig_idx+3]:
                #     self.aMsg(f"{ss}",2)
            if new_rem_bts != bts:
                vars['sleep_stages'][pre_ss_orig_idx][2] = new_rem_bts
                vars['sleep_stages'][ss_orig_idx][1] = new_rem_bts
                # self.aMsg(f"new_rem_bts({new_rem_bts}) != bts({bts})",1)
                # self.aMsg(f"chk sleep stages:",1)
                # for ss in vars['sleep_stages'][max(0,ss_orig_idx-1):ss_orig_idx+3]:
                #     self.aMsg(f"{ss}",2)

        # self.aMsg(f"\nsleep stages after scale_REM")
        # for i,ss in enumerate(vars['sleep_stages']):
        #     self.aMsg(f"{ss}  "
        #               f"{time.strftime('%Y%m%d_%H%M%S',time.localtime(ss[1]))}, "
        #               f"{time.strftime('%Y%m%d_%H%M%S',time.localtime(ss[2]))}  "
        #               f"{ss[1] == vars['sleep_stages'][i-1][2]}  "
        #               f"{ss[1] < ss[2]}",1)
        return True
    
    def is_fatal(self,vars,ts,hrDat,rrDat,attached,status):
        # self.aMsg(f"\nis_fatal  status={status}  attached={attached}  pre_ts={vars['pre_ts']}  ts={ts}")
        if status is Sleep.NONE or not attached or vars['pre_ts'] is None:
            # self.aMsg(f"\nis_fatal: ts={ts}  status={status} is None?  attached?{attached}  pre_ts?{vars['pre_ts']}  ts={ts} => quit and return False ")
            return False
                
        if ts > vars['pre_ts'] + 17:    # 接收到的訊息間隔過長 => reset
            # self.aMsg(f"\nis_fatal: ts({ts}) > pre_ts({vars['pre_ts']}) + 17 => reset")
            for typ in ['hr','rr']:
                vars[f'zero_{typ}_cnt'] = 0   # 遇到無效的hr
                vars[f'same_{typ}_cnt'] = 0   # 連續一樣的hr
                vars[f'rt_ref_{typ}'] = 0     # real time ref hr(和 sleepstage的baseline不同，這是用來即時判斷上升還是下降的)
                vars[f'{typ}_rising_blvl'] = 300
                vars[f'{typ}_rising_bts'] = 0
                vars[f'{typ}_falling_blvl'] = 0
                vars[f'{typ}_falling_bts'] = 0
                vars[f'{typ}_rising_cnt'] = 0
                vars[f'{typ}_falling_cnt'] = 0

        data = {'hr':hrDat, 'rr':rrDat}
        res = False
        expired_t = ts - self.expired_min
        abs_UL = [self.hr_UL, self.rr_UL]
        abs_LL = [self.hr_LL, self.rr_LL]
        # clth = 5 if self.scaledSC else 0.5
        for dat_idx,info in enumerate(data.items()):
            typ,(val,cl) = info

            if cl < 5:  #clth:
                continue

            # 變化太大 不合理 => 跳過
            if ((val >= min(vars[f'pre_{typ}'], vars[f'pre2_{typ}'])*self.ratio_to_pre_UL[dat_idx])
                    or (val <= max(vars[f'pre_{typ}'], vars[f'pre2_{typ}'])*self.ratio_to_pre_LL[dat_idx])):
                vars[f'last_{typ}_bigChange_ts'] = ts
                # self.aMsg(f"\nis_fatal: bigChange at ts={ts}={ts-self.debugVars['t0']}  {typ}({val}) >= "
                #           f"min(pre({vars[f'pre_{typ}']}), pre2({vars[f'pre2_{typ}']}))*{self.ratio_to_pre_UL[dat_idx]}="
                #           f"{min(vars[f'pre_{typ}'], vars[f'pre2_{typ}'])*self.ratio_to_pre_UL[dat_idx]}  OR  "
                #           f"<= {max(vars[f'pre_{typ}'], vars[f'pre2_{typ}'])*self.ratio_to_pre_LL[dat_idx]}")
                # self.debugVars[f'bigChange_{typ}_list'].append([ts,val])
                continue
                
            # 可能還是亂跳之後不穩定的情況(尤其是RR)
            if ts - vars[f'last_{typ}_bigChange_ts'] <= 11:
                continue

            # = remove expired sharp cnt
            for typ2 in ['falling','rising']:
                orig_idx = -1
                for t in vars[f'{typ}_has_sharp_{typ2}_ts_list'][::-1]:
                    if t <= expired_t:
                        del vars[f'{typ}_has_sharp_{typ2}_ts_list'][orig_idx]
                        orig_idx += 1
                    orig_idx -= 1

            if not val:    # 不是有效的hr, rr
                vars[f'zero_{typ}_cnt'] += 1
                if vars[f'zero_{typ}_cnt'] > 2: # 太多次就得要reset
                    vars[f'{typ}_rising_cnt'] = vars[f'{typ}_falling_cnt'] = 0
            else:
                # pre2,pre都有值, pre2 != pre(有轉折), pre2 => 即時的參考值
                if vars[f'pre2_{typ}'] and vars[f'pre_{typ}'] and vars[f'pre2_{typ}'] != vars[f'pre_{typ}']:
                    vars[f'rt_ref_{typ}'] = vars[f'pre2_{typ}']
                    # self.debugVars[f'rt_ref_{typ}_list'].append([vars['pre2_ts'],vars[f'rt_ref_{typ}']])

                # 如果連續4個都不變，就重置 rising/falling cnt
                if val == vars[f'pre_{typ}']:
                    vars[f'same_{typ}_cnt'] += 1
                    if vars[f'same_{typ}_cnt'] > 3:
                        vars[f'{typ}_rising_cnt'] = vars[f'{typ}_falling_cnt'] = 0
                else:
                    vars[f'same_{typ}_cnt'] = 0
                
                # 雖然還是等值，但最後可能會覺得還在uptrend上, 所以暫時允許
                # 這段用來更新 上升下降的起始點 與 limit
                if vars[f'same_{typ}_cnt'] <= 3:
                    if vars[f'rt_ref_{typ}'] and val > vars[f'rt_ref_{typ}']:
                        if not vars[f'{typ}_rising_cnt']:   #定義起始點 時間 與 數值 => 順便更新 limit
                            if vars[f"pre2_{typ}"] and vars[f"pre_{typ}"] >= vars[f"pre2_{typ}"]:
                                vars[f"{typ}_rising_bts"] = vars['pre2_ts']
                                vars[f"{typ}_rising_blvl"] = vars[f'pre2_{typ}']
                                alarmUL = min((min(vars[f'{typ}_baseline_alarm_UL'], vars[f"pre2_{typ}"] * self.ratio_to_ref_UL[dat_idx])
                                                           if vars[f'{typ}_baseline_alarm_UL'] is not None
                                                           else vars[f"pre2_{typ}"] * self.ratio_to_ref_UL[dat_idx]), abs_UL[dat_idx])
                                # self.debugVars[f'{typ}_rising_start_list'].append([vars['pre2_ts'],vars[f"pre2_{typ}"]])
                            else:
                                vars[f"{typ}_rising_bts"] = vars['pre_ts']
                                vars[f"{typ}_rising_blvl"] = vars[f'pre_{typ}']
                                alarmUL = min((min(vars[f'{typ}_baseline_alarm_UL'], vars[f"pre_{typ}"] * self.ratio_to_ref_UL[dat_idx])
                                                           if vars[f'{typ}_baseline_alarm_UL'] is not None
                                                           else vars[f"pre_{typ}"] * self.ratio_to_ref_UL[dat_idx]), abs_UL[dat_idx])
                                # self.debugVars[f'{typ}_rising_start_list'].append([vars['pre_ts'],vars[f"pre_{typ}"]])
                            vars[f'{typ}_alarm_UL'] = ((vars[f'{typ}_alarm_UL']*0.9 + alarmUL*0.1
                                                            if alarmUL >= vars[f'{typ}_alarm_UL']
                                                            else vars[f'{typ}_alarm_UL']*0.95 + alarmUL*0.05)
                                                       if vars[f'{typ}_alarm_UL'] is not None
                                                       else alarmUL)
                        vars[f'{typ}_rising_cnt'] += 1
                        if vars[f'{typ}_rising_cnt'] > 1:  # 比較確定是rising了
                            vars[f'{typ}_falling_cnt'] = 0
                    elif val < vars[f'rt_ref_{typ}']:
                        if not vars[f'{typ}_falling_cnt']:  #定義起始點 時間 與 數值 => 順便更新 limit
                            if vars[f'last_overUL_{typ}_ts'] is not None and ts - vars[f'last_overUL_{typ}_ts'] < 21 and vars[f'last_overUL_{typ}_blvl'] - max(vars[f"pre_{typ}"], vars[f"pre2_{typ}"]) < 3:   # 從過高點下降的，要從前面的上升起點當基準高度
                                vars[f"{typ}_falling_bts"] = vars[f'last_overUL_{typ}_ts']
                                alarmLL = max(vars[f'last_overUL_{typ}_blvl'] * self.ratio_to_ref_LL[dat_idx], abs_LL[dat_idx])
                                # self.debugVars[f'{typ}_falling_start_list'].append([vars[f"{typ}_falling_bts"], vars[f'last_overUL_{typ}_lvl']])
                                # self.aMsg(f"{typ} {ts}: near over alarmUL pk(lvl={vars[f'last_overUL_{typ}_lvl']}): rising at lvl={vars[f'{typ}_rising_blvl']}")
                            elif vars[f"pre2_{typ}"] and vars[f"pre_{typ}"] <= vars[f"pre2_{typ}"]:
                                vars[f"{typ}_falling_bts"] = vars['pre2_ts']
                                alarmLL = max((max(vars[f'{typ}_alarm_LL'], vars[f"pre2_{typ}"] * self.ratio_to_ref_LL[dat_idx])
                                                           if vars[f'{typ}_baseline_alarm_LL'] is not None
                                                           else vars[f"pre2_{typ}"] * self.ratio_to_ref_LL[dat_idx]), abs_LL[dat_idx])
                                # self.debugVars[f'{typ}_falling_start_list'].append([vars['pre2_ts'],vars[f"pre2_{typ}"]])
                                # if typ == 'rr' and (2500 < ts < 2800 or 4700 < ts < 5000):
                                #     msg = (f'{vars[f"pre2_{typ}"]} * {self.ratio_to_ref_LL[dat_idx]}'
                                #            if vars[f'{typ}_baseline_alarm_LL'] is None
                                #            else f'max of ({vars[f"{typ}_alarm_LL"]}, {vars[f"pre2_{typ}"]} * {self.ratio_to_ref_LL[dat_idx]})')
                                #     self.aMsg(f"{typ} {ts}: falling_start at {vars[f'{typ}_falling_bts']}  updated temp alarm_LL={alarmLL}  ({msg})")
                            else:
                                vars[f"{typ}_falling_bts"] = vars['pre_ts']
                                alarmLL = max((max(vars[f'{typ}_alarm_LL'], vars[f"pre_{typ}"] * self.ratio_to_ref_LL[dat_idx])
                                                           if vars[f'{typ}_baseline_alarm_LL'] is not None
                                                           else vars[f"pre_{typ}"] * self.ratio_to_ref_LL[dat_idx]), abs_LL[dat_idx])
                                # self.debugVars[f'{typ}_falling_start_list'].append([vars['pre_ts'],vars[f"pre_{typ}"]])
                                # if typ == 'rr' and (2700 < ts < 2800 or 4900 < ts < 5000):
                                #     msg = (f'{vars[f"pre_{typ}"]} * {self.ratio_to_ref_LL[dat_idx]}'
                                #            if vars[f'{typ}_baseline_alarm_LL'] is None
                                #            else f'max of ({vars[f"{typ}_alarm_LL"]}, {vars[f"pre_{typ}"]} * {self.ratio_to_ref_LL[dat_idx]})')
                                #     self.aMsg(f"{typ} {ts}: falling_start at {vars[f'{typ}_falling_bts']}  updated alarm_LL={vars[f'{typ}_alarm_LL']}  ({msg})")
                            vars[f'{typ}_alarm_LL'] = ((vars[f'{typ}_alarm_LL']*0.9 + alarmLL*0.1
                                                            if alarmLL <= vars[f'{typ}_alarm_LL']
                                                            else vars[f'{typ}_alarm_LL']*0.95 + alarmLL*0.05)
                                                       if vars[f'{typ}_alarm_LL'] is not None
                                                       else alarmLL)
                            # if typ == 'rr' and (2500 < ts < 2800 or 4700 < ts < 5000):
                            #     self.aMsg(f"{typ} {ts}: updated alarm_LL={vars[f'{typ}_alarm_LL']}  ({msg})")
                        vars[f'{typ}_falling_cnt'] += 1
                        if vars[f'{typ}_falling_cnt'] > 1:
                            vars[f'{typ}_rising_cnt'] = 0
                    
                    if vars[f'{typ}_rising_cnt'] > 1 and vars[f'{typ}_rising_cnt'] < vars[f'{typ}_falling_cnt']:
                        vars[f'{typ}_falling_cnt'] = 0
                    elif vars[f'{typ}_falling_cnt'] > 1 and vars[f'{typ}_falling_cnt'] < vars[f'{typ}_rising_cnt']:
                        vars[f'{typ}_rising_cnt'] = 0
                
                # self.debugVars[f'{typ}_alarm_UL_list'].append([ts,vars[f'{typ}_alarm_UL']])
                # self.debugVars[f'{typ}_alarm_LL_list'].append([ts,vars[f'{typ}_alarm_LL']])

                # if vars[f'{typ}_alarm_UL'] is not None and val >= vars[f'{typ}_alarm_UL']:
                #     self.aMsg(f"{typ} overUL ts={ts}: val_{val} >= {vars[f'{typ}_alarm_UL']:.2f} and 20 < {ts - vars[f'{typ}_rising_bts']} <= 60??",0)
                # if vars[f'{typ}_alarm_LL'] is not None and val <= vars[f'{typ}_alarm_LL']:
                #     self.aMsg(f"{typ} overLL ts={ts}: val_{val} <= {vars[f'{typ}_alarm_LL']:.2f} and 20 < {ts - vars[f'{typ}_falling_bts']} <= 60??",0)

                if vars[f'{typ}_alarm_UL'] is not None and val >= vars[f'{typ}_alarm_UL']:
                    vars[f'last_overUL_{typ}_ts'] = ts
                    vars[f'last_overUL_{typ}_lvl'] = val
                    vars[f'last_overUL_{typ}_blvl'] = vars[f"{typ}_rising_blvl"]
                    # self.aMsg(f"{typ} {ts}sec lvl={val} over alarmUL: blvl={vars[f'{typ}_rising_blvl']}")

                if vars[f'{typ}_alarm_UL'] is not None and val >= vars[f'{typ}_alarm_UL'] and 20 < ts - vars[f"{typ}_rising_bts"] <= 60:  # 超過界線 且 是合理的急速上升才算
                    # vars[f'{typ}_has_sharp_rising_cnt'] += 1
                    vars[f'{typ}_has_sharp_rising_ts_list'].append(ts)
                    # self.debugVars[f'{typ}_has_sharp_rising_list'].append([ts,val])
                    # self.aMsg(f"{typ}_has_sharp_rising ts={ts}: val_{val:.2f} >= {vars[f'{typ}_alarm_UL']:.2f} and 20 < {ts - vars[f'{typ}_rising_bts']} <= 60",0)
                elif vars[f'{typ}_alarm_LL'] is not None and val <= vars[f'{typ}_alarm_LL'] and 20 < ts - vars[f"{typ}_falling_bts"]:
                    # vars[f'{typ}_has_sharp_falling_cnt'] += 1
                    vars[f'{typ}_has_sharp_falling_ts_list'].append(ts)
                    # self.debugVars[f'{typ}_has_sharp_falling_list'].append([ts,val])
                    # self.aMsg(f"{typ}_has_sharp_falling ts={ts}: val_{val:.2f} <= {vars[f'{typ}_alarm_LL']:.2f} and 20 < {ts - vars[f'{typ}_falling_bts']} <= 60",0)
                
                if ts > vars['fatal_alram_mute_ets']:
                    c0 = vars['rr_has_sharp_falling_ts_list']
                    c1 = (vars['hr_has_sharp_rising_ts_list'] and vars['hr_has_sharp_falling_ts_list']
                        and (np.array(vars['hr_has_sharp_rising_ts_list']) < vars['hr_has_sharp_falling_ts_list'][-1]).any())   # hr要先急速上升 再急速下降
                    if c0 or c1:
                        res = True
                        vars['fatal_alram_mute_ets'] = ts + 600
                        if c1:  # 因為為了保留能看到"hr要先急速上升"這個條件
                            vars['hr_has_sharp_rising_ts_list'] = []
                        vars[f'hr_has_sharp_falling_ts_list'] = []
                        vars[f'rr_has_sharp_falling_ts_list'] = []
                        # self.debugVars['fatal_alarm_ts_list'].append(ts)
                        # self.aMsg(f"{typ} fatal alarm ts={ts}: c0(rr)?{c0}  c1(hr)?{c1}",1)
                elif ts <= vars['fatal_alram_mute_ets']:
                    # vars[f'hr_has_sharp_rising_ts_list'] = [] # 因為為了保留能看到"hr要先急速上升"這個條件
                    vars[f'hr_has_sharp_falling_ts_list'] = []
                    vars[f'rr_has_sharp_falling_ts_list'] = []

            # for typ2 in ['falling','rising']:
            #     self.debugVars[f'{typ}_{typ2}_cnt_list'].append([ts,vars[f'{typ}_{typ2}_cnt']])

        return res

    def addData(self,udid,ts,hrDat,rrDat,sc,isWellAttached):
        '''
        hrDat: hr, CL
        rrDat: rr, CL
        scDat: sc
        isWellAttached: isWellAttached
        '''
        vars = self.load_context(udid)
        msg = ""
        vars['awakeAlarm_ts'] = 0

        ts = int(ts)
        # if self.debugVars['t0'] is None:
        #     self.debugVars['t0'] = ts

        sleepstages = None

        if vars['pre_ts'] is not None and ts - vars['pre_ts'] >= 1200:
            # self.aMsg(f"right after a long blank: {ts - vars['pre_ts']}sec")
            if self.goCalcSS(vars,ts,afterLongLoss=True):
                msgtmp,rem_long_sum = self.draft_REM(vars)
                msg += msgtmp
                
                self.scale_REM(vars,rem_long_sum)
                # self.debugVars['sleep_stages'].extend(copy.deepcopy(vars['sleep_stages']))
                sleepstages = copy.deepcopy(vars['sleep_stages']) if len(vars['sleep_stages']) > 1 else None
                vars['last_sleep_stages'] = sleepstages
            # self.aMsg(f"clear_vars at {ts}")
            self.clear_vars(vars)   #,udid)
        elif vars['pre_ts'] is None:
            vars['pre_ts'] = ts - 5

        # self.debugVars['ts_list'].append(ts)
        # self.debugVars['hr_list'].append(hrDat)
        # self.debugVars['rr_list'].append(rrDat)
        # self.debugVars['sc_list'].append(sc)
        # self.debugVars['isWellAttach_list'].append(isWellAttached)
        
        status = self.draft_sleepstatus(vars,ts,hrDat,rrDat,sc,isWellAttached)
        # self.debugVars['draft_status_list'].append(status)

        self.update_draft_sleep_stages(vars, ts, status)

        if status == Sleep.AWAKE:
            vars['awakeAlarm_ts'] = self.getAwakeAlarm(vars, ts)

            goEnd = True
            # hasSS = False   # debug
            if self.goCalcSS(vars,ts,afterLongLoss=False):   # 確定起床了(睡夠久) 才計算(並結束)這段睡眠
                msgtmp,rem_long_sum = self.draft_REM(vars)
                msg += msgtmp
                self.scale_REM(vars,rem_long_sum)
                # self.debugVars['sleep_stages'].extend(copy.deepcopy(vars['sleep_stages']))
                # hasSS = True    # debug
            elif vars['sleep_bts'] is not None or vars['unWellAttach_bts'] is not None:   # 有睡著過(但時間不夠), 或 剛貼附 或 未貼附，就清除stages(=> 還沒睡著過 且 貼附夠久 就保留awake，繼續累積stage)
                msg = "This sleep duration is too short to infer sleep stages!"
                # self.aMsg(f"{ts}sec: {msg}")
                goEnd = False
            else:
                goEnd = False

            if goEnd:
                sleepstages = copy.deepcopy(vars['sleep_stages']) if len(vars['sleep_stages']) > 1 else None
                vars['last_sleep_stages'] = sleepstages
                # self.aMsg(f"clear_vars at {ts} hasSS={hasSS}")
                self.clear_vars(vars)   #,udid,hasSS)
            else:
                # self.aMsg(f"clear_vars at {ts} hasSS={hasSS}")
                self.clear_vars(vars)   #,udid)
        
        fatal_alarm = False
        if vars['pre2_hr'] is not None:
            fatal_alarm = self.is_fatal(vars,ts,hrDat,rrDat,isWellAttached,status)
            if fatal_alarm:
                vars['last3_fatalalarm_ts'].append(ts)
                vars['last3_fatalalarm_ts'] = vars['last3_fatalalarm_ts'][-3:]
        
        vars['pre_stillCnt'] = sc
        vars['pre2_ts'] = vars['pre_ts']
        vars['pre2_hr'] = vars['pre_hr']
        vars['pre2_rr'] = vars['pre_rr']
        vars['pre_ts'] = ts
        vars['pre_hr'] = hrDat[0]
        vars['pre_rr'] = rrDat[0]

        self.save_context(udid,vars)
        return udid,vars,sleepstages,vars['goComfort'],ts - vars['awakeAlarm_ts'] < 1,fatal_alarm,msg   # sleepstages is not None，就表示有產出


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
    stillCntfn="./sleepstate_2022-08-12-23-20-52/2022-08-12-23-20-52-pose_activity_v20221021.csv"
    attachfn=""
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
    
    # get wellAttach status from broadcast which was upated every 5sec
    ts = None
    data = pd.read_csv(attachfn, header=[0],skiprows=[],quotechar="'")
    attachData = data[['tsMic','isWellAttached']].to_numpy()
    cnt = 1
    wellatt_list = []
    wellatt = None
    for dat in attachData:
        tbc = cnt*5
        if dat[0] <= tbc:
            ts = dat[0]
            wellatt = dat[1]
        elif ts is not None:    # dat[0] > tbc
            while ts > tbc:
                if len(wellatt_list):
                    wellatt_list.append([tbc,wellatt_list[-1][1]])
                tbc += 5
                cnt += 1
            wellatt_list.append([tbc,wellatt])
            ts = dat[0]
            wellatt = dat[1]
            cnt += 1
        else:
            ts = dat[0]
            wellatt = dat[1]
            wellatt_list.append([tbc,0,0])
            cnt += 1

    udid = "123"

    sleepstages_fatalalarm = SleepStatus_FatalAlarm(udid=udid,age=2)   # 需要實際age(幾個月大)這個參數
    # sleepstages_fatalalarm.save_context(udid)   # init

    # = simulation of receiving broadcast data
    len_hrlist = len(hr_list)
    len_rrlist = len(rr_list)
    len_stillCntlist = len(stillCnt_list)
    len_wellatt_list = len(wellatt_list)
    idx_bc = 0  # broadcase index
    tbc = 5
    go = gohr = gorr = gostill = True
    while idx_bc < len_hrlist and idx_bc < len_rrlist and idx_bc < len_stillCntlist and idx_bc < len_wellatt_list:
        ts = tbc
        hrts = hr_list[idx_bc][0]
        rrts = rr_list[idx_bc][0]
        stillCntts = stillCnt_list[idx_bc][0]
        wellatt_ts = wellatt_list[idx_bc][0]
        # if not (hrts == rrts and rrts == stillCntts and stillCntts == wellatt_ts):  # 若確認無誤，dat就可以移除ts
        #     input('ts does not match!',ts,hrts,rrts,stillCntts,wellatt_ts)

        udid,vars,sleepstages,goComfort,goAwakeAlarm,goFatalAlarm,msg = sleepstages_fatalalarm.addData(udid,
                                                                         ts,
                                                                         hr_list[idx_bc][1:],
                                                                         rr_list[idx_bc][1:],
                                                                         stillCnt_list[idx_bc][1],  # stillcnt
                                                                         wellatt_list[idx_bc][1])
        print(sleepstages,goComfort)
        idx_bc += 1
        
        tbc += sleepstages_fatalalarm.broadcast_intvl

        # if sleepstages_fatalalarm.vars['rr_BL'] and sleepstages_fatalalarm.vars['hr_BL']:
        #     break
    
    # sleepstages_fatalalarm.save_context(udid,vars)      # 暫時看看能不能 不要每次都存 來加速開發，正式版不能這樣