SYS_INFO_BAT_STATE_NO_WPOWER_HIGH_BAT  =0
SYS_INFO_BAT_STATE_NO_WPOWER_MED_BAT  =1
SYS_INFO_BAT_STATE_NO_WPOWER_LOW_BAT  =2
SYS_INFO_BAT_STATE_NO_WPOWER_BAT_ALARM  =3
SYS_INFO_BAT_STATE_WPOWER_CHARGE_DONE  =4
SYS_INFO_BAT_STATE_WPOWER_CHARGING  =5
SYS_INFO_BAT_STATE_WPOWER_BAT_FAIL  =6
SYS_INFO_BAT_STATE_WPOWER_LOW_CURR_ALARM  =7

int_to_bat_status_map={
    0:'HIGH BATTERY LEVEL',
    1:'MED BATTERY LEVEL',
    2:'LOW BATTERY LEVEL',
    3:'LOW BATTERY ALARM',
    4:'CHARGE DONE',
    5:'CHARGING',
    6:'BATTERY FAIL',
    7:'LOW CHARGE CURRENT'}

int_to_att_map={}
int_to_pose_map={}
int_to_status_map={}
int_to_act_map={}

int_to_att_map[0]='unattached'
int_to_att_map[1]='attached'
int_to_att_map[2]='well_attached'

int_to_pose_map[0]='None'
int_to_pose_map[1]='sit'
int_to_pose_map[2]='side_right'
int_to_pose_map[3]='side_left'
int_to_pose_map[4]='back'
int_to_pose_map[5]='stomach'

int_to_status_map[0]='None'
int_to_status_map[1]='sleep'
int_to_status_map[2]='calm'
int_to_status_map[3]='motion'
int_to_status_map[4]='shock_or_fall'
int_to_status_map[5]='rest_on_stomach'

int_to_act_map[0]='None'
int_to_act_map[1]='shock_like'
int_to_act_map[2]='shock'
int_to_act_map[3]='large_motion'
int_to_act_map[4]='gentle_motion'