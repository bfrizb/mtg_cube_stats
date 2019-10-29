#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
By:            Brian Frisbie
Date:          2018-07-15
"""
import aggregator
import argparse
import common
import groupings
import logging
import yaml
PROGRAM_PURPOSE = """Generates statistics on a proposed MTG Cube based on other popular cubes on cubetutor.com"""

def parse_args():
    parser = argparse.ArgumentParser(description=PROGRAM_PURPOSE)
    parser.add_argument(
        '-c', '--config_path', default='inputs/vintage_cube_config.yaml',
        help='Path to the configuration file')
    parser.add_argument(
        '-s', '--skip_downloads', action='store_true', help='Skips downloading data from websites. This will '
        'forced cached values to be used even if the max age of the cache is exceeded.')
    parser.add_argument(
        '-u', '--update_throttled_entries', action='store_true', help='By default, cached prices are not updated '
        'unless they are outdated. Using this flag will update any cached prices that have an non-empty entry for '
        'the "skipped_due_to_throttle" field in the cache, even if the price is not outdated.')
    return parser.parse_args()


def print_examples(ag, num_cards=10):
    i = 0
    print('\n\n* START Example Card JSON *')
    for card_objs in ag.cards.values():
        i += 1
        if i >= num_cards:
            break
        print('\n{}'.format(card_objs))
    print('\n*END Example Card JSON*')


def main(args):
    logging.basicConfig(level=logging.DEBUG)
    with open(args.config_path, 'r') as fh:
        config = yaml.load(fh.read())

    ag = aggregator.Aggregator(config, args.skip_downloads, args.update_throttled_entries)
    '''
    print('\n***************')
    print('* Card Counts *')
    print('***************')
    for card_name in ag.cards:
        print('{}: {}'.format(card_name, ag.cards[card_name].json[common.OCCUR_STR]))
    print_examples(ag)

    print('\n\n*************')
    print('* Groupings *')
    print('*************')
    '''
    all_groupings = groupings.create_groupings(ag.grouping_specs, ag.num_other_cubes)
    groupings.GroupingProcessor(ag.cards, config['output_dir'], all_groupings, True)


if __name__ == '__main__':
    main(parse_args())
