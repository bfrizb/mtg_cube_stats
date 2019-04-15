#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import csv
import os
import texttable
import yaml
from collections import namedtuple
from common import Card
from common import read_price_cache
IncludedCard = namedtuple('IncludedCard', ['name', 'group', 'more'])


class PossibleCard(Card):

    def __init__(self, name, my_cube_occurs, total_occur, tokens):
        super().__init__(name, {}, None, None)
        self.occur_per_cube = my_cube_occurs  # {CUBE_NAME: OCCUR_STR} | E.g. {'Legacy': '3/7'}
        self.total_occur = total_occur        # Total occurances across all of my cubes that I'm comparing
        self.tokens = tokens 

    def get_occurences(self, cube_names):
        return [self.occur_per_cube[cname] if cname in self.occur_per_cube else '' for cname in cube_names]


class Comparer(object):

    def __init__(self, config):
        self.config = config     # Loaded configuration file (as python dictionary)
        self.my_cube_lists = {}  # E.g. {'Legacy': [IncludedCard(...), IncludedCard(...), ...]}
        self.group_lists = {}    # E.g. {'simic': [PossibleCard(...), PossibleCard(...), ...]}

    def update_group_list(self, group_name, cube_name, csv_path):
        possible_cards = self.group_lists.get(group_name, {})
        with open(csv_path) as csvfile:
            reader = csv.reader(csvfile)
            for i, row in enumerate(reader):
                if i == 0:
                    headers = row
                    continue
                name = row[headers.index('NAME')]
                occur_col = row[headers.index('OCCURRENCES/7')]
                count = int(occur_col.split('/')[0])
                tokens = row[headers.index('TOKENS')]

                if name in possible_cards:
                    possible_cards[name].total_occur += count
                    possible_cards[name].occur_per_cube[cube_name] = occur_col
                else:
                    possible_cards[name] = PossibleCard(name, {cube_name: occur_col}, count, tokens)
        self.group_lists[group_name] = possible_cards

    def load_files(self):
        for cube_name in self.config['cubes']:
            self.my_cube_lists[cube_name] = []
            card_list = self.config['cubes'][cube_name]['my_card_list']
            with open(card_list) as csvfile:
                reader = csv.reader(csvfile)
                for i, row in enumerate(reader):
                    if i == 0:  # Header row should be "NAME, GROUP, MORE"
                        continue
                    if len(row) < 2:
                        continue
                    incard = IncludedCard(row[0], row[1], row[2:] if len(row) > 2 else None)
                    self.my_cube_lists[cube_name].append(incard)
        
        for cube_name in self.config['cubes']:
            stats_dir = self.config['cubes'][cube_name]['stats_csvs']
            for csvfile in [f for f in os.listdir(stats_dir) if not f.startswith('.')]:
                group_name = csvfile.rsplit('.', 1)[0]
                self.update_group_list(group_name, cube_name, os.path.join(stats_dir, csvfile))

    def get_include_marks(self, card_name):
        include_marks = []
        # Iteratre thru all my cube lists (e.g. Legacy, Vinetage)
        for mcl in self.my_cube_lists.values():
            is_included_in_mcl = False
            for incard in mcl:
                if card_name == incard.name:
                    is_included_in_mcl = True
                    break
            include_marks.append('X' if is_included_in_mcl else '')
        return include_marks

    def generate_tables(self):
        all_group_tables = {}  # {group_name: table_rows}
        price_cache = read_price_cache(self.config['price_cache_path'])
        header = ['NAME', 'PRICE', 'TOTAL_COUNT'] + \
            ['{} Count'.format(name) for name in list(self.config['cubes'].keys())] + \
            ['Have in {}?'.format(name) for name in list(self.config['cubes'].keys())] + ['TOKENS']

        for group_name in self.group_lists:
            all_possibles = list(self.group_lists[group_name].values())
            all_possibles.sort(key=lambda card: card.total_occur, reverse=True)  # Sort by highest card count

            table = [header]
            # Go thru all PossibleCard's within the group
            for pcard in all_possibles:
                table.append([pcard.name, price_cache.get(pcard.name, 'MISSING'), pcard.total_occur]
                    + pcard.get_occurences(self.my_cube_lists.keys()) + self.get_include_marks(pcard.name)
                    + [pcard.tokens])

            # Now, iterate thru all my cube lists (e.g. Legacy, Vinetage), looking for cards NOT in 
            # the PossibleCard's (which were collected from stats_csvs)
            my_choice_cards = []  # Cards that I chose that didn't appear in most popular cubetutor.com cubes
            for mcl in self.my_cube_lists.values():
                 for incard in mcl:
                     if incard.group == group_name and incard.name not in my_choice_cards + all_possibles:
                         my_choice_cards.append(incard.name)
            # Mark which cubes contain my choice cards
            for card_name in my_choice_cards:
                card_data = price_cache.get(card_name)
                if card_data is None or card_data['price'] is None:
                    price = '<Missing>'
                else:
                    price = card_data['price']
                table.append([card_name, price, '', '', ''] + self.get_include_marks(card_name))            
            all_group_tables[group_name] = table

        return all_group_tables


def write_csv(group_name, table, output_dir):
    try:
        os.makedirs(output_dir)
    except FileExistsError:
        pass
    with open(os.path.join(output_dir, group_name + '.csv'), 'w') as csvfile:
        csv_writer = csv.writer(csvfile)
        for row in table:
            csv_writer.writerow(row)


def pretty_print_table(group_name, table):
    print('\n\n*** {} ***'.format(group_name))
    tt = texttable.Texttable()
    tt.add_rows(table)
    print(tt.draw())


def main():
    with open('inputs/compare_legacy_vs_vinetage.yaml', 'r') as fh:
        config = yaml.load(fh.read())
    c = Comparer(config)
    c.load_files()
    tables = c.generate_tables()
    for group_name, table in tables.items():
        write_csv(group_name, table, config['output_dir'])
        # pretty_print_table(group_name, table)


if __name__ == '__main__':
    main()
