"""
Unit tests for cisco_deskpro_mqtt.py

Tests the MQTT bridge functionality including:
- Configuration management
- Device status fetching
- MQTT discovery publishing
- MQTT status publishing
- MQTT client setup
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, call
import json
import os
from pathlib import Path
import sys

# Add parent directory to path to import the module under test
sys.path.insert(0, str(Path(__file__).parent.parent))

import paho.mqtt.client as mqtt
from deskpro import DeskproError, Deskpro
import cisco_deskpro_mqtt as bridge


class TestConfigInitialization(unittest.TestCase):
    """Test Config dataclass initialization and environment variable loading"""

    def test_config_instance_has_all_required_fields(self):
        """Config instance should have all required configuration fields"""
        config = bridge.Config()
        self.assertIsNotNone(config.deskpro_host)
        self.assertIsNotNone(config.deskpro_username)
        self.assertIsNotNone(config.deskpro_password)
        self.assertIsNotNone(config.mqtt_host)
        self.assertIsNotNone(config.mqtt_port)
        self.assertIsNotNone(config.device_name)
        self.assertIsNotNone(config.device_id)
        self.assertIsNotNone(config.poll_interval_ms)

    def test_config_instance_types_are_correct(self):
        """Config fields should have correct types"""
        config = bridge.Config()
        self.assertIsInstance(config.deskpro_host, str)
        self.assertIsInstance(config.deskpro_username, str)
        self.assertIsInstance(config.deskpro_password, str)
        self.assertIsInstance(config.mqtt_host, str)
        self.assertIsInstance(config.mqtt_port, int)
        self.assertIsInstance(config.deskpro_verify_ssl, bool)
        self.assertIsInstance(config.mqtt_tls, bool)

    def test_config_mqtt_credentials_can_be_none(self):
        """Config should support optional MQTT credentials"""
        config = bridge.Config()
        # mqtt_username and mqtt_password can be None or str
        self.assertTrue(config.mqtt_username is None or isinstance(config.mqtt_username, str))
        self.assertTrue(config.mqtt_password is None or isinstance(config.mqtt_password, str))

    def test_config_instance_has_topic_root(self):
        """Config instance should initialize topic_root in __post_init__"""
        config = bridge.Config()
        self.assertIsNotNone(config.topic_root)
        self.assertIsInstance(config.topic_root, str)
        self.assertIn(config.discovery_prefix, config.topic_root)
        self.assertIn(config.device_id, config.topic_root)


class TestSensorConfiguration(unittest.TestCase):
    """Test the SENSORS list configuration"""

    def test_sensors_list_not_empty(self):
        """SENSORS should not be empty"""
        self.assertGreater(len(bridge.SENSORS), 0)

    def test_sensors_have_required_attributes(self):
        """Each sensor should have required attributes"""
        for sensor in bridge.SENSORS:
            self.assertIsNotNone(sensor.key)
            self.assertIsNotNone(sensor.name)
            self.assertIsNotNone(sensor.icon)
            self.assertIsNotNone(sensor.deskpro_key)

    def test_sensor_keys_are_unique(self):
        """All sensor keys should be unique"""
        keys = [s.key for s in bridge.SENSORS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_sensor_deskpro_keys_are_unique(self):
        """All sensor deskpro_keys should be unique"""
        deskpro_keys = [s.deskpro_key for s in bridge.SENSORS]
        self.assertEqual(len(deskpro_keys), len(set(deskpro_keys)))

    def test_sensors_have_expected_keys(self):
        """There should be a 1:1 mapping between bridge and deskpro sensors"""
        
        for mapkey in Deskpro.Statii.STATUSMAP.keys():
            self.assertIn(
                mapkey,
                [s.deskpro_key for s in bridge.SENSORS], 
                f"Deskpro key {mapkey} is not mapped to any sensor in the bridge"
            )
            
        # less likely, but also check to ensure that the bridge doesn't have any sensors that aren't mapped to deskpro keys, 
        # since that would be suspicious.  
        # If we add new sensors to the bridge, but forget to add them to the deskpro parsing, that would be a problem, and this test would catch that.
        
        for sensor in bridge.SENSORS:
            self.assertIn(
                sensor.deskpro_key,
                Deskpro.Statii.STATUSMAP.keys(),
                f"Sensor {sensor.key} is mapped to deskpro key {sensor.deskpro_key}, but that key is not in the Deskpro status map"
            )


class TestBuildDeskproClient(unittest.TestCase):
    """Test build_deskpro_client function"""

    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_build_deskpro_client_creates_client(self, mock_config):
        """build_deskpro_client should create and return a Deskpro client"""
        mock_config.deskpro_host = "10.0.0.1"
        mock_config.deskpro_username = "admin"
        mock_config.deskpro_password = "password"
        mock_config.deskpro_verify_ssl = False
        
        client = bridge.build_deskpro_client()
        
        self.assertIsInstance(client, Deskpro)
        # Verify the client was constructed with the correct URL
        self.assertIn("10.0.0.1", client.url)

    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_build_deskpro_client_uses_config_values(self, mock_config):
        """build_deskpro_client should use values from CONFIG"""
        mock_config.deskpro_host = "192.168.1.100"
        mock_config.deskpro_username = "testuser"
        mock_config.deskpro_password = "testpass"
        mock_config.deskpro_verify_ssl = True
        
        client = bridge.build_deskpro_client()
        
        # Verify the URL contains the correct host
        self.assertIn("192.168.1.100", client.url)
        # Verify SSL verification is enabled
        self.assertTrue(client.certverify)


class MockDeskproTestBase(unittest.TestCase):
    """Base class providing helper methods for tests that mock Deskpro"""

    def setUp(self):
        """Set up common test fixtures"""
        self.mock_deskpro = MagicMock(spec=Deskpro)
        self.mock_status = {
            "ambient_noise_level": "32",
            "sound_level": "41",
            "people_count": "1",
            "room_in_use": "True",
            "t3_alarm_detected": "False",
            "ambient_temperature": "24.0",
            "relative_humidity": "50",
            "standby_state": "Off",
        }

    def create_test_status(self, **overrides):
        """Create a test status dict with optional overrides"""
        status = self.mock_status.copy()
        status.update(overrides)
        return status


class TestGetDeviceStatus(MockDeskproTestBase):
    """Test get_device_status function"""

    @patch("cisco_deskpro_mqtt.DESKPRO_CLIENT")
    def test_get_device_status_success(self, mock_client):
        """get_device_status should return status dict on success"""
        mock_client.update = MagicMock()
        mock_client.status = self.mock_status.copy()
        
        result = bridge.get_device_status()
        
        self.assertIsInstance(result, dict)
        mock_client.update.assert_called_once()

    @patch("cisco_deskpro_mqtt.DESKPRO_CLIENT")
    def test_get_device_status_returns_all_keys(self, mock_client):
        """get_device_status should return all sensor keys"""
        mock_client.update = MagicMock()
        mock_client.status = self.mock_status.copy()
        
        result = bridge.get_device_status()
        
        for sensor in bridge.SENSORS:
            self.assertIn(sensor.key, result)

    @patch("cisco_deskpro_mqtt.DESKPRO_CLIENT")
    def test_get_device_status_maps_deskpro_keys(self, mock_client):
        """get_device_status should map from deskpro_key to sensor key"""
        deskpro_status = {
            "AmbientNoiseLevel": "32",
            "SoundLevel": "41",
            "PeopleCount": "1",
            "RoomInUse": "True",
            "T3AlarmDetected": "False",
            "AmbientTemperature": "24.0",
            "RelativeHumidity": "50",
            "StandbyState": "Off",
        }
        mock_client.update = MagicMock()
        mock_client.status = deskpro_status
        
        result = bridge.get_device_status()
        
        self.assertEqual(result["ambient_noise_level"], "32")
        self.assertEqual(result["sound_level"], "41")
        self.assertEqual(result["people_count"], "1")

    @patch("cisco_deskpro_mqtt.DESKPRO_CLIENT")
    def test_get_device_status_on_deskpro_error(self, mock_client):
        """get_device_status should return unavailable on DeskproError"""
        mock_client.update = MagicMock(side_effect=DeskproError("Connection failed"))
        
        result = bridge.get_device_status()
        
        # All keys should be "unavailable"
        for sensor in bridge.SENSORS:
            self.assertEqual(result[sensor.key], "unavailable")

    @patch("cisco_deskpro_mqtt.DESKPRO_CLIENT")
    def test_get_device_status_initializes_unavailable(self, mock_client):
        """get_device_status should initialize all keys as unavailable"""
        mock_client.update = MagicMock()
        # Return partial data
        mock_client.status = {"AmbientNoiseLevel": "30"}
        
        result = bridge.get_device_status()
        
        # All keys should exist
        for sensor in bridge.SENSORS:
            self.assertIn(sensor.key, result)

    @patch("cisco_deskpro_mqtt.DESKPRO_CLIENT")
    def test_get_device_status_missing_deskpro_key_unavailable(self, mock_client):
        """get_device_status should mark missing keys as unavailable"""
        mock_client.update = MagicMock()
        mock_client.status = {"AmbientNoiseLevel": "32"}  # Only one key
        
        result = bridge.get_device_status()
        
        # First key should be available, others unavailable
        self.assertEqual(result["ambient_noise_level"], "32")
        self.assertEqual(result["sound_level"], "unavailable")


class TestPublishDiscovery(MockDeskproTestBase):
    """Test publish_discovery function"""

    def setUp(self):
        """Set up common test fixtures"""
        super().setUp()
        self.mock_mqtt_client = MagicMock(spec=mqtt.Client)

    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_publish_discovery_publishes_for_each_sensor(self, mock_config):
        """publish_discovery should publish config for each sensor"""
        mock_config.topic_root = "homeassistant/sensor/test_device"
        mock_config.discovery_prefix = "homeassistant"
        mock_config.device_id = "test_device"
        
        bridge.publish_discovery(self.mock_mqtt_client, self.mock_status)
        
        # Should publish once per sensor
        self.assertEqual(self.mock_mqtt_client.publish.call_count, len(bridge.SENSORS))

    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_publish_discovery_payload_structure(self, mock_config):
        """publish_discovery should publish valid discovery payloads"""
        mock_config.topic_root = "homeassistant/sensor/test_device"
        mock_config.discovery_prefix = "homeassistant"
        mock_config.device_id = "test_device"
        mock_config.device_name = "Test Device"
        
        bridge.publish_discovery(self.mock_mqtt_client, self.mock_status)
        
        # Check first call to verify structure
        call_args = self.mock_mqtt_client.publish.call_args_list[0]
        topic = call_args[0][0]
        payload_str = call_args[0][1]
        
        # Should include device config
        self.assertIn("homeassistant/sensor", topic)
        payload = json.loads(payload_str)
        self.assertIn("unique_id", payload)
        self.assertIn("name", payload)
        self.assertIn("state_topic", payload)
        self.assertIn("device", payload)

    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_publish_discovery_includes_device_class(self, mock_config):
        """publish_discovery should include device_class for applicable sensors"""
        mock_config.topic_root = "homeassistant/sensor/test_device"
        mock_config.discovery_prefix = "homeassistant"
        mock_config.device_id = "test_device"
        mock_config.device_name = "Test Device"
        
        bridge.publish_discovery(self.mock_mqtt_client, self.mock_status)
        
        # temperature sensor should have device_class
        payloads = [json.loads(call[0][1]) for call in self.mock_mqtt_client.publish.call_args_list]
        temp_payload = next((p for p in payloads if "temperature" in p.get("name", "").lower()), None)
        
        if temp_payload:
            self.assertEqual(temp_payload.get("device_class"), "temperature")

    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_publish_discovery_includes_unit_of_measurement(self, mock_config):
        """publish_discovery should include unit_of_measurement when specified"""
        mock_config.topic_root = "homeassistant/sensor/test_device"
        mock_config.discovery_prefix = "homeassistant"
        mock_config.device_id = "test_device"
        mock_config.device_name = "Test Device"
        
        bridge.publish_discovery(self.mock_mqtt_client, self.mock_status)
        
        payloads = [json.loads(call[0][1]) for call in self.mock_mqtt_client.publish.call_args_list]
        sound_payload = next((p for p in payloads if "Sound Level" in p.get("name", "")), None)
        
        if sound_payload:
            self.assertEqual(sound_payload.get("unit_of_measurement"), "dB")

    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_publish_discovery_uses_retain_flag(self, mock_config):
        """publish_discovery should use retain=True for discovery messages"""
        mock_config.topic_root = "homeassistant/sensor/test_device"
        mock_config.discovery_prefix = "homeassistant"
        mock_config.device_id = "test_device"
        mock_config.device_name = "Test Device"
        
        bridge.publish_discovery(self.mock_mqtt_client, self.mock_status)
        
        # Check that retain=True is passed in each call
        for call_args in self.mock_mqtt_client.publish.call_args_list:
            # Third positional argument or 'retain' keyword argument should be True
            if len(call_args[0]) > 2:
                self.assertTrue(call_args[0][2])
            else:
                self.assertTrue(call_args[1].get("retain", False))


class TestPublishStatus(MockDeskproTestBase):
    """Test publish_status function"""

    def setUp(self):
        """Set up common test fixtures"""
        super().setUp()
        self.mock_mqtt_client = MagicMock(spec=mqtt.Client)

    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_publish_status_publishes_for_each_sensor(self, mock_config):
        """publish_status should publish state for each sensor"""
        mock_config.topic_root = "homeassistant/sensor/test_device"
        
        bridge.publish_status(self.mock_mqtt_client, self.mock_status)
        
        # Should publish once per sensor
        self.assertEqual(self.mock_mqtt_client.publish.call_count, len(bridge.SENSORS))

    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_publish_status_publishes_correct_values(self, mock_config):
        """publish_status should publish the correct status values"""
        mock_config.topic_root = "homeassistant/sensor/test_device"
        
        bridge.publish_status(self.mock_mqtt_client, self.mock_status)
        
        # Check that values were published
        publish_calls = self.mock_mqtt_client.publish.call_args_list
        
        # Find the ambient_noise_level publish call
        noise_call = next(
            (call for call in publish_calls if "ambient_noise_level" in call[0][0]),
            None
        )
        self.assertIsNotNone(noise_call)
        self.assertEqual(noise_call[0][1], "32")

    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_publish_status_handles_unavailable(self, mock_config):
        """publish_status should publish unavailable when value is unavailable"""
        mock_config.topic_root = "homeassistant/sensor/test_device"
        status = self.create_test_status(sound_level="unavailable")
        
        bridge.publish_status(self.mock_mqtt_client, status)
        
        # Check sound_level publish
        sound_call = next(
            (call for call in self.mock_mqtt_client.publish.call_args_list 
             if "sound_level" in call[0][0]),
            None
        )
        self.assertIsNotNone(sound_call)
        self.assertEqual(sound_call[0][1], "unavailable")

    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_publish_status_handles_none_values(self, mock_config):
        """publish_status should convert None to unavailable"""
        mock_config.topic_root = "homeassistant/sensor/test_device"
        status = self.create_test_status(people_count=None)
        status["people_count"] = None
        
        bridge.publish_status(self.mock_mqtt_client, status)
        
        # Check that None was converted to "unavailable"
        people_call = next(
            (call for call in self.mock_mqtt_client.publish.call_args_list 
             if "people_count" in call[0][0]),
            None
        )
        self.assertIsNotNone(people_call)
        self.assertEqual(people_call[0][1], "unavailable")

    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_publish_status_uses_retain_flag(self, mock_config):
        """publish_status should use retain=True"""
        mock_config.topic_root = "homeassistant/sensor/test_device"
        
        bridge.publish_status(self.mock_mqtt_client, self.mock_status)
        
        # Check that retain=True is passed
        for call_args in self.mock_mqtt_client.publish.call_args_list:
            if len(call_args[0]) > 2:
                self.assertTrue(call_args[0][2])


class TestBuildMqttClient(unittest.TestCase):
    """Test build_mqtt_client function"""

    @patch("cisco_deskpro_mqtt.mqtt.Client")
    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_build_mqtt_client_creates_client(self, mock_config, mock_mqtt_class):
        """build_mqtt_client should create and return an MQTT client"""
        mock_config.device_id = "test_device"
        mock_config.topic_root = "homeassistant/sensor/test_device"
        mock_client = MagicMock()
        mock_mqtt_class.return_value = mock_client
        
        result = bridge.build_mqtt_client()
        
        self.assertIsNotNone(result)
        mock_mqtt_class.assert_called_once()

    @patch("cisco_deskpro_mqtt.mqtt.Client")
    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_build_mqtt_client_sets_credentials_when_provided(self, mock_config, mock_mqtt_class):
        """build_mqtt_client should set credentials if provided"""
        mock_config.device_id = "test_device"
        mock_config.topic_root = "homeassistant/sensor/test_device"
        mock_config.mqtt_username = "user"
        mock_config.mqtt_password = "pass"
        mock_client = MagicMock()
        mock_mqtt_class.return_value = mock_client
        
        bridge.build_mqtt_client()
        
        mock_client.username_pw_set.assert_called_once_with("user", "pass")

    @patch("cisco_deskpro_mqtt.mqtt.Client")
    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_build_mqtt_client_skips_credentials_when_not_provided(self, mock_config, mock_mqtt_class):
        """build_mqtt_client should skip credentials if not provided"""
        mock_config.device_id = "test_device"
        mock_config.topic_root = "homeassistant/sensor/test_device"
        mock_config.mqtt_username = None
        mock_config.mqtt_password = None
        mock_client = MagicMock()
        mock_mqtt_class.return_value = mock_client
        
        bridge.build_mqtt_client()
        
        mock_client.username_pw_set.assert_not_called()

    @patch("cisco_deskpro_mqtt.mqtt.Client")
    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_build_mqtt_client_sets_tls_when_enabled(self, mock_config, mock_mqtt_class):
        """build_mqtt_client should set TLS if enabled"""
        mock_config.device_id = "test_device"
        mock_config.topic_root = "homeassistant/sensor/test_device"
        mock_config.mqtt_username = None
        mock_config.mqtt_tls = True
        mock_client = MagicMock()
        mock_mqtt_class.return_value = mock_client
        
        bridge.build_mqtt_client()
        
        mock_client.tls_set.assert_called_once()

    @patch("cisco_deskpro_mqtt.mqtt.Client")
    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_build_mqtt_client_skips_tls_when_disabled(self, mock_config, mock_mqtt_class):
        """build_mqtt_client should skip TLS if disabled"""
        mock_config.device_id = "test_device"
        mock_config.topic_root = "homeassistant/sensor/test_device"
        mock_config.mqtt_username = None
        mock_config.mqtt_tls = False
        mock_client = MagicMock()
        mock_mqtt_class.return_value = mock_client
        
        bridge.build_mqtt_client()
        
        mock_client.tls_set.assert_not_called()

    @patch("cisco_deskpro_mqtt.mqtt.Client")
    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_build_mqtt_client_sets_will_message(self, mock_config, mock_mqtt_class):
        """build_mqtt_client should set LWT (last will and testament) message"""
        mock_config.device_id = "test_device"
        mock_config.topic_root = "homeassistant/sensor/test_device"
        mock_config.mqtt_username = None
        mock_config.mqtt_tls = False
        mock_client = MagicMock()
        mock_mqtt_class.return_value = mock_client
        
        bridge.build_mqtt_client()
        
        # Should set will message
        mock_client.will_set.assert_called_once()
        call_args = mock_client.will_set.call_args[0]
        self.assertIn("availability", call_args[0])
        self.assertEqual(call_args[1], "offline")

    @patch("cisco_deskpro_mqtt.mqtt.Client")
    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_build_mqtt_client_sets_callbacks(self, mock_config, mock_mqtt_class):
        """build_mqtt_client should set on_connect and on_disconnect callbacks"""
        mock_config.device_id = "test_device"
        mock_config.topic_root = "homeassistant/sensor/test_device"
        mock_config.mqtt_username = None
        mock_config.mqtt_tls = False
        mock_client = MagicMock()
        mock_mqtt_class.return_value = mock_client
        
        bridge.build_mqtt_client()
        
        self.assertIsNotNone(mock_client.on_connect)
        self.assertIsNotNone(mock_client.on_disconnect)

    @patch("cisco_deskpro_mqtt.mqtt.Client")
    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_mqtt_on_connect_callback_success(self, mock_config, mock_mqtt_class):
        """MQTT on_connect callback should publish online and log on success"""
        mock_config.device_id = "test_device"
        mock_config.topic_root = "homeassistant/sensor/test_device"
        mock_config.mqtt_username = None
        mock_config.mqtt_tls = False
        mock_config.mqtt_host = "localhost"
        mock_config.mqtt_port = 1883
        
        mock_client_instance = MagicMock()
        mock_mqtt_class.return_value = mock_client_instance
        
        with patch("cisco_deskpro_mqtt.log") as mock_log:
            bridge.build_mqtt_client()
            
            # Get the on_connect callback and call it with success
            on_connect_cb = mock_client_instance.on_connect
            # Create a mock reason_code with is_success() method
            mock_reason_code = MagicMock()
            mock_reason_code.is_failure = False
            on_connect_cb(mock_client_instance, None, {}, mock_reason_code, None)
            
            # Should publish online and log success
            mock_client_instance.publish.assert_called_once()
            call_args = mock_client_instance.publish.call_args[0]
            self.assertEqual(call_args[1], "online")

    @patch("cisco_deskpro_mqtt.mqtt.Client")
    @patch("cisco_deskpro_mqtt.CONFIG")
    def test_mqtt_on_connect_callback_failure(self, mock_config, mock_mqtt_class):
        """MQTT on_connect callback should log error on failure"""
        mock_config.device_id = "test_device"
        mock_config.topic_root = "homeassistant/sensor/test_device"
        mock_config.mqtt_username = None
        mock_config.mqtt_tls = False
        
        mock_client_instance = MagicMock()
        mock_mqtt_class.return_value = mock_client_instance
        
        with patch("cisco_deskpro_mqtt.log") as mock_log:
            bridge.build_mqtt_client()
            
            # Get the on_connect callback and call it with error code
            on_connect_cb = mock_client_instance.on_connect
            # Create a mock reason_code with is_success() returning False
            mock_reason_code = MagicMock()
            mock_reason_code.is_failure = True
            on_connect_cb(mock_client_instance, None, {}, mock_reason_code, None)
            
            # Should not publish, should log error
            mock_log.error.assert_called()


class TestDeviceInfoTemplate(unittest.TestCase):
    """Test DEVICE_INFO_TEMPLATE structure"""

    def test_device_info_has_required_fields(self):
        """DEVICE_INFO_TEMPLATE should have required fields"""
        self.assertIn("identifiers", bridge.DEVICE_INFO_TEMPLATE)
        self.assertIn("name", bridge.DEVICE_INFO_TEMPLATE)
        self.assertIn("manufacturer", bridge.DEVICE_INFO_TEMPLATE)
        self.assertIn("model", bridge.DEVICE_INFO_TEMPLATE)

    def test_device_info_identifiers_is_list(self):
        """DEVICE_INFO_TEMPLATE identifiers should be a list"""
        self.assertIsInstance(bridge.DEVICE_INFO_TEMPLATE["identifiers"], list)

    def test_device_info_manufacturer_is_cisco(self):
        """DEVICE_INFO_TEMPLATE manufacturer should be Cisco"""
        self.assertEqual(bridge.DEVICE_INFO_TEMPLATE["manufacturer"], "Cisco")

    def test_device_info_model_is_desk_pro(self):
        """DEVICE_INFO_TEMPLATE model should be Desk Pro"""
        self.assertEqual(bridge.DEVICE_INFO_TEMPLATE["model"], "Desk Pro")


if __name__ == "__main__":
    unittest.main()
