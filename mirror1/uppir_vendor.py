""" 
<Author>
  Justin Cappos
  (inspired from a previous version by Geremy Condra)

<Start Date>
  May 15th, 2011

<Description>
  Vendor code for upPIR.   The vendor serves the manifest and mirror list.
  Thus it acts as a way for mirrors to advertise that they are alive and 
  for clients to find living mirrors.   

  A later version will support client notifications of cheating.

  For more technical explanation, please see the upPIR papers on my website.
  

<Usage>
  $ python uppir_vendor.py 


<Options>

  See Below

"""

# This file is laid out in three main parts.   First, there are helper routines
# that manage the addition and expiration of mirrorlist content.   Following
# this are the server routines that handle communications with the clients 
# or mirrors.   The final part contains the argument parsing and main 
# function.   To understand the code, it is recommended one starts at main
# and reads from there.
#
# EXTENSION POINTS:
#
# To handle malicious mirrors, the client and vendor will need to have 
# support for malicious block reporting.   This change will be primarily
# in the server portion although, the mirror would also need to include 
# a way to blacklist offending mirrors to prevent them from re-registering




import sys

import optparse

# helper functions that are shared
import uppirlib

import optparse


# Check the python version
if sys.version_info[0] != 2 or sys.version_info[1] < 5:
  print "Requires Python >= 2.5 and < 3.0"
  sys.exit(1)

# get JSON 
if sys.version_info[1] == 5:
  try:
    import simplejson as json
  except ImportError:
    # This may have plausibly been forgotten
    print "Requires simplejson on Python 2.5.X"
    sys.exit(1)
else:
  # This really should be there.   Let's ignore the try-except block...
  import json


# This is used to communicate with clients with a message like abstraction
import session

# used to get a lock
import threading


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
_global_rawmanifestdata = None
_global_rawmirrorlist = None

# These are more defensible.   
_global_mirrorinfodict = {}
_global_mirrorinfolock = threading.Lock()


########################### Mirrorlist manipulation ##########################
import time



def _check_for_expired_mirrorinfo():
  # Private function to check to see if mirrors are expired...

  # I'll be updating this
  global _global_rawmirrorlist

  # No need to block and wait for this to happen if there are multiple of these
  if _global_mirrorinfolock.acquire(False):

    # always release the lock...
    try:
      now = time.time()
      # walk through the mirrors and remove any that are over time...
      for mirrorip in _global_mirrorinfodict:
    
        # if it's expired, remove the entry...
        if now > _commandlineoptions.mirrorexpirytime + _global_mirrorinfodict[mirrorip]['advertisetime']:
          del _global_mirrorinfodict[mirrorip]
    
      mirrorlist = []
      # now let's rebuild the mirrorlist
      for mirrorip in _global_mirrorinfodict:
        mirrorlist.append(_global_mirrorinfodict[mirrorip]['mirrorinfo'])

      # and replace the global
      _global_rawmirrorlist = json.dumps(mirrorlist)

    finally:
      # always release
      _global_mirrorinfolock.release()




def _add_mirrorinfo_to_list(thismirrorinfo):
  # Private function to add mirror information

  # add mirror information along with the time
  mirrorip = thismirrorinfo['ip']

  # get the lock and add it to the dict
  _global_mirrorinfolock.acquire()
  try:
    # I get the time in here, in case I block for a noticible time waiting for
    # the lock
    now = time.time()
    _global_mirrorinfodict[mirrorip] = {'mirrorinfo':thismirrorinfo, 'advertisetime':now}

  finally:
    _global_mirrorinfolock.release()
  

  


######################### Serve upPIR vendor requests ########################


# I don't need to change this much, I think...
class ThreadedVendorServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer): 
  allow_reuse_address=True


