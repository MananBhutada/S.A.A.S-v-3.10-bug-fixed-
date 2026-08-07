"""
_05_Agent/mqtt_client.py
Real MQTT publisher for ESP32 scrubber nodes.
"""
import json, logging, os
log = logging.getLogger("MQTT")

_client = None

def _get_client():
    global _client
    if _client is not None:
        return _client
    try:
        import paho.mqtt.client as mqtt
        broker = os.getenv("MQTT_BROKER_HOST", "localhost")
        port   = int(os.getenv("MQTT_BROKER_PORT", "1883"))
        user   = os.getenv("MQTT_USERNAME", "")
        pwd    = os.getenv("MQTT_PASSWORD", "")

        c = mqtt.Client(client_id="saas-backend", clean_session=True)
        if user: c.username_pw_set(user, pwd)
        c.connect(broker, port, keepalive=60)
        c.loop_start()
        _client = c
        log.info("MQTT connected → %s:%d", broker, port)
        return c
    except Exception as exc:
        log.warning("MQTT unavailable (%s) — commands logged only", exc)
        return None

def publish_scrubber_command(ward_name: str, action: str,
                              droplet_um: float = 28.0,
                              wind_bearing_deg: float = 270.0) -> dict:
    topic   = f"saas/wards/{ward_name}/scrubber/cmd"
    payload = json.dumps({"action": action, "droplet_um": droplet_um,
                          "wind_bearing_deg": wind_bearing_deg})
    c = _get_client()
    if c:
        try:
            c.publish(topic, payload, qos=1, retain=False)
            log.info("MQTT → %s: %s %.0fμm @%.0f°", ward_name, action, droplet_um, wind_bearing_deg)
            return {"status": "published", "topic": topic}
        except Exception as exc:
            log.error("MQTT publish failed: %s", exc)
    log.info("MQTT (offline) → %s: %s", ward_name, action)
    return {"status": "offline_logged"}

def publish_wind(city_bearing: float, ward_winds: dict) -> dict:
    payload = json.dumps({"city_bearing_deg": city_bearing, "wards": ward_winds})
    c = _get_client()
    if c:
        try:
            c.publish("saas/met/wind_bearing", payload, qos=0)
            return {"status": "published"}
        except Exception as exc:
            log.error("Wind MQTT failed: %s", exc)
    return {"status": "offline_logged"}
