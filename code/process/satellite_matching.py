import numpy as np
import matplotlib.pyplot as plt
import glob
import json
from dateutil import parser
from pytz import utc
import pandas as pd
from datetime import datetime
from pytz import timezone
from datetime import timedelta
import cv2
from PIL import Image, ImageChops
from scipy.ndimage import generic_filter
from skimage.morphology import medial_axis
import math
from math import atan2
import multiprocessing
from multiprocessing import Pool, shared_memory
import numpy as np
from datetime import timedelta
import pytz
import time

import scipy

from multiprocessing import Pool, cpu_count

from scipy.stats import ks_2samp
from scipy import stats
from tqdm import tqdm
import os
from collections import defaultdict
from matching_utils import *

from config import DATA_PATH

PATH = f"{DATA_PATH}/obs_data/perf_starlink/"
stat_file_path = PATH
est = timezone('US/Eastern')


def check_dates(filename, start_date, end_date, type='obs_stats'):
    if start_date.tzinfo is None or start_date.tzinfo.utcoffset(start_date) is None:
        start_date = est.localize(start_date)
    if end_date.tzinfo is None or end_date.tzinfo.utcoffset(end_date) is None:
        end_date = est.localize(end_date)
    if type == 'obs_stats':
        date_str = ' '.join(filename.split('/')[-1].split('_')[2:])
        date_str = date_str.split('.json')[0]
        in_date = parser.parse(date_str)
        in_date = est.localize(in_date)
        if in_date < start_date or in_date > end_date:
            return False
        return True
    elif type == 'obs_map':
        curr_date = est.localize(parser.parse(' '.join(filename.split('/')[-1].split('_')[2:]).split('.')[0]))
        if curr_date < start_date or curr_date > end_date:
            return False
        return True
    elif type == 'tle':
        date = filename.split('/')[-1].split('_')[-1].split('.')[0]
        date = parser.parse(date)
        date = est.localize(date)
        date = date.date()
        start_date = start_date.date()
        end_date = end_date.date()
        if date < start_date or date > end_date:
            return False
        return True


def get_rst_obsmap_dict(start_date, end_date):
    rst_obsmap_dict = {}
    error_files = []
    for p in ['pi1', 'pi2']:
        rst_obsmap_dict[p] = {}
        obs_image_dir = stat_file_path + p + '/obs_maps_rst/'
        obs_image_files = glob.glob(obs_image_dir + '*.png')
        valid_obs_image_files = []
        for files in obs_image_files:
            if check_dates(files, start_date, end_date, type='obs_map'):
                valid_obs_image_files.append(files)
        obs_image_files = valid_obs_image_files
        f_conv = obs_image_dir + 'converted/'
        if not os.path.exists(f_conv):
            os.makedirs(f_conv)
        total_files = 0
        for obs_image in sorted(obs_image_files):
            total_files += 1
            try:
                im = cv2.imread(obs_image, -1)
                im[np.where(im[:, :, 3] == 0)] = (0, 0, 0, 255)
                f_name = obs_image.split('/')[-1]
                cv2.imwrite(f_conv + f_name, im)
            except:
                error_files.append(obs_image)
                continue
        obs_converted_files = sorted(glob.glob(f_conv + '/*.png'))
        valid_files = []
        for files in obs_converted_files:
            if check_dates(files, start_date, end_date, type='obs_map'):
                valid_files.append(files)
        obs_converted_files = valid_files
        error_files = []
        for im_file in obs_converted_files:
            try:
                curr_date = est.localize(parser.parse(' '.join(im_file.split('/')[-1].split('_')[2:]).split('.')[0]))
                rst_obsmap_dict[p][curr_date] = im_file
            except:
                error_files.append(im_file)
                print(im_file)
    return rst_obsmap_dict


