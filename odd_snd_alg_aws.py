import numpy as np
from scipy import signal
import struct
import time,threading
import queue
import numpy as np  
from os import SEEK_SET, SEEK_CUR, SEEK_END

class Detector():
    def __init__(self, micsr=4000, config=None, filterSet=None, tsHz=32768, istsec=True, pkgnum=4, pkglen=64, len_UL=12000, t0=0, ver=20230125):
        self.micsr = micsr
        self.fwts_target = 0.016*tsHz
        self.fwts_th = self.fwts_target/2
        self.toffset = t0   # for debug
        self.istsec = istsec
        self.tsHz = tsHz if not istsec else 1
        self.pkgnum = pkgnum
        self.len_UL = len_UL    # debug: 有時候aws上有明顯不滿3秒的資料，需要透過這個來結束poo偵測, 
        if filterSet is None:
            filterSet = {
                "typ": "high",
                "fcut": [75],
                "isfiltfilt": 0,
                "noZi": 0,
                "resetZi": 0
            }
        if 'isfiltfilt' not in filterSet:
            filterSet['isfiltfilt'] = 0
        if 'noZi' not in filterSet:
            filterSet['noZi'] = 0
        if 'resetZi' not in filterSet:
            filterSet['resetZi'] = 0
        self.msg = ''
        self.loadConfig(config)
        self.update_sr(micsr,filterSet,pkglen)
        self.ver = ver
        #print(f'\ndetect oddsnd ver.{ver}  toffset={self.toffset}')

    
    def bwfilter(self, data_in=None, sr=None, f_cut=None, N_filt=3, filtype='bandpass',
                    b_filt=None, a_filt=None, isfiltfilt=False, forback=False, iszi=True, zf=None):
        """apply butterworth filter with zero phase shift"""
        data_filtered = None
        next_zi = None
        if b_filt is None:
            nyq = sr/2
            wn = np.array(f_cut) if isinstance(f_cut,list) or isinstance(f_cut,tuple) else np.array([f_cut])
            if not wn[0] and wn[-1]>=nyq:
                raise ValueError(f'oddsnd bwfilter:  wn{wn} is not valid!')
            if np.max(wn) >= nyq and filtype == 'bandpass':
                # wn[np.argmax(wn)] = nyq*0.99
                wn = wn[0]
                filtype = 'highpass'
            if wn.size == 2 and not wn[0]:
                wn = wn[1]
                filtype = 'lowpass'
            elif wn.size == 2 and wn[-1]>=nyq:
                wn = wn[0]
                filtype = 'highpass'
            elif (filtype != 'bandpass' and filtype != 'bandstop') and wn.size == 2:
                wn = wn[0] if filtype == 'highpass' else wn[1]
            #print((f'oddsnd bwfilter: sr{sr:.1f} wn{wn} type:{filtype} N={N_filt} '
            #        f'isfiltfilt:{isfiltfilt} forback:{forback} iszi:{iszi}'))
            b_filt, a_filt = signal.butter(N_filt, wn/nyq, btype=filtype)
        if data_in is not None:
            if isfiltfilt:
                #print('oddsnd: filtfilt')
                data_filtered = signal.filtfilt(b_filt, a_filt, data_in)
            elif forback:
                #print('oddsnd: lfilter forward+backward')
                zi = signal.lfilter_zi(b_filt, a_filt)
                data_filtered,_ = signal.lfilter(b_filt, a_filt, data_in, zi=zi*data_in[0])
                data_filtered,_ = signal.lfilter(b_filt, a_filt, data_filtered[::-1], zi=zi*data_filtered[-1])
                data_filtered = data_filtered[::-1]
            elif not iszi:
                #print('oddsnd: no zi')
                data_filtered = signal.lfilter(b_filt, a_filt, data_in)
            elif iszi and zf is not None:
                data_filtered,next_zi = signal.lfilter(b_filt, a_filt, data_in, zi=zf)
            elif iszi:
                # print('oddsnd: reset zi')
                zi = signal.lfilter_zi(b_filt, a_filt)
                data_filtered,next_zi = signal.lfilter(b_filt, a_filt, data_in, zi=zi*data_in[0])
        return data_filtered, b_filt, a_filt, next_zi
    
    def loadConfig(self,config):
        if config is not None:
            # self.th_nonpk_percentile = config['th_nonpk_percentile']
            # self.th_PK_SNR = config['th_PK_SNR']
            # self.minInterval_pairingPk = config['minInterval_pairingPk']
            # # self.fcut = config['fcut']
            # self.th_lowVol = config['th_lowVol']
            # self.minInterval_pickingPk = config['minInterval_pickingPk']
            self.showMsg = config['showMsg']
            # self.maxInterval_mergingPk = config['maxInterval_mergingPk']
            self.update_sr_parameters()
        else:
            self.showMsg = 0
            # # quiet spike-like bowel sound
            self.main_lvl_UL = 9e-1    # for debug
            # self.main_1800hp_lvl_UL = 4e-2
            self.main_lvl_LL = 2.6e-1
            # self.main_class0_slope_th = 2.0e-2*4000 #4000sps:2.5e-4*4000
            self.main_class1_slope_th = 4e-2*4000   #4000sps:9e-4*4000
            # self.weight_10 = self.main_class1_slope_th/self.main_class0_slope_th-1  # 計算密度時所加上去的class1權重
            self.main_class2_slope_th = 2.2e-1/2*4000   #0.9e-1/2*4000   #2.4e-1/2*4000 #4000sps:4e-3/2*4000
            self.main_class3_slope_th = 3.9e-1*4000 # for sharp turn detection   4000sps:5.5e-3*4000
            self.main_class4_slope_th = 5.5e-1*4000
            self.max_nonclass0_interval_sec = 8/4000 # 波包裡, 最大的空格點距離 0.002sec
            # self.min_grp_duration_sec = 0.00125 # 波包最小寬度
            self.max_grp_duration_sec = 0.013 # 波包最大寬度
            self.calc_reflvl_len_sec = 0.013    # 用來計算ref_lvl的最長範圍
            self.calc_reflvl_halflen_sec = self.calc_reflvl_len_sec/2   # 取出seg最後一小段的max，避免下一seg的第一個需要計算ref_lvl時，資訊量不足
            self.snr = 3.5    # ref_lvl 是 max的幾倍
            self.grp_intvl_th_sec = 0.007 # 波包的淨空距離，也用於 計算該idx_gaps點的lvl
            self.mx_marked_density_th = 0.4  # 有標記出的點佔波包多少比例
            self.high_mx_marked_density_th = 1.2  # 有標記出的點佔波包多少比例
            self.clear_period_sec = 0.007    # 用來清除太靠近的點

            # self.min_absndgrp_length = 3    # 0.064*3=0.192sec
            # self.max_absndgrp_length = 30   # 1.92sec # 0.064*8=1.152sec
            # self.max_absndgrp_sec = 1.93    # add 0.01 tolerance for 
            # self.ext_unstable_sec = 0.0064  # unstable, absnd timeslot延伸出去的範圍
            
            # 評估最近一段時間內是否為unstable的時間長度, 若unstable比例過高(>self.unstable_ratio_th), 放棄absnd/hamo計算與輸出
            # self.eval_unstable_period_sec = 3.5
            # self.unstable_ratio_th = 0.5    # 高於 就是 isUnstablePeriod

            self.pks_intvl_LL = 0.005
            self.pks_intvl_UL = 0.08

            # 可傳輸3秒資料到station, 剛好設定 self.extremely_unstable_length 40seg = 0.064*40 = 2.56, 也許擷取出來的前後都可以多保留些
            self.ts_storage_sec = 3

    def update_sr_parameters(self):
        # quiet spike-like bowel sound
        self.max_nonclass0_interval = self.max_nonclass0_interval_sec*self.micsr
        # self.main_class0_step_th = self.main_class0_slope_th/self.micsr
        self.main_class1_step_th = self.main_class1_slope_th/self.micsr
        self.main_bigclass1_step_th = self.main_class1_step_th*2
        self.main_class2_step_th = self.main_class2_slope_th/self.micsr*2
        self.main_bigclass2_step_th = self.main_class2_step_th*2
        self.main_sharp_turn_step_th = self.main_class3_slope_th/self.micsr
        # self.min_grp_duration = self.min_grp_duration_sec*self.micsr
        self.max_grp_duration = self.max_grp_duration_sec*self.micsr
        self.calc_reflvl_len = int(self.calc_reflvl_len_sec*self.micsr)
        self.calc_reflvl_halflen = int(self.calc_reflvl_halflen_sec*self.micsr)
        # self.dyna_max_grp_duration = self.max_grp_duration
        self.grp_intvl_th = self.grp_intvl_th_sec*self.micsr

        # # == unstable period evaluation
        # self.mx_eval_unstable_idx = int(self.eval_unstable_period_sec/self.proc_len_sec)
        # self.eval_unstable_sum_th = int(self.mx_eval_unstable_idx*self.unstable_ratio_th)

        # == abnormal sound
        # self.class0Cnt_UL = int(self.proc_len * 0.31) 
        # self.class1Cnt_UL = int(self.proc_len * 0.11)
        # self.class2Cnt_UL = int(self.proc_len * 0.04)
        # self.extremely_unstable_length = int(2.56/self.proc_len_sec) # 2.56sec 若超過這長度 就不計算hamonic 需小於3秒(傳輸長度)
        # self.min_absndgrp_length_sec = self.min_absndgrp_length*self.proc_len_sec
        # self.max_absndgrp_length_sec = self.max_absndgrp_length*self.proc_len_sec

    def update_sr(self,sr,filterSet={},pkglen=64):
        #print('update sr=',sr,'Hz  pkglen=',pkglen)
        self.micsr = sr
        self.step_sec = 1/sr
        self.pkglen = pkglen
        self.pkglen_sec = pkglen/sr
        self.proc_len = self.pkgnum*self.pkglen
        self.proc_len_sec = self.pkgnum*self.pkglen_sec
        self.same_timeslot_intvl_th_sec = self.proc_len_sec * 1.25
        self.segEnd_len = min((3 - self.proc_len_sec)*sr, self.len_UL-3)
        self.update_sr_parameters()
        self.updatefilter(filterSet)
        self.reset(True,True)
    
    def updatefilter(self,filterSet):
        if filterSet:
            self.filterSet = filterSet
            #print('update filter:',filterSet)
        _,self.b_bw_hp,self.a_bw_hp,_ = self.bwfilter(sr=self.micsr,f_cut=self.filterSet['fcut'],filtype='highpass')
        self.zi_main = None

    def aMsg(self,msg,pre=0,post=0):
        for i in range(pre):
            self.msg += '\t'
        for i in range(post):
            msg += '\t'
        self.msg += msg+'\n'

    def reset(self, proc=False, all=False, closegrp=False, closeObsSnd=False):
        if all:
            self.ti = None
            self.tNow = None
            # self.accuCnt = 1
            self.idxi_plt = 0 # for debug plt and (aws 3sec data)index of end of data
            # self.ts_pre = 0
            # self.idxi = 0   # idx offset of each input segment (maybe deprecated)

            # === for stream
            self.lastMainSndData = []
            
            # === findspike
            # = 校正強度門檻
            # self.isScaling_main = False
            # self.last3MxSnd_arry = np.array([0])    # 收集過去的背景值
            # self.last3MxSnd_ref_lvl = 0 # 背景值參考
            self.ref_lvl = None

            # === abnormal sound
            # self.absndGrp_start_sec = None
            # self.lastAbSndGrp_end_sec = -1
            # self.lastAbSndGrp_length = 0
            # self.unstable_start_sec = None
            # self.unstable_timeslot_list = []
            # self.lastUnstable_end_sec = -1
            # self.lastUnstable_length = 0
            # self.last2_c1_density = []
            # self.high_c1_density_cnt = 0
            # self.isStable = True
            self.has_high_c1_density = False    # 若沒有poo  has_high_c1_density也沒有 ==> 才進行呼吸異音與大聲腸鳴偵測
            # self.eval_unstable_idx = 0
            # self.eval_unstable_sum = 0
            # self.eval_unstable_arr = np.zeros(self.mx_eval_unstable_idx, dtype=bool)
            # self.isUntablePeriod = True
            # self.last_abSnd_c1lc = []     
                        
            # = poo sound
            self.is_prominent = False   # 特別突出的
            self.is_prominent_cnt = 0
            self.last_idxs_gap_lc_is_prominent = False
            # self.is_priorP_prominent = False
            self.last_abs_onestep_gap_next = None
            self.last_abs_onestep_gap = None
            self.last_idxs_gap_lc = None
            self.last_idxs_gap_lvl = None   # 用於結合下一段資料再來決定 last_idxs_gap_lc_is_prominent
            self.last_idxs_gap_ref_lvl = None   # 保留到下一段，當下一段的第一個idx_gaps前面的資料點不足，可以加入
            # self.has_class2 = False
            # self.is_turned = False
            # self.has_sharp_turn = False
            # self.is_over_lvl_UL = False
            # self.hasEnvNoise = False
            self.grp_start_sec = 0
            self.grp_duration = 0
            self.pre_intvl = 0
            self.cnt_marked = 0
            self.mx_marked_density = 0
            # self.is_pre_class1 = False
            # self.harmonic_turns = 0
            # self.lc_turnP = np.array([],dtype=int)
            # self.chk_harmonic_lcs = np.array([],dtype=int)
            # self.grp_pk_lvl = 0
            self.is_priorP_pk = False
            self.poo_ts_list = []
            self.poo_lc_arr = np.array([],dtype=int)   # debug only 與 self.poo_ts_list 同步

            # self.final_poo_ts_list = []

            # === for 阻塞音
            self.isLowBand = False     # 強低頻帶
            self.isHighPk = 0     # 強:2, 中:1, 弱:0
        
        if proc or all: # for debug
            # self.msg = f"reset  proc={proc}  all={all}  closegrp={closegrp}\n"
            self.ts = np.array([],dtype=float) # for debug
            self.pltdat_main = []   # for debug
            self.pltdat_env = []    # for debug
            self.poo_lc_arr = self.poo_lc_arr - self.idxi_plt
            self.idxi_plt = 0   # idx offset of each input segment  # for debug plt and (aws 3sec data)index of end of data
            self.class0_lcs = np.array([],dtype=int)    # for debug
            self.class1_lcs = np.array([],dtype=int)    # for debug
            self.class2_lcs = np.array([],dtype=int)    # for debug
            self.poo_lc_pltarr = np.array([],dtype=int)   # debug only
            # if all:
            #     self.poo_lc_i = 0
            #     self.poo_lc_arr = np.array([],dtype=int)   # debug only
            # else:
            #     self.poo_lc_i = len(self.poo_ts_list)
            #     self.poo_lc_arr = self.poo_lc_arr[-self.poo_lc_i:]
            # self.absnd_timeslot_pltlist = []   # debug only
            # self.unstable_timeslot_pltlist = [] # debug only
            self.c1_density_pltlist = [] # for debug
            self.c2_density_pltlist = [] # for debug
            # self.high_c1_density_cnt_pltlist = [] # for debug
            self.pltdat_100lp_seg = []    # for debug
            self.pltdat_100lp_shortseg = []    # for debug

            # = 強低頻帶 for 阻塞音
            self.isLowBand = False
            self.isHighPk = 0     # 強:2, 中:1, 弱:0
        
        if closegrp:
            self.msg += f"reset  proc={proc}  all={all}  closegrp={closegrp}\n"
            # self.has_class2 = False
            # self.is_turned = False
            # self.has_sharp_turn = False
            # self.is_over_lvl_UL = False
            self.is_prominent = False
            self.grp_duration = 0
            self.pre_intvl = 0
            self.cnt_marked = 0
            # self.is_pre_class1 = False
            # self.harmonic_turns = 0
            self.mx_marked_density = 0
            # self.is_priorP_prominent = False
            self.is_prominent_cnt = 0   # for estimation of poo candidate point density
            # self.grp_pk_lvl = 0

        if closeObsSnd:
            tlc_tmp_list = []
            flc_tmp_list = []
            last_pk_lc = 0
            last_pk_lvl = 0
            pk_lvl_list = []
            self.isHighPk = 0
            veryLowFreqCnt = 0
            isVeryLowfreq = False
            isContiVeryLowFreq = False
            isStrongLowBand = False
            strongLowBandCnt = 0
            lowBandCnt = 0
            self.isLowBand = False

            vars = (tlc_tmp_list,flc_tmp_list,last_pk_lc,last_pk_lvl,pk_lvl_list,
                    veryLowFreqCnt,isVeryLowfreq,isContiVeryLowFreq,isStrongLowBand,strongLowBandCnt,lowBandCnt)

            return vars
    
    def formatMsg(self,msg,typ='f3'):
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

    def lc2ts(self,lc):
        return self.ti+self.step_sec*lc

    def lc2Hz(self,lc):
        if lc is None:
            return None
        else:
            return 1/(self.step_sec*lc)
                    
    def chk_lcs_in_list(self,lci,lcf,lclist):
        if not len(lclist) or lclist[0] >= lcf or lclist[-1] <= lci:
            return None, False
        for i,lc in enumerate(lclist):
            if lci <= lc <= lcf:
                return i+1, True
        return lclist.size, False
    
    def chk_lc_in_rangelist(self,lc,rangelist):
        if not len(rangelist) or lc < rangelist[0][0] or lc > rangelist[-1][-1]:
            return False,None
        for i,r in enumerate(rangelist):
            if r[0] <= lc <= r[1]:
                return True,i
        return False,None
        
    def countMarkerDuration(self,abs_onestep_gap_lc,abs_onestep_gap_nextlc, is_prominent):
        '''累積標記點數 與 group長度  計算 mx_marked_density
        '''
        self.msg += (f"\tcountMarkerDuration: self.grp_start_sec={self.grp_start_sec:.3f}\n")
        self.grp_duration += self.pre_intvl if self.cnt_marked else 1
        c1 = abs_onestep_gap_lc + abs_onestep_gap_nextlc >= self.main_bigclass2_step_th # big class2
        # c12 = abs_onestep_gap_lc >= self.main_bigclass2_step_th # big class2  # c12 已經包在c11，之前是為了 4000sps的poo detetction
        # c1 = c11 or c12 #c10 or c11 or c12
        if is_prominent and self.is_prominent_cnt > 1:
            self.cnt_marked += 3*(self.is_prominent_cnt -1)
        elif c1:
            self.cnt_marked += 2
        else:
            self.cnt_marked += 1
        self.mx_marked_density = (max(self.mx_marked_density, self.cnt_marked/self.grp_duration)
                                    if self.cnt_marked > 5
                                    else self.cnt_marked/self.grp_duration)
        self.aMsg(f"c1={c1}({abs_onestep_gap_lc:.3e} + {abs_onestep_gap_nextlc:.3e} >= {self.main_bigclass2_step_th})  "
            # f"c12={c12}({abs_onestep_gap_lc:.3e} >= {self.main_bigclass2_step_th})  "
            f"is_prominent={is_prominent}  is_prominent_cnt={self.is_prominent_cnt}  cnt_marked={self.cnt_marked}\n"
            f"\t\tdensity={self.cnt_marked}/{self.grp_duration}={self.cnt_marked/self.grp_duration:.3f} mx_density={self.mx_marked_density:.3f}",2)
    
    def closegrp(self, lc, interval, nextlc, snd, is_prominent=False, inRemains=False):
        '''若與下一個標記點距離大於 grp_intvl_th, 確認是否為 短、高Pulse的poo 
        snd: 用於計算ref_lvl
        '''
        self.msg += (f"\tclosegrp: interval={interval} > self.grp_intvl_th={self.grp_intvl_th}?  "
                    # f"grp_duration={self.grp_duration} >= {self.min_grp_duration}?  grp_start_sec={self.grp_start_sec:.3f}\n")
                    f"grp_start_sec={self.grp_start_sec:.3f}\n")
        if interval > self.grp_intvl_th:    # 0.007sec
            self.grp_start_sec = self.lc2ts(nextlc)
            self.msg += f"\t\tupdate grp_start_sec= {self.grp_start_sec:.3f}\n"
            msg = ''
            if inRemains:
                msg += f"\t\t\tinterval_{interval} <= {self.calc_reflvl_len}?{interval <= self.calc_reflvl_len}  "
                if interval <= self.calc_reflvl_len:    # 一定需要參考上一段尾巴的lvl
                    if nextlc > 1:
                        self.ref_lvl = (max(max(self.last_idxs_gap_ref_lvl, np.abs(snd).max())*self.snr, self.main_lvl_LL)
                                        if snd.size
                                        else max(self.last_idxs_gap_ref_lvl*self.snr, self.main_lvl_LL))
                        msg += (f"nextlc_{nextlc}>1: last_idxs_gap_ref_lvl_{self.last_idxs_gap_ref_lvl:.2e} > snd_{np.abs(snd).max():.2e}?\n"
                                if snd.size
                                else f"nextlc_{nextlc}>1: last_idxs_gap_ref_lvl_{self.last_idxs_gap_ref_lvl:.2e}")
                    else:
                        self.ref_lvl = max(self.last_idxs_gap_ref_lvl*self.snr, self.main_lvl_LL)
                        msg += f"last_idxs_gap_ref_lvl_{self.last_idxs_gap_ref_lvl:.2e}\n"
                else:
                    msg += f"nextlc_{nextlc} > calc_reflvl_len_{self.calc_reflvl_len}?\n"
                    if nextlc > self.calc_reflvl_len:   # 可以只看這一段的lvl
                        self.ref_lvl = max(np.abs(snd[-self.calc_reflvl_len:]).max()*self.snr, self.main_lvl_LL)
                    elif nextlc > 1:
                        self.ref_lvl = (max(max(self.last_idxs_gap_ref_lvl, np.abs(snd).max())*self.snr, self.main_lvl_LL)
                                        if snd.size
                                        else max(self.last_idxs_gap_ref_lvl*self.snr, self.main_lvl_LL))
                        msg += (f"nextlc_{nextlc}>1: last_idxs_gap_ref_lvl_{self.last_idxs_gap_ref_lvl:.2e} > snd_{np.abs(snd).max():.2e}?\n"
                                if snd.size
                                else f"nextlc_{nextlc}>1: last_idxs_gap_ref_lvl_{self.last_idxs_gap_ref_lvl:.2e}")
                    else:
                        self.ref_lvl = max(self.last_idxs_gap_ref_lvl*self.snr, self.main_lvl_LL)
                        msg += f"last_idxs_gap_ref_lvl_{self.last_idxs_gap_ref_lvl:.2e}\n"
            else:
                self.ref_lvl = max((np.abs(snd[lc+3:nextlc-2]).max()*self.snr if interval <= self.calc_reflvl_len
                                else np.abs(snd[nextlc-self.calc_reflvl_len:nextlc-2]).max()*self.snr),self.main_lvl_LL)
            self.aMsg((f"updated ref_lvl={self.ref_lvl:.2e} (interval({interval}) <= calc_reflvl_len({self.calc_reflvl_len})?)\n"
                        f"\t\t\t{msg}"),2)

            # = 短pulse (max_grp_duration:0.013sec)
            c0 = self.grp_duration < min(self.max_grp_duration, interval)   #min(self.max_grp_duration, self.dyna_max_grp_duration, interval)
            # = is_prominent
            c1 = c0 and is_prominent
            # = 高密度
            c2 = c1 and self.mx_marked_density > self.high_mx_marked_density_th
            self.msg += (f"\t\tgrp_duration={self.grp_duration} < min(max_grp_duration={self.max_grp_duration} "
                            f"and interval={interval})?{c0}\t"    # >= min_grp_duration={self.min_grp_duration}?\t"
                            # f"cnt_marked={self.cnt_marked}\t"   #mx_density={self.mx_marked_density:.3f} > "
                            f"mx_marked_density({self.mx_marked_density:.2f}) > {self.high_mx_marked_density_th}?"
                            f"{self.mx_marked_density > self.high_mx_marked_density_th}  "
                            # f"{self.high_mx_marked_density_th}({self.mx_marked_density>self.high_mx_marked_density_th})?  "
                            f"is_prominent?{self.is_prominent or is_prominent}(c1_{c1}) ==>add?{c2}\n"
                            )
            if c2:
                # self.dyna_max_grp_duration = max(interval,self.max_grp_duration)
                tsNew = self.lc2ts(lc)
                if len(self.poo_ts_list) and self.poo_ts_list[-1] + self.clear_period_sec >= tsNew: # clear previous poo if it's too close to new poo
                    self.aMsg(f"\t\t\tclear previous poo={self.poo_ts_list[-1]:.3f} because it's too close to new poo"
                                f"({self.poo_ts_list[-1] + self.clear_period_sec} >= {tsNew:.3f})")
                    self.poo_lc_arr = self.poo_lc_arr[:-1]    # for debug
                    self.poo_ts_list = self.poo_ts_list[:-1]
                self.poo_lc_arr = np.r_[self.poo_lc_arr,lc+self.idxi_plt] # for debug
                self.poo_ts_list.append(tsNew)
                # self.last_pk_lc = lc
                self.msg += (f"\t\twithin {self.lc2ts(lc-self.grp_duration):.3f} ~ {tsNew:.3f}sec ==> add poo pk({tsNew:.3f})\n")
            self.msg += '\t\t'
            self.reset(proc=False,all=False,closegrp=True)
            return True
        else:
            self.pre_intvl = interval
            return False
        
    def closeABSndGrp(self, maskC1, maskC2, maxsize):  #, sndData):
        '''
        由c1lc_arr_density來決定unstable範圍
        absnd 還要加上 class2 density 的輔助
        self.absnd_timeslot_list 在 get_poo 再次檢查是否有需要排除的poo, 需要丟出的absnd ==> poo不需要

        '''
        self.aMsg(f"\ncloseABSndGrp")
        # lcs = (np.r_[self.last_abSnd_lc, np.nonzero(mask)[0]]).astype('int')  # for class2 cluster + extended by class1
        # c1lc_arr_now = np.nonzero(maskC1)[0]
        # c1lc_arr = np.r_[self.last_abSnd_c1lc, c1lc_arr_now]
        # self.last_abSnd_c1lc = c1lc_arr[-1] - maxsize if c1lc_arr_now.size else []
        c1lc_arr = np.nonzero(maskC1)[0]
        c1lc_arr_density = c1lc_arr.size/maxsize
        self.c1_density_pltlist.append([self.ti, self.tNow, c1lc_arr_density])  # for debug
        c2lc_arr = np.nonzero(maskC2)[0]
        c2_density = c2lc_arr.size/maxsize  # for debug
        self.c2_density_pltlist.append([self.ti, self.tNow, c2_density])  # for debug

        self.aMsg(f"c1lc_arr_density={c1lc_arr_density}",1) #  isStable={self.isStable}",1)

        self.has_high_c1_density = self.has_high_c1_density or c1lc_arr_density > 0.09

    def chkRemains(self, maxsize, interval, lc0=None, snd=None):
        '''
        處理前一段資料 音資料長度不足而還沒辦法確認的部分
        interval: 與下一個idxs_gap的間距 if self.last_idxs_gap_lc else updated self.grp_start_sec 
        snd: 到lc0為止的sndData
        '''
        self.msg += (f"chkRemains: ti={self.ti:.4f} maxsize={maxsize} interval_to_next_lc={interval} "
                    # f"len(self.remain_main_lcs)={len(self.remain_main_lcs)} "
                    f"self.last_idxs_gap_lc={self.last_idxs_gap_lc}")
        self.msg += f"={self.lc2ts(self.last_idxs_gap_lc):.3f}\n" if self.last_idxs_gap_lc is not None else "\n"
        if self.last_idxs_gap_lc is not None:  # 處理前一段裡最後一個idxs_gap
            # if not self.is_over_lvl_UL:
            self.countMarkerDuration(self.last_abs_onestep_gap, self.last_abs_onestep_gap_next, self.last_idxs_gap_lc_is_prominent)
            lc0 = self.last_idxs_gap_lc + interval if lc0 is None else lc0
            self.closegrp(self.last_idxs_gap_lc, interval, lc0, snd, self.is_prominent or self.last_idxs_gap_lc_is_prominent, inRemains=True)
        else:
            self.grp_start_sec = interval
            self.msg += f"\tupdate grp_start_sec= {self.grp_start_sec:.3f}\n"

    def findspike(self, sndData):   #, sndData_env):
        '''
        先把符合 main_class2_step_th 的gap 當標記點(候選名單), 然後依次檢查
        1. 累計一個poo group的標記點 cnt_marked ==> 用來計算 標記點的密度, 與group長度
            計算該group累積的 cnt_marked(不同的權重)
        2. 若與下一個標記點相距超過 一定距離以上的，當作目前group的結尾，確認是否符合條件
        '''
        sndData = np.r_[self.lastMainSndData,sndData]
        self.lastMainSndData = sndData[-2:]
        
        onestep_gap = np.diff(sndData)
        abs_onestep_gap = np.abs(onestep_gap)
        self.last_abs_onestep_gap_next = (abs_onestep_gap[1] 
                                            if self.last_abs_onestep_gap and self.last_abs_onestep_gap_next is None
                                            else self.last_abs_onestep_gap_next)
        # twostep_gap = onestep_gap[:-1] + onestep_gap[1:]
        # abs_twostep_gap = np.abs(twostep_gap)
        maxsize = onestep_gap.size-1   #twostep_gap.size
        # = a simple estimation of last point only for "self.has_class2 |= (mask_class2[lc] or mask_class2[nextlc])"
        # abs_twostep_gap = np.r_[abs_twostep_gap, abs_onestep_gap[-1]+np.diff(abs_onestep_gap[-2:])]

        
        # ======== mask_class1   for c1_density evaluation
        mask_class1 = (abs_onestep_gap >= self.main_class1_step_th) #4000sps | (abs_twostep_gap >= self.main_bigclass1_step_th)
        # idxs_gap = np.nonzero(mask_class1)[0]
        # if not self.grp_start_sec and idxs_gap.size:
        #     self.grp_start_sec = self.lc2ts(idxs_gap[0])
        #     self.msg += f"\tinitializing grp_start_sec= {self.grp_start_sec:.3f}sec\n"
        
        # ===== for abnormal sound, poo sound
        mask_class2 = abs_onestep_gap >= self.main_class2_step_th   #4000sps abs_twostep_gap >= self.main_class2_step_th
        idxs_gap = np.nonzero(mask_class2)[0]
        if not self.grp_start_sec and idxs_gap.size:
            self.grp_start_sec = self.lc2ts(idxs_gap[0])
            self.msg += f"\tinitializing grp_start_sec= {self.grp_start_sec:.3f}sec\n"

        # ===== for abnormal sound and unstable estimation
        self.closeABSndGrp(mask_class1, mask_class2, maxsize)  #, sndData)
        
        # = 不用做go_chk_hamonic，暫時先給空的
        mask_class0 = []
        # lcC0_arr = np.array([],dtype='int')
        lc_mi = []
        
        if idxs_gap.size:
            if self.last_idxs_gap_lc is not None:   # 上一段有資料點
                next_intvl = -self.last_idxs_gap_lc + idxs_gap[0]
                if self.last_idxs_gap_lc_is_prominent is None:  # 上一段的資料點離結尾太近，尚無法準確判斷該點的lvl 或 上一段沒有點
                    if self.last_idxs_gap_lvl is not None:
                        addlen = int(self.grp_intvl_th + self.last_idxs_gap_lc)
                        if addlen:
                            self.last_idxs_gap_lc_is_prominent = max(self.last_idxs_gap_lvl, np.abs(sndData[:addlen]).max()) > self.ref_lvl
                            self.aMsg(f"(current seg head)get last_idxs_gap_lc_is_prominent_{self.last_idxs_gap_lc_is_prominent}: "
                                    f"{self.ti:.3f} ~ {self.lc2ts(addlen):.3f}  "
                                    f": max(self.last_idxs_gap_lvl({self.last_idxs_gap_lvl:.2e}), {np.abs(sndData[:addlen]).max():.2e}) > "
                                    f"ref_lvl_{self.ref_lvl:.2e}?",1)
                        else:
                            self.last_idxs_gap_lc_is_prominent = False
            else:
                next_intvl = self.lc2ts(idxs_gap[0])

            self.chkRemains(maxsize, next_intvl, idxs_gap[0], sndData[:idxs_gap[0]-2])
            
            idxs_gap_intvl = np.diff(idxs_gap) if idxs_gap.size > 1 else None
            lc = idxs_gap[-1]
            self.last_abs_onestep_gap = abs_onestep_gap[lc]
            self.last_abs_onestep_gap_next = abs_onestep_gap[lc+1] if lc+1 < abs_onestep_gap.size else None
            self.last_idxs_gap_lc = lc-maxsize
            # lcf = int(min(lc + self.grp_intvl_th, maxsize))
            # self.last_idxs_gap_lc_is_prominent = (abs(sndData[lc:lcf]) >= self.last3MxSnd_ref_lvl).any()

            if self.ref_lvl is None:
                previewlen = idxs_gap[0]-self.calc_reflvl_len
                if previewlen >= 0:
                    self.ref_lvl = max(np.abs(sndData[previewlen:idxs_gap[0]-2]).max()*self.snr,self.main_lvl_LL)
                elif self.last_idxs_gap_ref_lvl is None:
                    self.ref_lvl = self.main_lvl_LL
                elif idxs_gap[0] > 3:
                    self.ref_lvl = max(max(self.last_idxs_gap_ref_lvl, np.abs(sndData[:idxs_gap[0]-3]).max())*self.snr, self.main_lvl_LL)
                else:   # lc0距離起頭太近，需要再參考前一段的lvl
                    self.ref_lvl = max(self.last_idxs_gap_ref_lvl*self.snr, self.main_lvl_LL)
                self.aMsg(f"\nget a new ref_lvl={self.ref_lvl:.2e}  previewlen={previewlen}  last_idxs_gap_ref_lvl={self.last_idxs_gap_ref_lvl}",1)

            lcf = int(lc + self.grp_intvl_th)
            if lcf < maxsize:   # 可以close a group
                self.last_idxs_gap_lvl = None   # 不需保留到下一段
                self.last_idxs_gap_lc_is_prominent = np.abs(sndData[lc:lcf]).max() >= self.ref_lvl
                self.aMsg(f"\n(current seg end)get last_idxs_gap_lc_is_prominent_{self.last_idxs_gap_lc_is_prominent}: {self.lc2ts(lc):.3f} ~ {self.lc2ts(lcf):.3f}  "
                            f": lvl_{np.abs(sndData[lc:lcf]).max():.2e} >= ref_lvl_{self.ref_lvl:.2e}?",1)
            else:   # 不足資訊來決定 last_idxs_gap_lc_is_prominent
                self.last_idxs_gap_lvl = np.abs(sndData[lc:]).max() # 結合下一段資料再來決定
                self.last_idxs_gap_lc_is_prominent = None
                self.aMsg(f"\nNOT get last_idxs_gap_lc_is_prominent: {self.lc2ts(lc):.3f} ~ {self.lc2ts(lcf):.3f}  "
                            f": last_idxs_gap_lvl_{self.last_idxs_gap_lvl:.2e}?",1)
            # 與下一段結合之後，可能會用於計算ref_lvl(看距離下一段的第一個idx_gaps有多遠)
            self.last_idxs_gap_ref_lvl = np.abs(sndData[max(lc+3,maxsize-self.calc_reflvl_halflen):]).max() if lc+3 < maxsize else 0
            # if idxs_gap[0] is not None and self.lc2ts(idxs_gap[0]) < 1.22:    # for debug
            #     print()
        else:
            next_intvl = -self.last_idxs_gap_lc+maxsize if self.last_idxs_gap_lc is not None else self.tNow
            self.chkRemains(maxsize,next_intvl,snd=sndData)
            self.last_abs_onestep_gap = None
            self.last_abs_onestep_gap_next = None
            self.last_idxs_gap_lc = None
            self.reset(proc=False,all=False,closegrp=True)
            self.ref_lvl = None
            self.last_idxs_gap_lvl = None
            self.last_idxs_gap_lc_is_prominent = None
            self.last_idxs_gap_ref_lvl = np.abs(sndData[-self.calc_reflvl_halflen:]).max()

        # = idxs_gap.size-1 -> 因為最後一個點無法得知與下一個idxs_gap點的距離, countMarkerDuration 也需要abs_onestep_gap[idxs_gap[i+1]]
        for i in range(idxs_gap.size-1):
            lc = idxs_gap[i]
            nextlc = idxs_gap[i+1]
            lcf = int(min(nextlc, lc + self.grp_intvl_th, maxsize))
            abs_snd = np.abs(sndData[lc:lcf]).max() # class2 不一定會在peak，所以要往後多看一小段
            self.msg += (f"{self.lc2ts(lc)}sec(={lc}) ~ {self.lc2ts(lcf):.4f}(lcf={lcf}) abs_snd={abs_snd:.2e} "
                            # f">self.last3MxSnd_ref_lvl={self.last3MxSnd_ref_lvl:.2e}?\n")   #  >self.main_lvl_LL={self.main_lvl_LL:.2e}?  "
                            # f">self.main_lvl_UL={self.main_lvl_UL:.2e}\n")
                            f"> ref_lvl={self.ref_lvl:.2e}?\n")
            is_prominent = abs_snd >= self.ref_lvl  #self.last3MxSnd_ref_lvl
            self.aMsg(f"abs_snd={abs_snd:.2e} >= ref_lvl={self.ref_lvl:.2e}?{is_prominent}",1)
            self.is_prominent |= is_prominent
            self.is_prominent_cnt += 1 if is_prominent else 0
            # == 累積標記點數 與 group長度
            self.countMarkerDuration(abs_onestep_gap[lc],abs_onestep_gap[nextlc],is_prominent)
            # = 若與下一個點的間距超過 grp_intvl_th, 就結算這個group
            if self.closegrp(lc, idxs_gap_intvl[i], nextlc=nextlc, snd=sndData, is_prominent=self.is_prominent):
                continue

        return idxs_gap, mask_class1, maxsize, lc_mi, mask_class0
    
    def isPoo(self):
        intvls = np.diff(self.poo_ts_list)
        cnt = 0
        farCnt = 0
        for t in intvls:
            if self.pks_intvl_LL < t < self.pks_intvl_UL:
                cnt += 1
            elif cnt < 3 or farCnt > 1:
                cnt = 0
            else:
                farCnt += 1
        self.aMsg(f"count of poo pks={cnt} >= 3? farCnt={farCnt} ==> isPoo?{cnt >= 3}"
                    f"\n\tpoo pks= {self.formatMsg(self.poo_ts_list)} sec"
                    f"\n\tintvls of poo pks= {self.formatMsg(intvls)} sec")
        return cnt >= 3     # 4 poo pks 因為從間隔算，第一筆就代表有兩個

    def get_poo(self):
        self.msg += (f"get_poo: tNow={self.ti:.3f}-{self.t0:.3f}={self.ti-self.t0:.3f}  "
                    f"expired_sec = {self.tNow - self.ts_storage_sec:.3f}  "
                    f"poo_lc_pltarr={self.formatMsg(self.lc2ts(self.poo_lc_pltarr-self.idxi_plt))}\n"
                    f"poo_lc_arr={self.formatMsg(self.lc2ts(self.poo_lc_arr-self.idxi_plt))}\n"
                    f"poo_ts_list={self.formatMsg(self.poo_ts_list)}\n")

        expired_sec = self.tNow - self.ts_storage_sec   # 早於這個時間的才算"過期"
        # == remove poo within absnd or unstable snd, put poo in queue if out of storage time
        # = 目前 absnd_timeslot_list ==> poo應該不需要;  unstable_timeslot_list ==> 沒有
        if len(self.poo_ts_list) and self.poo_ts_list[-1] < expired_sec:
            poo_lc_arr = self.poo_lc_arr.copy()   # for debug
            self.poo_lc_arr = np.array([],dtype=int) # for debug
            poo_ts_list = self.poo_ts_list.copy() 
            self.poo_ts_list = []
            for i,ts in enumerate(poo_ts_list):
                if not i:
                    self.aMsg(f"remove poo within absnd or unstable snd, and put poo in queue if out of storage time={expired_sec:.3f} self.idxi_plt={self.idxi_plt}")
                if ts <= expired_sec:
                    # self.final_poo_ts_list.append(ts) # 不需要了
                    if poo_lc_arr[i] >= 0:
                        self.poo_lc_pltarr = np.r_[self.poo_lc_pltarr, poo_lc_arr[i]]
                else:
                    self.poo_ts_list.append(ts)  # Pㄟ還要等一小段時間之後，才知道poo pk是否還需要保留
                    try:
                        self.poo_lc_arr = np.r_[self.poo_lc_arr, poo_lc_arr[i]]
                    except:
                        print(
                            f"\n\terr! {self.ti}  i={i}\n\tpoo_ts_list={poo_ts_list}\n\tpoo_lc_arr={self.lc2ts(poo_lc_arr-self.idxi_plt)}"
                        )
                # else:   # debug
                #     self.aMsg(f"removed",2)
            self.aMsg(f"poo_lc_arr={self.formatMsg(self.lc2ts(self.poo_lc_arr-self.idxi_plt))}\n",1)
            self.aMsg(f"poo_lc_pltarr={self.formatMsg(self.lc2ts(self.poo_lc_pltarr-self.idxi_plt))}",1)
            # self.aMsg(f"final_poo_ts_list={self.formatMsg(self.final_poo_ts_list)}",1)
        else:
            if len(self.poo_ts_list):
                self.aMsg(f"self.poo_ts_list[-1]={self.poo_ts_list[-1]:.3f} >= expired_sec={expired_sec:.3f}")
            else:
                self.aMsg(f"no poo_ts")

        # == poo peaks是否能形成 poo cluster
        isPoo = self.isPoo()

        return isPoo
        
    def addData(self, dat):
        ts = dat[0]/self.tsHz
        updateplt = False   # for debug
        has_poo = False
        procData_hp_main = None
        debuginfo = ()
        main_dat = dat[1]

        # # == update time stamp with fw ts  (only for debug)
        # # print(f'dat[0]={dat[0]}  tsHz={self.tsHz}  self.ts_step={self.ts_step}')
        if self.ti is None: # initial
            self.t0 = ts    # for calculate accumulative poo
            self.ti = ts #- self.t0 + self.toffset   #  toffset should be removed when porting to c
        else:
            self.ti = ts - self.step_sec*2 #- self.t0 + self.toffset
        self.tNow = self.ti + self.proc_len_sec - self.step_sec # only for debug
        self.msg += (f'\nSearching poo: {self.ti:.3f}~{self.tNow:.3f}sec {self.tNow-self.ti}\n')
        procData_hp_main,_,_,self.zi_main = self.bwfilter(main_dat, b_filt=self.b_bw_hp, a_filt=self.a_bw_hp,
                                                                zf=self.zi_main)
        # === for debug only
        self.pltdat_main = np.r_[self.pltdat_main, self.lastMainSndData, procData_hp_main[:-2]]

        class2_lcs,mask_class1,maxsize_main, lc_mi, mask_class0 = (
                                            self.findspike(procData_hp_main))    #,envSnd))

        # === for debug only
        self.ts = np.r_[self.ts, np.linspace(self.ti,self.tNow,maxsize_main)]
        self.class0_lcs = np.r_[self.class0_lcs, np.nonzero(mask_class0)[0]+self.idxi_plt]
        self.class1_lcs = np.r_[self.class1_lcs, np.nonzero(mask_class1)[0]+self.idxi_plt]
        self.class2_lcs = np.r_[self.class2_lcs, class2_lcs+self.idxi_plt]

        has_poo = self.get_poo()

        self.idxi_plt += maxsize_main
        if self.idxi_plt > self.segEnd_len:    # for AWS: an indicator of end of audio data
            self.poo_lc_pltarr = np.r_[self.poo_lc_pltarr, self.poo_lc_arr] # for debug
            mask = self.lc2ts(self.poo_lc_pltarr-self.idxi_plt) > self.ts[0] # for debug
            self.poo_lc_pltarr = self.poo_lc_pltarr[mask] # for debug
            self.msg += (f"going to plt:\n"
                        f"poo_lc_pltarr={self.formatMsg(self.lc2ts(self.poo_lc_pltarr-self.idxi_plt))}\n"
                        f"poo_lc_arr={self.formatMsg(self.lc2ts(self.poo_lc_arr-self.idxi_plt))}\n"
                        f"poo_ts_list={self.formatMsg(self.poo_ts_list,'f3')}sec\n")
            debuginfo = (self.ts.copy(),self.pltdat_main.copy(),    # for obs snd
                            self.class0_lcs.copy(), self.class1_lcs.copy(), self.class2_lcs.copy(),  # for debug
                            self.poo_lc_pltarr.copy(),  # for debug
                            self.msg,  # for debug
                            self.c1_density_pltlist.copy(),  # for debug
                            self.c2_density_pltlist.copy())  # for debug
            self.reset(True,False)  # for debug
            updateplt = True

        return updateplt, has_poo, debuginfo
        
    def has_obs(self,main_dat, t0):
        '''
        t0: for debug
        '''
        # f_stft,t_stft,zxx = signal.stft(main_dat,fs=self.micsr,nperseg=256,noverlap=225,nfft=768,boundary=None) # for 4000sps
        f_stft,t_stft,zxx = signal.stft(main_dat,fs=self.micsr,nperseg=256,noverlap=128,nfft=256,boundary=None) # for 4000sps
        fstep = f_stft[1]
        # tstep = t_stft[1]
        band_width_lim_Hz = [110,650] # 頻帶的寬度上下限
        band_width_lim = band_width_lim_Hz/fstep    #np.round(band_width_lim_Hz/fstep,0).astype('int')
        # print(f"{band_width_lim_Hz}Hz  ==> {band_width_lim} ==> {f_stft[band_width_lim]}Hz")
        zxx = np.log10(np.abs(zxx))
        # [0,1] 用於窄頻偵測的界線; 2: isVeryLowfreq的分界點; 3:找頻帶時的最強pk頻率上限; 4:頻帶的頻率上限; 5:進入harmonic偵測的下限
        f_lim = [50,400,70,450,850,150]
        flc_lim = np.searchsorted(f_stft, f_lim)    # 頻率界線
        fsum = [400,800]    # 用於計算頻帶強度的分界點
        self.flc_fsum = np.searchsorted(f_stft, fsum)
        # print(f"{t_stft[0]+t0:.3f}sec:  zxx_shape={zxx.shape}  tstep={t_stft[1]}  fstep={f_stft[1]}  "
        #         f"flc_lim({f_lim}Hz)={flc_lim}  flc_fsum({fsum}Hz)={self.flc_fsum}")
        dens_th = [self.flc_fsum[0]*0.4,self.flc_fsum[0]*0.55,self.flc_fsum[0]*0.32]

        zxx += 4.5  # offset for zeroing
        
        # = ignore noise 與 避免減去backgroud的時候反而反向增強了
        mask = np.bitwise_or(zxx > 4, zxx < 0)
        zxx[mask] = 0
        # zxx[zxx < 0] = 0
        # zxx[:self.flc_fsum[0]+2][zxx[:self.flc_fsum[0]+2] > 4] = 0
        # zxx[self.flc_fsum[0]+2:][zxx[self.flc_fsum[0]+2:] > 3] = 0

        # = remove background
        # backgnd = np.median(zxx[self.flc_fsum[1]:],axis=1)
        # zxx[self.flc_fsum[1]:] -= (backgnd.reshape(-1,1)*np.ones((1,zxx.shape[1])))
        backgnd = np.median(zxx,axis=1)
        zxx -= (backgnd.reshape(-1,1)*np.ones((1,zxx.shape[1])))

        # = 避免負數(在計算band_sum不太適合有負數，就像在看spectrogram"圖片")
        zxx[zxx < 0] = 0
        
        # ====== 試圖找出 具有連續(相近)特徵頻率
        tlc_list = []
        flc_list = []
        tlc_tmp_list = []
        flc_tmp_list = []
        last_pk_lc = 0
        last_pk_lvl = 0
        pk_lvl_list = []    # 用來判斷該段是否為highPk
        breakCnt = 0    # 允許中斷一次 if (is_weak_conti_freq or is_conti_freq) and isMoreThan2
        # = 是否屬於極低頻(<70Hz)
        veryLowFreqCnt = 0
        isVeryLowfreq = False
        isContiVeryLowFreq = False
        # = 是否屬於強低頻帶
        strongLowBandCnt = 0
        isStrongLowBand = False
        lowBandCnt = 0

        isMoreThan2 = False
        isMoreThan1 = False

        pk_lvl_LL = 0.5

        for i,tbin in enumerate(zxx.T):
            # band1 = np.sum(tbin[:self.flc_fsum[0]])   # 目前沒用到了
            dens1 = np.count_nonzero(tbin[flc_lim[0]:self.flc_fsum[0]]>=0.45) # 50~400Hz 高於門檻值以上的資料點比例(密度)
            band3 = np.sum(tbin[self.flc_fsum[1]:])
            lc = flc_lim[0] + np.argmax(tbin[flc_lim[0]:])    # 強度最高的 freq lc
            pk_lvl = tbin[lc]

            isMoreThan2 = len(flc_tmp_list) > 2 # 判斷是否有更能相信的"頻率特徵"
            isMoreThan1 = len(flc_tmp_list) > 1 # 判斷是否有更能相信的"頻率特徵"

            # = 還沒有第一個特徵點 or 與前2個特徵點裡的任一點頻率相近(<=3)
            is_conti_freq = not last_pk_lc or abs(last_pk_lc - lc) <= 3 or (len(flc_tmp_list) > 1 and abs(flc_tmp_list[-2]-lc) <= 3)
            is_weak_conti_freq = False
            # tmpMsg = f"{t_stft[i]+t0:.3f}({i})sec:\n"
            # if not is_conti_freq:
            #     tmpMsg += (f"\tnot is_conti_freq: isMoreThan1?{isMoreThan1}  (ignore this)lc/last_pk_lc={lc/last_pk_lc:.3f} within (1.8,2.2)?\n")
            # === 確認是否能接續 last_pk_lc
            # 已經連續4個了 或 高度基本要求(pk_lvl_LL)
            # 與 last_pk_lvl 或 pk_lvl 相差不大
            isPkChanged = False     # 影響後續 prominent 的判斷門檻是否要放寬
            if not is_conti_freq and isMoreThan1:# or 1.8 < lc/last_pk_lc < 2.2):
                lci = max(0, last_pk_lc-3)
                lcf = min(tbin.size, last_pk_lc+4)
                lc2 = lci + np.argmax(tbin[lci:lcf])  # 考慮會特徵頻率會飄移，所以找附近的最高點
                pk2_lvl = tbin[lc2]
                # tmpMsg += (f"\t\tcheck pk near last_pk: pk:{f_stft[lc2]}(lc2={lc2} > {flc_lim[0]}?)Hz  "
                #            f"lvl={pk2_lvl:.3f} > {pk_lvl_LL}?  "
                #            f"> last_pk_lvl - 0.15={last_pk_lvl - 0.15:.3f}?  "
                #            f"> pk_lvl - 0.15={pk_lvl - 0.15:.3f}?\n")
                if lc2 >= flc_lim[0] and pk2_lvl > 0.4 and (len(flc_tmp_list) > 3 or pk2_lvl > pk_lvl_LL):
                    is_weak_conti_freq = True
                    if (pk2_lvl > last_pk_lvl - 0.15 or pk2_lvl > pk_lvl - 0.15):
                        lc = lc2
                        pk_lvl = pk2_lvl
                        is_conti_freq = True
                        isPkChanged = True
                        # tmpMsg += (f"\t\t\tselect last_pk as this pk!\n")

            if lc <= flc_lim[2]:    # 70Hz
                isVeryLowfreq = True    # 判斷是否考慮有些特別的規則
                veryLowFreqCnt += 1
            
            c1 = lc < flc_lim[1]     # 35 <= 特徵頻率 < 400Hz
            # === 在低頻區有某個頻率特別明顯的可能性較高
            # = pk_lvl門檻：高頻區(>800Hz)不同強度，pk_lvl有不同的門檻 (之前嘗試過用比例，但是可能因為band3的涵蓋範圍較廣，且取log，所以不太合適)
            c2 = (band3 <= 12 and pk_lvl > pk_lvl_LL) or (band3 < 21 and pk_lvl > 1.2) or (is_conti_freq and isMoreThan2)
            # = 密度篩選：密度太高表示很亂，pk高時也允許比較高的密度(也許做該頻段的median去背景也是一個選擇，但這牽涉到變更比較大)
            c2 = c2 and (dens1 < dens_th[2] or (dens1 < dens_th[0] and pk_lvl > 0.7) or (dens1 < dens_th[1] and pk_lvl > 1.2) or pk_lvl > 1.4)
            # self.aMsg(f"{tmpMsg}"
            #           f"\tpk:{f_stft[lc]}({lc})Hz height={pk_lvl:.3f}   "
            #           f"last_pk lc={last_pk_lc}={f_stft[last_pk_lc]:.1f}Hz lvl={last_pk_lvl:.3f} "
            #           f"is_conti_freq={is_conti_freq}  len(flc_tmp_list)={len(flc_tmp_list)}  "
            #           f"self.isLowBand={self.isLowBand}  lowBandCnt={lowBandCnt}  strongLowBandCnt={strongLowBandCnt}  "
            #           f"isVeryLowfreq={isVeryLowfreq}  veryLowFreqCnt={veryLowFreqCnt}\n"
            #           f"\tdens1={dens1}<{dens_th}?  band3={band3:.2f}  c2={c2}")

            # ===== 是否有連續窄頻(某freqency bin特別突出)
            c3 = False
            # = 頻率在偵測範圍, 強度夠突出, 不是低頻帶類, (與上一個最強頻率相近(連續) or 連續累積小於2個)
            if c1 and c2 and not self.isLowBand and (is_conti_freq or len(flc_tmp_list)<2):
                # == 窄頻
                valy_th = [pk_lvl*.55, pk_lvl*.3, pk_lvl*.35] if isMoreThan2 else [pk_lvl*.5, pk_lvl*.25, pk_lvl*.3]
                # = 依據不同高度, 可信度(連續多少個來調整搜尋範圍)
                # pk_lvl很高(>1.5)(比較容易溢的其他頻率)
                # 與上一個最強頻率連續, 有連續3個以上, pk_lvl高(>1 or >0.9 if 很低頻(<50Hz,可能是因為fcut在75Hz,50Hz以下的強度被平滑了))
                if pk_lvl > 1.5 or (is_conti_freq and isMoreThan2 and (pk_lvl > 1 or (isVeryLowfreq and pk_lvl > 0.9))):
                    lci = max(0, lc-7)
                    lcf = min(tbin.size, lc+8)
                # 還沒有連續3個, pk_lvl不夠高(<0.8)
                elif not isMoreThan2 and pk_lvl < 0.8:
                    lci = max(0, lc-3)
                    lcf = min(tbin.size, lc+4)
                # 還沒有連續3個, pk_lvl略高 [0.8,1)
                elif not isMoreThan2 and pk_lvl < 1:
                    lci = max(0, lc-3)
                    lcf = min(tbin.size, lc+5)
                # 還沒有連續3個, pk_lvl高(>=1)  或  已經連續3個, pk_lvl不很高(<= 1)
                else:
                    lci = max(0, lc-5)
                    lcf = min(tbin.size, lc+6)
                mi_L = tbin[lci:lc].min()
                mi_R = tbin[lc+1:lcf].min()
                if tbin[lc-1] > pk_lvl: # 避免心音
                    c30 = c3 = False
                    # self.aMsg(f"tbin[lc-1] > pk_lvl: very low band => ignore!",1)
                else:
                    c30 = isPkChanged or (mi_L <= valy_th[0] and mi_R <= valy_th[0])   # 兩邊 3格內 < pk*0.5 (窄頻)
                    valy_th_c3 = pk_lvl * 0.69 if isPkChanged else valy_th[1]
                    c3 = c30 and (mi_L <= valy_th_c3 or mi_R <= valy_th_c3)    # 至少一邊 3格內 < pk*0.25 (窄頻)
                    # if c3 and pk_lvl < 0.9:     # 太弱的，周遭要有淨空區
                    #     c3 = np.count_nonzero(tbin[lci:lc]<valy_th[1]) >= 2 and np.count_nonzero(tbin[lc+1:lcf]<valy_th[1]) >= 2
                    #     msg = f"is nearby clear?{c3}"
                    # else:
                    #     msg = ''
                    # self.aMsg(f"is prominent?{c3}  both a little sharp?{c30}  "
                    #         f"nearby_lvl_ratio={self.formatMsg(tbin[lci:lcf]/pk_lvl)}  "
                    #         f"mi_L={mi_L:.3f}<={valy_th[1]:.3f}?  mi_R={mi_R:.3f}<={valy_th[1]:.3f}",1)
                    if not c3 and c30 and pk_lvl > 1.3:  # 想針對"有個陡降又遇到緩降"，但目前只是簡單的判斷，所以限定高peak
                        lci = max(0, lc-3)
                        lcf = min(tbin.size, lc+4)
                        c3 = (tbin[lci:lc] <= valy_th[2]).any() or (tbin[lc+1:lcf] <= valy_th[2]).any() # 至少一邊 3格內 < pk*0.3 (窄頻)
                        # self.aMsg(f"sharp then smooth?{c3}  "
                        #         f"nearby_lvl_ratio={self.formatMsg(tbin[lci:lcf]/pk_lvl)}",1)
            
            # # === 非低頻帶的狀態, 頻率不連續(可能是最強的頻率超出上限(摩擦音、腸音)、或不突出) => 在前面就已經先 讓last_pk優先了, 所以這段整併到前面
            # # === 但 有基本強度(> pk_lvl_LL), 已經連續1個以上的特徵點, 還有機會利用last_pk, 再進行比較寬鬆的窄頻偵測
            # c30 = not c3 and pk_lvl > pk_lvl_LL and not is_conti_freq and len(flc_tmp_list) > 0 and last_pk_lc
            # if c30:
            #     lci = max(0, last_pk_lc-3)
            #     lcf = min(tbin.size, last_pk_lc+4)
            #     lc2 = lci + np.argmax(tbin[lci:lcf])  # 考慮會特徵頻率會飄移，所以找附近的最高點
            #     isVeryLowfreq2 = lc2 <= flc_lim[2]   # 70Hz  # 判斷是否考慮有些特別的規則
            #     pk2_lvl = tbin[lc2]
            #     c30 = flc_lim[0] <= lc2 < flc_lim[1] and pk2_lvl >= last_pk_lvl*0.68   # lc2仍要滿足頻率偵測範圍
            #     if c30 and not self.isLowBand:
            #         # = 依據不同高度, 可信度(連續多少個來調整搜尋範圍)
            #         if isMoreThan2 and (pk2_lvl > 1 or (isVeryLowfreq2 and pk2_lvl > 0.9)):  # 已經有連續3個, pk_lvl高(>1), 可以放寬更多搜尋範圍
            #             lci = max(0, lc2-6)
            #             lcf = min(tbin.size, lc2+7)
            #         elif not isMoreThan2 and pk2_lvl < 0.8:  # 還沒有連續3個, pk_lvl不夠高(<0.8)
            #             lci = max(0, lc2-3)
            #             lcf = min(tbin.size, lc2+4)
            #         elif not isMoreThan2 and pk2_lvl < 1:  # 還沒有連續3個, pk_lvl略高(0.8~1)
            #             lci = max(0, lc2-3)
            #             lcf = min(tbin.size, lc2+5)
            #         else:   # 還沒有連續3個, pk_lvl高(>=1)  或  已經連續3個, pk_lvl不很高(<= 1)
            #             lci = max(0, lc2-5)
            #             lcf = min(tbin.size, lc2+6)
            #         valy_th = pk2_lvl*.69
            #         mi_L = tbin[lci:lc2].min()
            #         mi_R = tbin[lc2+1:lcf].min()
            #         c3 = (mi_L <= valy_th and mi_R <= valy_th)    # 窄頻
            #     else:
            #         c30 = False
            #     if c3 and not c1:   # 從last_pk找出來的(lc2)是窄頻 且 現在最高點超出400Hz --> 更新lc為lc2
            #         self.aMsg(f"c3?{c3} not c1?{not c1} => update lc and pk_lvl to those near last_pk",1)
            #         lc = lc2
            #         pk_lvl = pk2_lvl
            #     is_conti_freq = is_conti_freq or c3
            #     self.aMsg(f"by last_pk_lc: c30={c30} lc={lc} lc2={lc2} similar height?ratio={pk2_lvl/last_pk_lvl:.2f} > 0.68?  "
            #                 f"conti and prominent?{c3}  "
            #                 f"nearby_lvl_ratio={self.formatMsg(tbin[lci:lcf]/max(1e-9,pk2_lvl))}  lci,lcf={lci},{lcf}",1)
            # else:
            #     msg = f"not by last_pk_lc: c30={c30}  c3={c3}  pk_lvl={pk_lvl:.2f}  last_pk_lc={last_pk_lc}  "
            #     if last_pk_lc:
            #         msg += f"{self.formatMsg(tbin[max(0, last_pk_lc-3):min(tbin.size, last_pk_lc+4)]/last_pk_lvl)}"
            #     self.aMsg(msg,1)

            # 有找到窄頻, 但頻率不連續 且 還未累積到3個連續特徵點, last_pk_lvl存在且較弱 --> reset
            if c3 and not is_conti_freq and not isMoreThan2 and 0 < last_pk_lvl < 0.9:
                (tlc_tmp_list,flc_tmp_list,last_pk_lc,last_pk_lvl,pk_lvl_list,
                    veryLowFreqCnt,isVeryLowfreq,isContiVeryLowFreq,isStrongLowBand,
                    strongLowBandCnt,lowBandCnt,isMoreThan2,isMoreThan1,breakCnt) = self.reset(closeObsSnd=True)

                # self.aMsg(f"not conti_freq and weak last_pk_lvl={last_pk_lvl:.2f} --> reset",1)

            c31 = True
            # == 試著排除環境中的說話(harmonic)
            if self.isHighPk != 2 and c3 and pk_lvl <= 1 and lc > flc_lim[5]:  # 連續窄頻, 強度不很強(<=1), 頻率高於100Hz
                hamo_th = max(0.4,pk_lvl*0.355)    # 判斷是否有harmonic的 peak 高度門檻
                n = 2
                smooth_pk_th = pk_lvl*0.85 # 避免f resolution不足造成pk lc不準，多檢查一個hlc2
                lc2 = 0
                hlci = lc*2 - 1
                hlcf = lc*2 + 2
                polar = 0
                if lc > 0 and lc+1 < tbin.size:
                    if tbin[lc-1] >= tbin[lc+1] and tbin[lc-1] > smooth_pk_th:
                        polar = -1
                        hlci = hlci + polar*n
                    elif tbin[lc-1] < tbin[lc+1] and tbin[lc+1] > smooth_pk_th:
                        polar = 1
                        hlcf = hlcf + polar*n
                elif lc+1 < tbin.size and tbin[lc+1] > smooth_pk_th:  # lc==0
                    polar = 1
                    hlcf = hlcf + polar*n
                elif lc > 0 and tbin[lc-1] > smooth_pk_th:
                    polar = -1
                    hlci = hlci + polar*n
                hCnt = 0
                # self.aMsg(f"check if there are harmonic tones   polar={polar}",1)
                last_pk_hamo_lc = -1
                overCnt = -1
                while c31 and n < 5 and not overCnt:    # 最高檢查到4x，避免誤判
                    overCnt = np.count_nonzero(tbin[hlci:hlcf] > hamo_th)
                    c41 = False
                    if overCnt == 0:  # 預估倍頻處 ==0: 不夠強
                        c41 = True
                        last_pk_hamo_lc = -1
                    elif overCnt > 2:  #  > 2:極可能是一段寬頻(可能是其他聲音干擾) => 當作不是倍頻
                        tmplc = np.argmax(tbin[hlci:hlcf])
                        if last_pk_hamo_lc < 0 or (last_pk_hamo_lc > 0 and abs(tmplc-last_pk_hamo_lc) < 3): # 還要pk頻率是連續的
                            c41 = True
                        last_pk_hamo_lc = tmplc

                    # tmpMsg = (f"{n}x tone({f_stft[hlci:hlcf]}Hz) height={self.formatMsg(tbin[hlci:hlcf],'f2')}="
                    #         f"{self.formatMsg(tbin[hlci:hlcf]/pk_lvl,'f2')}X  "
                    #         f"<= {hamo_th/pk_lvl:.3f}?{c41}  overCnt={overCnt}  last_pk_hamo_lc={last_pk_hamo_lc}  ")
                    n += 1
                    hlci = lc*n - 1 if polar >= 0 else lc*n + polar*n
                    hlcf = lc*n + 2 if polar < 0 else lc*n + polar*n + 1
                    hCnt += 1 if not c41 else 0
                    c3 = c31 = hCnt < 2
                    # self.aMsg(f"{tmpMsg}hCnt={hCnt}",2)
            # self.aMsg(f"continuous and not harmonic?{c3}  lowBandCnt({lowBandCnt}) < {len(flc_tmp_list)/2}?",1)
            if c3 and lowBandCnt < len(flc_tmp_list)/2 :    # lowBandCnt佔不到時間長度一半 但偵測到連續窄頻且非明顯harmonic, 就清除lowBandCnt
                self.isLowBand = False
                isStrongLowBand = False
                strongLowBandCnt = 0
                lowBandCnt = 0
                # self.aMsg(f"reset isLowBand / isStrongLowBand / strongLowBandCnt / lowBandCnt",2)

            c5 = False
            # === 非連續窄頻 或 已經有lowBandCnt and strongLowBandCnt, 最強頻率 < 450Hz
            c50 = (not c3 or (lowBandCnt and strongLowBandCnt)) and lc < flc_lim[3]
            # # = pk_lvl夠高(>=0.9), 且 (只有2個以下連續特徵點(還不很確定) 或 有連續頻率)
            # c51 = c50 and pk_lvl >= 0.9 and (not isMoreThan2 or is_conti_freq or abs(last_pk_lc - lc) <= 5)
            # # = 適用於最強頻率切換時，考慮last_pk_lc是否有夠高(c30=有基本強度(>0.8), 已連續2個以上的特徵點, 與last_pk_lvl差不多高(>=0.68X)) 
            # c52 = not c51 and c50 and c30
            # self.aMsg(f"go to low band detection?  c50={c50}",1)
            if c50:
                # === 找頻帶範圍
                band_range = []
                thcnt = 0
                band_width = 0
                band_sum = 0
                for idx,lvl in enumerate(tbin):
                    if lvl > 0.38 and thcnt < 3:    # 還沒有起點, 強度超過門檻(0.45), cnt還沒到上限(3)
                        thcnt += 1
                        if not len(band_range) and thcnt == 3:  # 還沒有起點 
                            band_range.append(idx-2)
                            band_sum += lvl
                    elif lvl <= 0.38 and thcnt > 0:    # 強度低過門檻(0.4), cnt還沒到0
                        thcnt -= 1
                        if len(band_range) and not thcnt:   # 有起點了, 歸零了, 頻帶結束
                            band_range.append(idx-2)
                            band_width = band_range[1]-band_range[0]
                            band_sum += lvl
                            break
                    if len(band_range):
                        band_sum += lvl
                # if band_range:
                #     msg = (f"band_width={band_width*fstep:.1f}Hz={band_width} within {band_width_lim}?  "
                #             f"band_range={band_range}={f_stft[band_range]}Hz < {flc_lim[4]}({f_lim[4]})  "
                #             f"avg_lvl={band_sum/len(band_range):.1f}")
                # else:
                #     msg = ''
                # === 200 <= band_width_Hz <= 650,  < 850Hz
                c5 = len(band_range) and band_width_lim[0] <= band_width <= band_width_lim[1] and band_range[1] < flc_lim[4]
                strongLowBandCnt += 1 if c5 and band_sum/len(band_range) > 1 else 0
                lowBandCnt += 1 if c5 else 0
                self.isLowBand = lowBandCnt > 2
                # self.aMsg(f"c5={c5}  isLowBand={self.isLowBand}  lowBandCnt={lowBandCnt}  strongLowBandCnt={strongLowBandCnt}  "
                #         f"band_range={self.formatMsg(f_stft[band_range],'f1')}Hz  {msg}",1)
                # self.aMsg(f"strong lowband?{c5}(c530={c530}  c531={c531}  c532={c532}  c534={c534})  "
                #         f"self.isLowBand={self.isLowBand}  lowBandCnt={lowBandCnt}  strongLowBandCnt={strongLowBandCnt} "
                #         f"band1={band1:.2f}  band2={band2:.2f}  band3={band3:.2f}  "
                #         f"ratio13={ratio13:.1f}  ratio23={ratio23:.1f}  "
                #         f"dens1_{dens1} >= {dens_th}?",1)

                # # = 選項0: band1夠高(>=8), band1密度夠高(>=0.32)
                # # = band1大於band3(>1.5X)(band3乾淨)
                # # =   或 band1密度不超高(<0.55)+pk很高(>=1.2)+band1稍高(>11)(雖然高頻不乾淨，但低頻夠強，有點類似沒那麼乾淨的窄頻)
                # c5 = c530 = band1 >= 8 and dens1 >= dens_th[2] and (ratio13 > 1.5 or (dens1 < dens_th[1] and pk_lvl >= 1.2 and band1 > 11))
                # # = 選項1:(強寬頻帶) band1+band2夠高(>=21), band1大於band3(>2X), band2大於band3(>1.5X)
                # c5 = c531 = c5 or (band1 + band2 >= 21 and ratio13 > 2 and ratio23 > 1.5 and dens1 >= dens_th[0])
                # # = 選項2:(弱頻帶) band1夠高(>=9), (密度夠高(>=0.55) 或 ratio13夠高(>2.5))
                # c5 = c532 = c5 or (band1 >= 9 and (dens1 >= dens_th[1] and ratio13 > 2.5))
                # # = 選項3:(連續弱頻帶, 允許稍弱的) 已經連續4個特徵點, ratio13夠高(>3)) ==> 已放寬在c530
                # # c5 = c533 = c5 or (len(flc_tmp_list) > 3 and ratio13 > 3)
                # # = 選項4:(強中頻帶) band2夠高(>=9), 密度夠高(>=0.32) 或 ratio23夠高(>4)
                # c5 = c534 = c5 or (band2 >= 9 and dens2 >= dens_th[2] and ratio23 > 4)
                # # c5 = c530 or c531 or c532 or c533
                # strongLowBandCnt += 1 if c531 else 0
                # lowBandCnt += 1 if c5 else 0
                # self.isLowBand = lowBandCnt > 2
                # self.aMsg(f"strong lowband?{c5}(c530={c530}  c531={c531}  c532={c532}  c534={c534})  "
                #         f"self.isLowBand={self.isLowBand}  lowBandCnt={lowBandCnt}  strongLowBandCnt={strongLowBandCnt} "
                #         f"band1={band1:.2f}  band2={band2:.2f}  band3={band3:.2f}  "
                #         f"ratio13={ratio13:.1f}  ratio23={ratio23:.1f}  "
                #         f"dens1_{dens1} >= {dens_th}?",1)
                            
            if (c3 or c5):    # 有意義的特徵點
                if breakCnt and tlc_tmp_list[-1] and tlc_tmp_list[-1] != i-1:
                    tlc_tmp_list.append(i-1)
                    flc_tmp_list.append(last_pk_lc)

                tlc_tmp_list.append(i)
                flc_tmp_list.append(lc)
                last_pk_lc = lc
                last_pk_lvl = pk_lvl
                pk_lvl_list.append(pk_lvl)
                pk_lvl_avg = np.mean(pk_lvl_list)
                if pk_lvl_avg > 1:
                    self.isHighPk = 2
                elif pk_lvl_avg > 0.9:
                    self.isHighPk = 1
                else:
                    self.isHighPk = 0
                isContiVeryLowFreq = isMoreThan2 and veryLowFreqCnt >= len(flc_tmp_list)/2
                isStrongLowBand = isMoreThan2 and strongLowBandCnt >= len(flc_tmp_list)/2
                # self.aMsg(f"append to tmp_list(len={len(flc_tmp_list)}) and update last_pk, isHighPk={self.isHighPk}  "
                #             f"isContiVeryLowFreq={isContiVeryLowFreq}(veryLowFreqCnt={veryLowFreqCnt})  "
                #             f"isStrongLowBand={isStrongLowBand}(strongLowBandCnt={strongLowBandCnt})",1)
            # === 特徵沒有連續出現了
            elif len(tlc_tmp_list) > 5 and not self.isHighPk and not self.isLowBand:  # 弱窄頻(pk_lvl_avg<=0.9), 要連續7個以上, 如果是極低頻(<70Hz)站了一半以上, 要連續8個
                if (isContiVeryLowFreq and len(tlc_tmp_list) > 6) or not isContiVeryLowFreq :
                    tlc_list.extend(tlc_tmp_list)
                    flc_list.extend(flc_tmp_list)

                (tlc_tmp_list,flc_tmp_list,last_pk_lc,last_pk_lvl,pk_lvl_list,
                    veryLowFreqCnt,isVeryLowfreq,isContiVeryLowFreq,isStrongLowBand,
                    strongLowBandCnt,lowBandCnt,isMoreThan2,isMoreThan1,breakCnt) = self.reset(closeObsSnd=True)

                # self.aMsg(f"found week narrow band and reset last_pk and isHighPk",1)
            elif len(tlc_tmp_list) > 4 and self.isHighPk == 1 and not self.isLowBand:  # 微強窄頻(0.9<pk_lvl_avg<=1), 要連續6個以上; 如果是極低頻(<70Hz)站了一半以上, 要連續7個
                if (isContiVeryLowFreq and len(tlc_tmp_list) > 5) or not isContiVeryLowFreq :
                    tlc_list.extend(tlc_tmp_list)
                    flc_list.extend(flc_tmp_list)

                (tlc_tmp_list,flc_tmp_list,last_pk_lc,last_pk_lvl,pk_lvl_list,
                    veryLowFreqCnt,isVeryLowfreq,isContiVeryLowFreq,isStrongLowBand,
                    strongLowBandCnt,lowBandCnt,isMoreThan2,isMoreThan1,breakCnt) = self.reset(closeObsSnd=True)

                # self.aMsg(f"found a little strong narrow band and reset last_pk and isHighPk",1)
            elif len(tlc_tmp_list) > 3 and self.isHighPk == 2 and not self.isLowBand:  # 強窄頻(pk_lvl_avg>1), 要連續4個以上; 如果是極低頻(<70Hz)站了一半以上, 要連續6個
                if (isContiVeryLowFreq and len(tlc_tmp_list) > 4) or not isContiVeryLowFreq :
                    tlc_list.extend(tlc_tmp_list)
                    flc_list.extend(flc_tmp_list)

                (tlc_tmp_list,flc_tmp_list,last_pk_lc,last_pk_lvl,pk_lvl_list,
                    veryLowFreqCnt,isVeryLowfreq,isContiVeryLowFreq,isStrongLowBand,
                    strongLowBandCnt,lowBandCnt,isMoreThan2,isMoreThan1,breakCnt) = self.reset(closeObsSnd=True)

                # self.aMsg(f"found strong narrow band and reset last_pk and isHighPk",1)
            elif len(tlc_tmp_list) > 3 and self.isLowBand:  # 強低頻帶, 要連續4個以上; 弱低頻帶, 要連續5個以上
                if isStrongLowBand or (not isStrongLowBand and len(flc_tmp_list) > 4):
                    tlc_list.extend(tlc_tmp_list)
                    flc_list.extend(flc_tmp_list)

                (tlc_tmp_list,flc_tmp_list,last_pk_lc,last_pk_lvl,pk_lvl_list,
                    veryLowFreqCnt,isVeryLowfreq,isContiVeryLowFreq,isStrongLowBand,
                    strongLowBandCnt,lowBandCnt,isMoreThan2,isMoreThan1,breakCnt) = self.reset(closeObsSnd=True)
                
                # self.aMsg(f"found strong low-freq band and reset last_pk, isHighPk and isStrongLowBand",1)
            elif (is_weak_conti_freq or is_conti_freq) and isMoreThan2 and breakCnt < 2:
                breakCnt += 1
                # self.aMsg(f"not found obstruction sound but is_conti_freq({is_weak_conti_freq},{is_conti_freq}) and isMoreThan2 and breakCnt({breakCnt}) < 2",1)
            else:
                (tlc_tmp_list,flc_tmp_list,last_pk_lc,last_pk_lvl,pk_lvl_list,
                    veryLowFreqCnt,isVeryLowfreq,isContiVeryLowFreq,isStrongLowBand,
                    strongLowBandCnt,lowBandCnt,isMoreThan2,isMoreThan1,breakCnt) = self.reset(closeObsSnd=True)

                # self.aMsg(f"not found obstruction sound and reset last_pk and isHighPk",1)

        if len(tlc_tmp_list):   # 一直延伸到檔案結尾 還沒有結案的
            c0 = len(tlc_tmp_list) >= 5 and not self.isHighPk and not self.isLowBand  # 弱窄頻, 要連續6個以上
            c1 = len(tlc_tmp_list) > 2 and self.isHighPk == 2 and not self.isLowBand  # 強窄頻, 要連續3個以上
            c2 = len(tlc_tmp_list) > 3 and self.isLowBand  # 強低頻帶, 要連續4個以上
            c3 = len(tlc_tmp_list) >= 4 and self.isHighPk == 1 and not self.isLowBand
            c4 = len(tlc_tmp_list) >= 3 and self.isHighPk == 2 and not self.isLowBand
            if c0 or c1 or c2 or c3 or c4:
                tlc_list.extend(tlc_tmp_list)
                flc_list.extend(flc_tmp_list)
            # self.aMsg(f"till end: {c0} {c1} {c2} {c3} {c4}")

        #return f_stft,t_stft,zxx,tlc_list,flc_list    # for debug plt
        return len(flc_list)>0    # for AWS, 0: no obstruction sound;  >1: found obstruction sound


