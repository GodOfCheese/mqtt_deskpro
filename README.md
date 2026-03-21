# mqtt_deskpro
MQTT Broker for the Cisco Deskpro and similar devices

This project is intended to replace the Cisco Deskpro HomeAssistant integration with a lightweight MQTT broker. 

## Why did I build this?
1. original package (`ha_deskpro_integration`) was synchronous and had to poll often to be useful (like every second).  This guaranteed that at some point the Deskpro would respond too slowly and the Integration would be unloaded by HA.
1. Using MQTT allows HA to auto-discover the device (although with the downside that you have to configure the broker manually and no HACS support, so TANSTAAFL I guess)
1. separating this from HA's integration structure makes it a lot easier to build, test, and (especially) debug.  

## Why should you run this instead of `ha_deskpro_integration`?
Running this as a separate service seems a lot more reliable than running it as a native integration (for me at least).  Also, updating it doesn't require restarting home assistant.  Also, if you're using this for something other than (or in addition to) HA, that's possible through MQTT.

# installation
Straightforward, IMHO.  First, some prerequisites:

## MQTT
You'll need a working MQTT.  Without it, this effort... doesn't make a lot of sense.
Gather these MQTT parameters:
1. the hostname it's running on
1. the port it's on (if not the default 1883 port)
1. if a secure instance, the username, password, and whether you're using TLS (hopefully `yes`)

You'll need these later.

## HomeAssistant (optional)
If you intend to use it with HomeAssistant, you'll need the MQTT integration up and running.  You can do this later if you want.

## Cisco Deskpro or other RoomOS device
The whole point of this integration is to launder data from your Deskpro to an MQTT somewhere.  So you'll need a Deskpro. 

In order to fetch status off your Deskpro, you'll need to create a user with `User` privileges. I'm sure there's documentation on cisco's site on how to do this. I'll link to it eventually, but if you don't know how to do this yet, experiment.  

1. Create a new user specifically for this.  **DO NOT use the default `admin` user**.  It's really easy to create new users.
1. give the new user a strong password, since only automation is going to use it.
1. UNCHECK the default option to require the user change their password on first login.
1. SAVE the credentials. You'll need them in the next step.

## Python (PROOF-OF-CONCEPT)
You may want to run this thing directly as a PoC, or for debugging, or whatever. 

* first, gather the requirements: `pip install -r requirements.txt`
* set these environment variables:
* then run it (next section)

### Environment variables
* DESKPRO_HOST: the hostname/IP of your deskpro.
* DESKPRO_USER: the name of the low-privilege user you created up above
* DESKPRO_PASS: that user's password
* DESKPRO_VERIFY_SSL: (optional) defaults to `false` because the Deskpro does.  If you have a TLS cert you want to verify rather than spraying your username at the above IP address, set this to `true`.  Recommended.
* MQTT_HOST: the hostname for your MQTT service
* MQTT_PORT: (optional) its port number.  Default 1883.
* MQTT_USER: (optional) username to connect to MQTT with, if required
* MQTT_PASS: (optional) password to go with that username
* MQTT_TLS: (optional) use TLS to connect.  Defaults to `false`.
* POLL_INTERVAL: (optional) how often to pound the deskpro, in seconds.  Defaults to 10.  I recommend turning this to 1 if you're using presence detection AFTER you've determined that it works.
* DEVICE_NAME: (optional) if you have more than one Deskpro, you might want to change this to something other than `Cisco Desk Pro`
* DEVICE_ID: (optional) the device_id for home assistant detection.  Defaults to `cisco_deskpro_1`, but if you have more than one, you'll probably need to change this.

### Run it!
After setting the environment variables (above):
`python cisco_deskpro_mqtt.py`

...and observe the output in stdout and/or MQTT.

## Docker (RECOMMENDED)
I recommend running this in a docker container.  

1. edit the provided `docker-compose.yml` and add the values from **Environment Variables** above.  
1. `docker compose up -d`

Watch it go.

Enjoy!

