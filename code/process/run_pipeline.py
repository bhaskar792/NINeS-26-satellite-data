from satellite_matching import *
import pickle
from datetime import datetime, timedelta
from pytz import timezone

from config import DATA_PATH

est = timezone('US/Eastern')


if __name__ == '__main__':
    abs_start_date = datetime(2025, 2, 14, 0, 0, 0, 0, est)
    abs_end_date = datetime(2025, 2, 18, 23, 59, 59, 0, est)
    day_num = (abs_end_date - abs_start_date).days

    for i in range(0, day_num + 1):
        print('-----------------------------------------------------')
        start_date = abs_start_date + timedelta(days=i)
        end_date = start_date + timedelta(days=1) - timedelta(seconds=1)
        print(start_date, end_date)

        rst_obsmap_dict = get_rst_obsmap_dict(start_date, end_date)
        pi_coord_dict = get_pi_coord_dict(rst_obsmap_dict)

        az_pd = read_processed_tle_df(start_date, end_date)
        all_sat_pc = get_sat_pc_dict_multi(az_pd, pi_coord_dict)

        pi_sat_match, pi_sat_error = match_satellite_multi(all_sat_pc, pi_coord_dict, 1)
        columns = ['date', 'pi1_sat', 'pi2_sat', 'pi1_min_ele', 'pi1_max_ele', 'pi1_min_az',
                   'pi1_max_az', 'pi2_min_ele', 'pi2_max_ele', 'pi2_min_az', 'pi2_max_az',
                   'pi1_az_ele', 'pi2_az_ele']
        sat_df = pd.DataFrame(columns=columns)
        all_sat_dates = pi_sat_match['pi1'].keys()

        for d in all_sat_dates:
            pi1_sat = list(pi_sat_match['pi1'][d].keys())[0]
            pi2_sat = list(pi_sat_match['pi2'][d].keys())[0]

            pi1_min_ele = min([pi_sat_match['pi1'][d][pi1_sat][i][0] for i in range(len(pi_sat_match['pi1'][d][pi1_sat]))])
            pi1_max_ele = max([pi_sat_match['pi1'][d][pi1_sat][i][0] for i in range(len(pi_sat_match['pi1'][d][pi1_sat]))])
            pi1_min_az  = min([pi_sat_match['pi1'][d][pi1_sat][i][1] for i in range(len(pi_sat_match['pi1'][d][pi1_sat]))])
            pi1_max_az  = max([pi_sat_match['pi1'][d][pi1_sat][i][1] for i in range(len(pi_sat_match['pi1'][d][pi1_sat]))])
            pi2_min_ele = min([pi_sat_match['pi2'][d][pi2_sat][i][0] for i in range(len(pi_sat_match['pi2'][d][pi2_sat]))])
            pi2_max_ele = max([pi_sat_match['pi2'][d][pi2_sat][i][0] for i in range(len(pi_sat_match['pi2'][d][pi2_sat]))])
            pi2_min_az  = min([pi_sat_match['pi2'][d][pi2_sat][i][1] for i in range(len(pi_sat_match['pi2'][d][pi2_sat]))])
            pi2_max_az  = max([pi_sat_match['pi2'][d][pi2_sat][i][1] for i in range(len(pi_sat_match['pi2'][d][pi2_sat]))])
            pi1_az_ele = pi_sat_match['pi1'][d][pi1_sat]
            pi2_az_ele = pi_sat_match['pi2'][d][pi2_sat]

            new_df = pd.DataFrame([[d, pi1_sat, pi2_sat, pi1_min_ele, pi1_max_ele, pi1_min_az,
                                    pi1_max_az, pi2_min_ele, pi2_max_ele, pi2_min_az, pi2_max_az,
                                    pi1_az_ele, pi2_az_ele]], columns=columns)
            sat_df = pd.concat([sat_df, new_df])

        file_path = f'{DATA_PATH}/sat_match/'
        start_date_file = start_date.strftime('%Y_%m_%d')
        print('saving to ' + file_path + start_date_file + '_sat_match.csv')
        sat_df.to_csv(file_path + start_date_file + '_sat_match.csv', index=False)
        with open(f'{DATA_PATH}/sat_match/{start_date_file}_all_sat_pc.pkl', 'wb') as f:
            pickle.dump(all_sat_pc, f)
