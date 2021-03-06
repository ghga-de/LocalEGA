"""Ensures communication with RabbitMQ Message Broker."""

import sys
import logging
import json
import ssl
from contextlib import contextmanager

import pika

from ..conf import CONF
from ..conf.logging import _cid
from . import redact_url

LOG = logging.getLogger(__name__)


class AMQPConnection():
    """Initiate AMQP Connection."""

    conn = None
    chann = None
    connection_params = None

    def __init__(self, conf_section='broker', on_failure=None):
        """Initialize AMQP class."""
        self.on_failure = on_failure
        self.conf_section = conf_section or 'broker'
        # LOG.debug('Conf section', self.conf_section)
        # assert self.conf_section in CONF.sections(), "Section not found in config file"

    def fetch_args(self):
        """Retrieve AMQP connection parameters."""
        LOG.debug('Getting a connection to "%s"', self.conf_section)
        params = CONF.getsensitive(self.conf_section, 'connection', raw=True)
        if isinstance(params, bytes):  # secret to str
            params = params.decode()

        LOG.info("Initializing a connection to: %s", redact_url(params))
        self.connection_params = pika.connection.URLParameters(params)

        # Handling the SSL options
        # Note: We re-create the SSL context, so don't pass any ssl_options in the above connection URI.
        if params.startswith('amqps'):

            LOG.debug("Enforcing a TLS context")
            context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS)  # Enforcing (highest) TLS version (so... 1.2?)

            context.verify_mode = ssl.CERT_NONE
            # Require server verification
            if CONF.getboolean(self.conf_section, 'verify_peer', fallback=False):
                LOG.debug("Require server verification")
                context.verify_mode = ssl.CERT_REQUIRED
                cacertfile = CONF.get(self.conf_section, 'cacertfile', fallback=None)
                if cacertfile:
                    context.load_verify_locations(cafile=cacertfile)

            # Check the server's hostname
            server_hostname = CONF.get(self.conf_section, 'server_hostname', fallback=None)
            if CONF.getboolean(self.conf_section, 'verify_hostname', fallback=False):
                LOG.debug("Require hostname verification")
                assert server_hostname, "server_hostname must be set if verify_hostname is"
                context.check_hostname = True
                context.verify_mode = ssl.CERT_REQUIRED

            # If client verification is required
            certfile = CONF.get(self.conf_section, 'certfile', fallback=None)
            if certfile:
                LOG.debug("Prepare for client verification")
                keyfile = CONF.get(self.conf_section, 'keyfile')
                context.load_cert_chain(certfile, keyfile=keyfile)

            # Finally, the pika ssl options
            self.connection_params.ssl_options = pika.SSLOptions(context=context, server_hostname=server_hostname)

    def connect(self, force=False):
        """Make a blocking/select connection to the Message Broker supporting AMQP(S)."""
        if force:
            self.close()

        if self.conn and self.chann:
            return

        if not self.connection_params:
            self.fetch_args()

        try:
            self.conn = pika.BlockingConnection(self.connection_params)  # this uses connection_attempts and retry_delay already
            self.chann = self.conn.channel()
            LOG.debug("Connection successful")
            return
        except (pika.exceptions.AMQPConnectionError,  # connection
                pika.exceptions.AMQPChannelError,     # channel
                pika.exceptions.ChannelError) as e:   # why did they keep that one separate?
            # See https://github.com/pika/pika/blob/master/pika/exceptions.py
            LOG.debug("MQ connection error: %r", e)
        except Exception as e:
            LOG.debug("Invalid connection: %r", e)

        # fail to connect
        if self.on_failure and callable(self.on_failure):
            LOG.error("Unable to connection to MQ")
            self.on_failure()

    @contextmanager
    def channel(self):
        """Retrieve connection channel."""
        if self.conn is None:
            self.connect()
        yield self.chann

    def close(self):
        """Close MQ channel."""
        LOG.debug("Closing the AMQP connection.")
        if self.chann and not self.chann.is_closed:
            self.chann.close()
        self.chann = None
        if self.conn and not self.conn.is_closed:
            self.conn.close()
        self.conn = None


# Instantiate a global instance
connection = AMQPConnection(on_failure=lambda: sys.exit(1))


def publish(message, exchange, routing, correlation_id=None):
    """Send a message to the local broker exchange using the given routing key."""
    correlation_id = correlation_id or _cid.get()
    assert(correlation_id), "You should not publish without a correlation id"
    with connection.channel() as channel:
        LOG.debug('Sending to exchange: %s [routing key: %s]', exchange, routing, extra={'correlation_id': correlation_id})
        channel.basic_publish(exchange,             # exchange
                              routing,              # routing_key
                              json.dumps(message),  # body
                              properties=pika.BasicProperties(correlation_id=correlation_id,
                                                              content_type='application/json',
                                                              delivery_mode=2))


def consume(work, from_queue, to_routing, ack_on_error=True):
    """Register callback ``work`` to be called, blocking function.

    If there are no message in ``from_queue``, the function blocks and waits for new messages.

    If the function ``work`` returns a non-None message, the latter is published
    to the `lega` exchange with ``to_routing`` as the routing key.
    """
    LOG.debug('Consuming message from %s', from_queue)
    assert(from_queue)

    def process_request(channel, method_frame, props, body):
        correlation_id = props.correlation_id
        message_id = method_frame.delivery_tag
        try:
            _cid.set(correlation_id)
            LOG.debug('Consuming message %s', message_id, extra={'correlation_id': correlation_id})

            # Process message in JSON format
            try:
                content = json.loads(body)
            except Exception as e:
                LOG.error('Malformed JSON-message: %s', e, extra={'correlation_id': correlation_id})
                LOG.error('Original message: %s', body, extra={'correlation_id': correlation_id})
                err_msg = {
                    'reason': 'Malformed JSON-message',
                    'original_message': body.decode(errors='ignore')  # or str(body) ?
                }
                publish(err_msg, 'cega', 'files.error', correlation_id=correlation_id)
                # Force acknowledging the message
                channel.basic_ack(delivery_tag=message_id)
                return  # game over

            # Message correctly formed
            answer, error = work(content)  # exceptions already caught by decorator

            # Publish the answer
            if answer:
                assert(to_routing)
                publish(answer, 'lega', to_routing, correlation_id=correlation_id)

            # Acknowledgment: Cancel the message resend in case MQ crashes
            if not error or ack_on_error:
                LOG.debug('Sending ACK for message: %s', message_id)
                channel.basic_ack(delivery_tag=message_id)
        finally:
            _cid.set(None)

    # Let's do this
    LOG.debug('MQ setup')
    while True:
        with connection.channel() as channel:
            try:
                LOG.info('Consuming message from %s', from_queue)
                channel.basic_qos(prefetch_count=1)  # One job per worker
                channel.basic_consume(from_queue, on_message_callback=process_request)
                channel.start_consuming()
            except KeyboardInterrupt:
                LOG.info('Stop consuming (Keyboard Interrupt)')
                channel.stop_consuming()
                connection.close()
                break
            except (pika.exceptions.AMQPConnectionError,
                    pika.exceptions.AMQPChannelError,
                    pika.exceptions.ChannelError,
                    pika.exceptions.AMQPError) as e:
                LOG.debug('Retrying after %s', e)
                connection.close()
                continue
            # Let it raise any other exception and bail out.
            except Exception as e:
                LOG.critical('%r', e)
                connection.close()
                # break
                sys.exit(2)
