import glob
import os
import json
import pandas as pd
from tqdm import tqdm
from datetime import datetime, timedelta
import pytz
from pytz import timezone
import pickle
import re
import cv2
import numpy as np
from PIL import Image
from typing import Dict, List

from satellite_matching import *
from irtt_processing import process_irtt

from config import DATA_PATH

est = timezone('US/Eastern')

file_path = f'{DATA_PATH}/obs_data/perf_starlink/{{pi}}/irtt_hourly/'


def read_sat_match_data(start_date, end_date):
    file_path_sat = f'{DATA_PATH}/sat_match/'

    errors = []
    data_df = pd.DataFrame()
    for date in tqdm(pd.date_range(start_date, end_date)):
        date = date.strftime('%Y_%m_%d')
        files = glob.glob(file_path_sat + f"{date}_sat_match.csv")
        for file in files:
            try:
                with open(file) as f:
                    local_data_df = pd.read_csv(f)
                    data_df = pd.concat([data_df, local_data_df])
            except Exception as e:
                errors.append(("error parsing file", file, e))
    columns = ['date', 'pi1_sat', 'pi2_sat', 'pi1_min_ele', 'pi1_max_ele', 'pi1_min_az', 'pi1_max_az', 'pi2_min_ele', 'pi2_max_ele', 'pi2_min_az', 'pi2_max_az', 'pi1_az_ele', 'pi2_az_ele']

    if data_df.empty:
        return pd.DataFrame(columns=columns + ['pi1_first_az', 'pi1_first_ele', 'pi2_first_az', 'pi2_first_ele'])

    data_df.columns = columns
    data_df['pi1_first_az'] = data_df['pi1_az_ele'].apply(lambda x: eval(x)[0][0])
    data_df['pi1_first_ele'] = data_df['pi1_az_ele'].apply(lambda x: eval(x)[0][1])
    data_df['pi2_first_az'] = data_df['pi2_az_ele'].apply(lambda x: eval(x)[0][0])
    data_df['pi2_first_ele'] = data_df['pi2_az_ele'].apply(lambda x: eval(x)[0][1])
    data_df['date'] = pd.to_datetime(data_df['date'], utc=True).dt.tz_convert('US/Eastern')

    return data_df

def read_all_sat_pc(start_date, end_date):
    file_path_sat = f'{DATA_PATH}/sat_match/'
    all_sat_pc = {}
    errors = []
    for date in tqdm(pd.date_range(start_date, end_date)):
        date = date.strftime('%Y_%m_%d')
        files = glob.glob(file_path_sat + f"{date}_all_sat_pc.pkl")
        for file in files:
            try:
                with open(file, 'rb') as f:
                    new_all_sat_pc = pickle.load(f)
                all_sat_pc.update(new_all_sat_pc)
            except Exception as e:
                errors.append(("error parsing file", file, e))
    columns = ['date', 'all_sat_first_pc']
    data = []

    for date, sat_pc in all_sat_pc.items():
        sat_pc_list = [{sat: pc[0]} for sat, pc in sat_pc.items()]
        data.append([date, sat_pc_list])

    all_sat_pc_df = pd.DataFrame(data, columns=columns)
    all_sat_pc_df['date'] = pd.to_datetime(all_sat_pc_df['date'])
    return all_sat_pc_df


def read_rtt_data(start_date, end_date):
    errors = []
    data_df = pd.DataFrame()
    for pi in ['pi1', 'pi2']:
        for date in tqdm(pd.date_range(start_date, end_date)):
            month_name = date.strftime("%B")
            date = date.strftime("%d")
            file_path_date = file_path.format(pi=pi) + month_name + "/" + date + "/"
            files = glob.glob(file_path_date + "*irtt_data_walltime.csv")
            for file in files:
                try:
                    with open(file) as f:
                        local_data_df = pd.read_csv(f)
                        data_df = pd.concat([data_df, local_data_df])
                except Exception as e:
                    errors.append(("error parsing file", file, e))
    data_df.columns = ['date', 'rtt', 'pi']
    data_df['date'] = data_df['date'].str[:-2]
    pi1_irtt_pdf = data_df[data_df['pi'] == 'pi1']
    pi2_irtt_pdf = data_df[data_df['pi'] == 'pi2']
    pi1_irtt_pdf.drop(columns=["pi"], inplace=True)
    pi2_irtt_pdf.drop(columns=["pi"], inplace=True)
    pi1_irtt_pdf.set_index('date', inplace=True)
    pi2_irtt_pdf.set_index('date', inplace=True)

    pi_irtt_pdf = pi1_irtt_pdf.join(pi2_irtt_pdf, lsuffix='_pi1', rsuffix='_pi2', how='outer')
    pi_irtt_pdf.reset_index(inplace=True)
    pi_irtt_pdf['date'] = pd.to_datetime(pi_irtt_pdf['date'], format='%Y-%m-%d %H:%M:%S:%f')
    pi_irtt_pdf['date'] = pi_irtt_pdf['date'].dt.tz_localize('UTC').dt.tz_convert(est)
    pi_irtt_pdf['date'] = pi_irtt_pdf['date'] + pd.Timedelta(hours=5)
    return pi_irtt_pdf