def bwfilter(data_in=None, sr=None, f_cut=None, N_filt=3, filtype='bandpass',
                b_filt=None, a_filt=None, isfiltfilt=False, forback=False, iszi=True, zf=None, job=''):
    """apply butterworth filter with zero phase shift"""
    data_filtered = None
    next_zi = None
    if b_filt is None:
        nyq = sr/2
        wn = np.array(f_cut) if isinstance(f_cut,list) or isinstance(f_cut,tuple) else np.array([f_cut])
        if not wn[0] and wn[-1]>=nyq:
            #print(f'bwfilter:  wn{wn} is not valid! Return original data')
            return data_in,[],[],[]
        if np.max(wn) >= nyq and filtype == 'bandpass':
            # wn[np.argmax(wn)] = nyq*0.99
            wn = wn[0]
            filtype = 'highpass'
        if wn.size == 2 and not wn[0]:
            wn = wn[1]
            filtype = 'lowpass'
        elif wn.size == 2 and wn[-1]>=nyq:
            wn = wn[0]
            filtype = 'highpass'
        elif (filtype != 'bandpass' and filtype != 'bandstop') and wn.size == 2:
            wn = wn[0] if filtype == 'highpass' else wn[1]
        #print((f'bwfilter_{job}: sr{sr:.2f} wn{wn} type:{filtype} N={N_filt} '
        #        f'isfiltfilt:{isfiltfilt} forback:{forback} iszi:{iszi}'))
        b_filt, a_filt = signal.butter(N_filt, wn/nyq, btype=filtype)
    if data_in is not None:
        if isfiltfilt:
            #print(f'{job}: filtfilt')
            data_filtered = signal.filtfilt(b_filt, a_filt, data_in)
        elif forback:
            #print(f'{job}: forback with reset zi')
            zi = signal.lfilter_zi(b_filt, a_filt)
            data_filtered,_ = signal.lfilter(b_filt, a_filt, data_in, zi=zi*data_in[0])
            data_filtered,_ = signal.lfilter(b_filt, a_filt, data_filtered[::-1], zi=zi*data_filtered[-1])
            data_filtered = data_filtered[::-1]
        elif not iszi:
            #print(f'{job}: no zi')
            data_filtered = signal.lfilter(b_filt, a_filt, data_in)
        elif iszi and zf is not None:
            data_filtered,next_zi = signal.lfilter(b_filt, a_filt, data_in, zi=zf)
        elif iszi:
            #print(f'{job}: reset zi')
            zi = signal.lfilter_zi(b_filt, a_filt)
            data_filtered,next_zi = signal.lfilter(b_filt, a_filt, data_in, zi=zi*data_in[0])
    return data_filtered, b_filt, a_filt, next_zi

