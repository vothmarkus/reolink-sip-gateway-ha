"""Constants for the Reolink SIP Gateway integration."""

from datetime import timedelta

DOMAIN = "reolink_sip_gateway"
NAME = "Reolink SIP Gateway"

CONF_API_URL = "api_url"
CONF_TOKEN = "token"

API_VERSION = 1
DEFAULT_API_URL = "http://homeassistant.local:18099/api/v1"
POLL_INTERVAL = timedelta(seconds=60)

CAPABILITY_CALL_STATUS = "call_status"
CAPABILITY_CALLER_NUMBER = "caller_number"
CAPABILITY_EVENTS = "events"
CAPABILITY_HANGUP = "hangup"
CAPABILITY_TEST_CALL = "test_call"
REQUIRED_CAPABILITIES = frozenset(
    {
        CAPABILITY_CALL_STATUS,
        CAPABILITY_CALLER_NUMBER,
        CAPABILITY_EVENTS,
        CAPABILITY_HANGUP,
        CAPABILITY_TEST_CALL,
    }
)

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
