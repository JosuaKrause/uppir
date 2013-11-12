""" 
<Author>
  Justin Cappos
  (inspired from a previous version by Geremy Condra)

<Start Date>
  May 15th, 2011

<Description>
  Mirror code that serves upPIR files.   A client obtains a list of live 
  mirrors from a vendor.   The client then sends bit strings to the mirror and
  the mirror returns XORed blocks of data.   The mirror will periodically
  announce its liveness to the vendor it is serving content for.   

  The files specified in the manifest must already exist on the local machine.

  For more technical explanation, please see the upPIR papers on my website.
  

<Usage>
  $ python uppir_mirror.py

  $ python uppir_mirror.py --help

<Options>
  See below...
"""


# This file is laid out in four main parts.   First, there are some helper
# functions to advertise the mirror with the vendor.   The second section
# includes the functionality to serve content via upPIR.   The third section
# serves data via HTTP.   The final part contains the option
# parsing and main.   To get an overall feel for the code, it is recommended
# to follow the execution from main on.
#
# EXTENSION POINTS:
#
# One can define new xordatastore types (although I need a more explicit plugin
# module).   These could include memoization and other optimizations to 
# further improve the speed of XOR processing.
#




import sys

import optparse

# Holds the mirror data and produces the XORed blocks
import fastsimplexordatastore

# helper functions that are shared
import uppirlib

import optparse

# TODO: consider FTP via pyftpdlib (?)

# This is used to communicate with clients with a message like abstraction
import session

# used to start the UPPIR / HTTP servers in parallel
import threading

import getmyip


# to handle upPIR protocol requests
import SocketServer

# to run in the background...
import daemon


# for logging purposes...
import time
import traceback

_logfo=None

def _log(stringtolog):
  # helper function to log data
  _logfo.write(str(time.time()) +" "+stringtolog+"\n")
  _logfo.flush()



# JAC: I don't normally like to use Python's socket servers because of the lack
#      of control but I'll give it a try this time.   Passing arguments to
#      requesthandlers is a PITA.   I'll use a messy global instead
_global_myxordatastore = None
_global_manifestdict = None


#################### Advertising ourself with the vendor ######################

def _send_mirrorinfo():
  # private function that sends our mirrorinfo to the vendor


  # adding more information here  is a natural way to extend the mirror /
  # client.   The vendor should not need to be changed
  # at a minimum, the 'ip' and 'port' are required to provide the client with
  # information about how to contact the mirror.
  mymirrorinfo = {'ip':_commandlineoptions.ip, 'port':_commandlineoptions.port}

  uppirlib.transmit_mirrorinfo(mymirrorinfo, _global_manifestdict['vendorhostname'], _global_manifestdict['vendorport'])
  



############################### Serve via upPIR ###############################


# I don't need to change this much, I think...
class ThreadedXORServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer): 
  allow_reuse_address=True


class ThreadedXORRequestHandler(SocketServer.BaseRequestHandler):

  def handle(self):

    # read the request from the socket...
    requeststring = session.recvmessage(self.request)

    # for logging purposes, get the remote info
    remoteip, remoteport = self.request.getpeername()

    # if it's a request for a XORBLOCK
    if requeststring.startswith('XORBLOCK'):

      bitstring = requeststring[len('XORBLOCK'):]
  
      expectedbitstringlength = uppirlib.compute_bitstring_length(_global_myxordatastore.numberofblocks)

      if len(bitstring) != expectedbitstringlength:
        # Invalid request length...
        _log("UPPIR "+remoteip+" "+str(remoteport)+" Invalid request with length: "+str(len(bitstring)))

        session.sendmessage(self.request, 'Invalid request length')
        return
  
      # Now let's process this...
      xoranswer = _global_myxordatastore.produce_xor_from_bitstring(bitstring)

      # and send the reply.
      session.sendmessage(self.request, xoranswer)
      _log("UPPIR "+remoteip+" "+str(remoteport)+" GOOD")

      # done!
      return

    elif requeststring == 'HELLO':
      # send a reply.
      session.sendmessage(self.request, "HI!")
      _log("UPPIR "+remoteip+" "+str(remoteport)+" HI!")

      # done!
      return

    else:
      # we don't know what this is!   Log and tell the requestor
      _log("UPPIR "+remoteip+" "+str(remoteport)+" Invalid request type starts:'"+requeststring[:5]+"'")

      session.sendmessage(self.request, 'Invalid request type')
      return





