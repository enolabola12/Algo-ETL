import datetime
import pandas as pd

import finnhub
from util.throttle import throttle
import secrets

finnhub_token = secrets.FINNHUB_TOKEN

# throttle finnhub request speed
finnhub.Client._request = throttle(period=60, max_times=58,
                                   on_throttle=lambda t, _: print(f'throttle {t:.2f}s'))(finnhub.Client._request)

class FinnhubDataFormatError(Exception):
    '''
    Finnhub Data format error
    '''
    pass


def get_client():
    return finnhub.Client(api_key=finnhub_token)


def get_stock_day_candles(symbol, start_date=None, end_date=None):
    '''
    - Returns a DataFrame[(symbol, t) o, h, l, c, v] sorted by 't' asc
    - Returns the data including both start_date and end_date
    - Both start_date and end_date should be datetime with only date, e.g. datetime.datetime(2020, 1, 1)
    - If the market is open, the candle data of today is removed because close price is not final.
    - If start_date is None, it means 1970-01-01.
    - If end_date is None, it means today.
    '''
    if start_date is None:
        start_date = datetime.datetime(1970, 1, 1)
    if end_date is None:
        end_date = datetime.datetime.today()
    start_timestamp = int(start_date.timestamp()) - int(start_date.timestamp()) % 86400
    end_timestamp = int(end_date.timestamp()) - int(end_date.timestamp()) % 86400

    stock_candle_all = {'c': [], 'h': [], 'l': [], 'o': [], 't': [], 'v': []}
    with finnhub.Client(api_key=finnhub_token) as fc:
        n = 5000
        while n >= 5000 and start_timestamp <= end_timestamp:
            res = fc.stock_candles(symbol, 'D', start_timestamp, end_timestamp)
            _check_stock_day_candle_data_format(res)
            n = len(res['t']) if res['s'] == 'ok' else 0
            if n > 0:
                for k in stock_candle_all:
                    stock_candle_all[k].extend(res[k])
                start_timestamp = res['t'][-1] - (res['t'][-1] % 86400) + 86400

    df = pd.DataFrame(stock_candle_all)
    df['t'] = df['t'] - (df['t'] % 86400)  # trunc datetime to full day
    df['t'] = pd.to_datetime(df['t'], unit='s')
    df.sort_values(by='t', inplace=True)
    df['symbol'] = symbol
    df = df[['symbol', 't', 'o', 'h', 'l', 'c', 'v']]
    df.drop_duplicates(['symbol', 't'], keep='last', inplace=True)
    df.set_index(['symbol', 't'], inplace=True)
    return df


def get_stock_1min_candles(symbol, start_time=None, end_time=None):
    '''
    - Return DataFrame[symbol, t, o, h, l, c, v] sorted by 't' asc
    - Return the data including both start_time and end_time
    - Use UTC time
    '''
    if start_time is None:
        start_time = datetime.datetime(1970, 1, 1)
    if end_time is None:
        end_time = datetime.datetime.now()
    start_timestamp = int(start_time.timestamp())
    end_timestamp = int(end_time.timestamp())

    stock_candle_all = {'c': [], 'h': [], 'l': [], 'o': [], 't': [], 'v': []}
    with finnhub.Client(api_key=finnhub_token) as fc:
        n = 5000
        while n > 0 and start_timestamp <= end_timestamp:
            res = fc.stock_candles(symbol, '1', start_timestamp, end_timestamp)
            _check_stock_1min_candle_data_format(res)
            n = len(res['t']) if res['s'] == 'ok' else 0
            if n > 0:
                for k in stock_candle_all:
                    stock_candle_all[k].extend(res[k])
                end_timestamp = res['t'][0] - (res['t'][0] % 60) - 60

    df = pd.DataFrame(stock_candle_all)
    df['t'] = df['t'] - (df['t'] % 60)  # trunc datetime to minute
    df['t'] = pd.to_datetime(df['t'], unit='s')
    df.sort_values(by='t', inplace=True)
    df['symbol'] = symbol
    df = df[['symbol', 't', 'o', 'h', 'l', 'c', 'v']]
    df.drop_duplicates(['symbol', 't'], keep='last', inplace=True)
    return df


def get_us_symbols():
    '''
    Return df with columns of 'symbol', 'type', 'mic', 'displaySymbol', 'description', 'figi'
    '''
    with finnhub.Client(api_key=finnhub_token) as fc:
        res = fc.stock_symbols('US')
    df = pd.DataFrame(res, columns=['symbol', 'type', 'mic', 'displaySymbol', 'description', 'figi'])
    return df


def get_split(symbol):
    '''
    Return DataFrame[symbol, date, fromFactor, toFactor]
    '''
    with finnhub.Client(api_key=finnhub_token) as fc:
        res = fc.stock_splits(symbol, '1970-01-01', '2030-01-01')
    df = pd.DataFrame(res, columns=['symbol', 'date', 'fromFactor', 'toFactor'])
    df['date'] = pd.to_datetime(df['date'])
    return df


def check_api_connection():
    '''
    Return True if connection is ok. Otherwise return False
    Check connection by getting the quote of AAPL
    '''
    try:
        res = get_quote('AAPL')
    except Exception:
        return False
    if res:
        return True
    else:
        return False


def get_quote(symbol):
    '''
    Return {'c': 132.05, 'h': 132.63, 'l': 130.23, 'o': 132.43, 'pc': 130.92, 't': 1610150400}
    '''
    with finnhub.Client(api_key=finnhub_token) as fc:
        res = fc.quote(symbol)
    return res

def _get_day_candle_available_time(dt: datetime.datetime):
    '''
    The data of day candle is available on 21:30 UTC
    '''
    return datetime.datetime(dt.year(), dt.month(), dt.day(), 21, 30, 0)


def _check_stock_day_candle_data_format(response):
    if 's' not in response.keys():
        raise FinnhubDataFormatError('"s" is not in the response dict')
    else:
        if response['s'] == 'ok':
            if not ({'c', 'h', 'l', 'o', 't', 'v'} <= set(response.keys())):  # response does not include all keys
                raise FinnhubDataFormatError(f'Response does not include all keys, {set(response.keys())}')
            else:
                if not(len(response['c']) == len(response['h']) == len(response['l']) == len(response['o']) == len(response['t']) == len(response['v'])):
                    raise FinnhubDataFormatError('Different len of candle data, len[chlotv]={}'.format(
                        (response[k] for k in ['c', 'h', 'l', 'o', 't', 'v'])))
                # for timestamp in response['t']:
                #     if timestamp % 86400 != 0:  # timestamp should be at 12:00am
                #         raise FinnhubDataFormatError(f'Timestamp should be at 12:00am, timestamp={timestamp}')


def _check_stock_1min_candle_data_format(response):
    if 's' not in response.keys():
        raise FinnhubDataFormatError('"s" is not in the response dict')
    else:
        if response['s'] == 'ok':
            if not ({'c', 'h', 'l', 'o', 't', 'v'} <= set(response.keys())):  # response does not include all keys
                raise FinnhubDataFormatError(f'Response does not include all keys, {set(response.keys())}')
            else:
                if not(len(response['c']) == len(response['h']) == len(response['l']) == len(response['o']) == len(response['t']) == len(response['v'])):
                    raise FinnhubDataFormatError('Different len of candle data, len[chlotv]={}'.format(
                        (response[k] for k in ['c', 'h', 'l', 'o', 't', 'v'])))
                for timestamp in response['t']:
                    if timestamp % 60 != 0:
                        raise FinnhubDataFormatError(f'Timestamp % 60 should be at 0, timestamp={timestamp}')
