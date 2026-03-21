#
# THIS FILE IS TEMPORARY UNTIL I CAN GET IT ONTO PYPI.
#

from typing import Optional
import requests
import xml.etree.ElementTree as ET
from requests.auth import HTTPBasicAuth

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
        self.session = requests.Session()

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

        STATUSMAP = {
            # looks like AmbientNoiseLevel is the estimated noise level all the time
            "AmbientNoiseLevel": "RoomAnalytics/AmbientNoise/Level/A",

            # SoundLevel seems to be the CURRENT noise level
            "SoundLevel": "RoomAnalytics/Sound/Level/A",
            "PeopleCount": "RoomAnalytics/PeopleCount/Current",
            "RoomInUse": "RoomAnalytics/RoomInUse",
            "T3AlarmDetected": "RoomAnalytics/T3Alarm/Detected",
            "AmbientTemperature": "RoomAnalytics/AmbientTemperature",
            "RelativeHumidity": "RoomAnalytics/RelativeHumidity",
            "StandbyState": "Standby/State"
        }

        @classmethod
        def DefaultStatus(cls) -> dict[str, Optional[str]]:
            """
            For generating initial (unknown) stats
            """
            ret = {}
            for stat in cls.STATUSMAP.keys():
                ret[stat] = None
            return ret

        def Parse(self) -> dict[str, str]:
            """
            Assuming we've already pulled down the XML,
            this triggers parsing of it.
            """
            ret = {}
            for stat, path in self.STATUSMAP.items():
                ret[stat] = self.gettext(path)

            return ret

        @classmethod
        def ToStatus(cls, xml: str) -> dict[str, str]:
            """
            Convenient wrapper for turning the XML data into
            a dictionary.
            """
            return cls(xml).Parse()

        pass  # the class

    def update(self):
        """
        updates the XML from the Deskpro, then turns it into
        a dictionary of stats.
        """
        xml_string = self.fetchStatus()
        #
        # for now we just pull the statii into a status dict.
        # 

        self.status = Deskpro.Statii.ToStatus(xml_string)
        return
    pass