def service_uppir_clients(myxordatastore, ip, port):

  # this should be done before we are called
  assert(_global_myxordatastore != None)

  # create the handler / server
  xorserver = ThreadedXORServer((ip, port), ThreadedXORRequestHandler)
  

  # and serve forever!   This call will not return which is why we spawn a new
  # thread to handle it
  threading.Thread(target=xorserver.serve_forever, name="upPIR mirror server").start()



################################ Serve via HTTP ###############################

import BaseHTTPServer

import urlparse

# handle a HTTP request
class MyHTTPRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):

  def do_GET(self):

    # get the path part of the request.   Ignore the host name, etc.
    requestedfilename = urlparse.urlparse(self.path).path

    # if there is a leading '/' then kill it.
    if requestedfilename.startswith('/'):
      requestedfilename = requestedfilename[1:]

    # let's look for the file...
    for fileinfo in _global_manifestdict['fileinfolist']:
      # great, let's serve it!
      if requestedfilename == fileinfo['filename']:
        # it's a good query!   Send 200!
        self.send_response(200)
        self.end_headers()

        # and send the response!
        filedata = _global_myxordatastore.get_data(fileinfo['offset'],fileinfo['length'])
        self.wfile.write(filedata)
        return

    # otherwise, it's unknown...
    self.send_error(404)
    return
    
  # log HTTP information
  def log_message(self,format, *args):
    _log("HTTP "+self.client_address[0]+" "+str(self.client_address[1])+" "+(format % args))




def service_http_clients(myxordatastore, manifestdict, ip, port):
  # time to serve HTTP clients...
  
  # this must have already been set
  assert(_global_myxordatastore != None)
  assert(_global_manifestdict != None)

  httpserver = BaseHTTPServer.HTTPServer((ip, port), MyHTTPRequestHandler)

  # and serve forever!   Just like with upPIR, this doesn't return so we need a
  # new thread...
  threading.Thread(target=httpserver.serve_forever, name="HTTP server").start()





########################### Option parsing and main ###########################
_commandlineoptions = None

def parse_options():
  """
  <Purpose>
    Parses command line arguments.

  <Arguments>
    None
  
  <Side Effects>
    All relevant data is added to _commandlineoptions

  <Exceptions>
    These are handled by optparse internally.   I believe it will print / exit
    itself without raising exceptions further.   I do print an error and
    exit if there are extra args...

  <Returns>
    None
  """
  global _commandlineoptions
  global _logfo

  # should be true unless we're initing twice...
  assert(_commandlineoptions==None)

  parser = optparse.OptionParser()

  parser.add_option("","--ip", dest="ip", type="string", metavar="IP", 
        default=getmyip.getmyip(), help="Listen for clients on the following IP (default is the public facing IP)")

  parser.add_option("","--port", dest="port", type="int", metavar="portnum", 
        default=62294, help="Use the following port to serve upPIR clients (default 62294)")

  parser.add_option("","--http", dest="http", action="store_true", 
        default=False, help="Serve legacy clients via HTTP (default False)")

  parser.add_option("","--httpport", dest="httpport", type="int",
        default=80, help="Serve HTTP clients on this port (default 80)")

  parser.add_option("","--mirrorroot", dest="mirrorroot", type="string", 
        metavar="dir", default=".", 
        help="The base directory where all mirror files live under")

  parser.add_option("","--retrievemanifestfrom", dest="retrievemanifestfrom", 
        type="string", metavar="vendorIP:port", default="",
        help="Specifies the vendor to retrieve the manifest from (default None).")

  parser.add_option("","--manifestfile", dest="manifestfilename", 
        type="string", default="manifest.dat",
        help="The manifest file to use (default manifest.dat).")

  parser.add_option("","--foreground", dest="daemonize", action="store_false",
        default=True,
        help="Do not detach from the terminal and run in the background")

  parser.add_option("","--logfile", dest="logfilename", 
        type="string", default="mirror.log",
        help="The file to write log data to (default mirror.log).")

  parser.add_option("","--announcedelay", dest="mirrorlistadvertisedelay",
        type="int", default=60,
        help="How many seconds should I wait between vendor notifications? (default 60).")


  # let's parse the args
  (_commandlineoptions, remainingargs) = parser.parse_args()


  # check the arguments
  if _commandlineoptions.port <=0 or _commandlineoptions.port >65535:
    print "Specified port number out of range"
    sys.exit(1)

  if _commandlineoptions.httpport <=0 or _commandlineoptions.httpport >65535:
    print "Specified HTTP port number out of range"
    sys.exit(1)

  if _commandlineoptions.mirrorlistadvertisedelay < 0:
    print "Mirror advertise delay must be positive"
    sys.exit(1)

  if remainingargs:
    print "Unknown options",remainingargs
    sys.exit(1)

  # try to open the log file...
  _logfo = open(_commandlineoptions.logfilename, 'a')


