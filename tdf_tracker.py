#!/usr/bin/env python3.4
"""
Custom livetracker based on the live GPS data delivered
by DimensionData during the Tour de France
"""

import json
import os
import time

from collections import defaultdict
from pathlib import Path

import numpy as np
import requests

from geopy.distance import great_circle

BASE_URL = 'http://letour-livetracking-api.dimensiondata.com/'
RACE_URL = BASE_URL + 'race/'
STAGES_URL = 'http://letour-livetracking-api.dimensiondata.com/race/stages'
CURRENT_STAGE_URL = STAGES_URL + '/current'
STAGE_URL = STAGES_URL + '/{}'
ROUTE_URL = STAGE_URL + '/route'
RIDER_CLASSIFICATION_URL = STAGE_URL + '/riderclassification'
RIDER_URL = BASE_URL + 'rider'
STATUS_URL = RACE_URL + 'status'

HEADERS = {
    'Host': 'letour-livetracking-api.dimensiondata.com',
    'User-Agent': 'Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:39.0) Gecko/'
                  '20100101 Firefox/39.0',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Referer': 'http://letour-livetracking.dimensiondata.com/',
    'Origin': 'http://letour-livetracking.dimensiondata.com',
    'Connection': 'keep-alive',
    'Cache-Control': 'max-age=0'
}


def get_route(stage_id=None):
    if stage_id is None:
        stage_id = requests.get(CURRENT_STAGE_URL).json().get('StageId')
    route = requests.get(ROUTE_URL.format(stage_id)).json()
    return route


def parse_point(point):
    return (point['Latitude'], point['Longitude'])

def parse_route(route):
    """Parse the route as a lat/long numpy array"""
    parsedroute = []
    for point in route:
        parsed = parse_point(point)
        parsedroute.append(parsed)
    return np.asarray(parsedroute)


def get_rider_list(fromfile=True):
    if fromfile:
        with open('tdf/rider.json', 'r') as jsonfile:
            return json.load(jsonfile)
    return s.get(RIDER_URL).json()


def get_rider_dict(riders):
    riderdict = {}
    for rider in riders:
        rider_id = rider['Id']
        first_name = rider['FirstName']
        last_name = rider['LastName']
        riderdict[rider_id] = u'{}, {}'.format(last_name, first_name)
    return riderdict


def get_nl_riders(riders):
    nl_riders = []
    for rider in riders:
        if not rider['IsWithdrawn'] and rider['Nationality'] == 'Netherlands':
            nl_riders.append(rider['Id'])
    return nl_riders


riderlist = get_rider_list()
riderdict = get_rider_dict(riderlist)
RIDERS = get_nl_riders(riderlist)

RIDERS.append(31)


