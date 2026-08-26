"""Constants for the Reolink SIP Gateway integration."""

from datetime import timedelta

DOMAIN = "reolink_sip_gateway"
NAME = "Reolink SIP Gateway"

CONF_API_URL = "api_url"
CONF_HOST = "host"
CONF_TOKEN = "token"

API_VERSION = 1
GATEWAY_API_PORT = 18099
GATEWAY_API_PATH = "/api/v1"
DEFAULT_HOST = "1c33278a-reolink-sip-gateway"
POLL_INTERVAL = timedelta(seconds=60)

CAPABILITY_CALL_STATUS = "call_status"
CAPABILITY_CALLER_NUMBER = "caller_number"
CAPABILITY_DTMF_EVENTS = "dtmf_events"
CAPABILITY_EVENTS = "events"
CAPABILITY_HANGUP = "hangup"
CAPABILITY_ROUTE_TEST_CALLS = "route_test_calls"
CAPABILITY_TEST_CALL = "test_call"
REQUIRED_CAPABILITIES = frozenset(
    {
        CAPABILITY_CALL_STATUS,
        CAPABILITY_CALLER_NUMBER,
        CAPABILITY_DTMF_EVENTS,
        CAPABILITY_EVENTS,
        CAPABILITY_HANGUP,
        CAPABILITY_TEST_CALL,
    }
)

EVENT_DTMF = f"{DOMAIN}_dtmf"

STATUS_READY = "bereit"
STATUS_INCOMING = "eingehend"
STATUS_OUTGOING = "ausgehend"
STATUS_CONNECTED = "verbunden"
STATUS_ERROR = "fehler"
STATUS_OPTIONS = (
    STATUS_READY,
    STATUS_INCOMING,
    STATUS_OUTGOING,
    STATUS_CONNECTED,
    STATUS_ERROR,
)