def parse_traceroute_lines_private(output: str) -> Dict[int, List[Dict[str, str]]]:
    hops = {}
    hop_line_regex = re.compile(r"^\s*(\d+)\s+(.*)$")
    ip_latency_regex = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s*\[(AS\d+|\*)\]?\s*(((\d+\.\d+) ms\s*)+)")

    for line in output.splitlines():
        hop_match = hop_line_regex.match(line)
        if not hop_match:
            continue

        hop_num = int(hop_match.group(1))
        details = hop_match.group(2)

        hop_data = []
        for ip_match in ip_latency_regex.finditer(details):
            ip = ip_match.group(1)
            asn = ip_match.group(2)
            latencies = [float(latency) for latency in re.findall(r"(\d+\.\d+) ms", ip_match.group(3))]
            min_latency = min(latencies) if latencies else None
            hop_data.append({
                "ip": ip,
                "asn": asn if asn != "*" else None,
                "latency": min_latency
            })

        hops[hop_num] = hop_data

    return hops

def get_traceroute_fh_latency(start_date, end_date):
    missing_file = []
    date_traceroute_dict = {}

    for pi in ['pi1', 'pi2']:
        date_traceroute_dict[pi] = {}
        base_file = f'{DATA_PATH}/obs_data/perf_starlink/{pi}/traceroute'
        for date in pd.date_range(start=start_date, end=end_date, freq='15s'):
            file = date.strftime(f'{base_file}/%Y/%m/%d/%H/traceroute_%m-%d-%Y_%H:%M:%S.json')
            try:
                with open(file, 'r') as f:
                    data = f.read()
                date_traceroute_dict[pi][str(date)] = parse_traceroute_lines_private(data)
            except FileNotFoundError:
                missing_file.append(file)
        columns = ['date', 'rtt']
        missing_file = []
        first_hop_latency = {}
        pi1_rtt_df = pd.DataFrame(columns=columns)
        pi2_rtt_df = pd.DataFrame(columns=columns)
        for pi, item in date_traceroute_dict.items():
            first_hop_latency[pi] = []
            for key, values in item.items():
                try:
                    hop1 = values[2]
                    if hop1[0]['ip'] != '100.64.0.1':
                        print(key, hop1)
                    else:
                        first_hop_latency[pi].append(hop1[0]['latency'])
                        date = key
                        rtt = hop1[0]['latency']
                        if pi == 'pi1':
                            new_df = pd.DataFrame([[date, rtt]], columns=columns)
                            pi1_rtt_df = pd.concat([pi1_rtt_df, new_df], ignore_index=True)
                        else:
                            new_df = pd.DataFrame([[date, rtt]], columns=columns)
                            pi2_rtt_df = pd.concat([pi2_rtt_df, new_df], ignore_index=True)
                except:
                    missing_file.append(key)

        pi1_rtt_df = pi1_rtt_df.set_index('date')
        pi2_rtt_df = pi2_rtt_df.set_index('date')
        rtt_df = pi1_rtt_df.join(pi2_rtt_df, lsuffix='_pi1', rsuffix='_pi2', how='outer')
        rtt_df = rtt_df.reset_index()
        rtt_df['date'] = pd.to_datetime(rtt_df['date'])
        rtt_df['date'] = rtt_df['date'].dt.tz_localize('UTC').dt.tz_convert(est)
        rtt_df['date'] = rtt_df['date'] + pd.Timedelta(hours=5)
        return rtt_df


def parse_irtt_loss_data(start_date, end_date):
    errors = process_irtt(start_date, end_date)
    return errors


def get_loss_data(start_date, end_date):
    errors = []
    data_df = pd.DataFrame()
    for pi in ['pi1', 'pi2']:
        for date in tqdm(pd.date_range(start_date, end_date)):
            month_name = date.strftime("%B")
            date = date.strftime("%d")
            file_path_date = file_path.format(pi=pi) + month_name + "/" + date + "/"
            files = glob.glob(file_path_date + "*loss_data_walltime.csv")
            for file in files:
                try:
                    with open(file) as f:
                        local_data_df = pd.read_csv(f)
                        data_df = pd.concat([data_df, local_data_df])
                except Exception as e:
                    errors.append(("error parsing file", file, e))
    if data_df.empty:
        return pd.DataFrame(columns=['date', 'pi1_loss', 'pi2_loss'])
    loss_df = data_df.copy()
    loss_df['full_timestamp'] = loss_df['full_timestamp'].str[:-2]
    loss_df['count'] = 1
    loss_df_count = loss_df.groupby(['full_timestamp', 'pi']).agg({'count': 'sum'}).reset_index()
    loss_df_count.reset_index(inplace=True, drop=True)

    pi1_loss = loss_df_count[loss_df_count['pi'] == 'pi1']
    pi1_loss.drop(columns=['pi'], inplace=True)
    pi1_loss.rename(columns={'count': 'pi1_loss'}, inplace=True)
    pi2_loss = loss_df_count[loss_df_count['pi'] == 'pi2']
    pi2_loss.drop(columns=['pi'], inplace=True)
    pi2_loss.rename(columns={'count': 'pi2_loss'}, inplace=True)
    pi_loss_df = pd.merge(pi1_loss, pi2_loss, on='full_timestamp', how='outer')

    pi_loss_df.rename(columns={'full_timestamp': 'date'}, inplace=True)
    pi_loss_df['date'] = pd.to_datetime(pi_loss_df['date'], format='%Y-%m-%d %H:%M:%S:%f')
    pi_loss_df['date'] = pi_loss_df['date'].dt.tz_localize('UTC').dt.tz_convert(est)
    pi_loss_df['date'] = pi_loss_df['date'] + pd.Timedelta(hours=5)
    pi_loss_df = pi_loss_df.sort_values('date').reset_index(drop=True)
    return pi_loss_df

