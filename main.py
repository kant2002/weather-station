from sys import version
from neopixel import NeoPixel
from network import WLAN, STA_IF
from onewire import OneWire
from ds18x20 import DS18X20
from machine import Pin, Timer, RTC, ADC
from time import ticks_ms, ticks_diff, sleep_ms, time, mktime
from base64 import b64decode
from ujson import load
import time_utils
import weather
import api_utils

print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
print("RPi-Pico MicroPython Ver:", version)
print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

CONFIG_FILE = "conf/config.json"
TEMPERATURE_SENSOR_IN_PIN = 19
WIND_DIR_SENSOR_IN_PIN = 4
WIFI_LED_OUT_PIN = 8
WIND_SPD_SENSOR_IN_PIN = 6
RAIN_CNT_SENSOR_IN_PIN = 5
RAIN_UNITS = "in"
TEMPERATURE_UNITS = "F"
SPEED_UNITS = "MPH"
# WIFI_MODE = 3
HOURLY = 3_600_000  # milliseconds
WIFI_CHECK_PERIOD = HOURLY
SECOND_PERIOD = 1000
DATA_POINT_CHECK_PERIOD = 5 * SECOND_PERIOD
MINUTE_PERIOD = 60 * SECOND_PERIOD
WEATHER_UPDATE_PERIOD = 2 * MINUTE_PERIOD
UPDATES_PER_HOUR = int(HOURLY / WEATHER_UPDATE_PERIOD)
DATA_POINTS_PER_UPDATE = int(WEATHER_UPDATE_PERIOD / DATA_POINT_CHECK_PERIOD)
DEFAULT_TIME_API_HOST = "worldtimeapi.org"
DEFAULT_TIME_API_PATH = "/api/timezone/America/New_York"
NUM_RGB_LEDS = 1
LED_POSITION = NUM_RGB_LEDS - 1
NUM_TEMP_SENSORS = 1
TEMP_SENSOR_POSITION = NUM_TEMP_SENSORS - 1

temp_sensor_pin = Pin(TEMPERATURE_SENSOR_IN_PIN)
wind_dir_pin = ADC(Pin(WIND_DIR_SENSOR_IN_PIN))
wifi_indicator = NeoPixel(Pin(WIFI_LED_OUT_PIN), NUM_RGB_LEDS)
wind_speed_pin = Pin(WIND_SPD_SENSOR_IN_PIN, Pin.IN)
rain_counter_pin = Pin(RAIN_CNT_SENSOR_IN_PIN, Pin.IN)
rtc = RTC()
wlan = WLAN(STA_IF)
wlan.active(True)
wind_dir_pin.atten(ADC.ATTN_11DB)
temp_sensor = DS18X20(OneWire(temp_sensor_pin))
roms = temp_sensor.scan()
weather_obj = weather.Weather(TEMPERATURE_UNITS, RAIN_UNITS, RAIN_UNITS, UPDATES_PER_HOUR, \
    DATA_POINTS_PER_UPDATE)

def set_time():
    time_utils.query_time_api(
        time_settings().get("host", DEFAULT_TIME_API_HOST),
        time_settings().get("path", DEFAULT_TIME_API_PATH),
        rtc
    )
    return get_wifi_conn_status(wlan.isconnected(), False)

def read_config_file(filename):
    json_data = None
    with open(filename) as fp:
        json_data = load(fp)
    return json_data

def wifi_settings():
    return config.get("wifi", {})

def time_settings():
    return config.get("time_api", {})

def weather_settings():
    return config.get("weather_api", {})

def database_settings():
    return config.get("database_api", {})

def wifi_led_red():
    wifi_indicator[LED_POSITION] = (2, 0, 0)  # dim red
    wifi_indicator.write()

def wifi_led_green():
    wifi_indicator[LED_POSITION] = (0, 2, 0)  # dim green
    wifi_indicator.write()

def init_wlan():
    wlan.active(True)
    wlan.config(dhcp_hostname=wifi_settings().get("hostname", "esp32-default-host"))

def connect_wifi():
    print("Attempting to connect to wifi AP!")
    ssid = b64decode(bytes(wifi_settings().get("ssid", ""), 'utf-8'))
    password = b64decode(bytes(wifi_settings().get("password", ""), 'utf-8'))
    connection_status = wlan.isconnected()
    if not connection_status:
        wlan.connect(ssid.decode("utf-8"), password.decode("utf-8"))
        while not wlan.isconnected():
            pass
        connection_status = wlan.isconnected()
    if connection_status:
        print("Successfully connected to the wifi AP!")
    return connection_status

