""" 
<Author>
  Justin Cappos
  (inspired from a previous version by Geremy Condra)

<Start Date>
  May 15th, 2011

<Description>
  Client code for retrieving upPIR files.   This program uses a manifest
  to communicate with a vendor and retrieve a list of mirrors.   The client
  then _privately_ downloads the appropriate files from mirrors in the mirror 
  list.  None of the mirrors can tell what file or files were downloaded.

  For more technical explanation, please see the upPIR papers on my website.
  

<Usage>
  $ python uppir_client.py file1 [file2 ...]
  
  This will anonymously download file1, file2, ... from the vendor specified.


<Options>
  See below
  

"""


# This file is laid out in two main parts.   First, there are some helper
# functions to do moderately complex things like retrieving a block from a 
# mirror or split a file into blocks.   The second part contains the option
# parsing and main.   To get an overall feel for the code, it is recommended
# to follow the execution from main on.
#
# EXTENSION POINTS:
#
# Making the client extensible is a major problem.   In particular, we will 
# need to modify mirror selection, block selection, malicious mirror detection, 
# and avoiding slow nodes simultaneously.   To do this effectively, we need 
# some sort of mechanism that gives the programmer control over how to handle 
# these.
#
# The XORRequestor interface is used to address these issues.   A programmer
# The programmer defines an object that is provided the manifest, 
# mirrorlist, and blocks to retrieve.   The XORRequestor object must support 
# several methods: get_next_xorrequest(), notify_failure(xorrequest), 
# notify_success(xorrequest, xordata), and return_block(blocknum).   The 
# request_blocks_from_mirrors function in this file will use threads to call 
# these methods to determine what to retrieve.   The notify_* routines are 
# used to inform the XORRequestor object of prior results so that it can 
# decide how to issue future block requests.   This separates out the 'what'
# from the 'how' but has a slight loss of control.  Note that the block 
# reconstruction, etc. is done here to allow easy extensibility of malicious 
# mirror detection / vendor notification.
#
#
# The manifest file could also be extended to support huge files (those that
# span multiple releases).   The client would need to download files from
# multiple releases and then stitch them back together.   This would require
# minor changes (or possibly could be done using this code as a black box).
#


import sys

import optparse


# helper functions that are shared
import uppirlib


# used to issue requests in parallel
import threading


# I really should have a way to do this based upon command line options
import simplexorrequestor


# for basename
import os.path



def _request_helper(rxgobj):
  # Private helper to get requests.   Multiple threads will execute this...

  thisrequest = rxgobj.get_next_xorrequest()
  
  # go until there are no more requests
  while thisrequest != ():
    mirrorip = thisrequest[0]['ip']
    mirrorport = thisrequest[0]['port']
    bitstring = thisrequest[2]
    try:
      # request the XOR block...
      xorblock = uppirlib.retrieve_xorblock_from_mirror(mirrorip, mirrorport, bitstring)

    except Exception, e:
      if 'socked' in str(e):
        rxgobj.notify_failure(thisrequest)
        sys.stdout.write('F')
        sys.stdout.flush()
      else:
        # otherwise, re-raise...
        raise  

    else:
      # we retrieved it successfully...
      rxgobj.notify_success(thisrequest, xorblock)
      sys.stdout.write('.')
      sys.stdout.flush()
    
    # regardless of failure or success, get another request...
    thisrequest = rxgobj.get_next_xorrequest()

  # and that's it!
  return


def request_blocks_from_mirrors(requestedblocklist, manifestdict):
  """
  <Purpose>
    Retrieves blocks from mirrors

  <Arguments>
    requestedblocklist: the blocks to acquire

    manifestdict: the manifest with information about the release
  
  <Side Effects>
    Contacts mirrors to retrieve blocks.    It uses some global options

  <Exceptions>
    TypeError may be raised if the provided lists are invalid.   
    socket errors may be raised if communications fail.

  <Returns>
    A dict mapping blocknumber -> blockcontents.
  """

  # let's get the list of mirrors...
  mirrorinfolist = uppirlib.retrieve_mirrorinfolist(manifestdict['vendorhostname'], manifestdict['vendorport'])
  print "Mirrors: ",mirrorinfolist


  # let's set up a requestor object...
  rxgobj = simplexorrequestor.RandomXORRequestor(mirrorinfolist, requestedblocklist, manifestdict, _commandlineoptions.numberofmirrors)

  # let's fire up the requested number of threads.   Our thread will also
  # participate
  # (-1 because of us!)
  for threadnum in range(_commandlineoptions.numberofthreads - 1):
    threading.Thread(target=_request_helper, args=[rxgobj]).start()

  _request_helper(rxgobj)
  print

  # okay, now we have them all...   Let's get the returned dict ready...
  retdict = {}
  for blocknum in requestedblocklist:
    retdict[blocknum] = rxgobj.return_block(blocknum)

  return retdict
  

  




