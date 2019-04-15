import json
import logging
import os
import re
import yaml
OCCUR_STR = 'occurrences'
NUM_MAP = {'a': 'ONE', 'two': 'TWO', 'three': 'THREE', 'four': 'FOUR'}


class Card(object):

    def __init__(self, name, card_json, mtg_sets=None, occurrences=None):
        self.name = name
        self.json = card_json
        self.sets = [mtg_sets] if mtg_sets else None
        # Occurrences are kept in the self.json dictionary to take advantage of code in 
        # "groupings.py" that filters and sorts by fields in Card.json
        # TODO: There's probably a better way to do this ...
        if occurrences:
            self.json.update({OCCUR_STR: occurrences})

        self.json['tokens'] = ''
        if 'text' in self.json:
            matches = re.findall(r'(C|c)reate (a|two|three|four) ([^.]+)( creature)? tokens?', self.json['text'])
            if matches and len(matches[0]) >= 3:
                self.json['tokens'] = '{} {}'.format(NUM_MAP[matches[0][1]], matches[0][2])

    def __str__(self):
        answer = type(self).__name__ + '('
        for k, v in self.__dict__.items():
            answer += '{}: {}, '.format(k, v)
        return answer + ')'

    def __repl__(self):
        return self.__str__()

    def merge_split_card_data(self, new_json):
        self.json['convertedManaCost'] = min(self.json['convertedManaCost'], new_json['convertedManaCost'])
        self.json['manaCost'] = '{} // {}'.format(self.json['manaCost'], new_json['manaCost'])
        self.json['name'] += ' // ' + new_json['name']
        if new_json['colors'] not in self.json['colors']:
            self.json['colors'] += new_json['colors']


def read_mtg_json_data(json_path):
    with open(json_path, 'r') as fh:
        return json.loads(fh.read())


def read_price_cache(cache_file_path):
    # Read in local cache of MTG card prices
    if os.path.exists(cache_file_path):
        with open(cache_file_path, 'r') as fh:
            return yaml.load(fh.read())
    else:
        return {}


def save_to_price_cache(price_cache, cache_file_path):
    with open(cache_file_path, 'w') as fh:
        fh.write(yaml.dump(price_cache))


def search_json_for_cards(card_names_to_find, all_sets_json):
    """Searches the tens of MBs of JSON of All MTG Sets only ONCE for all cube cards.

    (Excepting split cards)

    Args:
        all_sets_json: https://mtgjson.com/json/AllSets.json.zip (already unzipped)
    """
    card_map = {}  # Key = name of card | Value = Python Card() object | E.g. {"Giant Spider": Card(json=...)}
    lower_card_dict = {card.lower(): card for card in card_names_to_find}  # E.g. {"giant spider": "Giant Spider"}

    split_cards_lower = {}  # E.g. {"fire": "Fire // Ice", "ice": "Fire // Ice"}
    for card_name in card_names_to_find:
        if ' // ' in card_name:
            for part in card_name.split(' // '):
                split_cards_lower[part.lower()] = card_name
    
    for set_key, set_content in all_sets_json.items():
        for card_json in set_content['cards']:
            if card_json['name'].lower() in lower_card_dict:
                name = lower_card_dict[card_json['name'].lower()]
                if name not in card_map:
                    card_map[name] = Card(name, card_json, set_key)
                else:
                    card_map[name].sets.append(set_key)
            elif card_json['name'].lower() in split_cards_lower:
                name = split_cards_lower[card_json['name'].lower()]
                if name not in card_map:
                    card_map[name] = Card(name, card_json, set_key)
                else:
                    # Each split card occurs only twice in each set
                    if len(card_map[name].sets) == 1 and set_key in card_map[name].sets:
                        card_map[name].merge_split_card_data(card_json)
                    elif set_key not in card_map[name].sets:
                        card_map[name].sets.append(set_key)

    for name in card_names_to_find:
        if name not in card_map:
            logging.error('The card "{}" appeared in No Sets'.format(name))
    return card_map
