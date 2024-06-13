from datetime import datetime

ICOSA_EPOCH = 1609459200000


def get_snowflake_timestamp(snowflake):
    timestamp = get_snowflake_timestamp_raw(snowflake)
    return datetime.fromtimestamp(timestamp / 1000)


def get_snowflake_timestamp_raw(snowflake):
    return (snowflake >> 22) + ICOSA_EPOCH