def get_pi_coord_dict(rst_obsmap_dict):
    r_pi1 = rst_obsmap_dict['pi1']
    r_pi2 = rst_obsmap_dict['pi2']
    all_obs_dates = set(list(rst_obsmap_dict['pi1']) + list(rst_obsmap_dict['pi2']))
    cf = 1.33333
    count = 0

    pi_coord_dict = {}
    pi_coord_dict['pi1'] = {}
    pi_coord_dict['pi2'] = {}
    missing_dates = []
    print('processing obs images to get polar coordinates')
    for d in tqdm(all_obs_dates):
        if (d in r_pi1) and (d in r_pi2):
            curr_image_pi1 = cv2.imread(r_pi1[d], cv2.IMREAD_GRAYSCALE)
            curr_image_pi2 = cv2.imread(r_pi2[d], cv2.IMREAD_GRAYSCALE)
            prev_d = d - timedelta(seconds=15)

            if prev_d in r_pi1:
                prev_image = cv2.imread(r_pi1[prev_d], cv2.IMREAD_GRAYSCALE)
                xor_image_pi1 = cv2.bitwise_xor(curr_image_pi1, prev_image)
                curr_image_pi1 = cv2.bitwise_and(xor_image_pi1, curr_image_pi1)
            if prev_d in r_pi2:
                prev_image = cv2.imread(r_pi2[prev_d], cv2.IMREAD_GRAYSCALE)
                xor_image_pi2 = cv2.bitwise_xor(curr_image_pi2, prev_image)
                curr_image_pi2 = cv2.bitwise_and(xor_image_pi2, curr_image_pi2)
            rm_pi1 = Image.fromarray(curr_image_pi1)
            rm_pi2 = Image.fromarray(curr_image_pi2)

            try:
                m_pi1_pixels = find_longest_contiguous_non_black(rm_pi1)
                m_pi2_pixels = find_longest_contiguous_non_black(rm_pi2)
            except:
                continue

            if len(m_pi1_pixels) >= 8 and len(m_pi2_pixels) >= 8:
                cpx = 62
                cpy = 62

                pi1_pos = []
                pi2_pos = []

                for p in m_pi1_pixels:
                    c_ele = calculate_radius((cpx, cpy), (p[1], p[0]))
                    c_az = calculate_clockwise(p, cpx, cpy)
                    pi1_pos.append((c_ele, c_az))

                pi1_pos = sorted(pi1_pos, key=lambda x: x[1])

                for p in m_pi2_pixels:
                    c_ele = calculate_radius((cpx, cpy), (p[1], p[0]))
                    c_az = calculate_clockwise(p, cpx, cpy)
                    pi2_pos.append((c_ele, c_az))

                pi2_pos = sorted(pi2_pos, key=lambda x: x[1])

                pi_coord_dict['pi1'][d] = pi1_pos
                pi_coord_dict['pi2'][d] = pi2_pos

                count += 1
    return pi_coord_dict


def read_tle_df(start_date, end_date):
    pd_tups = list()
    processed_tle = f"{DATA_PATH}/processed_tle/"
    tle_file_path = processed_tle
    print(f'reading processed tle data from {tle_file_path}*')
    current_tle_files = glob.glob(f'{tle_file_path}*')
    for current_tle in tqdm(current_tle_files):
        date = current_tle.split('/')[-1].split('_')[-1].split('.')[0]
        date = parser.parse(date)
        if date < start_date or date > end_date:
            continue

        print(current_tle)
        sat_json = read_sat_json(current_tle, 'sats')
        for t in sat_json:
            curr_dict = sat_json[t]
            for sat in curr_dict:
                tup = (t, sat[0], sat[1], sat[2], (np.pi/180)*sat[2])
                pd_tups.append(tup)

    az_pd = pd.DataFrame(pd_tups, columns=['c_time', 'sat', 'aoe', 'az', 'az_rad'])
    az_pd = az_pd.sort_values(by='c_time')
    return az_pd

