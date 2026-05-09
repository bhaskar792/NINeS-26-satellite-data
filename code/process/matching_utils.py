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
import scipy
from scipy.stats import ks_2samp
from scipy import stats
from tqdm import tqdm
import os
from collections import defaultdict
from fastdtw import fastdtw
from scipy.spatial.distance import euclidean


def find_longest_contiguous_non_black(image_in):
    image = image_in.convert('L')
    image_array = np.array(image)

    binary_image = (image_array > 0).astype(int)

    visited = np.zeros_like(binary_image, dtype=bool)
    longest_component = []

    def dfs(x, y, current_component):
        if x < 0 or x >= binary_image.shape[0] or y < 0 or y >= binary_image.shape[1]:
            return
        if visited[x, y] or binary_image[x, y] == 0:
            return
        visited[x, y] = True
        current_component.append((x, y))
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
        for dx, dy in directions:
            dfs(x + dx, y + dy, current_component)

    for i in range(binary_image.shape[0]):
        for j in range(binary_image.shape[1]):
            if binary_image[i, j] == 1 and not visited[i, j]:
                current_component = []
                dfs(i, j, current_component)
                if len(current_component) > len(longest_component):
                    longest_component = current_component

    return longest_component


import math

def calculate_radius(center, point):
    x_center, y_center = center
    x, y = point

    dx = x - x_center
    dy = y - y_center

    radius = (math.sqrt(dx**2 + dy**2) * (1.3333))

    return (90 - radius)


def calculate_clockwise(point, cpx, cpy):
    y = cpy - point[0]
    x = point[1] - cpx

    angle_radians = math.atan2(y, x)
    angle_degrees = math.degrees(angle_radians)

    if x >= 0:
        clockwise_angle = (90 - angle_degrees) % 360
    else:
        clockwise_angle = (450 - angle_degrees) % 360

    if clockwise_angle > 360:
        clockwise_angle = clockwise_angle - 360

    return clockwise_angle


def get_dtw_distance(cartesian1, cartesian2):
    cartesian1 = sorted(cartesian1, key=lambda x: x[1])
    cartesian2 = sorted(cartesian2, key=lambda x: x[1])
    distance, path = fastdtw(cartesian1, cartesian2, dist=euclidean)
    return distance

def calculate_dtw_error(list1, list2):
    cartesian1 = [(r * np.cos(np.radians(a)), r * np.sin(np.radians(a))) for r, a in list1]
    cartesian2 = [(r * np.cos(np.radians(a)), r * np.sin(np.radians(a))) for r, a in list2]
    return get_dtw_distance(cartesian1, cartesian2)

def max75_normalize(list1, list2):
    cartesian1 = [(((r-25)/75) * np.cos(np.radians(a)), ((r-25)/75) * np.sin(np.radians(a))) for r, a in list1]
    cartesian2 = [(((r-25)/75) * np.cos(np.radians(a)), ((r-25)/75)* np.sin(np.radians(a))) for r, a in list2]
    return get_dtw_distance(cartesian1, cartesian2)

def max90_normalize(list1, list2):
    cartesian1 = [((r/90) * np.cos(np.radians(a)), (r/90) * np.sin(np.radians(a))) for r, a in list1]
    cartesian2 = [((r/90) * np.cos(np.radians(a)), (r/90)* np.sin(np.radians(a))) for r, a in list2]
    return get_dtw_distance(cartesian1, cartesian2)

def cos_normalize(list1, list2):
    cartesian1 = [(np.cos(np.radians(r)) * np.cos(np.radians(a)), np.cos(np.radians(r)) * np.sin(np.radians(a))) for r, a in list1]
    cartesian2 = [(np.cos(np.radians(r)) * np.cos(np.radians(a)), np.cos(np.radians(r)) * np.sin(np.radians(a))) for r, a in list2]
    return get_dtw_distance(cartesian1, cartesian2)

def sin_normalize(list1, list2):
    cartesian1 = [(np.sin(np.radians(r)) * np.cos(np.radians(a)), np.sin(np.radians(r)) * np.sin(np.radians(a))) for r, a in list1]
    cartesian2 = [(np.sin(np.radians(r)) * np.cos(np.radians(a)), np.sin(np.radians(r)) * np.sin(np.radians(a))) for r, a in list2]
    return get_dtw_distance(cartesian1, cartesian2)


def read_sat_json(file, dtype):
    f = open(file, 'r')
    sat_json = json.load(f)
    if dtype == 'sats':
        sats = convert_pickled_dict(sat_json, "sat")
    else:
        sats = convert_pickled_dict(sat_json, "gs")
    f.close()
    return sats

def match_sat(pi_coords, sat_coords):
    sv = np.inf
    ss = None

    for sat in sat_coords:
        list1 = pi_coords
        list2 = sat_coords[sat]
        dtw_error = calculate_dtw_error(list1, list2)
        if dtw_error < sv:
            sv = dtw_error
            ss = sat

    return ss, sat_coords[ss], sv

def match_top_k_sat(pi_coords, sat_coords, k=2):
    sv = [np.inf]*k
    ss = [None]*k

    for sat in sat_coords:
        list1 = pi_coords
        list2 = sat_coords[sat]
        dtw_error = calculate_dtw_error(list1, list2)
        if dtw_error < max(sv):
            index = sv.index(max(sv))
            sv[index] = dtw_error
            ss[index] = sat
    sv, ss = zip(*sorted(zip(sv, ss)))
    sv = list(sv)
    ss = list(ss)
    top_k_sats_coords = [sat_coords[s] for s in ss]
    return ss, top_k_sats_coords, sv

def get_single_sat_from_top_k(pi1_sat_top_k, pi2_sat_top_k, pi1_sc_top_k, pi2_sc_top_k, pi1_error_top_k, pi2_error_top_k):
    sum_error = np.inf
    pi1_error = pi1_error_top_k[0]
    pi2_error = pi2_error_top_k[0]
    pi1_sat = pi1_sat_top_k[0]
    pi2_sat = pi2_sat_top_k[0]
    pi1_sc = pi1_sc_top_k[0]
    pi2_sc = pi2_sc_top_k[0]
    for i in range(len(pi1_sat_top_k)):
        for j in range(len(pi2_sat_top_k)):
            if pi1_sat_top_k[i] == pi2_sat_top_k[j]:
                if pi1_error_top_k[i] + pi2_error_top_k[j] < sum_error:
                    sum_error = pi1_error_top_k[i] + pi2_error_top_k[j]
                    pi1_error = pi1_error_top_k[i]
                    pi2_error = pi2_error_top_k[j]
                    pi1_sat = pi1_sat_top_k[i]
                    pi2_sat = pi2_sat_top_k[j]
                    pi1_sc = pi1_sc_top_k[i]
                    pi2_sc = pi2_sc_top_k[j]
    return pi1_sat, pi2_sat, pi1_sc, pi2_sc, pi1_error, pi2_error

def convert_pickled_dict(dict_in, dtype):
    est = timezone('US/Eastern')
    converted_pickled_dict = {}
    if dtype == "sat":
        for t in dict_in:
            ct = parser.parse(t).astimezone(est)
            converted_pickled_dict[ct] = eval(dict_in[t])
    elif dtype == "gs":
        for town in dict_in:
            converted_pickled_dict[town] = {}
            curr_town = dict_in[town]
            for t in curr_town:
                ct = parser.parse(t).astimezone(utc)
                converted_pickled_dict[town][ct] = eval(curr_town[t])
    return converted_pickled_dict
