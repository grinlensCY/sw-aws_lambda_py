import numpy as np
from scipy import signal
import struct
import time,threading
import queue
import numpy as np  
from os import SEEK_SET, SEEK_CUR, SEEK_END
import cache_util as CU

class Detector():
    def __init__(self, udid, t0, age, micsr=4000, pkglen=64, pkgnum=4, tsHz=32768, istsec=True, len_UL=12000, ver=20240617.0):
        # ver: 小數點 代表是不影響演算法的小改版
        # 導入AWS時，要修改 註解裡有AWS(大寫) 與 移除debug的段落!
        # 20240118 review:因為目前obs的判斷沒有stream的概念，而是每三秒(~2.936sec)的spectrogram獨立去判斷(因為之前只限定不連續的三秒資料)
        # 20240322 把age加入
        self.udid = udid
        #self.varfn = f"odd_{udid}.json"
        self.varkey = f"odd_det_{udid}_key"
        self.age = age

        self.toffset = t0   # 用來判斷是否為連續數據
        
        self.istsec = istsec
        self.tsHz = tsHz if not istsec else 1
        
        self.len_UL = len_UL    # debug: 有時候aws上有明顯不滿3秒的資料，需要透過這個來結束poo偵測, 

        filterSet = {
            "typ": "high",
            "fcut": [75],
            "isfiltfilt": 0,
            "noZi": 0,
            "resetZi": 0
            }
        self.msg = ''
        self.loadConfig()
        self.update_sr(micsr,filterSet,pkglen,pkgnum)

        self.load_context()
        self.reset(True,False)  # for debug
        
        self.ver = ver
        #print(f'\ndetect oddsnd ver.{ver}  toffset={self.toffset}')

    
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
    
    def aMsg(self,msg,pre=0,post=0):
        for i in range(pre):
            self.msg += '\t'
        for i in range(post):
            msg += '\t'
        self.msg += msg+'\n'

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
        
    def loadConfig(self,):
        # # quiet spike-like bowel sound
        self.main_lvl_UL = 9e-1    # for debug
        self.main_lvl_LL = 2.0e-1
        # self.main_class0_slope_th = 2.0e-2*4000 #4000sps:2.5e-4*4000
        self.main_class1_slope_th = 4e-2*4000   #4000sps:9e-4*4000
        self.main_class2_slope_th = 2e-1/2*4000   #0.9e-1/2*4000   #2.4e-1/2*4000 #4000sps:4e-3/2*4000
        self.main_class3_slope_th = 3.9e-1*4000 # for sharp turn detection   4000sps:5.5e-3*4000
        self.main_class4_slope_th = 5.5e-1*4000
        self.max_nonclass0_interval_sec = 8/4000 # 波包裡, 最大的空格點距離 0.002sec
        # self.min_grp_duration_sec = 0.00125 # 波包最小寬度
        self.max_grp_duration_sec = 0.013 # 波包最大寬度
        self.calc_reflvl_len_sec = 0.013    # 用來計算ref_lvl的最長範圍
        self.calc_reflvl_halflen_sec = self.calc_reflvl_len_sec/2   # 取出seg最後一小段的max，避免下一seg的第一個需要計算ref_lvl時，資訊量不足(用於計算 last_idxs_gap_ref_lvl)
        self.snr = 7    # ref_lvl 是 max的幾倍 !!!
        self.grp_intvl_th_sec = 0.006 # 波包的淨空距離，也用於 計算該idx_gaps點的lvl
        self.mx_marked_density_th = 0.4  # 有標記出的點佔波包多少比例
        self.high_mx_marked_density_th = 1.2  # 有標記出的點佔波包多少比例
        self.clear_period_sec = 0.007    # 用來清除太靠近的點

        # self.pks_intvl_LL = 0.005   # 因為 grp_intvl_th_sec 與 clear_period_sec 都 > pks_intvl_LL, poo_pk 之間應該都會 > pks_intvl_LL => 移除這限制
        self.pks_intvl_UL = 0.085

        # 可傳輸3秒資料到station, 剛好設定 self.extremely_unstable_length 40seg = 0.064*40 = 2.56, 也許擷取出來的前後都可以多保留些
        self.ts_storage_sec = 2 # 每個poo ts的保存期限

        self.tdiff_th_sec = 3.5 # 若與前一個時間戳記相差超過tdiff_th_sec(3+0.5)，視為不連續數據

        # === poo stft
        self.poo_stft_nperseg = 256
        self.poo_stft_noverlap = 240
        self.poo_stft_nfft = 512
        self.poo_stft_stride = self.poo_stft_nperseg - self.poo_stft_noverlap

        # 0: 0~300Hz 允許多少低強度;
        # 1: 當poo_long超過poo_long_LL0(0.1sec), 0~300Hz 可以放寬 poo_stft_LowCnt_LL 與 non_poo_cnt (也就是，前面要確保有低頻, 後面可以放寬)
        self.poo_stft_fHz = [40,70,300,500]
        
    def update_sr_parameters(self):
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
        self.grp_intvl_th = self.grp_intvl_th_sec*self.micsr

        self.poo_stft_t_step = (self.poo_stft_nperseg - self.poo_stft_noverlap)/micsr
        self.poo_long_LL = 0.28 // self.poo_stft_t_step   # 超出這長度才能算poo
        self.poo_long_LL0 = 0.1//self.poo_stft_t_step   # 超出這長度，可以放寬低頻要求
    
    def updatefilter(self,filterSet):
        if filterSet:
            self.filterSet = filterSet
            #print('update filter:',filterSet)
        _,self.b_bw_hp,self.a_bw_hp,_ = self.bwfilter(sr=self.micsr,f_cut=self.filterSet['fcut'],filtype='highpass')
        self.zi_main = None

    def update_sr(self,sr=4000,filterSet={},pkglen=64,pkgnum=4):
        self.micsr = sr
        self.step_sec = 1/self.micsr
        self.pkglen_sec = pkglen/self.micsr
        self.proc_len = pkgnum*pkglen
        self.proc_len_sec = pkgnum*self.pkglen_sec
        self.same_timeslot_intvl_th_sec = self.proc_len_sec * 1.25
        # self.segEnd_len = min(3*self.micsr//self.proc_len*self.proc_len, self.len_UL-3)
        self.segEnd_len = min(3*self.micsr - self.proc_len, self.len_UL-3)  # debug
        print(f"update_sr: sr={self.micsr}  pkglen={pkglen}  self.segEnd_len={self.segEnd_len}={self.segEnd_len/self.micsr:.3f}sec")
        self.update_sr_parameters()
        self.updatefilter(filterSet)
        # self.reset(True,True) # 要取決於是否為時間連續資料
    
    def reset(self, proc=False, all=False, closegrp=False, closeObsSnd=False, closePoo=False):
        # self.aMsg(f"reset: proc={proc}, all={all}, closegrp={closegrp}, closeObsSnd={closeObsSnd}, closePoo={closePoo}")
        if all:     # init / end of a consecutive upload event
            self.ti = None
            self.t0 = None
            self.tNow = None
            #self.idxi_plt = 0 # for debug plt and (aws 3sec data)index of end of data

            # === for stream
            self.lastMainSndData = []
            
            # === findspike
            # = 校正強度門檻
            self.ref_lvl = None

            # === suspect abnormal sound
            self.has_high_c1_density = False    # 若沒有poo  has_high_c1_density也沒有 ==> 才進行呼吸異音 (有has_high_c1_density 再進行大聲腸鳴?)
            self.conti_high_c2_density_cnt = 0  # 以目前 64*4 來說，連續2次 = 0.128sec; 連續兩次就進行 poo_stft 偵測

            self.last_poo_ts = -3600
            # == poo sound detection by features in time-series data
            self.is_prominent = False   # 特別突出的
            self.is_prominent_cnt = 0
            self.last_idxs_gap_lc_is_prominent = False
            self.last_abs_onestep_gap_next = None
            self.last_abs_onestep_gap = None
            self.last_idxs_gap_lc = None
            self.last_idxs_gap_lvl = None   # 用於結合下一段資料再來決定 last_idxs_gap_lc_is_prominent
            self.last_idxs_gap_ref_lvl = None   # 保留到下一段，當下一段的第一個idx_gaps前面的資料點不足，可以加入
            # 簡單地判斷grp是不是單一pulse(只看C2有沒有過多的轉折，想像中應該最多兩個)
            self.last_c2_lvl = None
            self.is_neg_slope_from_lastC2 = None
            self.turnCnt_c2 = 0

            self.grp_start_sec = 0
            self.grp_duration = 0
            self.pre_intvl = 0
            self.cnt_marked = 0
            self.mx_marked_density = 0
            self.is_priorP_pk = False
            self.poo_ts_list = []   # 從時序信號找到的poo
            # self.poo_lc_arr = np.array([],dtype=int)   # debug: 與 self.poo_ts_list 同步, 提供給 self.poo_lc_pltarr

            # == poo sound detection by features in spectrogram
            self.poo_stft_micData = []  # mic data for poo stft detection
            self.pre_poo_stft_micData = []  # 往前延伸一段，可以得到從無到有比較完整的stft (接在第一段前面)
            self.poo_stft_bts = None    # debug + 為了知道是否需要加上 pre_poo_stft_micData
            self.ti_micDat = None   # 用於 設定 要進行poo_stft的 poo_stft_bts 起始值, 檢查poo_ts的第一點與前面的間隔
            self.poo_long = 0   # 在poo_stft找到的Poo長度
            self.non_poo_cnt = 0    # 在poo_stft裡不合格的次數
            self.allowOnlyHigherFreqBand = False    # 是否允許套用 比較寬鬆的 poo_stft 認定條件
            # self.poo_timespans = [] # debug, found in poo_stft

            # === for 阻塞音
            self.isLowBand = False     # 強低頻帶
            self.isHighPk = 0     # 強:2, 中:1, 弱:0
        
        if proc or all: # for debug
            # self.msg = f"reset  proc={proc}  all={all}  closegrp={closegrp}\n"
            # self.ts = np.array([],dtype=float) # for debug
            self.micDat_obs = []   # for debug + obs
            # self.pltdat_env = []    # for debug
            # self.raw_micDat = []   # raw mic data for debug
            # self.poo_lc_arr = self.poo_lc_arr - self.idxi_plt   # debug: 與 self.poo_ts_list 同步, 提供給 self.poo_lc_pltarr
            #self.idxi_plt = 0   # idx offset of each input segment  # for debug plt and (aws 3sec data)index of end of data
            # self.class0_lcs = np.array([],dtype=int)    # for debug
            # self.class1_lcs = np.array([],dtype=int)    # for debug
            # self.class2_lcs = np.array([],dtype=int)    # for debug
            # self.poo_lc_pltarr = np.array([],dtype=int)   # debug only

            # self.c1_density_pltlist = [] # for debug
            # self.c2_density_pltlist = [] # for debug
            # self.high_c1_density_cnt_pltlist = [] # for debug

            # = 強低頻帶 for 阻塞音
            self.isLowBand = False
            self.isHighPk = 0     # 強:2, 中:1, 弱:0
        
        if closegrp:
            self.msg += f"reset  proc={proc}  all={all}  closegrp={closegrp}\n"
            self.is_prominent = False
            self.grp_duration = 0
            self.pre_intvl = 0
            self.cnt_marked = 0
            self.mx_marked_density = 0
            self.is_prominent_cnt = 0   # for estimation of poo candidate point density
            self.last_c2_lvl = None
            self.is_neg_slope_from_lastC2 = None
            self.turnCnt_c2 = 0

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
            isMoreThan2 = False
            isMoreThan1 = False
            breakCnt = 0

            vars = (tlc_tmp_list,flc_tmp_list,last_pk_lc,last_pk_lvl,pk_lvl_list,
                    veryLowFreqCnt,isVeryLowfreq,isContiVeryLowFreq,isStrongLowBand,
                    strongLowBandCnt,lowBandCnt,isMoreThan2,isMoreThan1,breakCnt)
            return vars
        
        if closePoo:
            self.poo_ts_list = []
            self.poo_stft_micData = []
            self.poo_stft_bts = None
            self.poo_long = 0
        
    def var2self(self,var):
        print(f"load dynamic parameters from var")
        # self.toffset = var['toffset']
        self.zi_main = var['zi_main']
        self.ti = var['ti']
        self.t0 = var['t0']
        self.tNow = var['tNow']
        #self.idxi_plt = var['idxi_plt'] # for debug plt and (aws 3sec data)index of end of data

        # === for stream
        self.lastMainSndData = var['lastMainSndData']
        
        # === findspike
        # = 校正強度門檻
        self.ref_lvl = None

        # === abnormal sound
        self.has_high_c1_density = var['has_high_c1_density']    # 若沒有poo  has_high_c1_density也沒有 ==> 才進行呼吸異音 (有has_high_c1_density 再進行大聲腸鳴?)
        self.conti_high_c2_density_cnt = var['conti_high_c2_density_cnt']  # 以目前 64*4 來說，連續2次 = 0.128sec; 連續兩次就進行 poo_stft 偵測
                    
        # = poo sound
        # self.goChkPoo = var['goChkPoo']
        self.last_poo_ts = var['last_poo_ts']
        self.is_prominent = var['is_prominent']   # 特別突出的
        self.is_prominent_cnt = var['is_prominent_cnt']
        self.last_idxs_gap_lc_is_prominent = var['last_idxs_gap_lc_is_prominent']
        self.last_abs_onestep_gap_next = var['last_abs_onestep_gap_next']
        self.last_abs_onestep_gap = var['last_abs_onestep_gap']
        self.last_idxs_gap_lc = var['last_idxs_gap_lc']
        self.last_idxs_gap_lvl = var['last_idxs_gap_lvl']   # 用於結合下一段資料再來決定 last_idxs_gap_lc_is_prominent
        self.last_idxs_gap_ref_lvl = var['last_idxs_gap_ref_lvl']   # 保留到下一段，當下一段的第一個idx_gaps前面的資料點不足，可以加入
        self.grp_start_sec = var['grp_start_sec']
        self.grp_duration = var['grp_duration']
        self.pre_intvl = var['pre_intvl']
        self.cnt_marked = var['cnt_marked']
        self.mx_marked_density = var['mx_marked_density']
        self.is_priorP_pk = var['is_priorP_pk']
        self.poo_ts_list = var['poo_ts_list']
        self.last_c2_lvl = var['last_c2_lvl']
        self.is_neg_slope_from_lastC2 = var['is_neg_slope_from_lastC2']
        self.turnCnt_c2 = var['turnCnt_c2']

        # self.poo_lc_arr = np.array(var['poo_lc_arr']).astype('int') # debug
        # print(f"var2self: self.poo_lc_arr={self.poo_lc_arr}  var['poo_lc_arr']={var['poo_lc_arr']}")
        self.poo_stft_micData = var['poo_stft_micData']
        self.pre_poo_stft_micData = var['pre_poo_stft_micData']
        self.poo_long = var['poo_long']
        self.non_poo_cnt = var['non_poo_cnt']
        self.allowOnlyHigherFreqBand = var['allowOnlyHigherFreqBand']
        self.ti_micDat = var['ti_micDat']
        self.poo_stft_bts = var['poo_stft_bts']

        # self.poo_timespans = var['poo_timespans']	# debug

        # === reset for 阻塞音
        # 因為目前obs的判斷沒有stream的概念，而是每三秒的spectrogram獨立去判斷(因為之前只限定不連續的三秒資料，所以就沒有寫有連續資料的狀態)
        self.isLowBand = False     # 強低頻帶
        self.isHighPk = 0     # 強:2, 中:1, 弱:0

    def load_context(self,):    # 載入前一次的動態參數
        print('load_context')
        
        var=CU.get_cache_data(self.varkey)
        if(var is not None):# 表示有前一次的參數
            if 'toffset' in var:
                print(f"self.toffset({self.toffset:.3f}) - var['toffset']({var['toffset']:.3f}) = {self.toffset - var['toffset']:.3f}")
            if ('toffset' not in var
                    or (self.toffset - var['toffset'] > self.tdiff_th_sec)):   # 間隔超出上限 => 非連續
                print('not consecutive data => reset all!')
                self.reset(all=True)
            else:
                self.var2self(var)
        else:
            print('no preset var')
            self.reset(all=True)

    def save_context(self,):
        #print('save_context to',self.varfn)
        var = {}
        var['zi_main'] = self.zi_main.tolist()
        var['toffset'] = self.toffset
        var['ti'] = self.ti
        var['t0'] = self.t0
        var['tNow'] = self.tNow
        #var['idxi_plt'] = self.idxi_plt # for debug plt and (aws 3sec data)index of end of data

        # === for stream
        var['lastMainSndData'] = self.lastMainSndData.tolist()
        
        # === findspike
        # = 校正強度門檻
        self.ref_lvl = None

        # === abnormal sound
        # # 若沒有poo  has_high_c1_density也沒有 ==> 才進行呼吸異音 (有has_high_c1_density 再進行大聲腸鳴?)
        # 因為之前都是每一個新檔案(~3秒)就reset，並沒有保留的概念，而且這個目前只用於 要不要 進入 poo以外的偵測，所以暫時就不動
        var['has_high_c1_density'] = False  #self.has_high_c1_density
        var['conti_high_c2_density_cnt'] = self.conti_high_c2_density_cnt   # 以目前 64*4 來說，連續2次 = 0.128sec; 連續兩次就進行 poo_stft 偵測'
                    
        # = poo sound
        # var['goChkPoo'] = self.goChkPoo
        var['last_poo_ts'] = self.last_poo_ts
        # == 有些特別加上 bool, int 是因為json dump時不接受numpy的東西
        var['is_prominent'] = bool(self.is_prominent)   # 特別突出的
        var['is_prominent_cnt'] = self.is_prominent_cnt
        var['last_idxs_gap_lc_is_prominent'] = bool(self.last_idxs_gap_lc_is_prominent)
        var['last_abs_onestep_gap_next'] = self.last_abs_onestep_gap_next
        var['last_abs_onestep_gap'] = self.last_abs_onestep_gap
        var['last_idxs_gap_lc'] = int(self.last_idxs_gap_lc) if self.last_idxs_gap_lc is not None else self.last_idxs_gap_lc
        var['last_idxs_gap_lvl'] = self.last_idxs_gap_lvl   # 用於結合下一段資料再來決定 last_idxs_gap_lc_is_prominent
        var['last_idxs_gap_ref_lvl'] = self.last_idxs_gap_ref_lvl   # 保留到下一段，當下一段的第一個idx_gaps前面的資料點不足，可以加入
        var['grp_start_sec'] = self.grp_start_sec
        var['grp_duration'] = int(self.grp_duration)
        var['pre_intvl'] = int(self.pre_intvl)
        var['cnt_marked'] = self.cnt_marked
        var['mx_marked_density'] = self.mx_marked_density
        var['is_priorP_pk'] = self.is_priorP_pk
        var['poo_ts_list'] = self.poo_ts_list
        var['last_c2_lvl'] = self.last_c2_lvl
        var['is_neg_slope_from_lastC2'] = self.is_neg_slope_from_lastC2
        var['turnCnt_c2'] = self.turnCnt_c2

        var['poo_stft_micData'] = self.poo_stft_micData
        var['pre_poo_stft_micData']= self.pre_poo_stft_micData
        var['poo_long'] = self.poo_long
        var['non_poo_cnt'] = self.non_poo_cnt
        var['allowOnlyHigherFreqBand'] = self.allowOnlyHigherFreqBand
        var['ti_micDat'] = self.ti_micDat
        var['poo_stft_bts'] = self.poo_stft_bts

        # debug
        # var['poo_lc_arr'] = self.poo_lc_arr.tolist()
        # var['poo_timespans'] = self.poo_timespans   # debug

        CU.set_cache_data(self.varkey,var,3*60)

        #try:
        #    with open(self.varfn, 'w', newline='') as jout:
        #        json.dump(var, jout, ensure_ascii=False, cls=NumpyEncoder)
        #except:
        #    print('json dump fails')
        #    for key in var.keys():
        #        print(key, var[key])
        #        json.dumps({key:var[key]})
    
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
        # self.msg += (f"\tclosegrp: turnCnt_c2={self.turnCnt_c2}  interval={interval} > self.grp_intvl_th={self.grp_intvl_th}?  "
                    # f"grp_duration={self.grp_duration} >= {self.min_grp_duration}?  grp_start_sec={self.grp_start_sec:.3f}\n")
                    # f"grp_start_sec={self.grp_start_sec:.3f}  "
                    # f"nextlc={nextlc}  is_prominent={is_prominent}  inRemains={inRemains}\n")
        if interval > self.grp_intvl_th:    # 0.006sec
            self.grp_start_sec = self.lc2ts(nextlc)
            self.msg += f"\t\tupdate grp_start_sec= {self.grp_start_sec:.3f}\n"
            msg = ''
            if not is_prominent:
                if inRemains:   # update ref_lvl
                    # msg += f"\t\t\tinterval_{interval} <= {self.calc_reflvl_len}?{interval <= self.calc_reflvl_len}  "
                    if interval <= self.calc_reflvl_len:    # 一定需要參考上一段尾巴的lvl
                        if nextlc > 1:
                            self.ref_lvl = (max(max(self.last_idxs_gap_ref_lvl, np.abs(snd).mean())*self.snr, self.main_lvl_LL)
                                            if snd.size
                                            else max(self.last_idxs_gap_ref_lvl*self.snr, self.main_lvl_LL))
                            # msg += (f"nextlc_{nextlc}>1: last_idxs_gap_ref_lvl_{self.last_idxs_gap_ref_lvl:.2e} > snd_{np.abs(snd).mean():.2e}?\n"
                            #         if snd.size
                            #         else f"nextlc_{nextlc}>1: last_idxs_gap_ref_lvl_{self.last_idxs_gap_ref_lvl:.2e}")
                        else:
                            self.ref_lvl = max(self.last_idxs_gap_ref_lvl*self.snr, self.main_lvl_LL)
                            # msg += f"last_idxs_gap_ref_lvl_{self.last_idxs_gap_ref_lvl:.2e}\n"
                    else:
                        # msg += f"nextlc_{nextlc} > calc_reflvl_len_{self.calc_reflvl_len}?\n"
                        if nextlc > self.calc_reflvl_len:   # 可以只看這一段的lvl
                            self.ref_lvl = max(np.abs(snd[-self.calc_reflvl_len:]).mean()*self.snr, self.main_lvl_LL)
                        elif nextlc > 1:
                            self.ref_lvl = (max(max(self.last_idxs_gap_ref_lvl, np.abs(snd).mean())*self.snr, self.main_lvl_LL)
                                            if snd.size
                                            else max(self.last_idxs_gap_ref_lvl*self.snr, self.main_lvl_LL))
                            # msg += (f"nextlc_{nextlc}>1: last_idxs_gap_ref_lvl_{self.last_idxs_gap_ref_lvl:.2e} > snd_{np.abs(snd).mean():.2e}?\n"
                            #         if snd.size
                            #        else f"nextlc_{nextlc}>1: last_idxs_gap_ref_lvl_{self.last_idxs_gap_ref_lvl:.2e}")
                        else:
                            self.ref_lvl = max(self.last_idxs_gap_ref_lvl*self.snr, self.main_lvl_LL)
                            # msg += f"last_idxs_gap_ref_lvl_{self.last_idxs_gap_ref_lvl:.2e}\n"
                else:
                    self.ref_lvl = max((np.abs(snd[lc+3:nextlc-2]).max()*self.snr if interval <= self.calc_reflvl_len
                                    else np.abs(snd[nextlc-self.calc_reflvl_len:nextlc-2]).max()*self.snr),self.main_lvl_LL)
                #self.aMsg((f"updated ref_lvl={self.ref_lvl:.2e} (interval({interval}) <= calc_reflvl_len({self.calc_reflvl_len})?)\n"
                #            f"\t\t\t{msg}"),2)

            # = 短pulse (max_grp_duration:0.013sec)
            c0 = self.grp_duration < min(self.max_grp_duration, interval)
            # = is_prominent
            c1 = c0 and is_prominent
            # = 高密度
            mx_marked_density = (1 if len(self.poo_ts_list) > 1 else 1.2 if self.turnCnt_c2 < 2 else 2)
            c2 = c1 and self.mx_marked_density >= mx_marked_density
            #self.msg += (f"\t\tgrp_duration={self.grp_duration} < min(max_grp_duration={self.max_grp_duration} "
            #                f"and interval={interval})?{c0}\t"    # >= min_grp_duration={self.min_grp_duration}?\t"
            #                # f"cnt_marked={self.cnt_marked}\t"   #mx_density={self.mx_marked_density:.3f} > "
            #                f"mx_marked_density({self.mx_marked_density:.2f}) >= {mx_marked_density}?"
            #                f"{self.mx_marked_density >= mx_marked_density}  "
            #                # f"{self.high_mx_marked_density_th}({self.mx_marked_density>self.high_mx_marked_density_th})?  "
            #                f"is_prominent?{self.is_prominent or is_prominent}(c1_{c1}) ==>add?{c2}\n"
            #                )
            if c2:
                tsNew = self.lc2ts(lc)
                if len(self.poo_ts_list) and self.poo_ts_list[-1] + self.clear_period_sec >= tsNew: # clear previous poo if it's too close to new poo
                    #self.aMsg(f"\t\t\tclear previous poo={self.poo_ts_list[-1]:.3f} because it's too close to new poo"
                    #            f"({self.poo_ts_list[-1] + self.clear_period_sec} >= {tsNew:.3f})")
                    self.poo_lc_arr = self.poo_lc_arr[:-1]    # for debug
                    self.poo_ts_list = self.poo_ts_list[:-1]
                # self.poo_lc_arr = np.r_[self.poo_lc_arr,lc+self.idxi_plt] # for debug
                self.poo_ts_list.append(tsNew)
                # self.last_pk_lc = lc
                # self.msg += (f"\t\twithin {self.lc2ts(lc-self.grp_duration):.3f} ~ {tsNew:.3f}sec ==> add poo pk({tsNew:.3f})\n")
            # self.msg += '\t\t'
            self.reset(proc=False,all=False,closegrp=True)
            # if increase_turnCnt_c2: # reset的時候會被清除
            #     self.turnCnt_c2 = 1
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
        #self.aMsg(f"\ncloseABSndGrp")
        c1lc_arr = np.nonzero(maskC1)[0]
        c1lc_arr_density = c1lc_arr.size/maxsize
        #self.c1_density_pltlist.append([self.ti, self.tNow, c1lc_arr_density])  # for debug
        c2lc_arr = np.nonzero(maskC2)[0]
        c2_density = c2lc_arr.size/maxsize
        #self.c2_density_pltlist.append([self.ti, self.tNow, c2_density])  # for debug
        if c2_density > 0.27:
            self.conti_high_c2_density_cnt += 1
        else:
            self.conti_high_c2_density_cnt = 0

        #self.aMsg(f"c1lc_arr_density={c1lc_arr_density}",1) #  isStable={self.isStable}",1)
        #self.aMsg(f"c2_density={c2_density}  self.conti_high_c2_density_cnt={self.conti_high_c2_density_cnt}",1)

        self.has_high_c1_density = self.has_high_c1_density or c1lc_arr_density > 0.09

    def chkRemains(self, maxsize, interval, lc0=None, snd=None):
        '''
        處理前一段資料 音資料長度不足而還沒辦法確認的部分
        interval: 與下一個idxs_gap的間距 if self.last_idxs_gap_lc else updated self.grp_start_sec 
        snd: 到lc0為止的sndData
        '''
        #self.msg += (f"\nchkRemains: ti={self.ti:.4f} maxsize={maxsize} interval_to_next_lc={interval} "
        #            f"self.last_idxs_gap_lc={self.last_idxs_gap_lc}")
        #self.msg += f"={self.lc2ts(self.last_idxs_gap_lc):.3f}\n" if self.last_idxs_gap_lc is not None else "\n"
        if self.last_idxs_gap_lc is not None:  # 處理前一段裡最後一個idxs_gap
            self.countMarkerDuration(self.last_abs_onestep_gap, self.last_abs_onestep_gap_next, self.last_idxs_gap_lc_is_prominent)
            lc0 = self.last_idxs_gap_lc + interval if lc0 is None else lc0
            self.closegrp(self.last_idxs_gap_lc, interval, lc0, snd, self.is_prominent or self.last_idxs_gap_lc_is_prominent, inRemains=True)
        else:
            self.grp_start_sec = interval
            #self.msg += f"\tupdate grp_start_sec= {self.grp_start_sec:.3f}\n"

    def findspike(self, sndData, goChkPoo):
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
            #self.msg += f"\tinitializing grp_start_sec= {self.grp_start_sec:.3f}sec\n"

        # ===== for abnormal sound and unstable estimation
        self.closeABSndGrp(mask_class1, mask_class2, maxsize)  #, sndData)

        if goChkPoo:
            if idxs_gap.size:
                if self.last_idxs_gap_lc is not None:   # 上一段有資料點
                    next_intvl = -self.last_idxs_gap_lc + idxs_gap[0]
                    if self.last_idxs_gap_lc_is_prominent is None:  # 上一段的資料點離結尾太近，尚無法準確判斷該點的lvl 或 上一段沒有點
                        if self.last_idxs_gap_lvl is not None:
                            addlen = int(self.grp_intvl_th + self.last_idxs_gap_lc)
                            if addlen:
                                self.last_idxs_gap_lc_is_prominent = max(self.last_idxs_gap_lvl, np.abs(sndData[:addlen]).max()) > self.ref_lvl
                                #self.aMsg(f"(current seg head)get last_idxs_gap_lc_is_prominent_{self.last_idxs_gap_lc_is_prominent}: "
                                #        f"{self.ti:.3f} ~ {self.lc2ts(addlen):.3f}  "
                                #        f": max(self.last_idxs_gap_lvl({self.last_idxs_gap_lvl:.2e}), {np.abs(sndData[:addlen]).max():.2e}) > "
                                #        f"ref_lvl_{self.ref_lvl:.2e}?",1)
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
                    previewlen = idxs_gap[0] - 4 -self.calc_reflvl_len
                    if previewlen >= 0:
                        self.ref_lvl = max(np.abs(sndData[previewlen:idxs_gap[0]-4]).mean()*self.snr,self.main_lvl_LL)
                    elif self.last_idxs_gap_ref_lvl is None:
                        self.ref_lvl = self.main_lvl_LL
                    elif idxs_gap[0] > 3:
                        self.ref_lvl = max(max(self.last_idxs_gap_ref_lvl, np.abs(sndData[:idxs_gap[0]-3]).mean())*self.snr, self.main_lvl_LL)
                    else:   # lc0距離起頭太近，需要再參考前一段的lvl
                        self.ref_lvl = max(self.last_idxs_gap_ref_lvl*self.snr, self.main_lvl_LL)
                    #self.aMsg(f"\nget a new ref_lvl={self.ref_lvl:.2e}  previewlen={previewlen}  last_idxs_gap_ref_lvl={self.last_idxs_gap_ref_lvl}",1)

                lci = max(0 if len(idxs_gap) == 1 else idxs_gap[-2] + 2, lc - 4)
                lcf = int(lc + self.grp_intvl_th)
                if lcf < maxsize:   # 可以close a group
                    self.last_idxs_gap_lvl = None   # 不需保留到下一段
                    self.last_idxs_gap_lc_is_prominent = np.abs(sndData[lci:lcf]).max() >= self.ref_lvl
                    #self.aMsg(f"\n(current seg end)get last_idxs_gap_lc_is_prominent_{self.last_idxs_gap_lc_is_prominent}: {self.lc2ts(lci):.3f} ~ {self.lc2ts(lcf):.3f}  "
                    #            f": lvl_{np.abs(sndData[lc:lcf]).max():.2e} >= ref_lvl_{self.ref_lvl:.2e}?",1)
                else:   # 不足資訊來決定 last_idxs_gap_lc_is_prominent
                    self.last_idxs_gap_lvl = np.abs(sndData[lci:]).max() # 結合下一段資料再來決定
                    self.last_idxs_gap_lc_is_prominent = None
                    #self.aMsg(f"\nNOT got last_idxs_gap_lc_is_prominent yet: {self.lc2ts(lci):.3f} ~ {self.lc2ts(lcf):.3f}  "
                    #            f": last_idxs_gap_lvl_{self.last_idxs_gap_lvl:.2e}?",1)
                # 與下一段結合之後，可能會用於計算ref_lvl(看距離下一段的第一個idx_gaps有多遠)
                self.last_idxs_gap_ref_lvl = np.abs(sndData[max(lc+3,maxsize-self.calc_reflvl_halflen):]).mean() if lc+3 < maxsize else 0
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
                self.last_idxs_gap_ref_lvl = np.abs(sndData[-self.calc_reflvl_halflen:]).mean()

            # = idxs_gap.size-1 -> 因為最後一個點無法得知與下一個idxs_gap點的距離, countMarkerDuration 也需要abs_onestep_gap[idxs_gap[i+1]]
            lcf = None
            for i in range(idxs_gap.size-1):
                lc = idxs_gap[i]
                nextlc = idxs_gap[i+1]
                lci = max(0,lc - 4) if lcf is None else lcf
                lcf = int(min(nextlc, lc + self.grp_intvl_th, maxsize))
                abs_snd = np.abs(sndData[lci:lcf]).max() # class2 不一定會在peak，所以要往後多看一小段
                #self.msg += (f"{self.lc2ts(lc)}sec(={lc}):{self.lc2ts(lcf):.4f}(lci={lci}) ~ {self.lc2ts(lcf):.4f}(lcf={lcf}) abs_snd={abs_snd:.2e} "
                                # f">self.last3MxSnd_ref_lvl={self.last3MxSnd_ref_lvl:.2e}?\n")   #  >self.main_lvl_LL={self.main_lvl_LL:.2e}?  "
                                # f">self.main_lvl_UL={self.main_lvl_UL:.2e}\n")
                                #f"> ref_lvl={self.ref_lvl:.2e}?\n")
                is_prominent = abs_snd >= self.ref_lvl  #self.last3MxSnd_ref_lvl
                #self.aMsg(f"abs_snd={abs_snd:.2e} >= ref_lvl={self.ref_lvl:.2e}?{is_prominent}",1)
                self.is_prominent |= is_prominent
                self.is_prominent_cnt += 1 if is_prominent else 0

                lvl = sndData[lc]
                increase_turnCnt_c2 = False
                #msg = f"\tlast_c2_lvl={self.last_c2_lvl}  lvl={lvl}\n"
                if self.last_c2_lvl is not None:
                    is_neg_slope_from_lastC2 = lvl < self.last_c2_lvl
                    #msg += (f"\tis_neg_slope_from_lastC2({self.is_neg_slope_from_lastC2}) != "
                    #        f"is_neg_slope_from_lastC2({is_neg_slope_from_lastC2})?\n")
                    if self.is_neg_slope_from_lastC2 is not None and is_neg_slope_from_lastC2 != self.is_neg_slope_from_lastC2:
                        self.turnCnt_c2 += 1
                        increase_turnCnt_c2 = True
                        #msg += "\t\tturnCnt_c2 += 1\n"
                    self.is_neg_slope_from_lastC2 = is_neg_slope_from_lastC2
                self.last_c2_lvl = lvl
                #self.aMsg(msg)

                # == 累積標記點數 與 group長度
                self.countMarkerDuration(abs_onestep_gap[lc],abs_onestep_gap[nextlc],is_prominent)
                # = 若與下一個點的間距超過 grp_intvl_th, 就結算這個group
                if self.closegrp(lc, idxs_gap_intvl[i], nextlc=nextlc, snd=sndData, is_prominent=self.is_prominent):
                    continue

        return idxs_gap, mask_class1, maxsize#, lc_mi, mask_class0
    
    def is_poo_stft(self,):
        poo_stft_f,poo_stft_t,poo_zxx = signal.stft(self.poo_stft_micData,fs=self.micsr,
                                                    nperseg=self.poo_stft_nperseg,
                                                    noverlap=self.poo_stft_noverlap,
                                                    nfft=self.poo_stft_nfft,  # stride=16 可以整除 (poo_stft_micData.size - 256)
                                                    boundary=None) # for 4000sps
        # f size = nfft//2+1; t size= math.ceil(data_size - nperseg)/(nperseg - noverlap) + 1
        poo_zxx = np.log10(np.abs(poo_zxx))
        poo_zxx += 5.4
        poo_zxx[poo_zxx < 0] = 0

        poo_stft_LowCnt_LL0, poo_stft_LowCnt_LL1, poo_stft_300Hz_lc, poo_stft_500Hz_lc = np.searchsorted(poo_stft_f, self.poo_stft_fHz)
        poo_stft_LowCnt_LL = poo_stft_LowCnt_LL0 if not self.allowOnlyHigherFreqBand else poo_stft_LowCnt_LL1

        #self.aMsg(f"\nis_poo_stft: poo_stft_bts={self.poo_stft_bts:.3f}sec  "
        #          f"poo_stft_LowCnt_LL=({poo_stft_LowCnt_LL0}, {poo_stft_LowCnt_LL1})  "
        #          f"poo_long_LL=({self.poo_long_LL0}, {self.poo_long_LL})  "
        #          f"poo_stft_300Hz_lc={poo_stft_300Hz_lc}  poo_stft_500Hz_lc={poo_stft_500Hz_lc}")

        for i,tbin in enumerate(poo_zxx.T):
            lowCnt_300Hz = np.count_nonzero(tbin[:poo_stft_300Hz_lc] < 2.8)
            lowCnt_500Hz = np.count_nonzero(tbin[poo_stft_300Hz_lc:poo_stft_500Hz_lc] < 2.8) if self.allowOnlyHigherFreqBand else poo_stft_300Hz_lc
            stft_ts = self.poo_stft_bts + poo_stft_t[i]
            #self.aMsg(f"{i} {stft_ts:.3f}sec: "
            #          f"lowCnt_300Hz={lowCnt_300Hz} <= {poo_stft_LowCnt_LL}?  "
            #          f"(allowOnlyHigherFreqBand={self.allowOnlyHigherFreqBand})"
            #          f"lowCnt_500Hz={lowCnt_500Hz}(<2.8 count={np.count_nonzero(tbin[poo_stft_300Hz_lc:poo_stft_500Hz_lc] < 2.8)}) <= {poo_stft_LowCnt_LL1}?"
            #          ,1)
            if lowCnt_300Hz <= poo_stft_LowCnt_LL or (self.allowOnlyHigherFreqBand and lowCnt_500Hz <= poo_stft_LowCnt_LL1):
                #if not self.poo_long:   # debug
                #    self.poo_timespans.append([stft_ts])
                self.poo_long += 1
                #self.aMsg(f"extend poo_long to {self.poo_long}",2)
                self.non_poo_cnt = 0
                if self.poo_long >= self.poo_long_LL:
                    #self.poo_timespans[-1].append(stft_ts)  # debug
                    # 可以清除 poo_stft了
                    #self.aMsg(f"poo_long({self.poo_long}) >= poo_long_LL (found poo) => clear poo_ts / poo_stft_micData => True",1)
                    self.reset(closePoo=True)
                    return True
                elif not self.allowOnlyHigherFreqBand and self.poo_long >= self.poo_long_LL0:   # 還沒放寬poo_stft_LowCnt_LL 但 poo_long 超過 poo_long_LL0了
                    poo_stft_LowCnt_LL = poo_stft_LowCnt_LL1
                    self.allowOnlyHigherFreqBand = True
                    #self.aMsg(f"poo_long({self.poo_long},{self.poo_long*self.poo_stft_t_step:.3f}sec) >= poo_long_LL0 => loose poo_stft_LowCnt_LL to {poo_stft_LowCnt_LL}",1)
            else:
                self.non_poo_cnt += 1
                self.poo_long += 1 if self.poo_long else 0
                #self.aMsg(f"increased non_poo_cnt={self.non_poo_cnt}",2)
                if self.poo_long and (self.non_poo_cnt > 1 and (not self.allowOnlyHigherFreqBand or self.non_poo_cnt > 4)):   # 連續兩個不合格的就reset
                    #self.aMsg(f"too many non_poo_cnt => reset poo temp info",3)
                    self.poo_long = 0
                    #del self.poo_timespans[-1]  # debug
        
        if self.poo_long:    # 到最後了，但還沒到達足夠長門檻 => 刪去前面沒用的
            self.poo_stft_bts = stft_ts + (-self.poo_stft_nperseg/2 + self.poo_stft_stride)/self.micsr
            self.poo_stft_micData = self.poo_stft_micData[-self.poo_stft_nperseg + self.poo_stft_stride:]  # 要讓下次能接續著stride
            orig_idx = len(self.poo_ts_list) - 1
            #self.aMsg(f"offset self.poo_stft_bts to {self.poo_stft_bts:.3f}  poo_stft_micData.size={self.poo_stft_micData.size}",1)
            #self.aMsg(f"before screen: poo_ts_list={self.poo_ts_list}",2)
            for i,t in enumerate(self.poo_ts_list[::-1]):
                if t < self.tNow:
                    #self.aMsg(f"del this poo_ts({self.poo_ts_list[orig_idx]:.3f})",2)
                    del self.poo_ts_list[orig_idx]
                orig_idx -= 1
            #self.aMsg(f"after screen: poo_ts_list={self.poo_ts_list}",2)
        else:
            self.reset(closePoo=True)
            #self.aMsg(f"no poo_long -> clear poo_stft_micData, poo_ts_list, poo_stft_bts",1)
        return False
    
    def get_poo(self, micDat):
        # === poo_ts 可能還是有存在的意義，譬如有些還不到c2_density門檻 或者 
        #self.msg += (f"\nget_poo: tNow={self.ti:.3f}-{self.t0:.3f}={self.ti-self.t0:.3f}  "
        #            f"expired_sec = {self.tNow - self.ts_storage_sec:.3f}  "
        #            f"\tpoo_lc_pltarr={self.formatMsg(self.lc2ts(self.poo_lc_pltarr-self.idxi_plt))}\n"
        #            f"\tpoo_lc_arr={self.formatMsg(self.lc2ts(self.poo_lc_arr-self.idxi_plt))}\n"
        #            f"\tpoo_ts_list={self.formatMsg(self.poo_ts_list)}\n"
        #            f"\tpoo_stft_micData size={len(self.poo_stft_micData)}={len(self.poo_stft_micData)/micDat.size}  "
        #            f"poo_long={self.poo_long}\n")

        # == remove poo ts if out of storage time or (前/後intvl > pks_intvl_UL)
        expired_sec = self.tNow - self.ts_storage_sec   # 早於這個時間的才算"過期"
        # == remove poo within absnd or unstable snd, put poo in queue if out of storage time
        # = 目前 absnd_timeslot_list ==> poo應該不需要;  unstable_timeslot_list ==> 沒有
        if len(self.poo_ts_list) and self.poo_ts_list[-1] < expired_sec:
            #poo_lc_arr = self.poo_lc_arr.copy()   # for debug
            #self.poo_lc_arr = np.array([],dtype=int) # for debug
            poo_ts_list = self.poo_ts_list.copy()
            self.poo_ts_list = []
            intvls = np.r_[poo_ts_list[0]-self.ti_micDat, np.diff(poo_ts_list), self.tNow-poo_ts_list[-1]]
            poo_ts_cnt_LL = 6 if intvls[-1] < self.pks_intvl_UL else poo_ts_cnt_LL
            mx_poo_ts_idx = len(poo_ts_list) - 1
            
            #self.aMsg(f"remove poo if earlier than expired time={expired_sec:.3f}  self.idxi_plt={self.idxi_plt}",1)
            for i,ts in enumerate(poo_ts_list):
                #if i < len(poo_lc_arr) and poo_lc_arr[i] not in self.poo_lc_pltarr: # debug
                #    self.poo_lc_pltarr = np.r_[self.poo_lc_pltarr, poo_lc_arr[i]]

                if ts <= expired_sec:   # 去除過期的
                    #self.aMsg(f"{ts} is expired",1)
                    continue
                else:
                    c0 = intvls[i] < 0 or intvls[i] > self.pks_intvl_UL  # 離前一個太遠
                    c1 = intvls[i+1] > self.pks_intvl_UL    # 離下一個太遠
                    
                    #self.aMsg(f"{i} {ts:.3f}sec: "
                    #            f"intvl to prior={ts - (poo_ts_list[i-1] if i > 0 else self.ti_micDat):.3f}({intvls[i]:.3f}) > pks_intvl_UL({self.pks_intvl_UL})?{c0}  "
                    #            f"intvl to next={(poo_ts_list[i+1] if i < mx_poo_ts_idx else self.tNow) - ts:.3f}({intvls[i+1]:.3f}) > pks_intvl_UL?{c1}",2)
                    if c0 and c1: # 前後的間隔都太遠 => 無效
                        #self.aMsg(f"intvl is too far => remove this",3)
                        continue
                    # 離下一個太遠 且 是最後一個 且 不夠多(<3 是因為這個還沒加入poo_ts_list，所以先少算一個) => 無效的 => 通通清除
                    elif c1 and len(self.poo_ts_list) < 3:
                        #self.aMsg(f"intvl to next is too far and len(self.poo_ts_list) < 3 => remove all poo ts",3)
                        self.poo_ts_list = []
                    elif i and i < mx_poo_ts_idx and len(self.poo_ts_list) < 3 and intvls[i+1] > 3*intvls[i]:
                        #self.aMsg(f"ratio of intvl to prior/next > 3 and len(self.poo_ts_list) < 3 => remove all poo ts",3)
                        self.poo_ts_list = []
                    else:
                        self.poo_ts_list.append(ts)
            #self.aMsg(f"poo_ts_list={self.formatMsg(self.poo_ts_list)}",1)        
            #self.aMsg(f"poo_lc_arr={self.formatMsg(self.lc2ts(self.poo_lc_arr-self.idxi_plt))}",1)
            #self.aMsg(f"poo_lc_pltarr={self.formatMsg(self.lc2ts(self.poo_lc_pltarr-self.idxi_plt))}",1)
        #else:   # debug msg
        #    self.aMsg(f"no poo_ts",1)
        
        # 清除 poo_ts_list: 在 expired 或 間隔太遠+數量少 或者 藉由 is_poo_stft 清除
        # conti_high_c2_density_cnt則是即時反應
        #self.aMsg(f"len(self.poo_ts_list)={len(self.poo_ts_list)}  conti_high_c2_density_cnt={self.conti_high_c2_density_cnt}  poo_long={self.poo_long}",1)
        if len(self.poo_ts_list) or self.conti_high_c2_density_cnt or self.poo_long:   # 如果有poo_ts 或 conti_high_c2_density_cnt -> 累積 poo_stft_micData 再用 is_poo_stft 來確認
            # 因為 poo_stft_micData 在poo_stft的時候會被清空, 所以要用 poo_stft_bts 來區隔
            if self.poo_stft_bts is None:
                self.poo_stft_micData = np.r_[self.pre_poo_stft_micData, micDat]
                self.poo_stft_bts = self.ti_micDat - self.proc_len_sec
                #self.aMsg(f"a new poo_stft_bts={self.poo_stft_bts:.3f}sec")
            else:
                self.poo_stft_micData = np.r_[self.poo_stft_micData, micDat]
            #self.aMsg(f"poo_stft_micData long={len(self.poo_stft_micData)/self.micsr:.3f}sec={len(self.poo_stft_micData)/micDat.size:.0f}segs",1)
            # 4 poo pks or 連續兩段(=0.128sec)以上的high_c2_density or 上一段poo_stft有找到但還不夠長
            if (len(self.poo_ts_list) >= poo_ts_cnt_LL or self.conti_high_c2_density_cnt > 1 or self.poo_long):
                if self.is_poo_stft():
                    self.last_poo_ts = self.ti
                    return True
                return False
        else:   # 先從poo_ts_list來篩選，降低poo_stft的資源(但不知道有沒有意義)
            self.reset(closePoo=True)
            #self.aMsg(f"clear poo_stft_micData/poo_stft_bts due to no poo_ts_list nor conti_high_c2_density_cnt",1)
            return False
        
    def addData(self, dat):
        ts = dat[0]/self.tsHz
        #updateplt = False   # for debug
        has_poo = False
        procData_hp_main = None
        #debuginfo = ()
        main_dat = dat[1]

        procData_hp_main,_,_,self.zi_main = self.bwfilter(main_dat,
                                                            b_filt=self.b_bw_hp,
                                                            a_filt=self.a_bw_hp,
                                                            zf=self.zi_main)
        
        #self.raw_micDat = np.r_[self.raw_micDat, main_dat]  # debug

        if self.ti is None: # initial
            self.t0 = ts    # for calculate accumulative poo
            self.ti = ts #- self.t0 + self.toffset   #  toffset should be removed when porting to c
        else:
            self.ti = ts - self.step_sec*2 #- self.t0 + self.toffset
        self.ti_micDat = ts
        self.tNow = self.ti + self.proc_len_sec - self.step_sec # for chk if intvl to next > UL

        goChkPoo = self.age < 12 and ts - self.last_poo_ts > 600    # debug時 要取消這個!!!

        #self.msg += (f'\nSearching poo: {self.ti:.3f}~{self.tNow:.3f}sec {self.tNow-self.ti}  goChkPoo?{goChkPoo}\n')
        
        # === for debug + obs
        self.micDat_obs = np.r_[self.micDat_obs, self.lastMainSndData, procData_hp_main[:-2]]

        # class2_lcs,mask_class1,maxsize_main, lc_mi, mask_class0 = (
        class2_lcs,mask_class1,maxsize_main = (
                                            self.findspike(procData_hp_main, goChkPoo))

        # === for debug only
        #self.ts = np.r_[self.ts, np.linspace(self.ti,self.tNow,maxsize_main)]
        # self.class0_lcs = np.r_[self.class0_lcs, np.nonzero(mask_class0)[0]+self.idxi_plt]
        #self.class1_lcs = np.r_[self.class1_lcs, np.nonzero(mask_class1)[0]+self.idxi_plt]
        #self.class2_lcs = np.r_[self.class2_lcs, class2_lcs+self.idxi_plt]

        if goChkPoo:
            has_poo = self.get_poo(main_dat)
            self.pre_poo_stft_micData = main_dat

        # self.idxi_plt += maxsize_main
        # if self.idxi_plt >= self.segEnd_len:    # debug 模擬aws上 結束一個新檔案的情況(每11776筆資料一個檔案)
            # print(f"in alg: self.idxi_plt={self.idxi_plt} >= {self.segEnd_len}")
            # self.poo_lc_pltarr = np.r_[self.poo_lc_pltarr, self.poo_lc_arr] # for debug 因為前面只有把expired的poo_lc_arr放入poo_lc_pltarr
            #mask = self.lc2ts(self.poo_lc_pltarr-self.idxi_plt) > self.ts[0] # for debug
            #self.poo_lc_pltarr = self.poo_lc_pltarr[mask] # for debug
            #self.msg += (f"going to plt:\n"
            #            f"poo_lc_pltarr={self.formatMsg(self.lc2ts(self.poo_lc_pltarr-self.idxi_plt))}\n"
            #            f"poo_lc_arr={self.formatMsg(self.lc2ts(self.poo_lc_arr-self.idxi_plt))}\n"
            #            f"poo_ts_list={self.formatMsg(self.poo_ts_list,'f3')}sec\n")
            #debuginfo = (self.ts.copy(),
            #            self.micDat_obs.copy(),self.raw_micDat.copy(),    # micDat_obs: obs snd; raw_micDat:
            #            self.class0_lcs.copy(), self.class1_lcs.copy(), self.class2_lcs.copy(),  # for debug
            #            self.poo_lc_pltarr.copy(),  # for debug
            #            self.msg,  # for debug
            #            self.c1_density_pltlist.copy(),  # for debug
            #            self.c2_density_pltlist.copy(), # for debug
            #            )
            #self.reset(True,False) ==> 在checkRaw結束一段(約3秒之後)來進行
            #updateplt = True

        # return updateplt, has_poo, debuginfo
        return has_poo
        
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
        # [0,1] 用於窄頻偵測的界線; 2: isVeryLowfreq的分界點; 3:找頻帶時的最強pk頻率上限; 4:頻帶的頻率上限;
        # 5:進入(環境)harmonic偵測的下限; 6:進入(自體)harmonic偵測的下限
        # 7: 要注意是否為從350以上連接過來的(說話)
        # 8: background 分成兩個頻帶來個別計算
        f_lim = [50,400,70,450,850,150,200,350,325]
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
        #zxx_orig = zxx.copy()   # debug
        # backgnd = np.median(zxx,axis=1)
        b0 = np.percentile(zxx[:flc_lim[8]],40,axis=1)   # < 325Hz
        b1 = np.percentile(zxx[flc_lim[8]:],50,axis=1)  # >=325Hz
        backgnd = np.r_[b0,b1]
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

        pk_lvl_LL0 = 0.38
        pk_lvl_LL1 = 0.5

        isHighPitch = False

        for i,tbin in enumerate(zxx.T):
            # band1 = np.sum(tbin[:self.flc_fsum[0]])   # 目前沒用到了
            dens1 = np.count_nonzero(tbin[flc_lim[0]:self.flc_fsum[0]]>=0.45) # 50~400Hz 高於門檻值以上的資料點比例(密度)
            band3 = np.sum(tbin[self.flc_fsum[1]:]) # 800Hz 以上的強度總和
            lc = flc_lim[0] + np.argmax(tbin[flc_lim[0]:])    # 強度最高的 freq lc
            pk_lvl = tbin[lc]

            isMoreThan2 = len(flc_tmp_list) > 2 # 判斷是否有更能相信的"頻率特徵"
            isMoreThan1 = len(flc_tmp_list) > 1 # 判斷是否有更能相信的"頻率特徵"

            # = 還沒有第一個特徵點 or 與前2個特徵點裡的任一點頻率相近(<=3)
            is_conti_freq = not last_pk_lc or abs(last_pk_lc - lc) <= 3 or (len(flc_tmp_list) > 1 and abs(flc_tmp_list[-2]-lc) <= 3)
            is_weak_conti_freq = False
            #tmpMsg = f"{t_stft[i]+t0:.3f}({i})sec:\n"
            #if not is_conti_freq:
            #    tmpMsg += (f"\tnot is_conti_freq: isMoreThan1?{isMoreThan1}  (ignore this)lc/last_pk_lc={lc/last_pk_lc:.3f} within (1.8,2.2)?\n")
            # === 確認是否能接續 last_pk_lc
            # 已經連續4個了 或 高度基本要求(pk_lvl_LL1)
            # 與 last_pk_lvl 或 pk_lvl 相差不大
            isPkChanged = False     # 影響後續 prominent 的判斷門檻是否要放寬
            if not is_conti_freq and isMoreThan1:# or 1.8 < lc/last_pk_lc < 2.2):
                lci = max(0, last_pk_lc-3)
                lcf = min(tbin.size, last_pk_lc+4)
                lc2 = lci + np.argmax(tbin[lci:lcf])  # 考慮會特徵頻率會飄移，所以找附近的最高點
                pk2_lvl = tbin[lc2]
                #tmpMsg += (f"\t\tcheck pk near last_pk: pk:{f_stft[lc2]}(lc2={lc2} > {flc_lim[0]}?)Hz  "
                #           f"lvl={pk2_lvl:.3f} > {pk_lvl_LL1}?  "
                #           f"> last_pk_lvl - 0.15={last_pk_lvl - 0.15:.3f}?  "
                #           f"> pk_lvl - 0.15={pk_lvl - 0.15:.3f}?\n")
                if lc2 >= flc_lim[0] and pk2_lvl > 0.4 and (len(flc_tmp_list) > 3 or pk2_lvl > pk_lvl_LL1):
                    is_weak_conti_freq = True
                    if (pk2_lvl > last_pk_lvl - 0.15 or pk2_lvl > pk_lvl - 0.15):
                        lc = lc2
                        pk_lvl = pk2_lvl
                        is_conti_freq = True
                        isPkChanged = True
                        #tmpMsg += (f"\t\t\tselect last_pk as this pk!\n")

            if lc <= flc_lim[2]:    # 70Hz
                isVeryLowfreq = True    # 判斷是否考慮有些特別的規則
                veryLowFreqCnt += 1
            
            c1 = lc < flc_lim[1]     #  特徵頻率 < 400Hz
            c2 = pk_lvl > pk_lvl_LL0    # 不能太弱
            # === 想要找出 有低頻帶突出 的跡象
            # = pk_lvl門檻：高頻區(>800Hz)不同強度，pk_lvl有不同的門檻 (之前嘗試過用比例，但是可能因為band3的涵蓋範圍較廣，且取log，所以不太合適)
            c2 = c2 and ((band3 <= 12 and pk_lvl > pk_lvl_LL1) or (band3 < 21 and pk_lvl > 1.2) or (is_conti_freq and isMoreThan2))
            # = 密度篩選：密度太高表示很亂，pk高時也允許比較高的密度(也許做該頻段的median去背景也是一個選擇，但這牽涉到變更比較大)
            #  或 密度高 但 band3(800Hz以上)很低
            c2 = (c2
                  and (dens1 < dens_th[2]
                       or (dens1 < dens_th[0] and pk_lvl > 0.7)
                       or (dens1 < dens_th[1] and pk_lvl > 1.2)
                       or pk_lvl > 1.4
                       or (pk_lvl > 0.8 and band3 < 3)))
            #self.aMsg(f"{tmpMsg}"
            #          f"\tpk:{f_stft[lc]}({lc})Hz height={pk_lvl:.3f}   "
            #          f"last_pk lc={last_pk_lc}={f_stft[last_pk_lc]:.1f}Hz lvl={last_pk_lvl:.3f} "
            #          f"is_conti_freq={is_conti_freq}  is_weak_conti_freq={is_weak_conti_freq}  len(flc_tmp_list)={len(flc_tmp_list)}  "
            #          f"self.isLowBand={self.isLowBand}  lowBandCnt={lowBandCnt}  strongLowBandCnt={strongLowBandCnt}  "
            #          f"isStrongLowBand={isStrongLowBand}  isVeryLowfreq={isVeryLowfreq}  veryLowFreqCnt={veryLowFreqCnt}\n"
            #          f"\tdens1={dens1}<{dens_th}?  band3={band3:.2f}  c2={c2}  breakCnt={breakCnt}")

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
                    #self.aMsg(f"tbin[lc-1] > pk_lvl: very low band => ignore!",1)
                else:
                    c30 = isPkChanged or (mi_L <= valy_th[0] and mi_R <= valy_th[0])   # 兩邊 3格內 < pk*0.5 (窄頻)
                    valy_th_c3 = pk_lvl * 0.69 if isPkChanged else valy_th[1]
                    c3 = c30 and (mi_L <= valy_th_c3 or mi_R <= valy_th_c3)    # 至少一邊 3格內 < pk*0.25 (窄頻)
                    # if c3 and pk_lvl < 0.9:     # 太弱的，周遭要有淨空區
                    #     c3 = np.count_nonzero(tbin[lci:lc]<valy_th[1]) >= 2 and np.count_nonzero(tbin[lc+1:lcf]<valy_th[1]) >= 2
                    #     msg = f"is nearby clear?{c3}"
                    # else:
                    #     msg = ''
                    #self.aMsg(f"is prominent?{c3}  both a little sharp?{c30}  "
                    #        f"nearby_lvl_ratio={self.formatMsg(tbin[lci:lcf]/pk_lvl)}  "
                    #        f"mi_L={mi_L:.3f}<={valy_th[1]:.3f}?  mi_R={mi_R:.3f}<={valy_th[1]:.3f}",1)
                    if not c3 and c30 and pk_lvl > 1.3:  # 想針對"有個陡降又遇到緩降"，但目前只是簡單的判斷，所以限定高peak
                        lci = max(0, lc-3)
                        lcf = min(tbin.size, lc+4)
                        c3 = (tbin[lci:lc] <= valy_th[2]).any() or (tbin[lc+1:lcf] <= valy_th[2]).any() # 至少一邊 3格內 < pk*0.3 (窄頻)
                        #self.aMsg(f"sharp then smooth?{c3}  "
                        #        f"nearby_lvl_ratio={self.formatMsg(tbin[lci:lcf]/pk_lvl)}",1)
            if c3 and not c1:
                isHighPitch = True
                c3 = False
                #self.aMsg(f"> 400Hz => c3=False  isHighPitch=True!",1)
            elif c3 and isHighPitch:
                if lc >= flc_lim[7]:
                    c3 = False
                    #self.aMsg(f"isHighPitch and > 350Hz => c3=False",1)
                else:
                    isHighPitch = False
                    #self.aMsg(f"isHighPitch and <= 350Hz => isHighPitch=False",1)
            else:
                isHighPitch = False
                #self.aMsg(f"not narrow band => isHighPitch=False",1)
            
            # 有找到窄頻, 但頻率不連續 且 沒有strongLowBandCnt, 還未累積到3個連續特徵點, last_pk_lvl存在且較弱 --> reset
            if c3 and not is_conti_freq and not strongLowBandCnt and not isMoreThan2 and 0 < last_pk_lvl < 0.9:
                (tlc_tmp_list,flc_tmp_list,last_pk_lc,last_pk_lvl,pk_lvl_list,
                    veryLowFreqCnt,isVeryLowfreq,isContiVeryLowFreq,isStrongLowBand,
                    strongLowBandCnt,lowBandCnt,isMoreThan2,isMoreThan1,breakCnt) = self.reset(closeObsSnd=True)

                #self.aMsg(f"not conti_freq and not strongLowBandCnt, weak last_pk_lvl={last_pk_lvl:.2f} --> reset",1)

            c31 = True
            # == 試著排除環境中的說話(harmonic)
            c4 = self.isHighPk != 2 and c3 and pk_lvl <= 1 and lc > flc_lim[5]  # 連續窄頻, 強度不很強(<=1), 頻率高於150Hz (試著排除環境中的說話(harmonic))
            c5 = c3 and (self.isHighPk == 2 or pk_lvl >= 1.2) and lc > flc_lim[6]    # 連續窄頻, 強度強, 頻率高於200Hz (試著排除自體的說話(harmonic))
            if c4 or c5:
                hamo_th = max(0.4,pk_lvl*0.355) if c4 else pk_lvl*0.5    # 判斷是否有harmonic的 peak 高度門檻
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
                last_pk_hamo_lc = -1
                overCnt = 10
                overCnt_th = 3 #if c4 else 4
                #self.aMsg(f"check if there are harmonic tones   polar={polar}  c31?{c31}  n({n}) < 5?  not overCnt?{not overCnt}",1)
                while c31 and n < 5 and overCnt:    # 最高檢查到4x，避免誤判
                    overCnt = np.count_nonzero(tbin[hlci:hlcf] > hamo_th)
                    c41 = True # 是否為harmonic pk
                    if overCnt == 0:  # 預估倍頻處 ==0: 不夠強
                        c41 = False
                        last_pk_hamo_lc = -1
                    elif overCnt >= overCnt_th:  #  >= overCnt_th:極可能是一段寬頻(可能是其他聲音干擾) => 可能不是倍頻
                        tmplc = np.argmax(tbin[hlci:hlcf])
                        if last_pk_hamo_lc > 0 and abs(tmplc-last_pk_hamo_lc) >= 3: # 若pk頻率不是連續的
                            c41 = False
                        last_pk_hamo_lc = tmplc

                    #tmpMsg = (f"{n}x tone({f_stft[hlci:hlcf]}Hz) height={self.formatMsg(tbin[hlci:hlcf],'f2')}="
                    #        f"{self.formatMsg(tbin[hlci:hlcf]/pk_lvl,'f2')}X  "
                    #        f"<= {hamo_th/pk_lvl:.3f}?{c41}  overCnt={overCnt}  last_pk_hamo_lc={last_pk_hamo_lc}  ")
                    n += 1
                    hlci = lc*n - 1 if polar >= 0 else lc*n + polar*n
                    hlcf = lc*n + 2 if polar < 0 else lc*n + polar*n + 1
                    hCnt += 1 if c41 else 0
                    c3 = c31 = hCnt < 2
                    #self.aMsg(f"{tmpMsg}hCnt={hCnt}",2)
                    hamo_th *= 0.9 if c5 else 1
            #self.aMsg(f"continuous and not harmonic?{c3}  lowBandCnt({lowBandCnt}) < {len(flc_tmp_list)/2}?",1)
            if c3 and lowBandCnt < len(flc_tmp_list)/2 :    # lowBandCnt佔不到時間長度一半 但偵測到連續窄頻且非明顯harmonic, 就清除lowBandCnt
                self.isLowBand = False
                isStrongLowBand = False
                strongLowBandCnt = 0
                lowBandCnt = 0
                #self.aMsg(f"reset isLowBand / isStrongLowBand / strongLowBandCnt / lowBandCnt",2)

            c5 = False
            # === 非連續窄頻 或 已經有lowBandCnt and strongLowBandCnt, 最強頻率 < 450Hz
            c50 = not isHighPitch and c2 and (not c3 or not isMoreThan1 or (lowBandCnt and strongLowBandCnt)) and lc < flc_lim[3]
            # # = pk_lvl夠高(>=0.9), 且 (只有2個以下連續特徵點(還不很確定) 或 有連續頻率)
            # c51 = c50 and pk_lvl >= 0.9 and (not isMoreThan2 or is_conti_freq or abs(last_pk_lc - lc) <= 5)
            # # = 適用於最強頻率切換時，考慮last_pk_lc是否有夠高(c30=有基本強度(>0.8), 已連續2個以上的特徵點, 與last_pk_lvl差不多高(>=0.68X)) 
            # c52 = not c51 and c50 and c30
            #self.aMsg(f"go to low band detection?  c50={c50}",1)
            if c50:
                # === 找頻帶範圍
                band_range = []
                thcnt = 0
                band_width = 0
                band_sum = 0
                for idx,lvl in enumerate(tbin):
                    if lvl > 0.38 and thcnt < 3:    # 還沒有起點, 強度超過門檻(0.38), cnt還沒到上限(3)
                        thcnt += 1
                        if not len(band_range) and thcnt == 3:  # 還沒有起點 
                            band_range.append(idx-2)
                            band_sum += lvl
                    elif lvl <= 0.38 and thcnt > 0:    # 強度低過門檻(0.38), cnt還沒到0
                        thcnt -= 1
                        if len(band_range) and not thcnt:   # 有起點了, 歸零了, 頻帶結束
                            band_range.append(idx-2)
                            band_width = band_range[1]-band_range[0]
                            band_sum += lvl
                            break
                    if len(band_range):
                        band_sum += lvl
                #if band_range:
                    #msg = (f"band_width={band_width*fstep:.1f}Hz={band_width} within {band_width_lim}?  "
                    #        f"band_range={band_range}={f_stft[band_range]}Hz < {flc_lim[4]}({f_lim[4]})  "
                    #        f"avg_lvl={band_sum/len(band_range):.1f}")
                #else:
                #    msg = ''
                # === 200 <= band_width_Hz <= 650,  < 850Hz
                c5 = len(band_range) and band_width_lim[0] <= band_width <= band_width_lim[1] and band_range[1] < flc_lim[4]
                strongLowBandCnt += 1 if c5 and band_sum/len(band_range) > 1 else 0
                lowBandCnt += 1 if c5 else 0
                self.isLowBand = lowBandCnt > 2
                #self.aMsg(f"c5={c5}  isLowBand={self.isLowBand}  lowBandCnt={lowBandCnt}  strongLowBandCnt={strongLowBandCnt}  "
                #        f"band_range={self.formatMsg(f_stft[band_range],'f1')}Hz  {msg}",1)
                            
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
                #self.aMsg(f"append to tmp_list(len={len(flc_tmp_list)}) and update last_pk, isHighPk={self.isHighPk}  "
                #            f"isContiVeryLowFreq={isContiVeryLowFreq}(veryLowFreqCnt={veryLowFreqCnt})  "
                #            f"isStrongLowBand={isStrongLowBand}(strongLowBandCnt={strongLowBandCnt})",1)
            # === 特徵沒有連續出現了
            elif len(tlc_tmp_list) > 5 and not self.isHighPk and not self.isLowBand:  # 弱窄頻(pk_lvl_avg<=0.9), 要連續6個以上, 如果是極低頻(<70Hz)站了一半以上, 要連續7個
                if (isContiVeryLowFreq and len(tlc_tmp_list) > 6) or not isContiVeryLowFreq :
                    tlc_list.extend(tlc_tmp_list)
                    flc_list.extend(flc_tmp_list)

                (tlc_tmp_list,flc_tmp_list,last_pk_lc,last_pk_lvl,pk_lvl_list,
                    veryLowFreqCnt,isVeryLowfreq,isContiVeryLowFreq,isStrongLowBand,
                    strongLowBandCnt,lowBandCnt,isMoreThan2,isMoreThan1,breakCnt) = self.reset(closeObsSnd=True)

                #self.aMsg(f"found week narrow band and reset last_pk and isHighPk",1)
            elif len(tlc_tmp_list) > 4 and self.isHighPk == 1 and not self.isLowBand:  # 微強窄頻(0.9<pk_lvl_avg<=1), 要連續5個以上; 如果是極低頻(<70Hz)站了一半以上, 要連續6個
                if (isContiVeryLowFreq and len(tlc_tmp_list) > 5) or not isContiVeryLowFreq :
                    tlc_list.extend(tlc_tmp_list)
                    flc_list.extend(flc_tmp_list)

                (tlc_tmp_list,flc_tmp_list,last_pk_lc,last_pk_lvl,pk_lvl_list,
                    veryLowFreqCnt,isVeryLowfreq,isContiVeryLowFreq,isStrongLowBand,
                    strongLowBandCnt,lowBandCnt,isMoreThan2,isMoreThan1,breakCnt) = self.reset(closeObsSnd=True)

                #self.aMsg(f"found a little strong narrow band and reset last_pk and isHighPk",1)
            elif len(tlc_tmp_list) > 3 and self.isHighPk == 2 and not self.isLowBand:  # 強窄頻(pk_lvl_avg>1), 要連續4個以上; 如果是極低頻(<70Hz)站了一半以上, 要連續5個
                if (isContiVeryLowFreq and len(tlc_tmp_list) > 4) or not isContiVeryLowFreq :
                    tlc_list.extend(tlc_tmp_list)
                    flc_list.extend(flc_tmp_list)

                (tlc_tmp_list,flc_tmp_list,last_pk_lc,last_pk_lvl,pk_lvl_list,
                    veryLowFreqCnt,isVeryLowfreq,isContiVeryLowFreq,isStrongLowBand,
                    strongLowBandCnt,lowBandCnt,isMoreThan2,isMoreThan1,breakCnt) = self.reset(closeObsSnd=True)

                #self.aMsg(f"found strong narrow band and reset last_pk and isHighPk",1)
            elif len(tlc_tmp_list) > 3 and self.isLowBand:  # 強低頻帶, 要連續4個以上; 弱低頻帶, 要連續5個以上
                if isStrongLowBand or (not isStrongLowBand and len(flc_tmp_list) > 4):
                    tlc_list.extend(tlc_tmp_list)
                    flc_list.extend(flc_tmp_list)

                (tlc_tmp_list,flc_tmp_list,last_pk_lc,last_pk_lvl,pk_lvl_list,
                    veryLowFreqCnt,isVeryLowfreq,isContiVeryLowFreq,isStrongLowBand,
                    strongLowBandCnt,lowBandCnt,isMoreThan2,isMoreThan1,breakCnt) = self.reset(closeObsSnd=True)
                
                #self.aMsg(f"found strong low-freq band and reset last_pk, isHighPk and isStrongLowBand",1)
            elif ((is_weak_conti_freq and isMoreThan2) or (is_conti_freq and isMoreThan1)) and breakCnt < 2:
                breakCnt += 1
                #self.aMsg(f"not found obstruction sound but ((is_weak_conti_freq and isMoreThan2) or (is_conti_freq and isMoreThan1)) and breakCnt < 2",1)
            else:
                (tlc_tmp_list,flc_tmp_list,last_pk_lc,last_pk_lvl,pk_lvl_list,
                    veryLowFreqCnt,isVeryLowfreq,isContiVeryLowFreq,isStrongLowBand,
                    strongLowBandCnt,lowBandCnt,isMoreThan2,isMoreThan1,breakCnt) = self.reset(closeObsSnd=True)

                #self.aMsg(f"not found obstruction sound and reset last_pk and isHighPk",1)

        if len(tlc_tmp_list):   # 一直延伸到檔案結尾 還沒有結案的
            c0 = len(tlc_tmp_list) >= 5 and not self.isHighPk and not self.isLowBand  # 弱窄頻, 要連續6個以上
            c1 = len(tlc_tmp_list) > 2 and self.isHighPk == 2 and not self.isLowBand  # 強窄頻, 要連續3個以上
            c2 = len(tlc_tmp_list) > 3 and self.isLowBand  # 強低頻帶, 要連續4個以上
            c3 = len(tlc_tmp_list) >= 4 and self.isHighPk == 1 and not self.isLowBand
            c4 = len(tlc_tmp_list) >= 3 and self.isHighPk == 2 and not self.isLowBand
            if c0 or c1 or c2 or c3 or c4:
                tlc_list.extend(tlc_tmp_list)
                flc_list.extend(flc_tmp_list)
            #self.aMsg(f"till end: {c0} {c1} {c2} {c3} {c4}")

        return f_stft,t_stft,zxx,tlc_list,flc_list,backgnd,zxx_orig    # for debug plt
        # return len(flc_list)    # for AWS, 0: no obstruction sound;  >1: found obstruction sound


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