def main():
  global _global_myxordatastore
  global _global_manifestdict

  
  # If we were asked to retrieve the mainfest file, do so...
  if _commandlineoptions.retrievemanifestfrom:
    # We need to download this file...
    rawmanifestdata = uppirlib.retrieve_rawmanifest(_commandlineoptions.retrievemanifestfrom)

    # ...make sure it is valid...
    manifestdict = uppirlib.parse_manifest(rawmanifestdata)
    
    # ...and write it out if it's okay
    open(_commandlineoptions.manifestfilename, "w").write(rawmanifestdata)


  else:
    # Simply read it in from disk

    rawmanifestdata = open(_commandlineoptions.manifestfilename).read()

    manifestdict = uppirlib.parse_manifest(rawmanifestdata)
  
  # We should detach here.   I don't do it earlier so that error
  # messages are written to the terminal...   I don't do it later so that any
  # threads don't exist already.   If I do put it much later, the code hangs...
  if _commandlineoptions.daemonize:
    daemon.daemonize()



  myxordatastore = fastsimplexordatastore.XORDatastore(manifestdict['blocksize'], manifestdict['blockcount'])

  # now let's put the content in the datastore in preparation to serve it
  uppirlib.populate_xordatastore(manifestdict, myxordatastore, rootdir = _commandlineoptions.mirrorroot)
    
  # we're now ready to handle clients!
  _log('ready to start servers!')

  # an ugly hack, but Python's request handlers don't have an easy way to
  # pass arguments
  _global_myxordatastore = myxordatastore
  _global_manifestdict = manifestdict
 
  # first, let's fire up the upPIR server
  service_uppir_clients(myxordatastore, _commandlineoptions.ip, _commandlineoptions.port)

  # If I should serve legacy clients via HTTP, let's start that up...
  if _commandlineoptions.http:
    service_http_clients(myxordatastore, manifestdict, _commandlineoptions.ip, _commandlineoptions.httpport)

  _log('servers started!')

  # let's send the mirror information periodically...
  # we should log any errors...
  while True:
    try:
      _send_mirrorinfo()
    except Exception, e:
      _log(str(e)+"\n"+str(traceback.format_tb(sys.exc_info()[2])))

    time.sleep(_commandlineoptions.mirrorlistadvertisedelay)



if __name__ == '__main__':
  parse_options()
  try:
    main()
  except Exception, e:
    # log errors to prevent silent exiting...   
    print(str(type(e))+" "+str(e))
    # this mess prints a not-so-nice traceback, but it does contain all 
    # relevant info
    _log(str(e)+"\n"+str(traceback.format_tb(sys.exc_info()[2])))
    sys.exit(1)

