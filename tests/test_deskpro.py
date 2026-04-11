import unittest
from unittest.mock import Mock, patch, MagicMock
import xml.etree.ElementTree as ET
import requests
from pathlib import Path

# Import the classes to test
import sys
import os
sys.path.insert(0, str(Path(__file__).parent.parent))
from deskpro import Deskpro, DeskproError

IPNUMBER="192.168.1.100"
DEFAULTUSERNAME="some user"
DEFAULTPASSWORD="some password"
EXAMPLE_XML_PATH = os.path.join( Path(__file__).parent, "example.xml")


def load_example_xml_bytes() -> bytes:
    """
    Load and return the contents of example.xml as bytes
    Use this when you want to test fetchStatus by mocking session.get(), since it returns bytes.
    """
    with open(EXAMPLE_XML_PATH, "rb") as f:
        return f.read()

def load_example_xml() -> str:
    """
    Load and return the contents of example.xml as a string
    Use this when you want to test anything other than fetchStatus, because everything else uses strings
    """
    b = load_example_xml_bytes()
    return b.decode("utf-8")

class TestDeskproError(unittest.TestCase):
    """Test the DeskproError exception class"""

    def test_deskpro_error_is_exception(self):
        """DeskproError should be an Exception"""
        self.assertTrue(issubclass(DeskproError, Exception))

    def test_deskpro_error_message(self):
        """DeskproError should support error messages"""
        error = DeskproError("Test error message")
        self.assertEqual(str(error), "Test error message")


class TestDeskproInitialization(unittest.TestCase):
    """Test Deskpro class initialization"""
    

    def test_init_with_required_parameters(self):
        """Deskpro should initialize with hostname, username, and password"""
        
        deskpro = Deskpro(IPNUMBER, DEFAULTUSERNAME, DEFAULTPASSWORD)
        self.assertEqual(deskpro.url, f"https://{IPNUMBER}/status.xml")
        self.assertIsNotNone(deskpro.auth)
        self.assertFalse(deskpro.certverify)

    def test_init_with_certverify_true(self):
        """Deskpro should support certverify parameter"""
        deskpro = Deskpro(IPNUMBER, DEFAULTUSERNAME, DEFAULTPASSWORD, certverify=True)
        self.assertTrue(deskpro.certverify)

    def test_init_with_certverify_false(self):
        """Deskpro should default certverify to False"""
        deskpro = Deskpro(IPNUMBER, DEFAULTUSERNAME, DEFAULTPASSWORD, certverify=False)
        self.assertFalse(deskpro.certverify)

    def test_init_default_status(self):
        """Deskpro should initialize with empty status"""
        deskpro = Deskpro(IPNUMBER, DEFAULTUSERNAME, DEFAULTPASSWORD)
        self.assertIsNotNone(deskpro.status)
        self.assertEqual(deskpro.status, Deskpro.Statii.DefaultStatus())

    def test_init_session_created(self):
        """Deskpro should create a requests.Session"""
        deskpro = Deskpro(IPNUMBER, DEFAULTUSERNAME, DEFAULTPASSWORD)
        self.assertIsInstance(deskpro.session, requests.Session)