class processSatMatchData():
    def __init__(self, start_date, end_date):
        self.start_date = start_date
        self.end_date = end_date
        self.sat_match_data = read_sat_match_data(start_date, end_date)
        self.all_sat_pc = read_all_sat_pc(start_date, end_date)

    def get_first_az_ele(self):
        self.sat_match_data['pi1_first_az']


def show_obs_image(time_check, rst_obsmap_dict):
    img1 = get_image(time_check, rst_obsmap_dict, 'pi1')
    img2 = get_image(time_check + pd.Timedelta(seconds=15), rst_obsmap_dict, 'pi1')
    img3 = get_image(time_check + pd.Timedelta(seconds=30), rst_obsmap_dict, 'pi1')
    img4 = get_image(time_check + pd.Timedelta(seconds=45), rst_obsmap_dict, 'pi1')

    img_p2 = get_image(time_check, rst_obsmap_dict, 'pi2')
    img_p2_2 = get_image(time_check + pd.Timedelta(seconds=15), rst_obsmap_dict, 'pi2')
    img_p2_3 = get_image(time_check + pd.Timedelta(seconds=30), rst_obsmap_dict, 'pi2')
    img_p2_4 = get_image(time_check + pd.Timedelta(seconds=45), rst_obsmap_dict, 'pi2')
    fig, axs = plt.subplots(2, 4)
    fig.set_size_inches(20, 10)
    axs[0, 0].imshow(img1)
    axs[0, 1].imshow(img2)
    axs[0, 2].imshow(img3)
    axs[0, 3].imshow(img4)
    axs[1, 0].imshow(img_p2)
    axs[1, 1].imshow(img_p2_2)
    axs[1, 2].imshow(img_p2_3)
    axs[1, 3].imshow(img_p2_4)

    for i in range(2):
        for j in range(4):
            axs[i, j].grid(True)
    filename = str(rst_obsmap_dict['pi2'][time_check])
    filename = filename.split('/')[-1]
    axs[0, 0].set_title(f'file name: {filename}')
    plt.tight_layout()
    plt.show()

def get_image(time_check, rst_obsmap_dict, pi):
    img_path = rst_obsmap_dict[pi][time_check]
    img = Image.open(img_path)
    d = time_check
    curr_image_pi1 = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    prev_d = d - timedelta(seconds=15)

    if prev_d in rst_obsmap_dict[pi]:
        prev_image = cv2.imread(rst_obsmap_dict[pi][prev_d], cv2.IMREAD_GRAYSCALE)
        xor_image_pi1 = cv2.bitwise_xor(curr_image_pi1, prev_image)
        curr_image_pi1 = cv2.bitwise_and(xor_image_pi1, curr_image_pi1)

    img = Image.fromarray(curr_image_pi1)
    img = img.resize((img.width * 4, img.height * 4))
    return img

def get_image_small(time_check, rst_obsmap_dict, pi):
    img_path = rst_obsmap_dict[pi][time_check]
    img = Image.open(img_path)
    d = time_check
    curr_image_pi1 = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    prev_d = d - timedelta(seconds=15)

    if prev_d in rst_obsmap_dict[pi]:
        prev_image = cv2.imread(rst_obsmap_dict[pi][prev_d], cv2.IMREAD_GRAYSCALE)
        xor_image_pi1 = cv2.bitwise_xor(curr_image_pi1, prev_image)
        curr_image_pi1 = cv2.bitwise_and(xor_image_pi1, curr_image_pi1)

    img = Image.fromarray(curr_image_pi1)
    img = img.resize((img.width, img.height))
    return img

def get_isolated_pixel_count(date, rst_obsmap_dict, pi):
    try:
        img = get_image(date, rst_obsmap_dict, pi)
        lnb = find_longest_contiguous_non_black(img)
        img_removed = np.array(img)
        for x, y in lnb:
            img_removed[x, y] = 0
    except:
        return -1
    return np.count_nonzero(img_removed)

def remove_longest_block(img, longest_block):
    img_removed = np.array(img)
    for x, y in longest_block:
        img_removed[x, y] = 0
    return Image.fromarray(img_removed)
