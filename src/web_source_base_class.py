#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import abc

SKIPPED_SETS_PARTIAL_NAME = [
    'Salvat 20', 'Magic Player Rewards', 'Comic Con'
]
SKIPPED_SETS_FULL_NAMES = [
    'Masters Edition', "Collector's Edition", "International Collector's Edition",
    'Vintage Masters', 'Tempest Remastered', 'Unstable', 'Unhinged', 'Unglued', 'Arena League',
    'Magic Online Promos', 'Magic Online Theme Decks', 'Duel Decks Mirrodin Pure vs New Phyrexia',
]

class WebSource(abc.ABC):

    def __init__(self, all_sets_json):
        self.name = 'ABSTRACT_CLASS'
        # {CARD_NAME: [SET_1, SET_2, ...]}   |   # E.g. {'Giant Spider': ['Alpha', 'Beta', ...]}
        self.setname_map = self._create_setname_map(all_sets_json)

    @abc.abstractmethod
    def create_card_url(self, card_name, set_name):
        pass

    @abc.abstractmethod
    def parse_url_response(self, response):
        pass

    @abc.abstractmethod
    def get_setname(self, set_name):
        pass

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
