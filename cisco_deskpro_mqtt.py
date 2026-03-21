#!/usr/bin/env python3
"""
Cisco Desk Pro → MQTT Bridge for Home Assistant
================================================
Polls a Cisco Desk Pro and publishes its room analytics
to an MQTT broker. Supports Home Assistant MQTT discovery.

Requirements:
    pip install paho-mqtt requests

Configuration:
    Edit the CONFIG section below, or set environment variables.
"""

import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import paho.mqtt.client as mqtt
from deskpro import Deskpro, DeskproError

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("cisco_deskpro_mqtt")


# ---------------------------------------------------------------------------
# CONFIG — edit here or override with environment variables
# ---------------------------------------------------------------------------
@dataclass
class Config:
    # --- Cisco Desk Pro ---
    deskpro_host: str = os.getenv("DESKPRO_HOST", "192.168.1.100")
    deskpro_username: str = os.getenv("DESKPRO_USER", "admin")
    deskpro_password: str = os.getenv("DESKPRO_PASS", "password")
    deskpro_verify_ssl: bool = os.getenv("DESKPRO_VERIFY_SSL", "false").lower() == "true"

    # --- MQTT Broker ---
    mqtt_host: str = os.getenv("MQTT_HOST", "192.168.1.10")
    mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))
    mqtt_username: Optional[str] = os.getenv("MQTT_USER")
    mqtt_password: Optional[str] = os.getenv("MQTT_PASS")
    mqtt_tls: bool = os.getenv("MQTT_TLS", "false").lower() == "true"

    # --- Bridge behaviour ---
    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL", "10"))
    device_name: str = os.getenv("DEVICE_NAME", "Cisco Desk Pro")
    device_id: str = os.getenv("DEVICE_ID", "cisco_deskpro_1")

    # MQTT topic root  →  homeassistant/<component>/cisco_deskpro_1/...
    topic_root: str = field(init=False)
    discovery_prefix: str = "homeassistant"

    def __post_init__(self):
        self.topic_root = f"{self.discovery_prefix}/sensor/{self.device_id}"


CONFIG = Config()

# ---------------------------------------------------------------------------
# Deskpro client initialization
# ---------------------------------------------------------------------------

def build_deskpro_client() -> Deskpro:
    """Initialize the Deskpro client."""
    return Deskpro(
        hostname=CONFIG.deskpro_host,
        username=CONFIG.deskpro_username,
        password=CONFIG.deskpro_password,
        certverify=CONFIG.deskpro_verify_ssl,
    )


DESKPRO_CLIENT = build_deskpro_client()


# ---------------------------------------------------------------------------
# Status extraction
# ---------------------------------------------------------------------------

def get_device_status() -> dict[str, Any]:
    """
    Poll the Desk Pro and return its room analytics status.
    """
    status: dict[str, Any] = {}
    
    # First, initialize the status with "unavailable" to ensure all keys are present even if fetching fails
    for sensor in SENSORS:
        status[sensor.key] = "unavailable"
        
    # now fetch the real data, and overwrite the "unavailable" values if successful

    try:
        DESKPRO_CLIENT.update()
        data = DESKPRO_CLIENT.status        
    except DeskproError as e:
        log.error("Failed to fetch Deskpro status: %s", e)
        data = None
        
        
    if data is not None:
        
        # Map Deskpro data to our status dict based on SENSORS configuration
        
        for sensor in SENSORS:
            status[sensor.key] = data.get(sensor.deskpro_key, "unavailable")
            pass
        
        #status["ambient_noise_level"] = data.get("AmbientNoiseLevel")
        #status["sound_level"] = data.get("SoundLevel")
        #status["people_count"] = data.get("PeopleCount")
        #status["room_in_use"] = data.get("RoomInUse")
        #status["t3_alarm_detected"] = data.get("T3AlarmDetected")
        #status["ambient_temperature"] = data.get("AmbientTemperature")
        #status["relative_humidity"] = data.get("RelativeHumidity")
    
        # Return unavailable status on error
        #status = {
        #    "ambient_noise_level": "unavailable",
        #    "sound_level": "unavailable",
        #    "people_count": "unavailable",
        #    "room_in_use": "unavailable",
        #    "t3_alarm_detected": "unavailable",
        #    "ambient_temperature": "unavailable",
        #    "relative_humidity": "unavailable",
        #}

    return status


# ---------------------------------------------------------------------------
# Home Assistant MQTT Discovery
# ---------------------------------------------------------------------------

DEVICE_INFO_TEMPLATE = {
    "identifiers": [CONFIG.device_id],
    "name": CONFIG.device_name,
    "manufacturer": "Cisco",
    "model": "Desk Pro",
}


@dataclass
class Sensor:
    key: str
    name: str
    icon: str
    deskpro_key: str
    device_class: Optional[str] = None
    unit: Optional[str] = None


