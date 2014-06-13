# Authenticating WAMP with a Web Service Login

This is a spike-test for authenticating a WAMP connection using a 
call to an external web service. It assumes the existence of a 
web service:

    http://localhost:8080/ws-login/

where the service accepts POST parameters:

    username: username 
    password: password 

and does a lookup e.g. in a Django users database table to 
authenticate the user.  The service then returns a json
response indicating the logged-in username, or a failure 
to log in.

As an example, here is a Django view that implements the protocol:

    import logging, json
    from django.http import HttpResponse
    from django.views.decorators.csrf import csrf_exempt
    from django.contrib.auth import authenticate
    # you'll have to define this yourself
    from library import local_or_login_required
    log = logging.getLogger( __name__ )

    @csrf_exempt
    @local_or_login_required
    def ws_login( request ):
        """Perform login (if required) and then do nginx-internal redirect to web service
        
        Link into your urls like so:
        
            url( r'^ws-login/$', 'messagerouter.views.ws_login_and_redirect', name='messagerouter' ),
        
        """
        if not request.user.is_authenticated():
            username,password = request.POST.get('username'),request.POST.get('password')
            if username and password:
                user = authenticate(username=username, password=password)
                if user is not None:
                    if user.is_active:
                        # Note: we don't create sessions or do a login here 
                        # we are creating a persistent connection for this 
                        # machine...
                        return HttpResponse( json.dumps( {'username':user.username,'success':True}), mimetype='application/json' )
                    else:
                        log.info( 'Inactive user' )
                else:
                    log.info( "Unknown user" )
            else:
                log.info( 'No username/password' )
            return HttpResponse( json.dumps( {'success':False,'error':True,'message':'Not Authenticated'}), mimetype = 'application/json' )
        else:
            # web-gui access for already-logged-in user...
            return HttpResponse( json.dumps( {'username':request.user.username,'success':True}), mimetype='application/json')

The client connects to the Router, and recieves a Challenge message. It responds by providing the 
credentials passed on the command line.  The Router connects to the web-service to validate the 
credentials and if they are accepted, accepts the connection.
