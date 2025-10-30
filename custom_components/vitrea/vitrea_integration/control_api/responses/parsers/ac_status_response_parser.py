# parsers/ac_status_response_parser.py
from .base import ResponseParser
import logging
from datetime import datetime
from ....utils.enums import ThermostatFanSpeeds, ThermostatModes, AirConditionerType, ThermostatTemperatureModes

logger = logging.getLogger(__name__)

class ACStatusResponseParser(ResponseParser):
    def parse(self, response):
        """
        Parses an air conditioning status response from the VBox.

        Expected format: S:Axxx:K:S:PP...P <CR><LF>
        Where:
        - Axxx is the air conditioning unit ID
        - K is the key number (always 1 for AC)
        - S is the status of the AC (On/Off)
        - PP...P are additional parameters
        
        :param response: The raw response string from the VBox.
        :return: A structured dictionary with the AC status suitable for database insertion.
        """
        try:
            response = response.strip()
            parts = response.split(':')
            if len(parts) < 4:
                raise ValueError("Incomplete AC status response")

            ac_id = int(parts[1][1:])
            status = parts[3] == 'O' # On = ASCII O, Off = ASCII F
            params = parts[4:]
            if '\ufffd' in params[0]:
                mode = ThermostatModes.AUTO
                fan_speed = ThermostatFanSpeeds.AUTO
            else: 
                mode = ThermostatModes(int(params[0][0]))
                fan_speed = ThermostatFanSpeeds(int(params[0][1]))
            set_temperature = int(params[1]) if '\ufffd' not in params[1] else 25
            measured_temperature = int(params[2]) if '\ufffd' not in params[2] else 25
            thermostat_type = AirConditionerType(int(params[3]))
            relay_state = params[4] == 'O' # On = ASCII O, Off = ASCII F - valid for FanCoil and Floor Heating
            temperature_mode = ThermostatTemperatureModes(int(params[5])) if '\ufffd' not in params[5] else ThermostatTemperatureModes.NA
            ac_status_record = {
                'type': 'ac_status',
                'ac_id': ac_id,
                'status': status,
                'parameters': {
                    'mode': mode,
                    'fan_speed': fan_speed,
                    'set_temperature': set_temperature,
                    'measured_temperature': measured_temperature,
                    'thermostat_type': thermostat_type,
                    'relay_state': relay_state,
                    'temperature_mode': temperature_mode
                },
                'timestamp': datetime.now()  # Timestamp for when the response was received
            }

            return ac_status_record

        except Exception as e:
            logger.error(f"Error parsing AC status response: {response} - Error: {e}")
            raise

