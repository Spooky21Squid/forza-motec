#!/usr/env/python
# -*- coding: utf-8 -*-
'''
This is a modified version of Morten Wang's data2file program that listens to a port for UDP packets
sent by Forza Motorsport 2023's Data Out feature, and writes them to a file.
'''

import csv
import logging
import socket

import yaml
import datetime as dt

from fdp import ForzaDataPacket

def to_str(value):
    '''
    Returns a string representation of the given value, if it's a floating
    number, format it.

    :param value: the value to format
    '''
    if isinstance(value, float):
        return('{:f}'.format(value))

    return('{}'.format(value))

def dump_stream(port, output_filename, format='tsv',
                append=False, packet_format='dash', config_file = None, motec = False):
    '''
    Opens the given output filename, listens to UDP packets on the given port
    and writes data to the file.

    :param port: listening port number
    :type port: int

    :param output_filename: path to the file we will write to
    :type output_filename: str

    :param format: what format to write out, either 'tsv' or 'csv'
    :type format: str

    :param append: if set, the output file will be opened for appending and
                   the header with column names is not written out
    :type append: bool

    :param packet_format: the packet format sent by the game, one of either
                          'sled' or 'dash'
    :type packet_format str

    :param config_file: path to the YAML configuration file
    :type config_file: str
    '''

    if config_file:
        import yaml
        with open(config_file) as f:
            config = yaml.safe_load(f)

        ## The configuration can override everything
        if 'port' in config:
            port = config['port']

        if 'output_filename' in config:
            output_filename = config['output_filename']

        if 'format' in config:
            format = config['format']

        if 'append' in config:
            append = config['append']

        if 'packet_format' in config:
            packet_format = config['packet_format']
        
        if 'motec' in config:
            motec = config['motec']

    params = ForzaDataPacket.get_props(packet_format = packet_format)
    if config_file and 'parameter_list' in config:
        params = config['parameter_list']

    # Motec needs a time field, so this normalises the time of a session even when there are game pauses. motec_time_modifier begins
    # as the time of arrival of the first packet, and increases by the amount of time is_race_on remains false. The time field of the
    # motec csv file then equals the time of receival of a packet, minus the modifier.
    motec_time_modifier = None  # Set when the first packet arrives
    pause_start_time = None  # Marks the time when a packet with is_race_on is False is received
    pause_end_time = None  # Marks the time when a packet with is_race_on is True is received
    was_paused = False

    if motec:
        params.insert(0, 'time')

    log_wall_clock = False
    if 'wall_clock' in params:
        log_wall_clock = True

    open_mode = 'w'
    if append:
        open_mode = 'a'

    with open(output_filename, open_mode, buffering=1) as outfile, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server_socket:
        if format == 'csv':
            csv_writer = csv.writer(outfile)
            if not append:
                csv_writer.writerow(params)

        ## If we're not appending, add a header row:
        if format == 'tsv' and not append:
            outfile.write('\t'.join(params))
            outfile.write('\n')
        
        server_socket.bind(('', port))

        logging.info('listening on port {}'.format(port))
        
        first_packet_received = False
        n_packets = 0
        
        while True:
            message, address = server_socket.recvfrom(1024)
            time_of_arrival = dt.datetime.now()
            fdp = ForzaDataPacket(message, packet_format = packet_format)
            if log_wall_clock:
                fdp.wall_clock = dt.datetime.now()

            if motec:
                if not first_packet_received:
                    motec_time_modifier = time_of_arrival
                    first_packet_received = True

            if fdp.is_race_on:
                if motec:
                    if was_paused:
                        pause_end_time = dt.datetime.now()
                        motec_time_modifier += (pause_end_time - pause_start_time)  # Moves time modifier forward by the duration of the pause
                        was_paused = False
                    fdp.time = (dt.datetime.now() - motec_time_modifier).total_seconds()  # subtraction returns a timedelta object
                if n_packets == 0:
                    logging.info('{}: in race, logging data'.format(dt.datetime.now()))
                if format == 'csv':
                    csv_writer.writerow(fdp.to_list(params))
                else:
                    outfile.write('\t'.join([to_str(v) \
                                             for v in fdp.to_list(params)]))
                    outfile.write('\n')

                n_packets += 1
                if n_packets % 60 == 0:
                    logging.info('{}: logged {} packets'.format(dt.datetime.now(), n_packets))
            else:
                if motec and not was_paused:
                    was_paused = True
                    pause_start_time = dt.datetime.now()
                if n_packets > 0:
                    logging.info('{}: out of race, stopped logging data'.format(dt.datetime.now()))
                n_packets = 0

def main():
    import argparse

    cli_parser = argparse.ArgumentParser(
        description="script that grabs data from a Forza Motorsport stream and dumps it to a TSV file"
    )

    # Verbosity option
    cli_parser.add_argument('-v', '--verbose', action='store_true',
                            help='write informational output')

    cli_parser.add_argument('-a', '--append', action='store_true',
                            default=False, help='if set, data will be appended to the given file')

    cli_parser.add_argument('-f', '--format', type=str, default='tsv',
                            choices=['tsv', 'csv'],
                            help='what format to write out, "tsv" means tab-separated, "csv" comma-separated; default is "tsv"')

    cli_parser.add_argument('-p', '--packet_format', type=str, default='dash',
                            choices=['sled', 'dash', 'fh4'],
                            help='what format the packets coming from the game is, either "sled", "dash", or "fh4"')

    cli_parser.add_argument('-c', '--config_file', type=str,
                            help='path to the YAML configuration file')

    cli_parser.add_argument('-m', '--motec', action='store_true',
                            default=False, help='if set, adds motec-specific metadata and fields to the file')

    cli_parser.add_argument('port', type=int,
                            help='port number to listen on')

    cli_parser.add_argument('output_filename', type=str,
                            help='path to the TSV file we will output')

    args = cli_parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    dump_stream(args.port, args.output_filename, args.format, args.append,
                args.packet_format, args.config_file, args.motec)

    return()

if __name__ == "__main__":
    main()
    