def checkWav(mic_fn):
    goNewfn = False
    goNew = False
    qmic = queue.Queue()
    qinfo = []
    pooData = np.array([])

    thd_readMic = threading.Thread(target=readMicData,
                                    # args=(mic_fn,mic_ts_fn,qmic,qinfo,timeslot_sec,config['pkgnum'],True,2000,),
                                    # args=(mic_fn,mic_ts_fn,qmic,qinfo,timeslot_sec,config['pkgnum'],False,4000,),
                                    args=(mic_fn,qmic,qinfo,[0,3],4,False,4000,),
                                    name='thd_readMic',
                                    daemon=True)
    thd_readMic.start()

    while qmic.empty():
        time.sleep(1)
    micsr = qinfo[0]
    datalen = qinfo[1]
    pkglen = qinfo[4]
    len_UL = qinfo[5]
    detectOdd = Detector(micsr=micsr,pkglen=pkglen,len_UL=len_UL)

    # if config['loadconfig_atfirst']:
    #     detectOdd = Detector(micsr=micsr, config=config, t0=timeslot_sec[0])
    # else:
    #     detectOdd = Detector(micsr=micsr, t0=timeslot_sec[0], pkgnum=config['pkgnum'])
    has_poo = False
    has_obs = False
    
    while not has_poo and (not qmic.empty() or qmic.qsize()): # for AWS
    #while (not qmic.empty() or qmic.qsize()):   # debug
        if qmic.qsize() < 3:
            #print('waiting for more q')
            time.sleep(1)
        tmp = qmic.get_nowait()

        updateplt, has_poo, debuginfo = detectOdd.addData(tmp)
        #print('\r\n')
        #if(has_poo):
        #    print('has_poo')
        
        if updateplt:   # 相當於3sec
            # === 除了 main_dat, ts之外，其他只是debug用
            (ts, main_dat,
                class0_lcs, class1_lcs, class2_lcs,
                poo_lc_arr,
                msg,
                lcC1_density_list,
                c2_density_pltlist) = debuginfo
            has_obs= detectOdd.has_obs(main_dat, ts[0])
            #if(has_obs):
            #    print('has_obs')

    if not has_poo and not detectOdd.has_high_c1_density:     # for AWS
        has_obs = detectOdd.has_obs(main_dat, ts[0])

    return (has_poo,has_obs)

