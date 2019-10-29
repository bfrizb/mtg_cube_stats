#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import downloaders
import json
import logging
import os
import requests
import texttable
import common
DEFAULT_MAX_CACHED_DAYS = 30
PRICE_CACHE_FNAME = 'mtg_price_cache.yaml'


class Aggregator(object):

    def __init__(self, config, skip_downloads=False, update_throttled=False):
        self.num_other_cubes = None  # int (None when uninitialized)
        self._skip_downloads = skip_downloads
        self._update_throttled = update_throttled
        self.grouping_specs = {}                # Specified in config
        card_map = self._aggregate_data(config)
        self.cards = card_map                   # {card_name: card_object}

    def _get_other_cube_lists(self, config):
        if self._skip_downloads:
            other_cube_paths = []
            for cid in config['cubetutor_ids']:
                new_path = downloaders.CubeTutorDownloader.get_cube_file_path(config['cache_dir'], cid)
                if not os.path.exists(new_path):
                    raise RuntimeError('Downloading is skipped and the specified list from '
                                       'cubetutor is Not cached locally: {}'.format(new_path))                
                other_cube_paths.append(new_path)
        else:
            other_cube_paths = downloaders.CubeTutorDownloader(
                config['cache_dir']).fetch_updated_cubetutor_lists(config['cubetutor_ids'])
        return other_cube_paths

    def _count_cards(self, other_cube_paths):
        """Counts the number of times each card appears in the Cubetutor card lists.

        Returns:
            A dictionary mapping the card name to the number of occurrences
        """
        card_dict = {}
        for fpath in other_cube_paths:
            with open(fpath, 'r') as fh:
                cube_list = [l.strip() for l in fh.readlines() if l.strip() != "" and not l.startswith("#")]
            for card in cube_list:
                if card in card_dict:
                    card_dict[card] += 1
                else:
                    card_dict[card] = 1
        return card_dict

    def _aggregate_data(self, config):
        # Load the config file
        self.grouping_specs = config['grouping_specs']

        # Gather and Organize Information
        other_cube_paths = self._get_other_cube_lists(config)
        self.num_other_cubes = len(other_cube_paths)
        all_sets_json = common.read_mtg_json_data(config['all_mtg_sets_path'])

        count_map = self._count_cards(other_cube_paths)
        card_map = common.search_json_for_cards(count_map.keys(), all_sets_json)
        for card_name in card_map:
            card_map[card_name].json[common.OCCUR_STR] = count_map[card_name]

        pf = downloaders.PriceFetcher(
            os.path.join(config['cache_dir'], PRICE_CACHE_FNAME),
            config.get('max_cached_days', DEFAULT_MAX_CACHED_DAYS), all_sets_json)
        if not self._skip_downloads:
            pf.bulk_query_price(list(card_map.values()), self._update_throttled)

        # Update Card JSON data with price info
        for card in card_map.values():
            cache_entry = pf.price_cache.get(card.name)
            if cache_entry is not None:
                cache_entry = cache_entry['price']
            card.json['price_raw'] = cache_entry if cache_entry is not None else None
            card.json['price'] = '${:,.2f}'.format(cache_entry) if cache_entry is not None else None
        return card_map
