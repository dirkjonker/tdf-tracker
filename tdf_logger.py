#!/usr/bin/env python3.4
"""
Save all livetracker updates to json for later analysis
"""

import datetime
import json
import os
import time

import requests


BASE_URL = 'http://letour-livetracking-api.dimensiondata.com/'
RACE_URL = BASE_URL + 'race/'

# Firefox headers
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


def refresh():
    s = requests.Session()
    s.headers = HEADERS
    while True:
        r = s.get(RACE_URL)
        j = r.json()
        if j is None:
            print('no content')
            yield None
            continue
        ts = j['TimeStampEpochInt']
        if time.time() - ts > 180:
            readable = datetime.datetime.fromtimestamp(ts)
            print('no update since {}... quitting...'.format(readable))
            break
        filename = '{}.json'.format(ts)
        path = os.path.join('tdf', filename)
        with open(path, 'w') as jsonfile:
            json.dump(j, jsonfile)
        yield j


def main():
    update = refresh()
    while True:
        j = next(update)
        time.sleep(5)


if __name__ == '__main__':
    main()