def checkRaw(ba):
    sig_cnt=len(ba)//2
    sig=struct.unpack('<'+'h'*sig_cnt,ba)

    micsr=4000
    pkglen=64
    pkg_num=4
    detectOdd = Detector(micsr=micsr,pkglen=pkglen)

    has_poo = False
    has_obs = False

    data_len=len(sig)
    offset=0
    ts=0

    sp_to_ts_ratio=1/4000.0
    
    main_dat=None#20230920出現main_dat未被設定的錯誤，進行臨時的處理

    while True:
        new_offset=offset+pkglen*pkg_num
        if(new_offset>data_len):
            break
        
        seg=sig[offset:new_offset]
        offset=new_offset
        
        np_seg=np.array(seg,dtype=np.float)
        np_seg/=32768.0
        pkg=(ts,np_seg)

        ts+=pkglen*pkg_num*sp_to_ts_ratio

        updateplt, has_poo, debuginfo = detectOdd.addData(pkg)

        if updateplt:   # 相當於3sec  for debug
            (ts,main_dat,class0_lcs,class1_lcs,class2_lcs,poo_lc_arr,
                    # absnd_timeslot_pltlist,
                    msg,
                    lcC1_density_list,  #high_c1_density_cnt_pltlist,
                    # unstable_timeslot_pltlist,
                    c2_density_pltlist) = debuginfo
                    
            has_obs= detectOdd.has_obs(main_dat, ts[0])    # debug
        if has_poo:
            break

    if not has_poo and not detectOdd.has_high_c1_density and main_dat is not None:     # for AWS
        has_obs = detectOdd.has_obs(main_dat, ts[0])
        #20230920出現main_dat未被設定的錯誤，進行臨時的處理

    return (has_poo,has_obs)

