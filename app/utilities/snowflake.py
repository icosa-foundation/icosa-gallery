import datetime
import os
import time

# Generates a 'unique' timestamp based on Twitter's Snowflake algorithm.
# https://github.com/twitter-archive/snowflake/tree/snowflake-2010
#
# Icosa Epoch: first second of 2020, or 1609459200000
#                                                    3 F   F   F   F    F
# Format: 111111111111111111111111111111111111111111 111111111111111111 1111
#         64                                         22                 4   0
# Timestamp  | 42 bits | Miliseconds since Icosa Epoch  | (snowflake >> 22) + ICOSA_EPOCH
# Process ID | 18 bits | Process ID of generator        | (snowflake & 0x3FFFF) >> 4
# Counter    | 4 bits  | Looping counter                | snowflake & 0xF

ICOSA_EPOCH = 1609459200000

counter = 0

def generate_snowflake():
    global counter
    timestamp = datetime.datetime.utcnow()
    unix_epoch = datetime.datetime(1970, 1, 1)
    timestamp = int((timestamp-unix_epoch).total_seconds() * 1000)
    process = os.getpid()
    process = process if (process < 0x3FFFF) else 0x3FFFF
    counter = (counter + 1) % 15
    snowflake = ((timestamp - ICOSA_EPOCH) << 22) | (process << 4) | counter
    return snowflake

def get_timestamp(snowflake):
    timestamp = get_timestamp_raw(snowflake) / 1000
    return datetime.datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%dT%H:%M:%SZ')

def get_timestamp_raw(snowflake):
    return (snowflake >> 22) + ICOSA_EPOCH
