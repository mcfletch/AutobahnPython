###############################################################################
#
# Copyright (C) 2011-2014 Tavendo GmbH
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
###############################################################################
"""Sample code that issues a request to a web-service to check authentication"""
import datetime,time,json,sys,urllib
from twisted.python import log
from twisted.internet.endpoints import serverFromString
from twisted.web.client import getPage

from autobahn.twisted.wamp import ApplicationSession
from autobahn.twisted.websocket import WampWebSocketServerFactory
from autobahn.twisted.wamp import RouterSession
from autobahn.wamp import types


class TimeService(ApplicationSession):
    """
    A simple time service application component.
    """
    def __init__(self, realm="vrplumber"):
        ApplicationSession.__init__(self)
        self._realm = realm

    def onConnect(self):
        self.join(self._realm)

    def onJoin(self, details):
        print( '%s joining %s'%(self,details))
        def utcnow():
            now = datetime.datetime.utcnow()
            return now.strftime("%Y-%m-%dT%H:%M:%SZ")

        self.register(utcnow, 'com.timeservice.now')
        log.msg( 'Registered time service' )


class WebServiceLogin:
    """Mix-in providing login via web-services using challenge-response to front-end
    
    Notes:
    
        The front-end should *only* allow connections from this host
        as otherwise it would allow for password cracking pretty easily.
        
        CSRF protection must be disabled on the login view...
        
        The idea here is to figure out how to write an auth mechanism, once 
        I know that we can look at e.g. using public-key crypto to allow transmitting
        the credentials here securely before we send them to the service.
    """
    URL = 'http://localhost:8080/ws-login/'
    USERNAME = 'username'
    PASSWORD = 'password'
    
    def onHello( self, realm, details ):
        """On receiving a hello, issue a Challenge to the client"""
        if getattr(self._transport,'_authenticated',None) is not None:
            return types.Accept(authid=self._transport._authenticated)
        else:
            return types.Challenge(
                'userpass',
                {
                    'timestamp': time.time(),
                }
            )
    def onAuthenticate( self, signature, extra ):
        """On receiving a response, check with the web-service if this is a valid user"""
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        signature = json.loads( signature )
        body = urllib.urlencode({self.USERNAME:signature['username'], self.PASSWORD:signature['password']})
        # TODO: copy cookies from original over to this request to provide 
        # seemless login for web-GUI clients
        d = getPage(url=self.URL,
                    method='POST',
                    postdata=body,
                    headers=headers)
        def on_success( response ):
            content = json.loads( response )
            if content.get('success'):
                username = content.get('username')
                if username:
                    return types.Accept( content['username'] )
            log.msg( 'Rejected login: %s'%( content,) )
            return types.Deny()
        def on_failure( response ):
            log.msg( 'Failure checking login: %s'%(response,) )
            return types.Deny()
        d.addCallbacks( on_success, on_failure )
        return d

class WebServiceLoginRouterSession(WebServiceLogin,RouterSession):
    """Example router session with web-service login"""

def get_options():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--debug", action="store_true",
                        help="Enable debug output.")
    parser.add_argument("--websocket", type=str, default="tcp:8000",
                        help='WebSocket server Twisted endpoint descriptor, e.g. "tcp:9000" or "unix:/tmp/mywebsocket".')
    parser.add_argument("--wsurl", type=str, default="ws://localhost:8000",
                        help='WebSocket URL (must suit the endpoint), e.g. "ws://localhost:9000".')
    parser.add_argument(
        "-r", "--realm", type=str, default="vrplumber",
        help="The WAMP realm to start the component in (if any)."
    )
    
    return parser

if __name__ == '__main__':
    # parse command line arguments
    ##
    parser = get_options()
    args = parser.parse_args()
    # start Twisted logging to stdout
    ##
    if True or args.debug:
        log.startLogging(sys.stdout)

    # we use an Autobahn utility to install the "best" available Twisted reactor
    ##
    from autobahn.twisted.choosereactor import install_reactor
    reactor = install_reactor()
    if args.debug:
        print("Running on reactor {}".format(reactor))

    # create a WAMP router factory
    ##
    from autobahn.wamp.router import RouterFactory
    router_factory = RouterFactory()

    # create a WAMP router session factory
    from autobahn.twisted.wamp import RouterSessionFactory
    session_factory = RouterSessionFactory(router_factory)
    session_factory.session = WebServiceLoginRouterSession

    session_factory.add(TimeService(args.realm))

    # create a WAMP-over-WebSocket transport server factory
    transport_factory = WampWebSocketServerFactory(
        session_factory, args.wsurl, debug_wamp=args.debug)
    #transport_factory.protocol = ServerProtocol

    transport_factory.setProtocolOptions(failByDrop=False)

    from twisted.web.server import Site
    from twisted.web.static import File
    from autobahn.twisted.resource import WebSocketResource

    # we serve static files under "/" ..
    root = File(".")

    # .. and our WebSocket server under "/ws"
    resource = WebSocketResource(transport_factory)
    root.putChild("ws", resource)

    # run both under one Twisted Web Site
    site = Site(root)

    # start the WebSocket server from an endpoint
    ##
    server = serverFromString(reactor, args.websocket)
    server.listen(site)

    # now enter the Twisted reactor loop
    ##
    reactor.run()
