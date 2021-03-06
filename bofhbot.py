#!/usr/bin/env python3

#### module load python/3.6
#### need python3 cuz exception handling for ssh call

# bofhbot - An enhanced sinfo -R for lazy sys admins--aka bofh :)
# see README.rst for detailed description (and license).
# tin (at) berkeley.edu 

# future exercise can likely write this using functional approach
# for now, regular scripting style. 
# OOP can have a structure with problem node as list of objects
# and parallel ssh/ping/etc check on them 
# to speed up output

# most functions moved to bofhbot_lib so that it can be used by the botd api server -Sn 2019.0302

import asyncio
import argparse
import json
import sys
from os import path
from pathlib import Path

from bot_lib import check_nodes, node_string_to_nodes, show_partition_info
from bot_analyzer import analyze
from bot_actions import suggest, interactive_suggest
from convert_json import show_table
from db_connector import db_storage

from termcolor import colored
from pygments import highlight
from pygments.lexers import JsonLexer 
from pygments.formatters import TerminalFormatter

def process_cli() :
    # https://docs.python.org/3/howto/argparse.html#id1
    parser = argparse.ArgumentParser(prog='bofhbot')
    subparsers = parser.add_subparsers(dest='subparser_name')

    check_parser = subparsers.add_parser('check')
    check_parser.add_argument('nodes', nargs='*', default=[])
    check_parser.add_argument('-x', '--no-sudo', dest='use_sudo', action='store_false', help='only run commands that do not require sudo')
    check_parser.add_argument('-c', '--concurrency', type=int, help='maximum number of nodes to check at once', default=50)
    check_parser.add_argument('-s', '--stdin', dest='read_stdin', action='store_true', help='read node list from stdin')
    check_parser.set_defaults(read_stdin=False, use_sudo=True, concurrency=50)

    analyze_parser = subparsers.add_parser('analyze')
    analyze_parser.add_argument('nodes', nargs='*', default=[])

    filter_parser = subparsers.add_parser('filter')
    filter_parser.add_argument('-p', '--property', action='append', help='filter based on node property:value')
    filter_parser.add_argument('nodes', nargs='*', default=[])

    show_parser = subparsers.add_parser('show')
    show_parser.add_argument('-f', '--fields', nargs='*', default=[], help='show only selected fields in columns')

    suggest_parser = subparsers.add_parser('suggest')
    suggest_parser.add_argument('-i', '--ignore-reason', dest='use_reason', action='store_false', help='make suggestions ignoring sinfo reason')
    suggest_parser.set_defaults(use_reason=True)

    report_parser = subparsers.add_parser('report')

    return parser.parse_args()
# process_cli()-end 

def read_stdin():
    return json.loads(''.join(sys.stdin.readlines()))

def get_analysis(node_info, use_reason=True):
    return { node: analyze(status, use_reason=use_reason) for node, status in node_info.items() }

def get_suggestions(node_info, use_reason=True):
    status = get_analysis(node_info, use_reason=use_reason)
    return { node: (suggest(node, state), state) for node, state in status.items() }

async def main(): 
    args = process_cli()
    print(args, file=sys.stderr)
    if args.subparser_name == 'check':
        nodes = (args.nodes + (sys.stdin.readlines() if args.read_stdin else [])) or ['sinfo']
        nodes = [ node.strip() for node in nodes ]
        results = await check_nodes(nodes, use_sudo=args.use_sudo, concurrency=args.concurrency)
        # db_storage(results, path.join(Path.home(), 'bofhbot.db'))
        results_json = json.dumps(results, sort_keys=True, indent=2)
        if sys.stdout.isatty():
            return print(highlight(results_json, JsonLexer(), TerminalFormatter()))
        return print(results_json)
    if args.subparser_name == 'analyze':
        print(get_analysis(read_stdin()))
    if args.subparser_name == 'show':
        selected_fields = [ f.upper() for f in args.fields ]
        data = { node: { k: v for k, v in data.items() if k.upper() in selected_fields or not args.fields } for node, data in read_stdin().items() }
        show_table(data)
    if args.subparser_name == 'suggest':
        status = read_stdin()
        suggestions = get_suggestions(status, use_reason=args.use_reason)
        await interactive_suggest(suggestions, status)
    if args.subparser_name == 'list':
        return show_status(args.nodes)
    if args.subparser_name == 'filter':
        status = read_stdin()
        if args.nodes:
            nodes = await node_string_to_nodes(args.nodes)
            results = { node: data for node, data in status.items() if node in nodes or node.split('.')[1] in args.nodes }
        else:
            results = status
        properties = { p.split(':')[0].upper(): p.split(':')[1] for p in (args.property or []) }
        def matches(data):
            for k, v in properties.items():
                if k not in data:
                    return False
                if not str(data[k]).upper() == v.upper():
                    return False
            return True
        results = { node: data for node, data in results.items() if matches(data) }
        results_json = json.dumps(results, sort_keys=True, indent=2)
        if sys.stdout.isatty():
            return print(highlight(results_json, JsonLexer(), TerminalFormatter()))
        return print(results_json)
    if args.subparser_name == 'report':
        return print(await show_partition_info())
# main()-end

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
loop.close()