class TestDeskproFetchStatus(unittest.TestCase):
    """Test Deskpro.fetchStatus() method"""

    def setUp(self):
        """Set up test fixtures"""
        self.deskpro = Deskpro(IPNUMBER, DEFAULTUSERNAME, DEFAULTPASSWORD)
        self.valid_xml_bytes = load_example_xml_bytes()
        self.valid_xml = load_example_xml()

    def test_fetchstatus_success(self):
        """fetchStatus should return XML content on successful response"""
        with patch.object(self.deskpro.session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = self.valid_xml_bytes
            mock_get.return_value = mock_response

            result = self.deskpro.fetchStatus()
            self.assertEqual(result, self.valid_xml)

    def test_fetchstatus_calls_correct_url(self):
        """fetchStatus should call the correct URL with auth"""
        with patch.object(self.deskpro.session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = self.valid_xml_bytes
            mock_get.return_value = mock_response

            self.deskpro.fetchStatus()
            mock_get.assert_called_once_with(
                self.deskpro.url,
                auth=self.deskpro.auth,
                verify=False
            )

    def test_fetchstatus_non_200_status(self):
        """fetchStatus should raise DeskproError on non-200 status"""
        with patch.object(self.deskpro.session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_get.return_value = mock_response

            with self.assertRaises(DeskproError) as context:
                self.deskpro.fetchStatus()
            self.assertIn("401", str(context.exception))

    def test_fetchstatus_404_error(self):
        """fetchStatus should raise DeskproError on 404"""
        with patch.object(self.deskpro.session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            with self.assertRaises(DeskproError):
                self.deskpro.fetchStatus()

    def test_fetchstatus_no_content(self):
        """fetchStatus should raise DeskproError when response.content is None"""
        with patch.object(self.deskpro.session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = None
            mock_get.return_value = mock_response

            with self.assertRaises(DeskproError) as context:
                self.deskpro.fetchStatus()
            self.assertIn("No content", str(context.exception))

    def test_fetchstatus_empty_content(self):
        """fetchStatus should accept empty but non-None content"""
        with patch.object(self.deskpro.session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b""
            mock_get.return_value = mock_response

            result = self.deskpro.fetchStatus()
            self.assertEqual(result, "")


class TestDeskproUpdate(unittest.TestCase):
    """Test Deskpro.update() method"""

    def setUp(self):
        """Set up test fixtures"""
        self.deskpro = Deskpro(IPNUMBER, DEFAULTUSERNAME, DEFAULTPASSWORD)
        self.valid_xml = load_example_xml()

    def test_update_fetches_and_parses(self):
        """update should fetch XML and parse it into status"""
        with patch.object(self.deskpro, "fetchStatus") as mock_fetch:
            mock_fetch.return_value = self.valid_xml

            self.deskpro.update()

            # Verify fetchStatus was called
            mock_fetch.assert_called_once()

            # Verify status is updated
            self.assertIsNotNone(self.deskpro.status)
            self.assertIsInstance(self.deskpro.status, dict)

    def test_update_populates_status_fields(self):
        """update should populate all expected status fields"""
        with patch.object(self.deskpro, "fetchStatus") as mock_fetch:
            mock_fetch.return_value = self.valid_xml
            
            self.deskpro.update()

            # Check that all expected keys exist
            from deskpro import SENSORS
            expected_keys = [s.key for s in SENSORS]
            for key in expected_keys:
                self.assertIn(key, self.deskpro.status)


class TestStatiiDefaultStatus(unittest.TestCase):
    """Test Statii.DefaultStatus() method"""

    def test_default_status_all_keys_none(self):
        """DefaultStatus should initialize all keys to None"""
        result = Deskpro.Statii.DefaultStatus()
        self.assertIsInstance(result, dict)
        for value in result.values():
            self.assertIsNone(value)

    def test_default_status_has_all_expected_keys(self):
        """DefaultStatus should have all keys from SENSORS"""
        from deskpro import SENSORS
        result = Deskpro.Statii.DefaultStatus()
        self.assertIsInstance(result, dict)
        self.assertEqual(set(result.keys()), {s.key for s in SENSORS})
        



class TestStatiiParsing(unittest.TestCase):
    """Test Statii XML parsing"""

    def setUp(self):
        """Set up test fixtures"""
        self.valid_xml = load_example_xml()

    def test_statii_init_with_xml(self):
        """Statii should initialize with XML bytes"""
        statii = Deskpro.Statii(self.valid_xml)
        self.assertIsNotNone(statii.root)
        self.assertIsNotNone(statii.ra)

    def test_statii_parse_returns_dict(self):
        """Statii.Parse() should return a dictionary"""
        statii = Deskpro.Statii(self.valid_xml)
        result = statii.Parse()
        self.assertIsInstance(result, dict)

    def test_statii_parse_ambient_noise(self):
        """Statii.Parse() should extract ambient_noise_level"""
        statii = Deskpro.Statii(self.valid_xml)
        result = statii.Parse()
        self.assertEqual(result["ambient_noise_level"], "32")

    def test_statii_parse_sound_level(self):
        """Statii.Parse() should extract sound_level"""
        statii = Deskpro.Statii(self.valid_xml)
        result = statii.Parse()
        self.assertEqual(result["sound_level"], "41")

    def test_statii_parse_people_count(self):
        """Statii.Parse() should extract people_count"""
        statii = Deskpro.Statii(self.valid_xml)
        result = statii.Parse()
        self.assertEqual(result["people_count"], "1")

    def test_statii_parse_room_in_use(self):
        """Statii.Parse() should extract room_in_use"""
        statii = Deskpro.Statii(self.valid_xml)
        result = statii.Parse()
        self.assertEqual(result["room_in_use"], "True")

    def test_statii_parse_t3_alarm(self):
        """Statii.Parse() should extract t3_alarm_detected"""
        statii = Deskpro.Statii(self.valid_xml)
        result = statii.Parse()
        self.assertEqual(result["t3_alarm_detected"], "False")

    def test_statii_parse_temperature(self):
        """Statii.Parse() should extract ambient_temperature"""
        statii = Deskpro.Statii(self.valid_xml)
        result = statii.Parse()
        self.assertEqual(result["ambient_temperature"], "24.0")

    def test_statii_parse_humidity(self):
        """Statii.Parse() should extract relative_humidity"""
        statii = Deskpro.Statii(self.valid_xml)
        result = statii.Parse()
        self.assertEqual(result["relative_humidity"], "50")

    def test_statii_parse_all_keys_present(self):
        """Statii.Parse() should have all keys from SENSORS"""
        from deskpro import SENSORS
        statii = Deskpro.Statii(self.valid_xml)
        result = statii.Parse()
        for sensor in SENSORS:
            self.assertIn(sensor.key, result)

    def test_statii_tostatus_wrapper(self):
        """Statii.ToStatus() should be a convenient wrapper"""
        result = Deskpro.Statii.ToStatus(self.valid_xml)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["ambient_noise_level"], "32")
        self.assertEqual(result["people_count"], "1")


class TestStatiiGettext(unittest.TestCase):
    """Test Statii.gettext() method"""

    def setUp(self):
        """Set up test fixtures"""
        self.valid_xml = load_example_xml()
        self.statii = Deskpro.Statii(self.valid_xml)

    def test_gettext_valid_path(self):
        """gettext should return text for valid path"""
        result = self.statii.gettext("RoomAnalytics/AmbientNoise/Level/A")
        self.assertEqual(result, "32")

    def test_gettext_invalid_path_returns_none(self):
        """gettext should return None for invalid path"""
        result = self.statii.gettext("NonExistent/Path")
        self.assertIsNone(result)

    def test_gettext_sound_level(self):
        """gettext should return SoundLevel correctly"""
        result = self.statii.gettext("RoomAnalytics/Sound/Level/A")
        self.assertEqual(result, "41")

    def test_gettext_room_in_use(self):
        """gettext should return RoomInUse correctly"""
        result = self.statii.gettext("RoomAnalytics/RoomInUse")
        self.assertEqual(result, "True")


class TestStatiiGet(unittest.TestCase):
    """Test Statii.get() method"""

    def setUp(self):
        """Set up test fixtures"""
        self.valid_xml = load_example_xml()
        self.statii = Deskpro.Statii(self.valid_xml)

    def test_get_valid_element(self):
        """get should return the element for valid path"""
        result = self.statii.get("AmbientNoise/Level/A", start=self.statii.ra)
        self.assertIsNotNone(result)
        self.assertEqual(result.text, "32")

    def test_get_not_found_raises_error(self):
        """get should raise DeskproError for missing element"""
        with self.assertRaises(DeskproError) as context:
            self.statii.get("NonExistent", start=self.statii.ra)
        self.assertIn("Expected exactly one", str(context.exception))

    def test_get_multiple_elements_raises_error(self):
        """get should raise DeskproError if multiple elements found"""
        # Create a mock root with multiple matching elements
        mock_root = ET.Element("Root")
        child1 = ET.SubElement(mock_root, "Item")
        child2 = ET.SubElement(mock_root, "Item")

        with self.assertRaises(DeskproError) as context:
            self.statii.get("Item", start=mock_root)
        self.assertIn("Expected exactly one", str(context.exception))

    def test_get_returns_element_object(self):
        """get should return an ElementTree element object"""
        result = self.statii.get("PeopleCount/Current", start=self.statii.ra)
        self.assertIsInstance(result, ET.Element)


class TestStatiiEdgeCases(unittest.TestCase):
    """Test Statii edge cases and error handling"""

    def setUp(self):
        """Set up test fixtures"""

    def test_statii_with_invalid_xml_raises_error(self):
        """Statii should raise error with invalid XML"""
        invalid_xml = "<Not>Valid<XML"
        with self.assertRaises(Exception):
            Deskpro.Statii(invalid_xml)

    def test_statii_with_empty_xml_raises_error(self):
        """Statii should raise error with empty XML"""
        with self.assertRaises(Exception):
            Deskpro.Statii("")

    def test_statii_minimal_valid_xml(self):
        """Statii should handle minimal valid XML with RoomAnalytics. 
        If I get at least ONE value, that value should be provided and the other values should be None."""
        minimal_xml = """<?xml version="1.0"?>
<Status>
  <RoomAnalytics>
    <AmbientNoise>
      <Level>
        <A>25</A>
      </Level>
    </AmbientNoise>
  </RoomAnalytics>
</Status>"""
        statii = Deskpro.Statii(minimal_xml)
        self.assertIsNotNone(statii.ra)
        result = statii.Parse()
        
        # all values in the SENSORS should be present.
        from deskpro import SENSORS
        self.assertEqual(set(result.keys()), {s.key for s in SENSORS})
               
        # ambient_noise_level should be the only one with a value, and the rest should be None.
        
        self.assertEqual(result["ambient_noise_level"], "25")
        
        for key, value in result.items():
            if key != "ambient_noise_level":
                self.assertIsNone(value)


class TestParseUnknowns(unittest.TestCase):
    """Test Statii.ParseUnknowns() method"""

    def test_parse_unknowns_excludes_known_sensors(self):
        """ParseUnknowns should not include Sensors already in SENSORS"""
        valid_xml = """<?xml version="1.0"?>
<Status>
  <RoomAnalytics>
    <AmbientNoise>
      <Level>
        <A>32</A>
      </Level>
    </AmbientNoise>
    <Sound>
      <Level>
        <A>41</A>
      </Level>
    </Sound>
  </RoomAnalytics>
  <Standby>
    <State>Off</State>
  </Standby>
</Status>"""
        statii = Deskpro.Statii(valid_xml)
        unknowns = statii.ParseUnknowns()

        from deskpro import SENSORS
        unknown_keys = {s.key for s in unknowns}
        for sensor in SENSORS:
            expected_key = sensor.xml_path.lower().replace("/", "_")
            self.assertNotIn(expected_key, unknown_keys)

    def test_parse_unknowns_includes_unknown_sensors(self):
        """ParseUnknowns should return a Sensor for leaf nodes not in SENSORS"""
        xml_with_unknowns = """<?xml version="1.0"?>
<Status>
  <RoomAnalytics>
    <AmbientNoise>
      <Level>
        <A>32</A>
      </Level>
    </AmbientNoise>
    <CustomMetric>
      <Value>123</Value>
    </CustomMetric>
  </RoomAnalytics>
  <Standby>
    <State>Off</State>
  </Standby>
</Status>"""
        statii = Deskpro.Statii(xml_with_unknowns)
        unknowns = statii.ParseUnknowns()

        keys = {s.key for s in unknowns}
        self.assertIn("roomanalytics_custommetric_value", keys)

        sensor = next(s for s in unknowns if s.key == "roomanalytics_custommetric_value")
        self.assertEqual(sensor.xml_path, "RoomAnalytics/CustomMetric/Value")
        self.assertEqual(sensor.icon, "mdi:information-outline")

    def test_parse_unknowns_returns_list(self):
        """ParseUnknowns should return a list of Sensor objects"""
        from deskpro import Sensor
        valid_xml = """<?xml version="1.0"?>
<Status>
  <RoomAnalytics>
    <AmbientNoise>
      <Level>
        <A>32</A>
      </Level>
    </AmbientNoise>
  </RoomAnalytics>
</Status>"""
        statii = Deskpro.Statii(valid_xml)
        result = statii.ParseUnknowns()
        self.assertIsInstance(result, list)
        for item in result:
            self.assertIsInstance(item, Sensor)

    def test_parse_unknowns_sanitizes_keys(self):
        """ParseUnknowns should build keys as lowercase path with slashes replaced by underscores"""
        xml_with_deep_path = """<?xml version="1.0"?>
<Status>
  <RoomAnalytics>
    <VeryDeeplyNested>
      <Path>
        <Here>42</Here>
      </Path>
    </VeryDeeplyNested>
  </RoomAnalytics>
</Status>"""
        statii = Deskpro.Statii(xml_with_deep_path)
        unknowns = statii.ParseUnknowns()

        expected_key = "roomanalytics_verydeeplyNested_path_here".lower()
        keys = {s.key for s in unknowns}
        self.assertIn(expected_key, keys)


class TestDeskproSensors(unittest.TestCase):
    """Test Deskpro.sensors property"""

    def _make_client(self):
        return Deskpro(hostname="host", username="u", password="p")

    def test_sensors_property_returns_known_sensors_by_default(self):
        """sensors should equal SENSORS before any update"""
        from deskpro import SENSORS
        client = self._make_client()
        self.assertEqual(client.sensors, SENSORS)

    @patch.object(Deskpro, "fetchStatus")
    def test_sensors_property_includes_unknowns_after_update(self, mock_fetch):
        """sensors should include unknown leaf nodes after update(includeUnknowns=True)"""
        from deskpro import SENSORS
        mock_fetch.return_value = """<?xml version="1.0"?>
<Status>
  <RoomAnalytics>
    <AmbientNoise><Level><A>32</A></Level></AmbientNoise>
    <CustomMetric><Value>99</Value></CustomMetric>
  </RoomAnalytics>
  <Standby><State>Off</State></Standby>
</Status>"""
        client = self._make_client()
        client.update(includeUnknowns=True)

        self.assertGreater(len(client.sensors), len(SENSORS))
        keys = {s.key for s in client.sensors}
        self.assertIn("roomanalytics_custommetric_value", keys)


if __name__ == "__main__":
    unittest.main()
