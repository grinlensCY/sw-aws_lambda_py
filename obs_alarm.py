import numpy as np
import json
import cache_util as CU

class ObsAlarm():
    def __init__(self, udid, ver=20230118):
        self.ver = ver
        
        # === default
        '''
        self.init_vars = {
            'obs_ts_list':[],
            'obs_res_list': []
        }
        '''
        #self.reset(udid)

    def load_context(self,udid):
        var_key=CU.OBS_VAR_KEY_HEADER+udid
        res=CU.get_cache_data(var_key)
        if(res==None):
            res = {}
        if 'obs_ts_list' not in res:
            res['obs_ts_list']=[]
        if 'obs_res_list' not in res:
            res['obs_res_list']=[]
        return res
        
        #with open(f"obsalarm_{udid}.json", 'r', newline='') as jf:
        #    return json.loads(jf.read())

    def save_context(self, udid, vars={}):
        var_key=CU.OBS_VAR_KEY_HEADER+udid
        res=CU.set_cache_data(var_key,vars,86400)#資料中斷超過一天就沒意義
        
        #with open(f"obsalarm_{udid}.json", 'w', newline='') as jout:
        #    json.dump(vars, jout, ensure_ascii=False)
    
    #def reset(self,udid):
    #    with open(f"obsalarm_{udid}.json", 'w', newline='') as jout:
    #        json.dump(self.init_vars, jout, ensure_ascii=False)
        
    def addData(self,udid,ts,has_obs):
        vars = self.load_context(udid)  # 用於AWS
        
        obs_ts_arr = np.array(vars['obs_ts_list'])
        obs_res_arr = np.array(vars['obs_res_list'])
        mask = obs_ts_arr > ts - 180    # 保留3分鐘內的
        obs_ts_arr = np.r_[obs_ts_arr[mask], ts]
        obs_res_arr = np.r_[obs_res_arr[mask], has_obs]

        alarm = obs_ts_arr.size >= 15 and ts-obs_res_arr[0] >= 115 and np.count_nonzero(obs_res_arr)/obs_res_arr.size > 0.66

        vars = {'obs_ts_list': obs_ts_arr.tolist(),
                'obs_res_list': obs_res_arr.tolist()}
        self.save_context(udid,vars)      # 用於AWS
        return alarm     # 用於AWS