class ThreadedVendorRequestHandler(SocketServer.BaseRequestHandler):

  def handle(self):

    # read the request from the socket...
    requeststring = session.recvmessage(self.request)

    # for logging purposes, get the remote info
    remoteip, remoteport = self.request.getpeername()

    # if it's a request for a XORBLOCK
    if requeststring == 'GET MANIFEST':

      session.sendmessage(self.request, _global_rawmanifestdata)
      _log("UPPIRVendor "+remoteip+" "+str(remoteport)+" manifest request")
  
      # done!
      return

    elif requeststring == 'GET MIRRORLIST':
      # let's try to clean up the list.   If we are busy with another attempt
      # to do this, the latter will be a NOOP
      _check_for_expired_mirrorinfo()

      # reply with the mirror list
      session.sendmessage(self.request, _global_rawmirrorlist)
      _log("UPPIRVendor "+remoteip+" "+str(remoteport)+" mirrorlist request")

      # done!
      return

    elif requeststring.startswith('MIRRORADVERTISE'):
      # This is a mirror telling us it's ready to serve clients.

      mirrorrawdata = requeststring[len('MIRRORADVERTISE'):]
      
      # handle the case where the mirror provides data that is larger than 
      # we want to serve
      if len(mirrorrawdata) > _commandlineoptions.maxmirrorinfo:
        session.sendmessage(self.request, "Error, mirrorinfo too large!")
        _log("UPPIRVendor "+remoteip+" "+str(remoteport)+" mirrorinfo too large: "+str(len(mirrorrawdata)))
        return

      # Let's sanity check the data...
      # can we deserialize it?
      try:
        mirrorinfodict = json.loads(mirrorrawdata)
      except (TypeError, ValueError), e:
        session.sendmessage(self.request, "Error cannot deserialize mirrorinfo!")
        _log("UPPIRVendor "+remoteip+" "+str(remoteport)+" cannot deserialize mirrorinfo!"+str(e))
        return

      # is it a dictionary and does it have the required keys?
      if type(mirrorinfodict) != dict or 'ip' not in mirrorinfodict or 'port' not in mirrorinfodict:
        session.sendmessage(self.request, "Error, mirrorinfo has an invalid format.")
        _log("UPPIRVendor "+remoteip+" "+str(remoteport)+" mirrorinfo has an invalid format")
        return
      
      # is it a dictionary and does it have the required keys?
      if mirrorinfodict['ip'] != remoteip:
        session.sendmessage(self.request, "Error, must provide mirrorinfo from the mirror's IP")
        _log("UPPIRVendor "+remoteip+" "+str(remoteport)+" mirrorinfo provided from the wrong IP")
        return
      
      # add the information to the mirrorlist
      _add_mirrorinfo_to_list(mirrorinfodict)

      # and notify the user
      session.sendmessage(self.request, 'OK')
      _log("UPPIRVendor "+remoteip+" "+str(remoteport)+" mirrorinfo update "+str(len(mirrorrawdata)))

      # done!
      return

   # add HELLO
    elif requeststring == 'HELLO':
      # send a reply.
      session.sendmessage(self.request, "VENDORHI!")
      _log("UPPIRVendor "+remoteip+" "+str(remoteport)+" VENDORHI!")

      # done!
      return

    else:
      # we don't know what this is!   Log and tell the requestor
      _log("UPPIRVendor "+remoteip+" "+str(remoteport)+" Invalid request type starts:'"+requeststring[:5]+"'")

      session.sendmessage(self.request, 'Invalid request type')
      return





def start_vendor_service(manifestdict, ip, port):

  # this should be done before we are called
  assert(_global_rawmanifestdata != None)

  # create the handler / server
  vendorserver = ThreadedVendorServer((ip, port), ThreadedVendorRequestHandler)
  

  # and serve forever!   This call will not return which is why we spawn a new
  # thread to handle it
  threading.Thread(target=vendorserver.serve_forever, name="upPIR vendor server").start()





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

  # I should use these from the manifest, not the command line...
#  parser.add_option("","--ip", dest="ip", type="string", metavar="IP", 
#        default="0.0.0.0", help="Listen for clients on the following IP")

#  parser.add_option("","--port", dest="port", type="int", metavar="portnum", 
#        default=62293, help="Run the vendor on the following port (default 62293)")

  parser.add_option("","--manifestfile", dest="manifestfilename", 
        type="string", default="manifest.dat",
        help="The manifest file to use (default manifest.dat).")

  parser.add_option("","--foreground", dest="daemonize", action="store_false",
        default=True,
        help="Do not detach from the terminal and run in the background")

  parser.add_option("","--logfile", dest="logfilename", 
        type="string", default="vendor.log",
        help="The file to write log data to (default vendor.log).")

  parser.add_option("","--maxmirrorinfo", dest="maxmirrorinfo", 
        type="int", default=10240,
        help="The maximum amount of serialized data a mirror can add to the mirror list (default 10K)")

  parser.add_option("","--mirrorexpirytime", dest="mirrorexpirytime", 
        type="int", default=300,
        help="The number of seconds of inactivity before expiring a mirror (default 300).")



  # let's parse the args
  (_commandlineoptions, remainingargs) = parser.parse_args()


  # check the maxmirrorinfo
  if _commandlineoptions.maxmirrorinfo <=0: 
    print "Max mirror info size must be positive"
    sys.exit(1)


  if remainingargs:
    print "Unknown options",remainingargs
    sys.exit(1)

  # try to open the log file...
  _logfo = open(_commandlineoptions.logfilename, 'a')



def main():
  global _global_rawmanifestdata
  global _global_rawmirrorlist 

  
  # read in the manifest file
  rawmanifestdata = open(_commandlineoptions.manifestfilename).read()

  # an ugly hack, but Python's request handlers don't have an easy way to
  # pass arguments
  _global_rawmanifestdata = rawmanifestdata
  _global_rawmirrorlist = json.dumps([])

  # I do this just for the sanity / corruption check
  manifestdict = uppirlib.parse_manifest(rawmanifestdata)

  vendorip = manifestdict['vendorhostname']
  vendorport = manifestdict['vendorport']
  
  # We should detach here.   I don't do it earlier so that error
  # messages are written to the terminal...   I don't do it later so that any
  # threads don't exist already.   If I do put it much later, the code hangs...
  if _commandlineoptions.daemonize:
    daemon.daemonize()

  # we're now ready to handle clients!
  _log('ready to start servers!')

 
  # first, let's fire up the upPIR server
  start_vendor_service(manifestdict, vendorip, vendorport)


  _log('servers started!')



if __name__ == '__main__':
  parse_options()
  try:
    main()
  except Exception, e:
    # log errors to prevent silent exiting...   
    print(str(type(e))+" "+str(e))
    # this mess prints a not-so-nice traceback, but it does contain all 
    # relevant info
    _log(str(traceback.format_tb(sys.exc_info()[2])))
    sys.exit(1)