def read_processed_tle_df(start_date, end_date):
    pd_tups = list()
    processed_tle_pd = f"{DATA_PATH}/processed_tle_pd/"
    current_tle_files = glob.glob(f'{processed_tle_pd}*')
    valid_tle_files = []
    for files in current_tle_files:
        if check_dates(files, start_date, end_date, type='tle'):
            valid_tle_files.append(files)
    current_tle_files = valid_tle_files
    print(current_tle_files)
    for current_tle in tqdm(current_tle_files):
        az_pd_csv = pd.read_csv(current_tle)
        pd_tups.extend(az_pd_csv.values.tolist())
    az_pd = pd.DataFrame(pd_tups, columns=['c_time', 'sat', 'aoe', 'az', 'az_rad'])
    az_pd = az_pd.sort_values(by='c_time')
    return az_pd


def split_list(lst, n):
    k, m = divmod(len(lst), n)
    return [lst[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n)]

def process_chunk_pc(chunk, shared_mem_name, shape, dtype):
    existing_shm = shared_memory.SharedMemory(name=shared_mem_name)
    az_pd_np = np.ndarray(shape, dtype=dtype, buffer=existing_shm.buf)

    all_sat_pc = {}
    for d in chunk:
        all_sat_pc[d] = {}
        s_t, e_t = d - timedelta(seconds=14), d + timedelta(seconds=0)
        e_t_index = np.searchsorted(az_pd_np[:, 0], e_t, side='right')
        s_t_index = np.searchsorted(az_pd_np[:, 0], s_t, side='left')

        curr_pd_np = az_pd_np[s_t_index:e_t_index]
        if curr_pd_np.size == 0:
            continue

        sats, indices, counts = np.unique(curr_pd_np[:, 1], return_index=True, return_counts=True)
        avail_15_sats = sats[counts >= 14]
        for sat in avail_15_sats:
            sat_mask = curr_pd_np[:, 1] == sat
            cpd = curr_pd_np[sat_mask]
            cpd = cpd[np.argsort(cpd[:, 2])]
            sat_polar = list(zip(cpd[:, 2], cpd[:, 3]))
            all_sat_pc[d][sat] = sat_polar

    existing_shm.close()
    return all_sat_pc

