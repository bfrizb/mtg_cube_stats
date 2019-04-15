#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import csv
import logging
import os
import texttable
from common import OCCUR_STR

class Grouping(object):
    """Takes in specifications for a desired grouping of cards.
    
    E.g. Which cards to include (i.e. not filter out), how to sort the cards, and
        what columns to output for the card grouping.

    Filters: Append "not_" to each filter-key in order to filter out that
        characteristic. For example, 'not_types': ['Creature'] means to exclude
        cards that have "Creature" as one of their types.

    Sort: Append "reverse_" to each sort-key to sort in descending rather than
        in ascending order.
    """

    def  __init__(self, name, filters, sorts, columns, force_include):
        self.name = name
        # Filters for Colorless Creatures: {'colors': None, 'types': ['Creature']}
        self.filters = filters
        # Sorts: ('convertedManaCost', 'manaCost', 'name')
        self.sorts = sorts
        # Columns: ('name', 'manaCost', ('power', '/', 'toughness'), 'notes')
        self.columns = columns
        self.force_include = force_include  # Grouping must include these card names
        # List of cards in the group
        self._cards = []
        self._sorted = True

    def add_unconditionally(self, card):
        self._sorted = False
        self._cards.append(card)

    def matches_custom_filter(self, card, custom_filter, include):
        if custom_filter == '3+_colors':
            return len(card.json['colors']) >= 3 if include else len(card.json['colors']) < 3
        else:
            logging.error('Unrecognized custom filer: {}'.format(custom_filter))
            return False

    def add_if_qualifies(self, card):
        """Adds a card to the grouping if it matches the filters."""
        matches = True
        for key, value in self.filters.items():
            include = not key.startswith('not_')
            if not include:
                key = key[4:]  # Remove "not_"

            if key == 'custom':
                matches = self.matches_custom_filter(card, value, include)
                break

            if key not in card.json:
                if include:
                    if value:  # E.g. No match: Colorless land for colors=['R']
                        matches = False
                        break
                else:
                    if not value:  # E.g. No match: Colorless land for not_colors=None
                        matches = False
                        break
            
            if value is None:  # None means the field should not exist
                if card.json.has_key(key):
                    matches = False
                    break                    
            elif type(value) == list:
                if include:  # E.g. No Match: Check red creature for colors=['R', 'G']
                    if any([target_attrib not in card.json.get(key, []) for target_attrib in value]):
                        matches = False
                        break
                else:  # No Match: Check red creature for not_colors=['R', 'G']
                    if any([target_attrib in card.json.get(key, []) for target_attrib in value]):
                        matches = False
                        break
        if matches:
            self.add_unconditionally(card)
            
    def sort(self):
        if self._sorted:
            return

        def order_func(card, sorts):
            def is_int(val):
                if val is None:
                    return False
                try:
                    int(val)
                except ValueError:
                    return False
                return True

            values = []
            for attribute in sorts:
                rev = attribute.startswith('reverse_')
                if rev:
                    attribute = attribute[8:]
                if attribute == 'convertedManaCost':
                    # I want to count each X as 100 in the calculation of the convertedManaCost
                    if '{X}' in card.json.get('manaCost', ''):
                        val = 100 * card.json['manaCost'].count('{X}') + int(card.json['convertedManaCost'])
                    else:
                        val = int(card.json['convertedManaCost'])
                elif is_int(card.json.get(attribute)):
                    val = int(card.json[attribute])
                else:
                    val = 1
                    # TODO how does str - sorted work?
                values.append(val if not rev else -1 * val)
            return values

        self._cards.sort(key=lambda card: order_func(card, self.sorts))
        self._sorted = True

    def print_results(self, number_rows=True):
        table = texttable.Texttable()
        if number_rows:
            new_rows = []
            for i, row in enumerate(self.get_rows()):
                new_rows.append(['#'] + row if i == 0 else [str(i)] + row)
            table.add_rows(new_rows)
        else:
            table.add_rows(self.get_rows())
        print('\n*** {} ***'.format(self.name))
        print(table.draw())

    def write_results_to_file(self, output_dir, number_rows=True):
        try:
            os.makedirs(output_dir)
        except FileExistsError:
            pass
        with open(os.path.join(output_dir, self.name + '.csv'), 'w') as csvfile:
            csv_writer = csv.writer(csvfile)
            for row in self.get_rows():
                csv_writer.writerow(row)

    def get_rows(self):
        if not self._sorted:
            raise RuntimeError('Must sort Grouping "{}" before getting output'.format(self.name))
        rows = []
        # Create Header Row
        header_row = []
        for top_cell in self.columns:
            if type(top_cell) == str:
                header_row.append(top_cell.upper())
            elif type(top_cell) == tuple:
                header_row.append(''.join([word.upper() for word in top_cell]))
        rows.append(header_row)
        for card in self._cards:
            new_row = []
            for col in self.columns:
                if type(col) == str:
                    new_row.append(card.json[col] if col in card.json else '<N/A>')
                elif type(col) == tuple:
                    new_cell = ''
                    for subcol in col:
                        new_cell += str(card.json[subcol]) if subcol in card.json else '{}'.format(subcol)
                    new_row.append(new_cell)
            rows.append(new_row)
        return rows


