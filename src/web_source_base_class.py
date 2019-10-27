#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import abc
import logging
import requests
import time
from datetime import datetime
from datetime import timedelta
INITIAL_THROTTLE_SECONDS = 5


SKIPPED_SETS_PARTIAL_NAME = [
    'Salvat 20', 'Magic Player Rewards', 'Comic Con',
]
SKIPPED_SETS_FULL_NAMES = [
    'Masters Edition', "Collector's Edition", "International Collector's Edition",
    'Vintage Masters', 'Tempest Remastered', 'Unstable', 'Unhinged', 'Unglued', 'Arena League',
    'Magic Online Promos', 'Magic Online Theme Decks', 'Duel Decks Mirrodin Pure vs New Phyrexia',
]

class WebSource(abc.ABC):

    def __init__(self, all_sets_json, throttle_mult=2):
        self.name = 'ABSTRACT_CLASS'
        # {CARD_NAME: [SET_1, SET_2, ...]}   |   # E.g. {'Giant Spider': ['Alpha', 'Beta', ...]}
        self.setname_map = self._create_setname_map(all_sets_json)
        self.was_throttled = None  # Did the latest HTTP request result in a Throttled response?
        self._current_throttle_in_sec = INITIAL_THROTTLE_SECONDS
        self._throttle_mult = throttle_mult
        self._throttle_end_time = None

    @abc.abstractmethod
    def _create_card_url(self, card_name, set_name):
        pass

    @abc.abstractmethod
    def parse_url_response(self, response):
        pass

    @abc.abstractmethod
    def get_setname(self, set_name):
        pass

    @property
    def is_throttled(self):
        return self._throttle_end_time is not None

    def make_http_request(self, card_name, set_name):
        """Makes an HTTP request to the passed in URL and does a quick check on the HTTP response."""
        if self._throttle_end_time and self._throttle_end_time > datetime.now():
            return None  # Continue throttling

        url = self._create_card_url(card_name, set_name)
        try:
            resp = requests.get(url)
        except requests.exceptions.SSLError as e:
            logging.error(e)
            return

        if 'Throttled' in resp.text:
            if self._throttle_end_time:  # Here, we only recently tried another request after throttling
                self._current_throttle_in_sec *= self._throttle_mult
            logging.warn('Throttle encountered for: {}'.format(url))
            logging.warn('\t' + resp.text)
            logging.info('\nThrottling for {} seconds'.format(self._current_throttle_in_sec))
            self._throttle_end_time = datetime.now() + timedelta(seconds=self._current_throttle_in_sec)
            return None                
        if resp.status_code != 200:
            logging.warn('\tThe following URL produced status_code={0}: {1}'.format(resp.status_code, url))
            return None
        if 'That page was not found.' in resp.text:
            logging.warn('\tThe following URL resulted in "That page was not found.": {0}'.format(url))
            return None
        if '<title></title>' in resp.text:
            logging.warn('\tThe following URL contained "<title></title>": {0}'.format(url))
            return None
        
        # Success!
        if self._throttle_end_time:  # Here, we only recently tried another request after throttling
            logging.info('Request success after throttling for {} seconds'.format(self._current_throttle_in_sec))
            self._throttle_end_time = None
        return resp

    def _create_setname_map(self, all_sets_json):
        setname_map = {}  
        for set_ in all_sets_json.values():
            if set_['name'] in SKIPPED_SETS_FULL_NAMES or \
                    any([set_['name'] in skip for skip in SKIPPED_SETS_PARTIAL_NAME]):
                continue
            
            setname = self.get_setname(set_['name'])

            for card in set_['cards']:
                cardname = card['name']
                if cardname in ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest']:
                    continue
                cardname = cardname.replace('Aether', 'AEther')

                if setname is not None:
                    if cardname in setname_map:
                        setname_map[cardname].append(setname)
                    else:
                        setname_map[cardname] = [setname]
        return setname_map