def secs_to_ms(total_secs):
    mins = mins = int(total_secs // 60)
    secs = int(total_secs % 60)
    return u'{}:{:02d}'.format(mins, secs)


def refresh(real=True):
    if real:
        return refresh_from_web()
    else:
        return refresh_from_file()


def refresh_from_web():
    s = requests.Session()
    s.headers = HEADERS
    while True:
        r = s.get(RACE_URL)
        j = r.json()
        if j is None:
            print('no content')
            yield None
            continue
        yield j


def refresh_from_file():
    p = Path('tdf').glob('14*.json')
    for file in sorted(p):
        with file.open() as jsonfile:
            yield json.load(jsonfile)

class PositionTracker:

    def __init__(self, stage_id=None):
        """Create an object that keeps track of a position through time"""
        route = get_route(stage_id)
        self.route = parse_route(route)
        self.head_time = [None] * len(route)
        self.last_head_ix = None
        self.haspos = False

    def track_head_pos(self, j):
        """Record the position at a given time"""
        # TODO take a group as input instead of the whole object
        head = j['Groups'][0]['Riders'][0]
        ts = j['TimeStampEpochInt']
        postuple = parse_point(head)
        idx = self.closest_point(postuple)[0]
        self.head_time[idx] = ts
        self.last_head_ix = idx
        self.check_empty_spots()
        self.haspos = True

    def check_empty_spots(self):
        """Check whether all intermediate spots in head_time
        are filled. Pretty ugly but it works for now
        """
        last_idx = self.last_head_ix
        if not self.haspos:
            return
        prev_idx = last_idx - 1
        prev_value = self.head_time[prev_idx]
        while prev_value is None:
            prev_idx -= 1
            prev_value = self.head_time[prev_idx]
        num_missing = last_idx - prev_idx + 1
        if num_missing > 0:
            last_time = self.head_time[last_idx]
            prev_time = self.head_time[prev_idx]
            timediff = last_time - prev_time
            each = timediff / num_missing
            for i in range(1, num_missing + 1):
                self.head_time[prev_idx + i] = int(prev_time + i * each)

    def time_behind_head(self, point, ts):
        """If known, return moment in time the head group passed this point"""
        if isinstance(point, dict):
            point = parse_point(point)
        idx = self.closest_point(point)[0]
        head_ts = self.head_time[idx]
        if head_ts is None:
            return None
        return ts - head_ts

    def closest_point(self, point, route=None):
        """Return the timestamp of a position closest to a point"""
        if route is None:
            route = np.asarray(self.route)
        if isinstance(point, dict):
            point = parse_point(point)
        dist = np.sum((route - point) ** 2, axis=1)
        idx_closest = np.argmin(dist)
        diff = great_circle(route[idx_closest], point).meters
        return idx_closest, self.route[idx_closest], diff


class RiderTracker:

    def __init__(self):
        """Create an instance that keeps track of all riders"""
        self.known_riders = {}
        self.missing_riders = defaultdict(lambda: 0)

    def update_riders(self, result):
        current_riders = set()
        for group in result['Groups']:
            for rider in group['Riders']:
                current_riders.add(rider['Id'])
                self.known_riders[rider['Id']] = group['GroupId']
        current_missing = self.known_riders.keys() - current_riders
        print('missing: {}'.format(current_missing))

    def return_valid_riderlist(self):
        pass
        # TODO create a method that returns a list of all riders and
        # their last known position


def main(real=True):
    max_speed = [0, 0]
    update = refresh(real)
    pt = PositionTracker(22)
    rt = RiderTracker()
    while True:
        os.system('clear')
        j = next(update)
        pt.track_head_pos(j)
        groups = j['Groups']
        head = groups[0]['Riders'][0]
        head_distance_left = head['DistanceToFinish']
        head_speed = head['CurrentSpeed']
        ts = j['TimeStampEpochInt']
        print(u'head of the race: {:.1f} km to go / current speed: {} km/h'.\
            format(head_distance_left, head_speed))
        is_first_group = True
        for group in groups:
            group_name = group['GroupName']
            group_size = group['GroupSize']
            group_distance = group['GroupDistanceToFinish']
            group_speed = group
            if is_first_group:
                distance_to_finish = group_distance
                is_first_group = False
                kw = 'left'
            else:
                group_distance = group_distance - distance_to_finish
                timegap = secs_to_ms(group['GapToLeadingGroupT'])
                kw = 'behind ({})'.format(timegap)
                first = group['Riders'][0]
                timediff = pt.time_behind_head(first, ts)
                if timediff is not None:
                    print('timediff w/head: {}'.format(
                        secs_to_ms(timediff)))
                    # this should be roughly equal to 'GapToLeadingGroupT'
                    # given that they are calculated in a similar fashion
            print('{} has {} riders and {:.1f} km {}'.format(
                    group_name, group_size, group_distance, kw))
            for rider in group['Riders']:
                rider_speed = rider['CurrentSpeed']
                if rider_speed > max_speed[0]:
                    max_speed[0] = rider_speed
                    max_speed[1] = rider['Id']
                yellow = ''
                if rider['HasYellowJersey']:
                    yellow = '* '
                if rider['Id'] in RIDERS:
                    ridername = riderdict.get(rider['Id'], 'unknown')
                    print(u'  {:>3}. {}{} travelling @ {} km/h'.\
                          format(
                        rider['PositionInTheGroup'],
                        yellow,
                        ridername,
                        rider_speed))
        max_speed_rider = riderdict[max_speed[1]]
        print(u'max speed: {} km/h by rider {}'.format(max_speed[0],
                                                       max_speed_rider))
        rt.update_riders(j)
        time.sleep(1)

if __name__ == '__main__':
    pass