class GroupingProcessor(object):

    def __init__(self, cards, output_dir, groupings=None, number_rows=True):
        self.cards = cards  # This is the {'card_name': Card(...)} dictionary from the Aggregator class
        self._groupings = {}  # {'grouping_name': Grouping(...)}
        self._done_processing = False

        if groupings:
            for group in groupings:
                self.add_grouping(group)
            self.process_groupings()
            for group in groupings:
                group.write_results_to_file(output_dir, number_rows)

    def add_grouping(self, grouping):
        if self._done_processing:
            raise RuntimeError('Cannot add more groupings because grouping processing is complete')
        self._groupings[grouping.name] = grouping

    def process_groupings(self):
        if self._done_processing:
            raise RuntimeError('Already completed grouping processing')
        for card in self.cards.values():
            for group in self._groupings.values():
                if card.name in group.force_include:
                    group.add_unconditionally(card)
                else:
                    group.add_if_qualifies(card)
        for group in self._groupings.values():
            group.sort()
        self._done_processing = True

def create_groupings(grouping_specs, num_other_cubes):
    FILTERS = 'filters'
    COLUMNS = 'columns'
    default_sorting = ('convertedManaCost', 'manaCost', 'reverse_' + OCCUR_STR, 'price', 'name')
    land_columns = ('name', 'colorIdentity', (OCCUR_STR, '/', str(num_other_cubes)), 'price', 'tokens', 'text')
    creature_columns = ('name', 'manaCost', ('power', '/', 'toughness'),
                        (OCCUR_STR, '/', str(num_other_cubes)), 'price', 'tokens', 'text')
    non_creature_columns = ('name', 'manaCost', 'type',
                            (OCCUR_STR, '/', str(num_other_cubes)), 'price', 'tokens', 'text')

    all_groupings = []
    for name, specs in grouping_specs.items():
        if FILTERS not in specs:
            raise ValueError('Missing required "filters" key for "{}" grouping'.format(name))
        if COLUMNS in specs:
            if specs[COLUMNS] == 'creature_columns':
                cols = creature_columns
            elif specs[COLUMNS] == 'non_creature_columns':
                cols = non_creature_columns
            elif specs[COLUMNS] == 'land_columns':
                cols = land_columns
            elif type(specs[COLUMNS]) == list:
                cols = specs[COLUMNS]
            else:
                raise ValueError('Invalid column specifier for "{}" grouping: {}'.format(name, specs[COLUMNS]))
        else:
            raise ValueError('Missing required "columns" key for "{}" grouping'.format(name))
        sorts = default_sorting if 'sorts' not in specs else specs['sorts']
        all_groupings.append(Grouping(name, specs[FILTERS], sorts, cols, specs.get('force_include', [])))
    return all_groupings
