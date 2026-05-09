import glob
import os
import json
import pandas as pd
from tqdm import tqdm
from datetime import datetime
import pytz
import multiprocessing
import gzip
import shutil
import re

from config import DATA_PATH

file_path = f"{DATA_PATH}/obs_data/perf_starlink/{{pi}}/irtt_hourly/"


def create_directory(pi, start_date, end_date):
    base_path = file_path.format(pi=pi)
    files = glob.glob(base_path + '*')
    error_files = []
    for file in tqdm(files):
        if file.endswith(".gz"):
            date = re.search(r'\d{4}-\d{2}-\d{2}', file).group()
            date = datetime.strptime(date, '%Y-%m-%d')
            month = date.strftime('%B')
            day = date.strftime('%d')
            if date < start_date or date > end_date:
                continue
            if not os.path.exists(base_path + month):
                os.makedirs(base_path + month)
            if not os.path.exists(base_path + month + '/' + day):
                os.makedirs(base_path + month + '/' + day)
            if os.path.exists(base_path + month + '/' + day + '/' + file.split('/')[-1].replace('.gz', '')):
                continue
            try:
                with gzip.open(file, 'rb') as f_in:
                    with open(base_path + month + '/' + day + '/' + file.split('/')[-1].replace('.gz', ''), 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
            except:
                print("error in unzipping the file")
                error_files.append(file)
                continue
    with open(f"{DATA_PATH}/obs_data/perf_starlink/{pi}/error_files.txt", 'a') as f:
        for item in error_files:
            f.write("%s\n" % item)
    return error_files


def process_irtt_chunk(dates_chunk, pi):
    dates_chunk = sorted(dates_chunk)
    create_directory(pi, dates_chunk[0], dates_chunk[-1])
    print('processing chunk', dates_chunk, pi)
    errors = []
    dates_chunk = list(dates_chunk)
    pi = pi
    for date in dates_chunk:
        irtt_data_list = []
        loss_data = []
        month_name = date.strftime("%B")
        day = date.strftime("%d")
        file_path_date = file_path.format(pi=pi) + month_name + "/" + day + "/"
        files = glob.glob(file_path_date + "*.json")
        csv_files = glob.glob(file_path_date + "*walltime.csv")
        if len(csv_files) > 0:
            try:
                irtt_df = pd.read_csv(csv_files[0])
                if irtt_df.shape[0] > 1000000:
                    continue
                else:
                    errors.append(('not enough data in csv file', csv_files))
                    pass
            except Exception as e:
                errors.append((csv_files, "error in reading csv file"))

        for file in files:
            try:
                with open(file) as f:
                    data = json.load(f)
                    for rtt in data['round_trips']:
                        if rtt['lost'] == 'false':
                            rtt_value = round(rtt['delay']['rtt'] / 1e6, 3)
                            wall_time = rtt['timestamps']['client']['send']['wall']
                            full_timestamp = datetime.fromtimestamp(wall_time / 1e9, pytz.timezone('US/Eastern')).strftime('%Y-%m-%d %H:%M:%S:%f')[:-3]
                            irtt_data_list.append({'full_timestamp': full_timestamp, 'rtt': rtt_value, 'pi': pi})
                        else:
                            loss_value = rtt['lost']
                            wall_time = rtt['timestamps']['client']['send']['wall']
                            full_timestamp = datetime.fromtimestamp(wall_time / 1e9, pytz.timezone('US/Eastern')).strftime('%Y-%m-%d %H:%M:%S:%f')[:-3]
                            loss_data.append({'full_timestamp': full_timestamp, 'loss': loss_value, 'pi': pi})
            except Exception as e:
                errors.append(("error parsing file", file, e))

        irtt_df = pd.DataFrame(irtt_data_list)
        loss_df = pd.DataFrame(loss_data)
        irtt_df.to_csv(f"{file_path_date}irtt_data_walltime.csv", index=False)
        loss_df.to_csv(f"{file_path_date}loss_data_walltime.csv", index=False)

    return errors


def process_irtt(start_date, end_date):
    errors = []
    dates = pd.date_range(start_date, end_date)
    num_chunks = min(multiprocessing.cpu_count(), len(dates))
    chunks = [dates[i::num_chunks] for i in range(num_chunks)]
    both_chunks = [(chunk, pi) for chunk in chunks for pi in ['pi1', 'pi2']]
    print(both_chunks)
    with multiprocessing.Pool(processes=num_chunks) as pool:
        results = []
        results.extend(pool.starmap(process_irtt_chunk, both_chunks))

    for result in results:
        errors.extend(result)

    return errors


if __name__ == '__main__':
    start_date = "2024-12-23"
    end_date = "2024-12-26"
    errors = process_irtt(start_date, end_date)
    print(errors)
