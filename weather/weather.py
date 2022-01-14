import time

TEMPERATURE_KEY = "Temperature"
WIND_KEY = "Wind"
WIND_GUST_KEY = "Gust"
WIND_SPEED_KEY = "Speed"
WIND_DIRECTION_KEY = "Direction"
RAIN_KEY = "Rain"
RAIN_COUNT_KEY = "Count"
RAIN_RATE_KEY = "Rate"
RAIN_COUNT_CONSTANT = 0.2794  # mm's rain
ANEMOMETER_CONSTANT = 2.4  # km/h
SECONDS_PER_HOUR = 3_600
WIND_DIR_DICT = {
    "E/NE": range(123, 132),
    "E": range(132, 165),
    "S/SE": range(165, 242),
    "SE": range(242, 297),
    "E/SE": range(297, 397),
    "S": range(397, 709),
    "NE": range(709, 927),
    "N/NE": range(927, 1165),
    "W/SW": range(1165, 1458),
    "S/SW": range(1458, 1520),
    "SW": range(1520, 1695),
    "N/NW": range(1695, 2100),
    "N": range(2100, 2480),
    "W/NW": range(2480, 2863),
    "NW": range(2863, 3403),
    "W": range(3403, 3800)
}
WIND_ANGLE_DICT = {
    "N": 0,
    "N/NE": 22.5,
    "NE": 45,
    "E/NE": 67.5,
    "E": 90,
    "E/SE": 112.5,
    "SE": 135,
    "S/SE": 157.5,
    "S": 180,
    "S/SW": 202.5,
    "SW": 225,
    "W/SW": 247.5,
    "W": 270,
    "W/NW": 292.5,
    "NW": 315,
    "N/NW": 337.5
}