def request_files_from_mirrors(requestedfilelist, manifestdict):
  """
  <Purpose>
    Reconstitutes files by privately contacting mirrors

  <Arguments>
    requestedfilelist: the files to acquire

    manifestdict: the manifest with information about the release
  
  <Side Effects>
    Contacts mirrors to retrieve files.   They are written to disk

  <Exceptions>
    TypeError may be raised if the provided lists are invalid.   
    socket errors may be raised if communications fail.

  <Returns>
    None
  """
  
  neededblocks = []
  # let's figure out what blocks we need
  for filename in requestedfilelist:
    theseblocks = uppirlib.get_blocklist_for_file(filename, manifestdict)
    print filename, theseblocks

    # add the blocks we don't already know we need to request
    for blocknum in theseblocks:
      if blocknum not in neededblocks:
        neededblocks.append(blocknum)
    

  # do the actual retrieval work
  blockdict = request_blocks_from_mirrors(neededblocks, manifestdict)

  # now we should write out the files
  for filename in requestedfilelist:
    filedata = uppirlib.extract_file_from_blockdict(filename, manifestdict, blockdict)  

    # let's check the hash
    thisfilehash = uppirlib.find_hash(filedata, manifestdict['hashalgorithm'])

    for fileinfo in manifestdict['fileinfolist']:
      # find this entry
      if fileinfo['filename'] == filename:
        if thisfilehash == fileinfo['hash']:
          # we found it and it checks out!
          break
        else:
          raise Exception("Corrupt manifest has incorrect file hash despite passing block hash checks")
    else:
      raise Exception("Internal Error: Cannot locate fileinfo in manifest")


    # open the filename w/o the dir and write it
    filenamewithoutpath = os.path.basename(filename)
    open(filenamewithoutpath,"w").write(filedata)
    print "wrote",filenamewithoutpath




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
    The list of files to retreive
  """
  global _commandlineoptions

  # should be true unless we're initing twice...
  assert(_commandlineoptions==None)

  parser = optparse.OptionParser()

  parser.add_option("","--retrievemanifestfrom", dest="retrievemanifestfrom", 
        type="string", metavar="vendorIP:port", default="",
        help="Specifies the vendor to retrieve the manifest from (default None).")

  parser.add_option("","--manifestfile", dest="manifestfilename", 
        type="string", default="manifest.dat",
        help="The manifest file to use (default manifest.dat).")

  parser.add_option("-n","--numberofmirrors", dest="numberofmirrors",
        type="int", default=3,
        help="How many mirrors should need to collude to break privacy? (default 3)")

  parser.add_option("","--numberofthreads", dest="numberofthreads",
        type="int", default=None,
        help="How many threads should concurrently contact mirrors? (default numberofmirrors)")



  # let's parse the args
  (_commandlineoptions, remainingargs) = parser.parse_args()

  if _commandlineoptions.numberofmirrors < 1:
    print "Mirrors to contact must be positive"
    sys.exit(1)

  if _commandlineoptions.numberofthreads == None:
    _commandlineoptions.numberofthreads = _commandlineoptions.numberofmirrors

  if _commandlineoptions.numberofthreads < 1:
    print "Number of threads must be positive"
    sys.exit(1)


  if len(remainingargs) == 0:
    print "Must specify some files to retrieve!"
    sys.exit(1)

  _commandlineoptions.filestoretrieve = remainingargs






def main():

  
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
  

  # we will check that the files are in the release

  # find the list of files
  manifestfilelist = uppirlib.get_filenames_in_release(manifestdict)

  print manifestfilelist
  # ensure the requested files are in there...
  for filename in _commandlineoptions.filestoretrieve:

    if filename not in manifestfilelist:
      print "File:",filename,"is not listed in the manifest."
      sys.exit(2)
    


  
  request_files_from_mirrors(_commandlineoptions.filestoretrieve, manifestdict)



if __name__ == '__main__':
  parse_options()
  main()

