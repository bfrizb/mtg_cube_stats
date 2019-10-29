#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import common
import logging
import os
import requests
import time
import urllib
import yaml
from collections import namedtuple
from datetime import datetime
try:
    import web_source_classes
except ImportError:
    logging.warn('Import "web_source_classes" is missing (it is intentionally .gitignore\'d), so '
        '"cube_stats.py" will only work when using theh "-s" flag')


class CubeTutorDownloader(object):

    def __init__(self, cache_dir):
        self.cache_dir = cache_dir

    @staticmethod
    def get_cube_file_path(cache_dir, cude_id):
        return os.path.join(cache_dir, '{}.txt'.format(cude_id))

    def fetch_updated_cubetutor_lists(self, cube_ids):
        try:
            os.mkdir(self.cache_dir)
        except OSError:
            pass
        cube_paths = []
        for cid in cube_ids:
            fpath = self.get_cube_file_path(self.cache_dir, cid)
            if self._should_refresh_list(fpath):
                self._download_cubetutor_list(cid, cube_ids[cid])
            cube_paths.append(fpath)
        return cube_paths

    def _download_cubetutor_list(self, cube_id, cube_name):
        url = 'https://www.cubetutor.com/viewcube/{}'.format(cube_id)
        logging.debug('Requesting {}'.format(url))
        r = requests.get(url)
        if r.status_code != 200:
            logging.warn('Got status code {} for request to {}'.format(r.status_code, url))
            return
        for k, v in r.cookies.items():
            if k == 'JSESSIONID':
                jess_id = v
        # Get t:formdata
        t_formdata = r.text.split('/viewcube.exportform.exportlistform', 1)[1].split(
            'name="t:ac" type="hidden"></input><input value="', 1)[1].split('"', 1)[0]
        logging.debug('t_formdata for cube {} = {}'.format(cube_id, t_formdata))

        url = 'https://www.cubetutor.com/viewcube.exportform.exportlistform?t:ac=' + str(cube_id)
        post_data={
            't:ac': cube_id,
            't:formdata': t_formdata,
            'fileType': 'CUBE_TXT',
            'submit_0': 'Export',
            't:submit': '["submit_2","submit_0"]',
        }
        r = requests.post(url, cookies=r.cookies, data=post_data)
        print('\ncurl -d "{}" --cookie "JSESSIONID={}" "{}"\n'.format(
            urllib.parse.urlencode(post_data), jess_id, url))

        with open(self.get_cube_file_path(self.cache_dir, cube_id), 'w') as fh:
            fh.write('# {}\n\n{}'.format(cube_name, r.text))  # .encode('utf-8')))  [py2.7 only]

    def _should_refresh_list(self, cube_path):
        try:
            modified = os.stat(cube_path).st_mtime
        except FileNotFoundError:
            return True

        one_month = 3600 * 24 * 30
        if time.time() - modified > one_month:
            os.remove(cube_path)
            return True
        return False


class FailLog(object):

    def __init__(self):
        # self._record ==>
        #   { set_name1:
        #     { web_source_name1: [
        #       { url: XXX, status_code: YYY, text: ZZZ},
        #       ...
        #     ]   }   }
        self._record = {}

    @staticmethod
    def parse_resp(resp):
        return {
            'url': resp.url,
            'status_code': resp.status_code,
            'text': resp.text.strip()[:100],
        }

    def add(self, set_name, web_source_name, resp):
        if set_name in self._record:
            if web_source_name in self._record[set_name]:
                self._record[set_name][web_source_name].append(FailLog.parse_resp(resp))
            else:
                self._record[set_name][web_source_name] = [FailLog.parse_resp(resp)]
        else:
            self._record[set_name] = {web_source_name: [FailLog.parse_resp(resp)]}

    def save(self, cache_folder):
        with open(os.path.join(cache_folder, 'fail_log.yaml'), 'w') as fh:
            fh.write(yaml.dump(self._record))


class PriceFetcher(object):

    def __init__(self, cache_file_path, max_cached_days, all_sets_json):
        self._cache_file_path = cache_file_path
        self._max_cached_days = max_cached_days
        self._fail_log = FailLog()
        # self.price_cache = {<CARD_NAME>: {'date': <>, 'price': <>}}
        # E.g. {Abrade: {date: '2018-01-23', price: 1.34}}
        self.price_cache = common.read_price_cache(cache_file_path)
        self.web_sources = web_source_classes.get_all_web_sources(all_sets_json)

    def query_price(self, card_name, update_throttled=False):
        """Queries the price of a specific MTG card given its name."""

        # First, check if the card price is in local cache and is not stale
        if card_name in self.price_cache:
            cached_date = datetime.strptime(self.price_cache[card_name]['date'], '%Y-%m-%d')
            data_age = (datetime.now() - cached_date).days
            if (
                data_age <= self._max_cached_days and
                'web_source' in self.price_cache[card_name] and
                self.price_cache[card_name]['web_source'].lower() != 'mtgprice' and  # mtgprice is unreliable
                self.price_cache[card_name]['price'] is not None and
                self.price_cache[card_name]['price'] != 0
                and (
                    # Use the price cache if:
                    #     (1) we are Not updating throttled entries, OR (2) the card entry was NOT throttled
                    not update_throttled or  # update_throttled=True
                    not self.price_cache[card_name].get('skipped_due_to_throttle', True)
                )
            ):
                return self.price_cache[card_name]['price']

            if 'web_source' in self.price_cache[card_name]:
                logging.debug('\n\t{} | {}'.format(card_name, self.price_cache[card_name]['web_source']))
            else:
                logging.debug('\n\t {} | No web source'.format(card_name))

        if all([card_name not in ws.setname_map for ws in self.web_sources]):
            return "NAME_NOT_FOUND"

        lowest_price = None
        skipped_due_to_throttle = set()
        missing_card_price = set()
        for web_source in self.web_sources:
            for set_name in web_source.setname_map[card_name]:
                resp = web_source.make_http_request(card_name, set_name)
                if resp is None:
                    self._fail_log.add(set_name, web_source.name, web_source.last_response)
                    if web_source.is_throttled:
                        skipped_due_to_throttle.add(web_source.name)
                    else:
                        missing_card_price.add(web_source.name)
                    continue
                price = web_source.parse_url_response(resp)
                if price != 0 and (lowest_price is None or price < lowest_price):
                    lowest_price = price
            if lowest_price is not None:
                break
        self.price_cache[card_name] = {
            'price': lowest_price,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'web_source': web_source.name,
            'skipped_due_to_throttle': skipped_due_to_throttle,
            'missing_card_price': missing_card_price,
        }
        return lowest_price

    def bulk_query_price(self, list_card_objs, update_throttled=False):
        list_card_objs.sort(key=lambda card: card.name)  # Sort by card name
        try:
            for card in list_card_objs:
                card.price = self.query_price(card.name, update_throttled)
        finally:
            # Saves card prices to the local cache file
            common.save_to_price_cache(self.price_cache, self._cache_file_path)
            self._fail_log.save(os.path.dirname(self._cache_file_path))
