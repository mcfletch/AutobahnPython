###############################################################################
##
# Copyright (C) 2014 Tavendo GmbH
##
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
##
# http://www.apache.org/licenses/LICENSE-2.0
##
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##
###############################################################################

import sys
import json

from twisted.python import log
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from autobahn.twisted.websocket import WampWebSocketClientFactory
from autobahn.twisted.websocket import WampWebSocketClientProtocol
from autobahn.wamp import message, types

from autobahn.twisted import wamp, websocket


class MyFrontendComponent(wamp.ApplicationSession):

    """
    Application code goes here. This is an example component that calls
    a remote procedure on a WAMP peer, subscribes to a topic to receive
    events, and then stops the world after some events.
    """

    @inlineCallbacks
    def onJoin(self, details):
        print( '%s joined on %s'%(self,details))
        # call a remote procedure
        ##
        try:
            now = yield self.call(u'com.timeservice.now')
        except Exception as e:
            print("Error: {}".format(e))
        else:
            print("Current time from time service: {}".format(now))

        # subscribe to a topic
        ##
        self.received = 0

        def on_event(i):
            print("Got event: {}".format(i))
            self.received += 1
            if self.received > 5:
                self.leave()

        sub = yield self.subscribe(on_event, u'com.myapp.topic1')
        print("Subscribed with subscription ID {}".format(sub.id))

    def onDisconnect(self):
        reactor.stop()

    def onMessage(self, msg):
        if isinstance(msg, message.Challenge):
            # TODO: verify that this can *only* come from the router!
            # Would seem better if we could get a deferred from the 
            # HELLO and attach this function to that...
            if msg.method == 'userpass':
                return self._transport.send(message.Authenticate(
                    json.dumps({
                        'method': msg.method,
                        'username': self.factory.credentials['username'],
                        'password': self.factory.credentials['password'],
                    }).decode('utf-8') # WTF!
                ))
        return wamp.ApplicationSession.onMessage(self, msg)

class LoginClientProtocol(WampWebSocketClientProtocol):
    pass


class ReconnectingWampWebSocketClientFactory(
    WampWebSocketClientFactory
):
    initialDelay = currentDelay = 1
    maxDelay = 60
    protocol = LoginClientProtocol

    def _increment_delay(self):
        # TODO: add random delay to avoid crashing waves of reconnects
        self.currentDelay *= 1.25
        self.currentDelay = min((self.maxDelay, self.currentDelay))
        return self.currentDelay

    def resetDelay(self):
        self.currentDelay = self.initialDelay

    def clientConnectionLost(self, connector, reason):
        reactor.callLater(self._increment_delay(), self.reconnect)

    def clientConnectionFailed(self, connector, reason):
        reactor.callLater(self._increment_delay(), self.reconnect)

    def reconnect(self):
        connectWS(self)

def get_options():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--debug", action="store_true",
                        help="Enable debug output.")
    parser.add_argument("--wsurl", type=str, default="ws://localhost:8000/ws",
                        help='WebSocket URL (must suit the endpoint), e.g. "ws://localhost:9000".')
    parser.add_argument("--auth", type=str, default="username:password",
        help="Username:Password value to pass to the web-service login: NOTE: you should not use this on a multi-user system, as other users can see your login!",
    )
    parser.add_argument(
        "-r", "--realm", type=str, default="vrplumber",
        help="The WAMP realm to start the component in (if any)."
    )
    return parser


if __name__ == '__main__':
    parser = get_options()
    args = parser.parse_args()
    if args.debug:
        log.startLogging(sys.stdout)

    session_factory = wamp.ApplicationSessionFactory(
        types.ComponentConfig(realm=args.realm)
    )
    session_factory.session = MyFrontendComponent
    username,password = args.auth.split(':',1)
    session_factory.credentials = {
        'username': username,
        'password': password,
    }
    transport_factory = websocket.WampWebSocketClientFactory(session_factory,
                                                             debug=args.debug,
                                                             debug_wamp=args.debug)

    from autobahn.twisted.websocket import connectWS
    transport_factory = ReconnectingWampWebSocketClientFactory(
        session_factory, url=args.wsurl,
        debug_wamp=args.debug,
    )
    transport_factory.setProtocolOptions(failByDrop=False)
    connectWS(transport_factory)
    reactor.run()