def get_sat_pc_dict_multi(az_pd, pi_coord_dict):
    all_sat_pc = {}

    az_pd['c_time'] = pd.to_datetime(az_pd['c_time'])
    az_pd = az_pd.sort_values(by='c_time')
    az_pd_np = az_pd[['c_time', 'sat', 'aoe', 'az']].to_numpy()

    shape = az_pd_np.shape
    dtype = az_pd_np.dtype

    shm = shared_memory.SharedMemory(create=True, size=az_pd_np.nbytes)
    shared_array = np.ndarray(shape, dtype=dtype, buffer=shm.buf)
    shared_array[:] = az_pd_np[:]

    pi1_coord_dict = pi_coord_dict['pi1']
    num_chunks = min(multiprocessing.cpu_count() // 2, len(pi1_coord_dict.keys()))
    chunks = split_list(list(pi1_coord_dict.keys()), num_chunks)
    with Pool(processes=num_chunks) as pool:
        results = pool.starmap(process_chunk_pc, [(chunk, shm.name, shape, dtype) for chunk in chunks])

    for result in results:
        all_sat_pc.update(result)

    shm.close()
    shm.unlink()

    return all_sat_pc


def match_satellite_multi(all_sat_pc, pi_coord_dict, k=2):
    dates = list(pi_coord_dict['pi1'].keys())
    num_chunks = min(120, len(dates))
    chunks = [dates[i::num_chunks] for i in range(num_chunks)]

    for i in tqdm(range(num_chunks)):
        pi_coord_dict_chunk = {}
        all_sat_pc_chunk = {}
        for pi in pi_coord_dict:
            pi_coord_dict_chunk[pi] = {d: pi_coord_dict[pi][d] for d in chunks[i]}
        all_sat_pc_chunk = {d: all_sat_pc[d] for d in chunks[i]}
        chunks[i] = (chunks[i], pi_coord_dict_chunk, all_sat_pc_chunk, k)

    with Pool(processes=num_chunks) as pool:
        results = pool.starmap(
            process_chunk_sat,
            chunks
        )

    pi_sat_match = {'pi1': {}, 'pi2': {}}
    pi_sat_error = {'pi1': {}, 'pi2': {}}

    for local_pi_sat_match, local_pi_sat_error in results:
        for pi_key in ['pi1', 'pi2']:
            pi_sat_match[pi_key].update(local_pi_sat_match[pi_key])
            pi_sat_error[pi_key].update(local_pi_sat_error[pi_key])

    same_sat = []
    diff_sat = []
    pi1_match_avg_error = []
    pi2_match_avg_error = []
    pi1_nomatch_avg_error = []
    pi2_nomatch_avg_error = []

    for d in pi_sat_match['pi1']:
        if pi_sat_match['pi1'][d].keys() == pi_sat_match['pi2'][d].keys():
            same_sat.append(d)
            pi1_match_avg_error.append(pi_sat_error['pi1'][d][list(pi_sat_match['pi1'][d].keys())[0]])
            pi2_match_avg_error.append(pi_sat_error['pi2'][d][list(pi_sat_match['pi2'][d].keys())[0]])
        else:
            diff_sat.append(d)
            pi1_nomatch_avg_error.append(pi_sat_error['pi1'][d][list(pi_sat_match['pi1'][d].keys())[0]])
            pi2_nomatch_avg_error.append(pi_sat_error['pi2'][d][list(pi_sat_match['pi2'][d].keys())[0]])
    print("Total instances, instances with different satellites, same sat percentage", len(pi_sat_match['pi1']), len(diff_sat), (len(same_sat)/len(pi_sat_match['pi1'])))

    return pi_sat_match, pi_sat_error


def process_chunk_sat(dates_chunk, pi_coord_dict, all_sat_pc, k=2):
    local_pi_sat_match = {'pi1': {}, 'pi2': {}}
    local_pi_sat_error = {'pi1': {}, 'pi2': {}}

    error_dates = []
    for d in dates_chunk:
        pi1_cd = pi_coord_dict['pi1'][d]
        pi2_cd = pi_coord_dict['pi2'][d]
        sat_coords = all_sat_pc[d]
        if len(sat_coords) == 0:
            error_dates.append(d)
            continue

        pi1_sat_top_k, pi1_sc_top_k, pi1_error_top_k = match_top_k_sat(pi1_cd, sat_coords, k)
        pi2_sat_top_k, pi2_sc_top_k, pi2_error_top_k = match_top_k_sat(pi2_cd, sat_coords, k)
        pi1_sat, pi2_sat, pi1_sc, pi2_sc, pi1_error, pi2_error = get_single_sat_from_top_k(pi1_sat_top_k, pi2_sat_top_k, pi1_sc_top_k, pi2_sc_top_k, pi1_error_top_k, pi2_error_top_k)

        local_pi_sat_match['pi1'][d] = {pi1_sat: pi1_sc}
        local_pi_sat_match['pi2'][d] = {pi2_sat: pi2_sc}
        local_pi_sat_error['pi1'][d] = {pi1_sat: pi1_error}
        local_pi_sat_error['pi2'][d] = {pi2_sat: pi2_error}
    if error_dates:
        print(f"number of missing satellite data chunks: {len(error_dates)}")
        print(f"missing date ex: {error_dates[0]}")

    return local_pi_sat_match, local_pi_sat_error


def match_trajectories(pi_coord_dict, threshold=[1.6]):
    pi_error = defaultdict(lambda: defaultdict(str))
    for d in tqdm(pi_coord_dict['pi1']):
        pi1_cd = pi_coord_dict['pi1'][d]
        pi2_cd = pi_coord_dict['pi2'][d]

        pi_error['default'][d] = calculate_dtw_error(pi1_cd, pi2_cd)
        pi_error['max75'][d] = max75_normalize(pi1_cd, pi2_cd)
        pi_error['max90'][d] = max90_normalize(pi1_cd, pi2_cd)
        pi_error['cos_normalize'][d] = cos_normalize(pi1_cd, pi2_cd)

    vals = threshold
    for key in pi_error.keys():
        for val in vals:
            print(key, val, len([e for e in pi_error[key].values() if e < val])/len(pi_error[key]))
    return pi_error