def checkBin(fn):
    with open(fn,'rb') as f:
        ba=f.read()

    return checkRaw(ba)
    
if __name__ == "__main__":
    #mic_fn = './poo_wav/poo_490.wav'       #get poo
    #mic_fn = './poo_wav/poo_463.wav'       #get poo
    #mic_fn = './poo_wav/poo_442.wav'       #get poo
    #mic_fn = './poo_wav/poo_437.wav'       #x,correct
    #mic_fn = './poo_wav/poo_419.wav'       #get poo
    #mic_fn = './poo_wav/poo_415.wav'       #x,correct
    #mic_fn = './obs_wav/2021-08-07-15-10-17-audio-env01_obs_4008.wav'
    #mic_fn = './obs_wav/2021-08-07-15-10-17-audio-env01_obs_4038.wav'
    #mic_fn = './obs_wav/2021-11-04-23-05-11-audio-env01_obs_24029.wav'
    #mic_fn = './obs_wav/2022-03-29-23-01-34-audio-env01_obs_4078.wav'
    #mic_fn = './obs_wav/2022-03-29-23-01-34-audio-env01_obs_4101.wav'
    #mic_fn = './obs_wav/2022-03-29-23-01-34-audio-env01_obs_4201.wav'
    #res=checkWav(mic_fn)
    
    #convert_wav_to_bin('./poo_wav/poo_463.wav','./test.bin')
    mic_fn = './test.bin' 
    res=checkBin(mic_fn)

    print(res)

    