class Weather:

    def __init__(self, temp_units="F", speed_units="MPH", rain_units="inches"):
        self.temp_units = temp_units
        self.speed_units = speed_units
        self.rain_units = rain_units
        self.__rain_count = 0.0
        self.__rain_rate = 0.0
        self.__rain_rate_factor = 0.0
        self.__wind_direction = "N"
        self.__wind_speed = 0.0
        self.__wind_speed_pulses = 0
        self.__max_wind_gust = 0.0
        self.__last_wind_speed_pulse = 0
        self.__temperature = 0.0
        self.__weather_dict = {
            RAIN_KEY: {
                RAIN_COUNT_KEY: self.__rain_count,
                RAIN_RATE_KEY: self.__rain_rate
            },
            WIND_KEY: {
                WIND_DIRECTION_KEY: self.__wind_direction,
                WIND_SPEED_KEY: self.__wind_speed,
                WIND_GUST_KEY: self.__max_wind_gust
            },
            TEMPERATURE_KEY: self.__temperature
        }

    def __repr__(self):
        return repr(self.__weather_dict)

    def get_rain_count(self):
        return self.__rain_count

    def set_rain_count(self, val):
        self.__rain_count = val
        self.__weather_dict[RAIN_KEY][RAIN_COUNT_KEY] = self.__rain_count

    def get_rain_rate(self):
        return self.__rain_rate

    def set_rain_rate(self, val):
        self.__rain_rate = val
        self.__weather_dict[RAIN_KEY][RAIN_RATE_KEY] = self.__rain_rate

    def get_rain_rate_factor(self):
        return self.__rain_rate_factor

    def set_rain_rate_factor(self, val):
        self.__rain_rate_factor = val

    def get_wind_gust(self):
        return self.__max_wind_gust

    def set_wind_gust(self, val):
        self.__max_wind_gust = val
        self.__weather_dict[WIND_KEY][WIND_GUST_KEY] = self.__max_wind_gust

    def get_wind_direction(self):
        return self.__wind_direction

    def set_wind_direction(self, adc_val):
        self.__wind_direction = Weather.wind_adc_to_direction(adc_val)
        self.__weather_dict[WIND_KEY][WIND_DIRECTION_KEY] = Weather.direction_to_angle(self.__wind_direction)

    def get_wind_speed(self):
        return self.__wind_speed

    def set_wind_speed(self, val):
        self.__wind_speed = val
        self.__weather_dict[WIND_KEY][WIND_SPEED_KEY] = self.__wind_speed

    def get_temperature(self):
        return self.__temperature

    def set_temperature(self, val):
        if not self.temp_units == "C":
            val = Weather.celsius2fahrenheit(val)
        self.__temperature = Weather.two_decimals(val)
        self.__weather_dict[TEMPERATURE_KEY] = self.__temperature

    def increment_rain(self):
        if self.rain_units == "mm":
            rain_count = self.get_rain_count() + RAIN_COUNT_CONSTANT
            rain_rate = self.get_rain_rate_factor() + RAIN_COUNT_CONSTANT
        else:
            rain_unit = Weather.millimeters2inches(RAIN_COUNT_CONSTANT)
            rain_count = self.get_rain_count() + rain_unit
            rain_rate = self.get_rain_rate_factor() + rain_unit
        self.set_rain_count(Weather.two_decimals(rain_count))
        self.set_rain_rate_factor(Weather.two_decimals(rain_rate))

    def add_wind_speed_pulse(self):
        self.__wind_speed_pulses += 1
        now = time.ticks_ms()
        self.wind_gust()
        self.__last_wind_speed_pulse = now

    def wind_gust(self):
        if self.__last_wind_speed_pulse:
            delta_t_wind_ticks = time.ticks_diff(time.ticks_ms(), self.__last_wind_speed_pulse)
            current_gust = self.calculate_wind_gust(delta_t_wind_ticks)
            if current_gust > self.__max_wind_gust:
                self.set_wind_gust(Weather.two_decimals(current_gust))
            self.__last_wind_speed_pulse = time.ticks_ms()

    def calculate_wind_gust(self, delta_time_ms):
        if self.__wind_speed_pulses == 0:
            gust = 0.0
        else:
            delta_time_s = (delta_time_ms / 1000.0)  # need delta in s to match ANEMOMETER_CONSTANT
            mph_conversion_divisor = self.get_mph_divisor()
            gust = ANEMOMETER_CONSTANT / (mph_conversion_divisor * delta_time_s)
        return gust

    def calculate_avg_wind_speed(self, delta_time):
        mph_conversion_divisor = self.get_mph_divisor()
        avg_wind_spd = ANEMOMETER_CONSTANT * self.__wind_speed_pulses / (mph_conversion_divisor * delta_time)
        self.__wind_speed_pulses = 0
        return Weather.two_decimals(avg_wind_spd)

    def get_mph_divisor(self):
        mph_conversion_divisor = 1.0
        if not self.speed_units == "km/h":
            mph_conversion_divisor = 1.6093
        return mph_conversion_divisor

    def calculate_rain_rate(self, time_since_last_update):
        rain_rate = self.get_rain_rate_factor() * (SECONDS_PER_HOUR / time_since_last_update)
        self.reset_rain_rate_factor()
        return Weather.two_decimals(rain_rate)

    def reset_wind_gust(self):
        self.set_wind_gust(0.0)

    def reset_daily_rain_count(self):
        self.set_rain_count(0.0)

    def reset_rain_rate_factor(self):
        self.set_rain_rate_factor(0.0)

    @staticmethod
    def wind_adc_to_direction(wind_adc_val):
        wind_direction = None
        for direction, voltage_range in WIND_DIR_DICT.items():
            if wind_adc_val in voltage_range:
                wind_direction = direction
                break
        return wind_direction if wind_direction else "ERROR"

    @staticmethod
    def two_decimals(val):
        return float("{:.2f}".format(val))

    @staticmethod
    def direction_to_angle(dir_val):
        return WIND_ANGLE_DICT.get(dir_val, 0)

    @staticmethod
    def celsius2fahrenheit(val):
        return val * 1.8 + 32

    @staticmethod
    def millimeters2inches(val):
        return val / 25.4  # 25.4 mm / inch
