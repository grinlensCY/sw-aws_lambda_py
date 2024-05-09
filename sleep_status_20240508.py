import os
import numpy as np
from scipy import signal
import time
import json
import enum
import copy
import sys

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)


class Sleep(enum.IntEnum):
    NONE = 0
    AWAKE = 1
    REM = 2
    LIGHT = 3
    DEEP = 4
    NREM = 5


class SleepStatus():
    def __init__(self, udid, age, ver=20240415, scaledSC=True):
        self.ver = ver
        self.imusr = 104
        self.broadcast_intvl = 5
        self.age = age

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

        self.debugVars = {  # only for debug on local, remove it if deploying on 
            # input
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

            # stage
            'rem_timespans': [],
            'rem_long_sum_list': [],
            'sleep_stages': [],    # 最終的sleep stages
        }

        # self.vars = self.init_vars.copy()
        # self.save_context(udid, self.vars)
        self.vars = self.load_context(udid, True)
        self.mx_vars_size = sys.getsizeof(self.vars)

        self.msg = ''   # debug


    def formatValList(self,msg,typ='f3'):
        ''' only for debug'''
        if msg is None:
            return msg
        msg = np.array(msg)
        if typ[0] == 'f':
            return np.around(msg,int(typ[1])).tolist()
        elif typ[0] == 'e':
            str_list = []
            for i in msg:
                str_list.append(f"{np.format_float_scientific(i,int(typ[1]))}")
            return str_list
    
    def aMsg(self,msg,pre=0,post=0):
        ''' only for debug'''
        for i in range(pre):
            self.msg += '\t'
        for i in range(post):
            msg += '\t'
        self.msg += msg+'\n'

    def hhmmss(self,sec=None, hms='',outType=3):    # 好像是沒用到
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

    def load_context(self,udid,init=False):
        if init:
            res = {
                # input
                'ts_list': [],
                'hr_list':[],
                'rr_list':[],
                'sc_list': [],
                'pre_stillCnt':0,
                'pre_ts':None,
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
            }
        else:
            # with open(f"sleepstat_{udid}.json", 'r', newline='') as jf:
            #     res = json.loads(jf.read())
            res = self.vars # 因為讀取檔案會很慢，為了加速開發，改用這樣的方式
        return res

    def clear_vars(self,vars,udid,saveJson=False):
        if saveJson:    # debug
            cnt = 1
            fn = f"sleepstat_{udid}_vars_mxsize_{cnt}.json"
            while os.path.exists(fn):
                cnt += 1
                fn = f"sleepstat_{udid}_vars_mxsize_{cnt}.json"
            with open(fn, 'w', newline='') as jout:
                json.dump(vars, jout, ensure_ascii=False, cls=NumpyEncoder)

        vars['ts_list'] = []
        vars['hr_list'] = []
        vars['rr_list'] = []
        vars['sc_list'] = []
        vars['hr_baseline'] = []
        vars['rr_baseline'] = []

        vars['sleep_stages'] = []
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
        # with open(f"sleepstat_{udid}.json", 'w', newline='') as jout:
        #     json.dump(vars, jout, ensure_ascii=False)
        self.vars = vars     # 因為讀取檔案會很慢，為了加速開發，改用這樣的方式
        # = debug
        tmp = sys.getsizeof(self.vars)
        if tmp > self.mx_vars_size:
            self.mx_vars_size = tmp
            self.aMsg(f"record high mx_vars_size={tmp}")
            with open(f"sleepstat_{udid}_vars_mxsize.json", 'w', newline='') as jout:
                json.dump(vars, jout, ensure_ascii=False, cls=NumpyEncoder)
        
    def getAwakeAlarm(self,vars,ts):    # awake狀態 才去計算
        self.aMsg(f"\ngetAwakeAlarm: ts={ts}")
        sleep_long = ts - vars['sleep_bts'] if vars['sleep_bts'] is not None else 0
        self.aMsg(f"sleep_long={sleep_long}",1)
        if (sleep_long > self.enable_awakeAlarm_sleeplong):    # 已經保持入睡一段時間(20min)
            # vars['sleep_duration'] = sleep_long
            self.debugVars['awakeAlarm_ts_list'].append(ts)
            return ts
        else:
            return 0
    
    def goCalcSS(self,vars,ts,afterLongLoss=False):    # awake狀態 或 空白很久(ts-pre_ts)才去計算
        self.aMsg(f"\ngoCalcSS: ts={ts}  afterLongLoss={afterLongLoss}")
        if afterLongLoss:
            ts = vars['pre_ts']
        sleep_long = ts - vars['sleep_bts'] if vars['sleep_bts'] is not None else 0
        self.aMsg(f"sleep_long={sleep_long}",1)
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
            self.debugVars['unWellAttach_timespans'][-1][1] = ts
        else:
            vars['unWellAttach_bts'] = vars['pre_ts']
            vars['unWellAttach_ets'] = ts
            self.debugVars['unWellAttach_timespans'].append([vars['pre_ts'],ts])

    def is_justWellAttachAfterLongDetach(self,vars,ts):
        '''
        為了避免小孩熟睡，但中途戴上去後呈現 awake 的型態
        會進來這裡，是在貼附狀態
            如果3min內有 連續20分鐘以上的未貼附 且 剛貼附不到3min分鐘，就不產出這段時間的睡眠階段
        '''
        if (vars['unWellAttach_bts'] is not None    # 有過未貼附，且還沒確認(justAttach)完畢
                and vars['unWellAttach_ets'] - vars['unWellAttach_bts'] >= 1200     # 夠長的未貼附=>極可能是未配戴
                and ts - vars['unWellAttach_ets'] <= 180):      # 剛貼附的3min內
            self.debugVars['justWellAttachAfterLongDetach_tslist'].append(ts)
            return True
        self.update_unWellAttach_info(vars,ts,reset=True)
        return False

    def chkGoComfort(self,vars,ts,isDeep=False):
        if isDeep and vars['goComfort'] and ts - vars['deep_bts'] > 180:    # deep超過3min就解除goComfort
            vars['goComfort'] = False
            vars['comfort_bts'] = None
            self.debugVars['comfortOff_ts_list'].append(ts)
        elif not isDeep:
            if vars['goComfort']:
                if ts - vars['comfort_bts'] >= 600:    # goComfort不超過10min
                    vars['goComfort'] = False
                    vars['comfort_bts'] = None
                    self.debugVars['comfortOff_ts_list'].append(ts)
            elif vars['had_deep'] and ts - vars['sleep_bts'] > 1800 and ts - vars['light_bts'] > 25:    # 還沒goComfort, 有過deep, 已經睡了30min以上 且 進入light 25sec以上
                vars['goComfort'] = True
                vars['comfort_bts'] = ts
                self.debugVars['comfortOn_ts_list'].append(ts)

    def isStillCntDropFreqt(self,vars,ts,sc):
        # 計算scDrop，若在頻繁(3min內有drop的情況下)，改以 sc - scDropSum 的結果來評估是否為 light/deep
        if sc < vars['pre_stillCnt']:   # 下降
            vars['scDropSum'] += vars['pre_stillCnt'] - sc  # 累積下降量
            vars['scDrop_ets'] = ts
            if vars['scDrop_bts'] is None:
                vars['scDrop_bts'] = ts # 目前似乎沒用到
            self.debugVars['scDrop_info'].append([ts,vars['scDrop_bts'],vars['scDrop_ets'],vars['scDropSum']])
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
                    self.debugVars['sleep_bts_list'].append(ts)
                    self.aMsg(f"\nsleep starts at {ts}")
                
                vars['ts_list'].append(ts)
                vars['hr_list'].append(hrDat)
                vars['rr_list'].append(rrDat)
                vars['sc_list'].append(sc)
                self.debugVars['calcBL_data_list'].append([ts,hrDat[0],rrDat[0],sc])

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
        self.aMsg(f"\ngetBaseline")
        scData = np.array(vars['sc_list'])
        hrData = np.array(vars['hr_list'])
        rrData = np.array(vars['rr_list'])
        hasBL = False

        while lcf < tsData.size:
            self.aMsg(f"calc BL in timeslot:{tsData[[0,lcf]]}")
            # check received data density
            data_density = tsData[:lcf].size / ((tsData[lcf] - tsData[0])/5)
            self.aMsg(f"data_density={data_density:.3f}",1)
            if data_density < 0.8:
                self.debugVars['low_data_density_infos'].append([int(tsData[0]),int(tsData[lcf]),data_density])
                self.extend_last_BL_timespan(vars,tsData[0],tsData[lcf])
                lcf, datalist = self.stride_data(tsData,scData,hrData,rrData,self.calcBL_step_sec,lcf)
                if not lcf:
                    break
                tsData,scData,hrData,rrData = datalist
                self.aMsg(f"stride data to:{tsData[[0,lcf]]}",2)
                continue
            # check high stillCnt density 
            highSC_density = np.count_nonzero(scData[:lcf] >= self.calcBL_stillCnt_LL) / lcf
            self.aMsg(f"highSC_density={highSC_density:.3f}",1)
            if highSC_density < 0.8:
                self.debugVars['low_highSC_density_infos'].append([int(tsData[0]),int(tsData[lcf]),highSC_density])
                self.extend_last_BL_timespan(vars,tsData[0],tsData[lcf])
                lcf, datalist = self.stride_data(tsData,scData,hrData,rrData,self.calcBL_step_sec,lcf)
                if not lcf:
                    break
                tsData,scData,hrData,rrData = datalist
                self.aMsg(f"stride data to:{tsData[[0,lcf]]}",2)
                continue
            # check high CL density
            highHRCL_density = np.count_nonzero(hrData[:lcf,1] >= 5) / lcf
            highRRCL_density = np.count_nonzero(rrData[:lcf,1] >= 5) / lcf
            self.aMsg(f"highHRCL_density={highHRCL_density:.3f}  highRRCL_density={highRRCL_density:.3f}",1)
            if highHRCL_density < 0.5 and highRRCL_density < 0.5:
                if highHRCL_density < 0.5:
                    self.debugVars['low_highHRCL_density_infos'].append([int(tsData[0]),int(tsData[lcf]),highHRCL_density])
                if highRRCL_density < 0.5:
                    self.debugVars['low_highRRCL_density_infos'].append([int(tsData[0]),int(tsData[lcf]),highRRCL_density])
                self.extend_last_BL_timespan(vars,tsData[0],tsData[lcf])
                lcf, datalist = self.stride_data(tsData,scData,hrData,rrData,self.calcBL_step_sec,lcf)
                if not lcf:
                    break
                tsData,scData,hrData,rrData = datalist
                self.aMsg(f"stride data to:{tsData[[0,lcf]]}",2)
                continue
            # update baseline
            hasBL = True
            if vars['hr_baseline']:
                self.aMsg(f"last hr_baseline={vars['hr_baseline'][-1]}",1)
            else:
                self.aMsg(f"no hr_baseline",1)
            if len(vars['hr_baseline']) and vars['hr_baseline'][-1][2] != -1:
                vars['hr_baseline'][-1][1] = tsData[0]  # 因為是stride，所以改變上一個baseline的結尾，讓新的時段套用新的baseline
                mask = hrData[:lcf,0] < vars['hr_baseline'][-1][2]*1.3  # screen data those > 1.3X lastest baseline
                perc50 = np.percentile(hrData[:lcf,0][mask],50) # debug
                perc40 = np.percentile(hrData[:lcf,0][mask],40)
                perc30 = np.percentile(hrData[:lcf,0][mask],30) # debug

                if perc40 < 55:
                    vars['hr_baseline'][-1][1] = tsData[-1]
                    self.aMsg(f"bad perc40 => extend last hr_baseline:{vars['hr_baseline'][-1]}",1)
                    self.debugVars['hr_baseline'][-1][1] = int(tsData[-1])
                else:
                    vars['hr_baseline'][-1][1] = tsData[0]
                    vars['hr_baseline'].append([tsData[0],tsData[-1],round(perc40,2)])
                    self.aMsg(f"update last two hr_baseline:{vars['hr_baseline'][-2:]}",1)
                    self.debugVars['hr_baseline'][-1][1] = int(tsData[0])
                    self.debugVars['hr_baseline'].append([int(tsData[0]),int(tsData[-1]),float(perc40)])
                
                self.debugVars['hr_baseline_50th'][-1][1] = int(tsData[0])
                self.debugVars['hr_baseline_30th'][-1][1] = int(tsData[0])
                self.debugVars['hr_baseline_50th'].append([int(tsData[0]),int(tsData[-1]),float(perc50)])
                self.debugVars['hr_baseline_30th'].append([int(tsData[0]),int(tsData[-1]),float(perc30)])
                self.aMsg(f"50th percentile={perc50}",2)
                self.aMsg(f"40th percentile={perc40}",2)
                self.aMsg(f"30th percentile={perc30}",2)
            else:
                perc50 = np.percentile(hrData[:lcf,0],50)   # debug
                perc40 = np.percentile(hrData[:lcf,0],40)
                perc30 = np.percentile(hrData[:lcf,0],30)   # debug

                if perc40 >= 55:
                    vars['hr_baseline'].append([tsData[0],tsData[-1],round(perc40,2)])
                    self.debugVars['hr_baseline'].append([int(tsData[0]),int(tsData[-1]),float(perc40)])
                    self.aMsg(f"append new hr_baseline:{vars['hr_baseline'][-1]}",1)
                else:
                    vars['hr_baseline'].append([tsData[0],tsData[-1],-1])
                    self.debugVars['hr_baseline'].append([int(tsData[0]),int(tsData[-1]),-1])
                    self.aMsg(f"bad perc40",1)

                self.debugVars['hr_baseline_50th'].append([int(tsData[0]),int(tsData[-1]),float(perc50)])
                self.debugVars['hr_baseline_30th'].append([int(tsData[0]),int(tsData[-1]),float(perc30)])
                self.aMsg(f"50th percentile={perc50}",2)
                self.aMsg(f"40th percentile={perc40}",2)
                self.aMsg(f"30th percentile={perc30}",2)
            
            if vars['rr_baseline']:
                self.aMsg(f"last rr_baseline={vars['rr_baseline'][-1]}",1)
            else:
                self.aMsg(f"no rr_baseline",1)
            if len(vars['rr_baseline']) and vars['rr_baseline'][-1][2] != -1:
                mask = rrData[:lcf,0] < vars['rr_baseline'][-1][2]*1.3  # screen data those > 1.3X lastest baseline
                perc50 = np.percentile(rrData[:lcf,0][mask],50) # debug
                perc40 = np.percentile(rrData[:lcf,0][mask],40)
                perc30 = np.percentile(rrData[:lcf,0][mask],30) # debug

                if perc40 < 10:
                    vars['rr_baseline'][-1][1] = tsData[-1]
                    self.aMsg(f"bad perc40 => extend last rr_baseline:{vars['rr_baseline'][-1]}",1)
                    self.debugVars['rr_baseline'][-1][1] = int(tsData[-1])
                else:
                    vars['rr_baseline'][-1][1] = tsData[0]
                    vars['rr_baseline'].append([tsData[0],tsData[-1],round(perc40,2)])
                    self.aMsg(f"update last two rr_baseline:{vars['rr_baseline'][-2:]}",1)
                    self.debugVars['rr_baseline'][-1][1] = int(tsData[0])
                    self.debugVars['rr_baseline'].append([int(tsData[0]),int(tsData[-1]),float(perc40)])

                self.debugVars['rr_baseline_50th'][-1][1] = int(tsData[0])
                self.debugVars['rr_baseline_30th'][-1][1] = int(tsData[0])
                self.debugVars['rr_baseline_50th'].append([int(tsData[0]),int(tsData[-1]),float(perc50)])
                self.debugVars['rr_baseline_30th'].append([int(tsData[0]),int(tsData[-1]),float(perc30)])
                self.aMsg(f"update last two rr_baseline:{vars['rr_baseline'][-2:]}",1)
                self.aMsg(f"50th percentile={perc50}",2)
                self.aMsg(f"40th percentile={perc40}",2)
                self.aMsg(f"30th percentile={perc30}",2)
            else:
                perc50 = np.percentile(rrData[:lcf,0],50)   # debug
                perc40 = np.percentile(rrData[:lcf,0],40)
                perc30 = np.percentile(rrData[:lcf,0],30)   # debug

                if perc40 >= 10:
                    vars['rr_baseline'].append([tsData[0],tsData[-1],round(perc40,2)])
                    self.debugVars['rr_baseline'].append([int(tsData[0]),int(tsData[-1]),float(perc40)])
                    self.aMsg(f"append new rr_baseline:{vars['rr_baseline'][-1]}",1)
                else:
                    vars['rr_baseline'].append([tsData[0],tsData[-1],-1])
                    self.debugVars['rr_baseline'].append([int(tsData[0]),int(tsData[-1]),-1])
                    self.aMsg(f"bad perc40",1)

                self.debugVars['rr_baseline_50th'].append([int(tsData[0]),int(tsData[-1]),float(perc50)])
                self.debugVars['rr_baseline_30th'].append([int(tsData[0]),int(tsData[-1]),float(perc30)])
                self.aMsg(f"50th percentile={perc50}",2)
                self.aMsg(f"40th percentile={perc40}",2)
                self.aMsg(f"30th percentile={perc30}",2)

            lcf, datalist = self.stride_data(tsData,scData,hrData,rrData,self.calcBL_stride_sec,lcf)
            if not lcf:
                break
            tsData,scData,hrData,rrData = datalist
            self.aMsg(f"stride data to:{tsData[[0,lcf]]}",2)
        self.extend_last_BL_timespan(vars,tsData[0],tsData[-1])

        return hasBL
    
    def draft_REM(self,vars):
        msg = ""
        rem_long_sum = 0

        self.aMsg(f"\nsleep stages before REM: age={self.age}")

        if self.age < 4:
            for ss in vars['sleep_stages']:
                self.aMsg(f"{ss}  {time.strftime('%Y%m%d_%H%M%S',ss[1])}, {time.strftime('%Y%m%d_%H%M%S',ss[2])}",1)

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
                self.aMsg(f"fail to get baseline to infer REM: insufficient data")
                return "fail to get baseline to infer REM: insufficient data",rem_long_sum
            if not self.getBaseline(vars,tsData,lcf):
                self.aMsg(f"fail to get baseline to infer REM: insufficient GOOD data")
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
                    self.aMsg(f"{ts} is just after rem_bts_LL({rem_bts_LL} {time.strftime('%Y%m%d %H:%M:%S',time.localtime(ts))})")
                    rightafter_rem_bts_LL = True
                hr = vars['hr_list'][i][0]
                rr = vars['rr_list'][i][0]
                while hrBL_idx < hrBL_idx_UL and (hrBL_val == -1 or hrBL_ets < ts):
                    hrBL_idx += 1
                    hrBL_bts,hrBL_ets,hrBL_val = vars['hr_baseline'][hrBL_idx]
                    self.aMsg(f"change hr BL:{hrBL_bts}({time.strftime('%Y%m%d %H:%M:%S',time.localtime(hrBL_bts))}) ~ "
                              f"{hrBL_ets}({time.strftime('%Y%m%d %H:%M:%S',time.localtime(hrBL_ets))}) "
                              f"{hrBL_val}",1)
                while rrBL_idx < rrBL_idx_UL and (rrBL_val == -1 or rrBL_ets < ts):
                    rrBL_idx += 1
                    rrBL_bts,rrBL_ets,rrBL_val = vars['rr_baseline'][rrBL_idx]
                    self.aMsg(f"change rr BL:{rrBL_bts}({time.strftime('%Y%m%d %H:%M:%S',time.localtime(rrBL_bts))}) ~ "
                              f"{rrBL_ets}({time.strftime('%Y%m%d %H:%M:%S',time.localtime(rrBL_ets))}) "
                              f"{rrBL_val}",1)

                if ((hrBL_bts <= ts and hr >= rem_hr_ratio*hrBL_val) or (rrBL_bts <= ts and rr >= rem_hr_ratio*rrBL_val)):
                    if rem_like_bts is None:
                        rem_like_bts = ts
                        self.aMsg(f"new rem_like_bts = {rem_like_bts} {time.strftime('%Y%m%d %H:%M:%S',time.localtime(ts))}",1)
                    # elif ts - rem_like_bts >= 60:  # 有rem_like_bts,持續1min
                    #     if rem_timespan[-1][0] == rem_like_bts:
                    #         rem_timespan[-1][1] = ts
                    #     else:
                    #         rem_timespan.append([rem_like_bts,ts])
                elif rem_like_bts is not None and ts - rem_like_bts >= 90:  # 沒有比baseline高了, 且已持續高 1.5min以上 => REM
                    rem_timespan.append([rem_like_bts, ts])
                    rem_long_sum += ts - rem_like_bts
                    rem_like_bts = None
                    self.aMsg(f"new rem_span = {rem_timespan[-1]}"
                              f"({time.strftime('%Y%m%d %H:%M:%S',time.localtime(rem_timespan[-1][0]))} ~ "
                              f"{time.strftime('%Y%m%d %H:%M:%S',time.localtime(rem_timespan[-1][1]))}) "
                              f"sum={rem_long_sum}",1)
                elif rem_like_bts is not None:  # 沒有比baseline高了
                    lowPeriod += ts - vars['ts_list'][i-1]
                    if lowPeriod > 30:
                        self.aMsg(f"ts={ts}={time.strftime('%Y%m%d %H:%M:%S',time.localtime(ts))}",2)
                        self.aMsg(f"(hrBL_bts({hrBL_bts}) <= ts({ts})? and hr({hr}) >= {rem_hr_ratio}*hrBL_val({rem_hr_ratio*hrBL_val})?)",3)
                        self.aMsg(f"(rrBL_bts({rrBL_bts}) <= ts and rr({rr}) >= {rem_rr_ratio}*rrBL_val({rem_rr_ratio*rrBL_val})?)",3)
                        self.aMsg(f"ts - rem_like_bts = ({ts - rem_like_bts}) >= 90?",3)
                        rem_like_bts = None
                        lowPeriod = 0
                
                # 超出有baseline, sleep_stages時間了
                if ((hrBL_idx == hrBL_idx_UL and hrBL_ets < ts) and (rrBL_idx == rrBL_idx_UL and rrBL_ets < ts)):
                        # or (ss_idx == ss_idx_UL and vars['sleep_stages'][ss_idx][2] <= rem_like_bts)):
                    self.aMsg(f"no more BL: "
                              f"hrBL_idx{hrBL_idx} == {hrBL_idx_UL} and "
                              f"hrBL_ets({hrBL_ets}) < {ts}({time.strftime('%Y%m%d %H:%M:%S',time.localtime(ts))})",1)
                    break
            
            self.aMsg(f"\ncurrent sleep stages")
            for ss in vars['sleep_stages']:
                self.aMsg(f"{ss}  {time.strftime('%Y%m%d_%H%M%S',time.localtime(ss[1]))}, {time.strftime('%Y%m%d_%H%M%S',time.localtime(ss[2]))}",1)
            
            # === merge REM into draft sleep stages
            if len(rem_timespan):   # 因為中間插入改list很麻煩，所以還是最後再來處理
                self.debugVars['rem_timespans'].extend(copy.deepcopy(rem_timespan))
                self.debugVars['rem_long_sum_list'].append(rem_long_sum)

                rem_idx = len(rem_timespan)-1
                rem_bts, rem_ets = rem_timespan[rem_idx]
                rem_long = rem_ets - rem_bts

                rev_ss = copy.deepcopy(vars['sleep_stages'][::-1])
                max_rev_ss_idx = len(rev_ss) - 1
                max_ss_idx = orig_max_ss_idx = len(vars['sleep_stages']) - 1
                
                self.aMsg(f"\nmerge REM into draft sleep stages")
                for i,(typ,bts,ets) in enumerate(rev_ss):
                    self.aMsg(f"{i}({orig_max_ss_idx - i:02d}) {typ}: {bts} ~ {ets}"
                              f"({time.strftime('%Y%m%d-%H:%M:%S',time.localtime(bts))} ~ {time.strftime('%Y%m%d-%H:%M:%S',time.localtime(ets))})  "
                              f"{typ}  rem: {rem_idx}  {rem_bts} ~ {rem_ets}"
                              f"({time.strftime('%Y%m%d-%H:%M:%S',time.localtime(rem_bts))} ~ {time.strftime('%Y%m%d-%H:%M:%S',time.localtime(rem_ets))})  ")
                    # 找出對應的sleep stage
                    if bts >= rem_ets:
                        continue
                    ss_orig_idx = orig_max_ss_idx - i
                    next_ss_orig_idx = ss_orig_idx + 1

                    # === 找出rem開頭在這個睡眠階段內的 (rem_bts會對應到有hr/rr/sc資料的，所以不會是Sleep.NONE)
                    while rem_idx >= 0 and rem_bts >= bts and rem_bts < ets:    # 持續把該睡眠時段內的rem_span加入
                        vars['sleep_stages'][ss_orig_idx][2] = rem_bts
                        self.aMsg(f"update stage{ss_orig_idx:02d} ets:{vars['sleep_stages'][ss_orig_idx]}",1)

                        isNextNone = False
                        # == 如果rem_span橫跨多個睡眠時段(rem_ets > next_stage_ets)(通常比較不會), 去找到最後一段
                        while next_ss_orig_idx <= max_ss_idx and rem_ets > vars['sleep_stages'][next_ss_orig_idx][2]:
                            self.aMsg(f"next_stage: idx_{next_ss_orig_idx}  "
                                      f"{vars['sleep_stages'][next_ss_orig_idx]}=>  rem_ets > next_stage_ets",1)
                            if vars['sleep_stages'][next_ss_orig_idx][0] == Sleep.NONE:    # 跳過NONE
                                isNextNone = True
                                next_ss_orig_idx += 1
                                self.aMsg(f"change next_ss_orig_idx={next_ss_orig_idx:02d}",2)
                                continue

                            self.aMsg(f"del {vars['sleep_stages'][next_ss_orig_idx]}",1)
                            del vars['sleep_stages'][next_ss_orig_idx]
                            max_ss_idx = len(vars['sleep_stages']) - 1
                            self.aMsg(f"update max_ss_idx={max_ss_idx}",1)

                        next_ss_orig_idx = ss_orig_idx + 1  # 因為有可能因為在前面處理時跳到下N個
                        if rem_ets > ets:   # 橫跨到後面的階段(要繞過NONE)
                            self.aMsg(f"rem_ets > ets: next_ss_orig_idx({next_ss_orig_idx:02d}) <= max_ss_idx({max_ss_idx})? "
                                      f"and nextSS is not None?{not isNextNone}",1)
                            if next_ss_orig_idx <= max_ss_idx and not isNextNone: # 有下一段
                                vars['sleep_stages'][next_ss_orig_idx][1] = rem_ets
                                self.aMsg(f"update bts of next sleep_stage({next_ss_orig_idx:02d})={vars['sleep_stages'][next_ss_orig_idx]}",2)
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
                            self.aMsg(f"insert {typ} at next sleep_stage({next_ss_orig_idx:02d})={vars['sleep_stages'][next_ss_orig_idx]}",1)
                            # vars['sleep_stages'].insert(next_ss_orig_idx,[Sleep.REM,rem_bts,rem_ets])
                        vars['sleep_stages'].insert(next_ss_orig_idx,[Sleep.REM,rem_bts,rem_ets])
                        self.aMsg(f"insert REM at next sleep_stage({next_ss_orig_idx:02d})={vars['sleep_stages'][next_ss_orig_idx]}",1)

                        self.aMsg(f"chk sleep stages:",1)
                        for ss in vars['sleep_stages'][max(0,ss_orig_idx-1):ss_orig_idx+3]:
                            self.aMsg(f"{ss}",2)

                        rem_idx -= 1
                        if rem_idx < 0:
                            break
                        ets = rem_bts   # 這段的ets已經變更了
                        rem_bts, rem_ets = rem_timespan[rem_idx]
                        self.aMsg(f"\nmerge another REM {rem_bts} ~ {rem_ets}"
                                  f"({time.strftime('%Y%m%d-%H:%M:%S',time.localtime(rem_bts))} ~ {time.strftime('%Y%m%d-%H:%M:%S',time.localtime(rem_ets))})",1)
            else:
                msg = "NO REM"
        self.aMsg(f"\nsleep stages after draft_REM")
        for i,ss in enumerate(vars['sleep_stages']):
            self.aMsg(f"{ss}  "
                      f"{time.strftime('%Y%m%d_%H%M%S',time.localtime(ss[1]))}, "
                      f"{time.strftime('%Y%m%d_%H%M%S',time.localtime(ss[2]))}  "
                      f"{ss[1] == vars['sleep_stages'][i-1][2]}  "
                      f"{ss[1] < ss[2]}",1)
        
        self.aMsg(f"draft_REM end: rem_long_sum={rem_long_sum}  msg={msg}  ")
        return msg,rem_long_sum
        
    def scale_REM(self,vars,rem_long_sum):
        self.aMsg(f"\nscale_REM (developing!)")
        if not rem_long_sum:
            return False
        
        gain = self.rem_ratio_target / (rem_long_sum / vars['sleep_duration']) - 1

        rev_ss = copy.deepcopy(vars['sleep_stages'][::-1])
        max_rev_ss_idx = len(rev_ss) - 1
        max_ss_idx = orig_max_ss_idx = len(vars['sleep_stages']) - 1
        
        self.aMsg(f"\nscaling REM to meet the requirement of rem_ratio_target={self.rem_ratio_target}  gain={gain}")
        for i,(typ,bts,ets) in enumerate(rev_ss):
            self.aMsg(f"{i}({orig_max_ss_idx - i:02d}): {bts} ~ {ets}  {typ}")
            if typ != Sleep.REM:
                continue
            ss_orig_idx = orig_max_ss_idx - i
            next_ss_orig_idx = ss_orig_idx + 1
            pre_ss_orig_idx = ss_orig_idx - 1
            add_REM_long = (vars['sleep_stages'][ss_orig_idx][2] - vars['sleep_stages'][ss_orig_idx][1]) * gain
            self.aMsg(f"target of add_REM_long={add_REM_long}",1)
            if (i and vars['sleep_stages'][next_ss_orig_idx][0] != Sleep.AWAKE):    # 還有下一段 且 不是awake
                self.aMsg(f"")
                new_rem_ets = int(max(min(vars['sleep_stages'][next_ss_orig_idx][2] - self.stage_long_LL_sec,   # 確保 這個與下一段 都有保留到
                                          ets + add_REM_long),
                                    min(ets,bts + self.stage_long_LL_sec)))
                add_REM_long -= new_rem_ets - ets
                self.aMsg(f"modify next stage: new_rem_ets={new_rem_ets}  update add_REM_long={add_REM_long}",2)
            else:
                next_ss_orig_idx = None
                new_rem_ets = ets
                self.aMsg(f"no next stage: new_rem_ets=ets  add_REM_long={add_REM_long}",2)

            if (pre_ss_orig_idx >= 0 and vars['sleep_stages'][pre_ss_orig_idx][0] != Sleep.AWAKE):  # 有前一段 且 不是awake
                new_rem_bts = int(min(max(vars['sleep_stages'][pre_ss_orig_idx][1] + self.stage_long_LL_sec,    # 確保 這個與前一段 都有保留到
                                      bts - add_REM_long),
                                    max(bts,new_rem_ets - self.stage_long_LL_sec)))
                self.aMsg(f"modify previous stage: new_rem_bts={new_rem_bts}  update add_REM_long={add_REM_long}",2)
            else:
                pre_ss_orig_idx = None
                new_rem_bts = bts
                self.aMsg(f"no previous stage: new_rem_bts=bts  add_REM_long={add_REM_long}",2)

            if new_rem_ets != ets:
                vars['sleep_stages'][next_ss_orig_idx][1] = new_rem_ets
                vars['sleep_stages'][ss_orig_idx][2] = new_rem_ets
                self.aMsg(f"new_rem_ets({new_rem_ets}) != ets({ets})",1)
                self.aMsg(f"chk sleep stages:",1)
                for ss in vars['sleep_stages'][max(0,ss_orig_idx-1):ss_orig_idx+3]:
                    self.aMsg(f"{ss}",2)
            if new_rem_bts != bts:
                vars['sleep_stages'][pre_ss_orig_idx][2] = new_rem_bts
                vars['sleep_stages'][ss_orig_idx][1] = new_rem_bts
                self.aMsg(f"new_rem_bts({new_rem_bts}) != bts({bts})",1)
                self.aMsg(f"chk sleep stages:",1)
                for ss in vars['sleep_stages'][max(0,ss_orig_idx-1):ss_orig_idx+3]:
                    self.aMsg(f"{ss}",2)

        self.aMsg(f"\nsleep stages after scale_REM")
        for i,ss in enumerate(vars['sleep_stages']):
            self.aMsg(f"{ss}  "
                      f"{time.strftime('%Y%m%d_%H%M%S',time.localtime(ss[1]))}, "
                      f"{time.strftime('%Y%m%d_%H%M%S',time.localtime(ss[2]))}  "
                      f"{ss[1] == vars['sleep_stages'][i-1][2]}  "
                      f"{ss[1] < ss[2]}",1)
        return True

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

        if vars['pre_ts'] is not None and ts - vars['pre_ts'] >= 1200:
            self.aMsg(f"right after a long blank: {ts - vars['pre_ts']}sec")
            if self.goCalcSS(vars,ts,afterLongLoss=True):
                msgtmp,rem_long_sum = self.draft_REM(vars)
                msg += msgtmp
                
                self.scale_REM(vars,rem_long_sum)
                self.debugVars['sleep_stages'].extend(copy.deepcopy(vars['sleep_stages']))
            self.aMsg(f"clear_vars at {ts}")
            self.clear_vars(vars)
        elif vars['pre_ts'] is None:
            vars['pre_ts'] = ts - 5

        self.debugVars['ts_list'].append(ts)
        self.debugVars['hr_list'].append(hrDat)
        self.debugVars['rr_list'].append(rrDat)
        self.debugVars['sc_list'].append(sc)
        self.debugVars['isWellAttach_list'].append(isWellAttached)
        
        status = self.draft_sleepstatus(vars,ts,hrDat,rrDat,sc,isWellAttached)
        self.debugVars['draft_status_list'].append(status)

        self.update_draft_sleep_stages(vars, ts, status)

        sleepstages = None
        if status == Sleep.AWAKE:
            vars['awakeAlarm_ts'] = self.getAwakeAlarm(vars, ts)

            goEnd = True
            hasSS = False   # debug
            if self.goCalcSS(vars,ts,afterLongLoss=False):   # 確定起床了(睡夠久) 才計算(並結束)這段睡眠
                msgtmp,rem_long_sum = self.draft_REM(vars)
                msg += msgtmp
                self.scale_REM(vars,rem_long_sum)
                self.debugVars['sleep_stages'].extend(copy.deepcopy(vars['sleep_stages']))
                hasSS = True    # debug
            elif vars['sleep_bts'] is not None or vars['unWellAttach_bts'] is not None:   # 有睡著過(但時間不夠), 或 剛貼附 或 未貼附，就清除stages(=> 還沒睡著過 且 貼附夠久 就保留awake，繼續累積stage)
                msg = "This sleep duration is too short to infer sleep stages!"
            else:
                goEnd = False

            if goEnd:
                sleepstages = copy.deepcopy(vars['sleep_stages']) if len(vars['sleep_stages']) > 1 else None
                self.aMsg(f"clear_vars at {ts} hasSS={hasSS}")
                self.clear_vars(vars,udid,hasSS)
        
        vars['pre_stillCnt'] = sc
        vars['pre_ts'] = ts

        self.save_context(udid,vars)
        return udid,vars,sleepstages,vars['goComfort'],ts - vars['awakeAlarm_ts'] < 1,msg   # sleepstages is not None，就表示有產出


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

    sleep_stat = SleepStatus(udid=udid,age=2)   # 需要實際age(幾個月大)這個參數
    # sleep_stat.save_context(udid)   # init

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

        udid,vars,status,goComfort,goAwakeAlarm,msg = sleep_stat.addData(udid,
                                                                         ts,
                                                                         hr_list[idx_bc][1:],
                                                                         rr_list[idx_bc][1:],
                                                                         stillCnt_list[idx_bc][1],  # stillcnt
                                                                         wellatt_list[idx_bc][1])
        print(status,goComfort)
        idx_bc += 1
        
        tbc += sleep_stat.broadcast_intvl