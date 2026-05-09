from skyfield.api import load, wgs84, utc
import datetime
from tqdm import tqdm
from dateutil import parser
import glob
from datetime import datetime, timezone, timedelta
import pandas as pd
import json
import haversine as hs
import numpy as np

from matching_utils import read_sat_json
from config import DATA_PATH, DISH_LOCATION

PATH = DATA_PATH
ts = load.timescale()


def get_rise_events_location(tle, location, alt, t0, t1):
    satellites = load.tle_file(tle)
    print('Loaded', len(satellites), 'satellites')

    sat_rise_dict = {}
    for satellite in satellites:
        sat_rise_dict[satellite.name] = list()
        t, events = satellite.find_events(location, t0, t1, altitude_degrees=alt)
        for ti, event in zip(t, events):
            name = ('rise above 30°', 'culminate', 'set below 30°')[event]
            sat_rise_dict[satellite.name].append((ti.utc_strftime('%Y %b %d %H:%M:%S'), name))

    sat_events_dict = {}
    for sat in sat_rise_dict:
        sat_events_dict[sat] = list()
        curr_sat = sat_rise_dict[sat]
        num_events = len(curr_sat)

        start_event = 0
        if num_events > 2:
            while 'rise' not in curr_sat[start_event][1]:
                start_event += 1

            i = start_event
            while i < num_events:
                curr_series = curr_sat[i:i+3]
                sat_events_dict[sat].append(curr_series)
                i += 3

    return sat_events_dict


def get_tuples_from_rise_events(purdue_rise_events, location):
    all_tuples = list()
    for s in tqdm(purdue_rise_events):
        if purdue_rise_events[s]:
            curr_sat_events = purdue_rise_events[s]
            curr_sat = get_curr_satellite(s)
            for event in curr_sat_events:
                if len(event) == 3:
                    start = event[0][0]
                    end = event[2][0]
                    time_list = get_time_list(start, end)
                    curr_sat_location_diff = curr_sat - location
                    all_diffs = curr_sat_location_diff.at(time_list)

                    for d in all_diffs:
                        alt, az, distance = d.altaz()
                        if alt.degrees >= 25:
                            if (az.degrees >= 180 and az.degrees <= 360) or (az.degrees >= 0 and az.degrees <= 180):
                                curr_t = parser.parse(d.t.utc_strftime('%Y %b %d %H:%M:%S'))
                                curr_tup = (s, curr_t, alt.degrees, az.degrees, distance.km)
                                all_tuples.append(curr_tup)

    return all_tuples


def get_curr_satellite(s):
    satellites = load.tle_file(curr_tle)
    for sat in satellites:
        if sat.name == s:
            return sat


def get_time_list(start, end):
    start = parser.parse(start)
    end = parser.parse(end)

    time_list = list()
    while start < end:
        time_list.append(start.replace(tzinfo=utc))
        start += timedelta(seconds=1)

    return ts.utc(time_list)


def get_nearest_gs(num_nearest, lat, long, ground_stations_file):
    purdue = (lat, long)
    f = open(ground_stations_file)
    ground_stations = json.load(f)

    hs_distances = list()
    for g in ground_stations:
        gs = (g["lat"], g["lng"])
        hs_dist = hs.haversine(purdue, gs)
        hs_distances.append((g["town"], hs_dist))

    nearest_gs = sorted(hs_distances, key=lambda x: x[1])[:num_nearest]
    nearest_gs_full_info = list()
    for gs in nearest_gs:
        for g in ground_stations:
            if gs[0] == g['town']:
                nearest_gs_full_info.append(g)

    return nearest_gs_full_info


def get_tle_date(in_date):
    tlist = list()
    all_tles = glob.glob(f'{PATH}/daily_tles/*')
    for tle in all_tles:
        try:
            tle_date = parser.parse('-'.join(tle.split('TLE_')[-1].split('-')[:3])).date()
            if tle_date == in_date:
                tlist.append(tle)
        except:
            continue
    middleIndex = int((len(tlist) - 1) / 2)
    return sorted(tlist)[middleIndex]


if __name__ == '__main__':
    all_maps = list()
    for p in ['pi2', 'pi1']:
        all_maps += glob.glob(f'{PATH}/obs_data/perf_starlink/' + p + '/obs_maps_rst/*.png')

    unique_days = set()
    print("getting unique days")
    for m in tqdm(all_maps):
        try:
            cd = m.split('/')[-1].split('map_')[-1].split('.')[0]
            parseDate = parser.parse(' '.join(cd.split('_')))
            unique_days.add(parseDate.date())
        except:
            print("error in unique days", m)

    unique_days = list(unique_days)
    processed_tle_data = glob.glob(f'{PATH}/processed_tle/*')
    processed_dates = list()
    for p in processed_tle_data:
        try:
            parseDate = parser.parse(p.split('/')[-1].split('_')[-1].split('.')[0])
            processed_dates.append(parseDate.date())
        except:
            print(p)

    lat, lon = DISH_LOCATION
    for u in unique_days:
        if (u.month >= 9 and u.year >= 2024) or u.year > 2024:
            if u not in processed_dates and u.day != datetime.now().date():
                print(f'processing date {u}')

                curr_tle = get_tle_date(u)
                print(curr_tle)
                satellites = load.tle_file(curr_tle)

                location = wgs84.latlon(lat, lon)
                print(location)

                t0 = ts.utc(u.year, u.month, u.day - 1, 23)
                t1 = ts.utc(u.year, u.month, u.day + 1, 1)
                print(t0, t1)
                tu = get_rise_events_location(curr_tle, location, 25.0, t0, t1)
                at = get_tuples_from_rise_events(tu, location)

                sorted_tuples = sorted(at, key=lambda x: x[1])

                time_sat_dict = {}
                for t in sorted_tuples:
                    curr_time = t[1].replace(tzinfo=utc)
                    if curr_time not in time_sat_dict:
                        time_sat_dict[curr_time] = list()
                    time_sat_dict[curr_time].append((t[0], t[2], t[3], t[4]))

                location_pickled = {}
                for t in time_sat_dict:
                    ct = str(t).split("+")[0]
                    location_pickled[ct] = str(time_sat_dict[t])

                with open(f'{PATH}/processed_tle/dual_' + str(u) + '.json', 'w') as fp:
                    json.dump(location_pickled, fp)

                current_tle = f'{PATH}/processed_tle/dual_' + str(u) + '.json'
                existing_pd_files = glob.glob(f'{PATH}/processed_tle_pd/*')
                pd_tups = list()

                exist = False
                for existing_pd_file in existing_pd_files:
                    if str(u) in existing_pd_file:
                        print(f'{current_tle} already processed')
                        exist = True
                        break
                if exist:
                    continue
                sat_json = read_sat_json(current_tle, 'sats')
                for t in tqdm(sat_json):
                    curr_dict = sat_json[t]
                    for sat in curr_dict:
                        tup = (t, sat[0], sat[1], sat[2], (np.pi / 180) * sat[2])
                        pd_tups.append(tup)
                az_pd_daily = pd.DataFrame(pd_tups, columns=['c_time', 'sat', 'aoe', 'az', 'az_rad'])
                az_pd_daily = az_pd_daily.sort_values(by='c_time')
                date = current_tle.split('/')[-1].split('_')[-1].split('.')[0]
                az_pd_daily.to_csv(f'{PATH}/processed_tle_pd/azimuth_data_{date}.csv', index=False)
