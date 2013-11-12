# this is a few simple integration tests for an upPIR mirror.   Uses any local
# mirror

# if everything passes, there is no output

import socket

import session

import getmyip

mirrortocheck = getmyip.getmyip()

def get_response(requeststring):
  s = socket.socket()
  s.connect((mirrortocheck,62294))
  session.sendmessage(s,requeststring)
  return session.recvmessage(s)
  

# We don't know the size so we won't test it 'working'...

# are you friendly?
assert('HI!' == get_response('HELLO'))

# too short of a string (len 0)
assert('Invalid request length' == get_response('XORBLOCK'))

# too short of a string (len 0)
assert('Invalid request type' == get_response('ajskdfjsad'))