SENSORS: list[Sensor] = [
    Sensor("ambient_noise_level", "Ambient Noise Level",  "mdi:volume-mute",      "AmbientNoiseLevel",  unit="dB"),
    Sensor("sound_level",         "Sound Level",          "mdi:volume-high",      "SoundLevel",         unit="dB"),
    Sensor("people_count",        "People Count",         "mdi:account-multiple", "PeopleCount"),
    Sensor("room_in_use",         "Room In Use",          "mdi:door-open",        "RoomInUse"),
    Sensor("t3_alarm_detected",   "T3 Alarm Detected",    "mdi:alarm",            "T3AlarmDetected"),
    Sensor("ambient_temperature", "Ambient Temperature",  "mdi:thermometer",      "AmbientTemperature", device_class="temperature", unit="°C"),
    Sensor("relative_humidity",   "Relative Humidity",    "mdi:water-percent",    "RelativeHumidity",   device_class="humidity",    unit="%"),
    Sensor("standby_state",       "Standby State",        "mdi:power-standby",    "StandbyState"),
]


def publish_discovery(client: mqtt.Client, status: dict[str, Any]) -> None:
    """Publish Home Assistant MQTT discovery config for each sensor."""
    for sensor in SENSORS:
        state_topic = f"{CONFIG.topic_root}/{sensor.key}/state"
        config_topic = f"{CONFIG.discovery_prefix}/sensor/{CONFIG.device_id}/{sensor.key}/config"

        payload: dict[str, Any] = {
            "unique_id": f"{CONFIG.device_id}_{sensor.key}",
            "name": sensor.name,
            "state_topic": state_topic,
            "icon": sensor.icon,
            "device": DEVICE_INFO_TEMPLATE,
        }
        if sensor.device_class:
            payload["device_class"] = sensor.device_class
        if sensor.unit:
            payload["unit_of_measurement"] = sensor.unit

        client.publish(config_topic, json.dumps(payload), retain=True)
        log.debug("Published discovery for %s", sensor.key)


def publish_status(client: mqtt.Client, status: dict[str, Any]) -> None:
    """Publish current values for all sensors."""
    for sensor in SENSORS:
        state_topic = f"{CONFIG.topic_root}/{sensor.key}/state"
        value = status.get(sensor.key, "unavailable")
        client.publish(state_topic, str(value) if value is not None else "unavailable", retain=True)
        pass
    log.debug("Published status: noise=%s sound=%s people=%s room_in_use=%s temp=%s humidity=%s",
             status.get("ambient_noise_level"), status.get("sound_level"),
             status.get("people_count"), status.get("room_in_use"),
             status.get("ambient_temperature"), status.get("relative_humidity"))


# ---------------------------------------------------------------------------
# MQTT setup
# ---------------------------------------------------------------------------

def build_mqtt_client() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{CONFIG.device_id}_bridge") 

    if CONFIG.mqtt_username:
        client.username_pw_set(CONFIG.mqtt_username, CONFIG.mqtt_password)

    if CONFIG.mqtt_tls:
        client.tls_set()

    lwt_topic = f"{CONFIG.topic_root}/availability"
    client.will_set(lwt_topic, "offline", retain=True)

    def on_connect(c, userdata, connect_flags, reason_code, properties):
        if not reason_code.is_failure:
            log.info("Connected to MQTT broker at %s:%s", CONFIG.mqtt_host, CONFIG.mqtt_port)
            c.publish(lwt_topic, "online", retain=True)
        else:
            log.error("MQTT connect failed, reason code: %s", reason_code)

    def on_disconnect(c, userdata, disconnect_flags, reason_code, properties):
        if reason_code != 0:
            log.warning("Unexpected MQTT disconnect (reason code=%s), will retry...", reason_code)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    return client


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    log.info("Starting Cisco Desk Pro → MQTT bridge")
    log.info("Polling %s every %ds → MQTT %s:%s",
             CONFIG.deskpro_host, CONFIG.poll_interval_seconds,
             CONFIG.mqtt_host, CONFIG.mqtt_port)

    client = build_mqtt_client()

    # Connect to MQTT (with retry)
    while True:
        try:
            client.connect(CONFIG.mqtt_host, CONFIG.mqtt_port, keepalive=60)
            break
        except Exception as e:
            log.error("Cannot connect to MQTT broker: %s — retrying in 10s", e)
            time.sleep(10)

    client.loop_start()

    # Graceful shutdown
    shutdown = False

    def handle_signal(sig, frame):
        nonlocal shutdown
        log.info("Shutdown signal received")
        shutdown = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    discovery_published = False

    while not shutdown:
        status = get_device_status()

        if not discovery_published:
            publish_discovery(client, status)
            discovery_published = True

        publish_status(client, status)
        time.sleep(CONFIG.poll_interval_seconds)

    log.info("Shutting down bridge...")
    client.publish(f"{CONFIG.topic_root}/availability", "offline", retain=True)
    client.loop_stop()
    client.disconnect()
    sys.exit(0)


if __name__ == "__main__":
    main()