def checkRaw(ba, udid, t0, age):
    sig_cnt=len(ba)//2
    sig=struct.unpack('<'+'h'*sig_cnt,ba)

    pkglen=64
    pkg_num=4
    detectOdd = Detector(udid, t0, age) # udid:為了能接續同一段stream的演算法參數, t0:用來判斷是否是同一段stream,  age:目前用在是否要進行poo

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

        has_poo = detectOdd.addData(pkg)

        # if updateplt:   # 相當於3sec  for debug   因為每一段進來的都約3秒，不需要這段來進入has_obs，在讀完整段之後進行has_obs即可
        #     (ts,main_dat,class0_lcs,class1_lcs,class2_lcs,poo_lc_arr,
        #             # absnd_timeslot_pltlist,
        #             msg,
        #             lcC1_density_list,  #high_c1_density_cnt_pltlist,
        #             # unstable_timeslot_pltlist,
        #             c2_density_pltlist) = debuginfo
                    
            # has_obs= detectOdd.has_obs(main_dat, ts[0])    # debug
        if has_poo:
            break

    if len(detectOdd.micDat_obs):
        main_dat = detectOdd.micDat_obs.copy()
    detectOdd.reset(True,False)
    
    if not has_poo and not detectOdd.has_high_c1_density and main_dat is not None:     # for AWS
        has_obs = detectOdd.has_obs(main_dat, ts)
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

    
