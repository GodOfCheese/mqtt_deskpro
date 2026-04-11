#
# THIS FILE IS TEMPORARY UNTIL I CAN GET IT ONTO PYPI.
#

from dataclasses import dataclass
from typing import Optional
import re
import requests
import xml.etree.ElementTree as ET
from requests.auth import HTTPBasicAuth


# ---------------------------------------------------------------------------
# Sensor Configuration
# ---------------------------------------------------------------------------

@dataclass
class Sensor:
    key: str
    name: str
    icon: str
    xml_path: str
    device_class: Optional[str] = None
    unit: Optional[str] = None


SENSORS: list[Sensor] = [
    Sensor("ambient_noise_level", "Ambient Noise Level",  "mdi:volume-mute",      "RoomAnalytics/AmbientNoise/Level/A",  unit="dB"),
    Sensor("sound_level",         "Sound Level",          "mdi:volume-high",      "RoomAnalytics/Sound/Level/A",         unit="dB"),
    Sensor("people_count",        "People Count",         "mdi:account-multiple", "RoomAnalytics/PeopleCount/Current"),
    Sensor("room_in_use",         "Room In Use",          "mdi:door-open",        "RoomAnalytics/RoomInUse"),
    Sensor("t3_alarm_detected",   "T3 Alarm Detected",    "mdi:alarm",            "RoomAnalytics/T3Alarm/Detected"),
    Sensor("ambient_temperature", "Ambient Temperature",  "mdi:thermometer",      "RoomAnalytics/AmbientTemperature", device_class="temperature", unit="°C"),
    Sensor("relative_humidity",   "Relative Humidity",    "mdi:water-percent",    "RoomAnalytics/RelativeHumidity",   device_class="humidity",    unit="%"),
    Sensor("standby_state",       "Standby State",        "mdi:power-standby",    "Standby/State"),
]


class DeskproError(Exception):
    """
    Most exceptions emitted by this class will be this
    """
    pass

class Deskpro:
    """
    Retrieves status data from the Cisco Deskpro.
    You'll need an account with at least User permissions
    to retrieve the status.
    """
    def __init__(
        self,
        hostname,
        # sadly we need these.
        username,
        password,
        certverify=False, # Deskpros default to a self-signed cert
    ):
        assert hostname is not None, "hostname is required"
        assert username is not None, "username is required"
        assert password is not None, "password is required"

        self.url = f"https://{hostname}/status.xml"
        self.auth = HTTPBasicAuth(username=username, password=password)
        self.certverify = certverify
        self.status = Deskpro.Statii.DefaultStatus()
        self._unknown_sensors: list[Sensor] = []
        self.session = requests.Session()

    @property
    def sensors(self) -> list[Sensor]:
        return SENSORS + self._unknown_sensors

    def fetchStatus(self) -> str:
        """
        actually retrieves the statusxml from the device.
        Separated for testing convenience
        """
        response = self.session.get(self.url, auth=self.auth, verify=self.certverify)
        if response.status_code != 200:
            raise DeskproError(f"{self.url} returned {response.status_code}")

        if response.content is None:
            raise DeskproError(f"No content in response from {self.url}")

        assert response.content is not None, "response.content should not be None here, but it is.  This is a sanity check to satisfy the type checker."
        return response.content.decode("utf-8")

    class Statii:
        """
        convenience library to simplify parsing the status data
        retrieved from the Deskpro.
        There are likely libraries for this specifically
        So when I find them, I'll switch to using those.
        """

        def __init__(self, xml:str):

            assert isinstance(xml, str), "xml must be a string.  If you have bytes, decode it first."
            self.root = ET.fromstring(xml)
            self.ra = self.get("RoomAnalytics", start=self.root)

        def gettext(self, xmlpath) -> Optional[str]:
            try:
                return self.get(xmlpath, start=self.root).text
            except DeskproError:
                return None

        def get(self, path, start):
            # all the Deskpro items we care about are unique.
            ret = start.findall(path)

            if ret is None:
                raise DeskproError(f"no {path} in {start}")

            if len(ret) != 1:
                raise DeskproError(
                    f"Expected exactly one {path}, but got {ret} from {start}"
                )

            return ret[0]

        @classmethod
        def DefaultStatus(cls) -> dict[str, Optional[str]]:
            """
            For generating initial (unknown) stats
            """
            ret = {}
            for sensor in SENSORS:
                ret[sensor.key] = None
            return ret

        def Parse(self) -> dict[str, str]:
            """
            Assuming we've already pulled down the XML,
            this triggers parsing of it.
            """
            ret = {}
            for sensor in SENSORS:
                ret[sensor.key] = self.gettext(sensor.xml_path)

            return ret

        def ParseUnknowns(self) -> list[Sensor]:
            """
            Walk the entire XML and return Sensor definitions for any leaf nodes
            not already present in SENSORS.  The key, name, and xml_path are derived
            from the element's path; the icon defaults to mdi:information-outline.
            """
            known_paths = {sensor.xml_path for sensor in SENSORS}

            sensors: list[Sensor] = []

            def walk_element(element, current_path=""):
                element_path = f"{current_path}/{element.tag}" if current_path else element.tag
                has_children_with_text = any(child.text and child.text.strip() for child in element)

                if element.text and element.text.strip() and not has_children_with_text:
                    if element_path not in known_paths:
                        key  = element_path.lower().replace("/", "_")
                        name = " ".join(
                            re.sub(r'([a-z])([A-Z])', r'\1 \2', part)
                            for part in element_path.split("/")
                        )
                        sensors.append(Sensor(
                            key=key,
                            name=name,
                            icon="mdi:information-outline",
                            xml_path=element_path,
                        ))

                for child in element:
                    walk_element(child, element_path)

            for child in self.root:
                walk_element(child)

            return sensors

        @classmethod
        def ToStatus(cls, xml: str) -> dict[str, str]:
            """
            Convenient wrapper for turning the XML data into
            a dictionary.
            """
            return cls(xml).Parse()

        pass  # the class

    def update(self, includeUnknowns=False) -> None:
        """
        updates the XML from the Deskpro, then turns it into
        a dictionary of stats.
        """
        xml_string = self.fetchStatus()
        #
        # for now we just pull the statii into a status dict.
        #

        self.status = Deskpro.Statii.ToStatus(xml_string)

        if includeUnknowns:
            statii = Deskpro.Statii(xml_string)
            self._unknown_sensors = statii.ParseUnknowns()
            assert self._unknown_sensors is not None, "ParseUnknowns should never return None, but it did.  This is a sanity check to satisfy the type checker."
            for sensor in self._unknown_sensors:
                assert sensor.key is not None, "Sensor key should not be None, but it is.  This is a sanity check to satisfy the type checker."
                self.status[sensor.key] = statii.gettext(sensor.xml_path)

        return
    pass
