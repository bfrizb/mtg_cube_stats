#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import common
import logging
import os
import requests
import time
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
        url = 'http://www.cubetutor.com/viewcube/{}'.format(cube_id)
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

        url = 'http://www.cubetutor.com/viewcube.exportform.exportlistform;jsessionid=' + jess_id
        r = requests.post(url, data = {
            't:ac': cube_id,
            't:formdata': t_formdata,
            'fileType': 'CUBE_TXT',
            'submit_0': 'Export',
            't:submit': '["submit_2","submit_0"]',
        })
        print('\ncurl -d "{}" -X POST "{}"\n'.format(r.request.body, r.request.url))

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


class PriceFetcher(object):

    def __init__(self, cache_file_path, max_cached_days, all_sets_json):
        self._cache_file_path = cache_file_path
        self._max_cached_days = max_cached_days
        # self.price_cache = {<CARD_NAME>: {'date': <>, 'price': <>}}
        # E.g. {Abrade: {date: '2018-01-23', price: 1.34}}
        self.price_cache = common.read_price_cache(cache_file_path)
        self.web_sources = web_source_classes.get_all_web_sources(all_sets_json)

    @staticmethod
    def get_http_response(url):
        """Makes an HTTP request to the passed in URL and does a quick check on the HTTP response.
        
        Currently requests pages from mtgprice.com and cardkingdom.com
        """
        try:
            resp = requests.get(url)
        except requests.exceptions.SSLError as e:
            logging.error(e)
            return

        if 'Throttled' in resp.text:
            logging.critical('Throttled encountered!!!')
            logging.warn(url)
            logging.warn(resp.text)
            time.sleep(10)
        if resp.status_code != 200:
            logging.warn('\tThe following URL produced status_code={0}: {1}'.format(resp.status_code, url))
            return None
        if 'That page was not found.' in resp.text:
            logging.warn('\tThe following URL resulted in "That page was not found.": {0}'.format(url))
            return None
        if '<title></title>' in resp.text:
            logging.warn('\tThe following URL contained "<title></title>": {0}'.format(url))
            return None
        return resp

    def query_price(self, card_name):
        """Queries the price of a specific MTG card given its name."""

        # First, check if the card price is in local cache and is not stale
        if card_name in self.price_cache:
            cached_date = datetime.strptime(self.price_cache[card_name]['date'], '%Y-%m-%d')
            data_age = (datetime.now() - cached_date).days
            if (
                    data_age <= self._max_cached_days and
                    'web_source' in self.price_cache[card_name] and
                    self.price_cache[card_name]['web_source'].lower() != 'mtgprice' and
                    self.price_cache[card_name]['price'] is not None and
                    self.price_cache[card_name]['price'] != 0
            ):
                return self.price_cache[card_name]['price']

        if all([card_name not in ws.setname_map for ws in self.web_sources]):
            return "NAME_NOT_FOUND"

        # Check mtggoldfish 1st, cardkingdom 2nd, and mtgprice 3rd (stopping as soon as a price is found)
        lowest_price = None
        for web_source in self.web_sources:
            for set_name in web_source.setname_map[card_name]:
                resp = PriceFetcher.get_http_response(web_source.create_card_url(card_name, set_name))
                if resp is None:
                    continue
                price = web_source.parse_url_response(resp)
                if price != 0 and (lowest_price is None or price < lowest_price):
                    lowest_price = price
            if lowest_price is not None:
                break
        self.price_cache[card_name] = {'price': lowest_price}
        self.price_cache[card_name]['date'] = datetime.now().strftime('%Y-%m-%d')
        self.price_cache[card_name]['web_source'] = web_source.name
        return lowest_price

    def bulk_query_price(self, list_card_objs):
        list_card_objs.sort(key=lambda card: card.name)  # Sort by card name
        try:
            for card in list_card_objs:
                card.price = self.query_price(card.name)
        finally:
            # Saves card prices to the local cache file
            common.save_to_price_cache(self.price_cache, self._cache_file_path)