def get_wifi_conn_status(conn_status, bool_query_time):
    if conn_status:
        wifi_led_green()
        if bool_query_time:
            conn_status = set_time()
    else:
        wifi_led_red()
        print("sorry, cant connect to wifi AP! connection --> {}".format(conn_status))
    return conn_status

def reset_rain_counter_daily(rain_timer):
    weather_obj.reset_daily_rain_count()
    rain_timer.init(period=ms_until_midnight(), mode=Timer.ONE_SHOT, callback=reset_rain_counter_daily)

def update_weather():
    global weather_update_time
    weather_obj.set_wind_direction(weather_obj.calculate_avg_wind_dir())
    weather_obj.set_temperature(weather_obj.calculate_avg_temperature())
    delta_t_s = int(ticks_diff(ticks_ms(), weather_update_time) / 1000)  # convert to seconds
    weather_obj.set_wind_speed(weather_obj.calculate_avg_wind_speed(delta_t_s))
    weather_obj.set_rain_count_hourly(weather_obj.calculate_hourly_rain())
    weather_obj.rotate_hourly_rain_buckets()
    weather_update_time = ticks_ms()
    if get_wifi_conn_status(wlan.isconnected(), False):
        update_weather_api()
        update_database()
    print(repr(weather_obj))
    weather_obj.reset_wind_gust()

def read_temperature(initial_reading=False):
    reading = 0
    try:
        temp_sensor.convert_temp()
        if initial_reading:
            sleep_ms(1000)
        reading = temp_sensor.read_temp(roms[TEMP_SENSOR_POSITION])
    except Exception as e:
        print("There was an error reading from the temp sensor.")
    return reading

def rain_counter_isr(irq):
    weather_obj.increment_rain()

def wind_speed_isr(irq):
    global wind_speed_last_intrpt  # software debounce mechanical reed switch
    if ticks_diff(ticks_ms(), wind_speed_last_intrpt) > 5:  # no less than 5ms between pulses
        wind_speed_last_intrpt = ticks_ms()
        weather_obj.add_wind_speed_pulse()

def record_weather_data_points(data_check_timer):
    global gust_start_timer
    weather_obj.add_wind_dir_reading(wind_dir_pin.read())
    weather_obj.add_temperature_reading(read_temperature())
    gust_start_timer = weather_obj.check_wind_gust(gust_start_timer)

def update_weather_api():
    creds = weather_settings().get("credentials", {})
    station_id = b64decode(bytes(creds.get("station_id", ""), 'utf-8'))
    station_key = b64decode(bytes(creds.get("station_key", ""), 'utf-8'))
    api_utils.update_weather_api(
        weather_settings().get("host", ""),
        weather_settings().get("path", ""),
        station_id.decode("utf-8"),
        station_key.decode("utf-8"),
        weather_obj.get_weather_data()
    )

def update_database():
    api_utils.send_json_to_telegraf_api(
        database_settings().get("host", ""),
        database_settings().get("port", 8080),
        database_settings().get("path", ""),
        weather_obj.get_weather_data()
    )

def ms_until_midnight():
    '''
    return the difference between future midnight and now, in ms
    '''
    now = rtc.datetime()
    return mktime((now[0], now[1], now[2] + 1, 0, 0, 0, 0, 0)) - time()

connection = ""
wifi_led_red()
config = read_config_file(CONFIG_FILE)
rain_timer = Timer(0)
data_check_timer = Timer(2)
init_wlan()
connection = get_wifi_conn_status(connect_wifi(), True)

begin_time = ticks_ms()
weather_update_time = begin_time
wind_speed_last_intrpt = begin_time
gust_start_timer = begin_time
rain_counter_pin.irq(trigger=Pin.IRQ_RISING, handler=rain_counter_isr)
wind_speed_pin.irq(trigger=Pin.IRQ_RISING, handler=wind_speed_isr)
rain_timer.init(period=ms_until_midnight(), mode=Timer.ONE_SHOT, callback=reset_rain_counter_daily)
data_check_timer.init(period=DATA_POINT_CHECK_PERIOD, mode=Timer.PERIODIC, callback=record_weather_data_points)
trash_temperature_reading = read_temperature(initial_reading=True)
del trash_temperature_reading  # first reading is always wrong so just put it in the garbage
while True:
    sleep_ms(100)
    if ticks_diff(ticks_ms(), weather_update_time) > WEATHER_UPDATE_PERIOD :
        update_weather()
