""" 
<Author>  Justin Cappos
  (inspired from a previous version by Geremy Condra)

<Start Date>
  May 16th, 2011

<Description>
  Lots of helper code for upPIR.   Much of this code will be used multiple 
  places, but some many not.   Anything that is at least somewhat general will
  live here.
  
"""

import sys

# used for os.path.exists, os.path.join and os.walk
import os

# only need ceil
import math 


import socket

# use this to turn the stream abstraction into a message abstraction...
import session


# Check the python version.   It's pretty crappy to do this from a library, 
# but it's an easy way to check this universally
if sys.version_info[0] != 2 or sys.version_info[1] < 5:
  print "Requires Python >= 2.5 and < 3.0"
  sys.exit(1)

# A safe way to serialize / deserialize network data
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


import hashlib


# Exceptions...

class FileNotFound(Exception):
  """The file could not be found"""

class IncorrectFileContents(Exception):
  """The contents of the file do not match the manifest"""



# these keys must exist in a manifest dictionary.
_required_manifest_keys = ['manifestversion', 'blocksize', 'blockcount', 
                           'blockhashlist', 'hashalgorithm', 
                           'vendorhostname', 'vendorport', 
                           'manifesthash', 'fileinfolist' ]

# an example manifest might look like:
# {'manifestversion':"1.0", 'blocksize':1024, 'blockcount':100, 
#  'blockhashlist':['ab3...', ''2de...', ...], 'hashalgorithm':'sha1-base64',
#  'vendorhostname':'blackbox.cs.washington.edu', vendorport:62293,
#  'manifesthash':'42a...', 
#  'fileinfolist':[{'filename':'file1',
#                   'hash':'a8...',
#                   'offset':1584, 
#                   'length':1023),   # (do I need this?)
#                  {'filename':'foo/file2', # (next file listed...)
#                   'hash':'4f...',
#                   'offset':2607,    
#                   'length':63451},  #  (do I need this?)
#                   ...]

def _validate_manifest(manifest):
  # private function that validates the manifest is okay
  # it raises a TypeError if it's not valid for some reason
  if type(manifest) != dict:
    raise TypeError("Manifest must be a dict!")

  # check for the required keys
  for key in _required_manifest_keys:
    if key not in manifest:
      raise TypeError("Manifest must contain key: "+key+"!")

  # check specific things
  if len(manifest['blockhashlist']) != manifest['blockcount']:
    raise TypeError("There must be a hash for every manifest block")

  # otherwise, I guess I'll let this slide.   I don't want the checking to
  # be too version specific  
  # JAC: Is this a dumb idea?   Should I just check it all?   Do I want
  # this to fail later?   Can the version be used as a proxy check for this?


_supported_hashalgorithms = ['md5', 'sha1', 'sha224', 'sha256', 'sha384', 
                             'sha512']

_supported_hashencodings = ['hex','raw']

def find_hash(contents, algorithm):
  # Helper function for hashing...   

  # first, if it's a noop, do nothing.   THIS IS FOR TESTING ONLY
  if algorithm == 'noop':
    return ''
  
  # accept things like: "sha1", "sha256-raw", etc.
  # before the '-' is one of the types known to hashlib.   After is

  hashencoding = 'hex'
  if '-' in algorithm:
    # yes, this will raise an exception in some cases...
    hashalgorithmname, hashencoding = algorithm.split('-')

  # check the args
  if hashalgorithmname not in _supported_hashalgorithms:
    raise TypeError("Do not understand hash algorithm: '"+algorithm+"'")

  if hashencoding not in _supported_hashencodings:
    raise TypeError("Do not understand hash algorithm: '"+algorithm+"'")

  
  hashobj = hashlib.new(hashalgorithmname)

  hashobj.update(contents)

  if hashencoding == 'raw':
    return hashobj.digest()
  elif hashencoding == 'hex':
    return hashobj.hexdigest()
  else:
    raise Exception("Internal Error!   Unknown hashencoding '"+hashencoding+"'")
  

  
def transmit_mirrorinfo(mirrorinfo, vendorlocation, defaultvendorport=62293):
  """
  <Purpose>
    Sends our mirror information to a vendor.   

  <Arguments>
    vendorlocation: A string that contains the vendor location.   This can be 
                    of the form "IP:port", "hostname:port", "IP", or "hostname"

    defaultvendorport: the port to use if the vendorlocation does not include 
                       one.
    

  <Exceptions>
    TypeError if the args are the wrong types or malformed...

    various socket errors if the connection fails.

    ValueError if vendor does not accept the mirrorinfo

  <Side Effects>
    Contacts the vendor and retrieves data from it

  <Returns>
    None
  """
  if type(mirrorinfo) != dict:
    raise TypeError("Mirror information must be a dictionary")

  # do the actual communication...
  answer = _remote_query_helper(vendorlocation, "MIRRORADVERTISE"+json.dumps(mirrorinfo), defaultvendorport)

  if answer != "OK":
    # JAC: I don't really like using ValueError.   I should define a new one
    raise ValueError(answer)



def retrieve_rawmanifest(vendorlocation, defaultvendorport=62293):
  """
  <Purpose>
    Retrieves the manifest data from a vendor.   It does not parse this
    data in any way.

  <Arguments>
    vendorlocation: A string that contains the vendor location.   This can be 
                    of the form "IP:port", "hostname:port", "IP", or "hostname"

    defaultvendorport: the port to use if the vendorlocation does not include 
                       one.
    

  <Exceptions>
    TypeError if the vendorlocation is the wrong type or malformed.

    various socket errors if the connection fails.

  <Side Effects>
    Contacts the vendor and retrieves data from it

  <Returns>
    A string containing the manifest data (unprocessed).   It is a good idea
    to use parse_manifest to ensure this data is correct.
  """
  return _remote_query_helper(vendorlocation, "GET MANIFEST", defaultvendorport)




def retrieve_xorblock_from_mirror(mirrorip, mirrorport,bitstring):
  """
  <Purpose>
    Retrieves a block from a mirror.   

  <Arguments>
    mirrorip: the mirror's IP address or hostname

    mirrorport: the mirror's port number

    bitstring: a bit string that contains an appropriately sized request that
               specifies which blocks to combine.

  <Exceptions>
    TypeError if the arguments are the wrong types.  ValueError if the 
    bitstring is the wrong size

    various socket errors if the connection fails.

  <Side Effects>
    Contacts the mirror and retrieves data from it

  <Returns>
    A string containing the manifest data (unprocessed).   It is a good idea
    to use parse_manifest to ensure this data is correct.
  """

  response = _remote_query_helper(mirrorip, "XORBLOCK"+bitstring,mirrorport)
  if response == 'Invalid request length':
    raise ValueError(response)

  return response





def retrieve_mirrorinfolist(vendorlocation, defaultvendorport=62293):
  """
  <Purpose>
    Retrieves the mirrorinfolist from a vendor.  

  <Arguments>
    vendorlocation: A string that contains the vendor location.   This can be 
                    of the form "IP:port", "hostname:port", "IP", or "hostname"
    
    defaultvendorport: the port to use if the vendorlocation does not include 
                       one.

  <Exceptions>
    TypeError if the vendorlocation is the wrong type or malformed.

    various socket errors if the connection fails.

    SessionEOF or ValueError may be raised if the other end is not speaking the
    correct protocol

  <Side Effects>
    Contacts the vendor and retrieves data from it

  <Returns>
    A list of mirror information dictionaries.   
  """
  rawmirrordata = _remote_query_helper(vendorlocation, "GET MIRRORLIST", defaultvendorport)

  mirrorinfolist = json.loads(rawmirrordata)

  # the mirrorinfolist must be a list (duh)
  if type(mirrorinfolist) != list:
    raise TypeError("Malformed mirror list from vendor.   Is a "+str(type(mirrorinfolist))+" not a list")
  
  for mirrorlocation in mirrorinfolist:
    # must be a string
    if type(mirrorlocation) != dict:
      raise TypeError("Malformed mirrorlocation from vendor.   Is a "+str(type(mirrorlocation))+" not a dict")

  # everything checked out
  return mirrorinfolist


  



def _remote_query_helper(serverlocation, command, defaultserverport):
  # private function that contains the guts of server communication.   It
  # issues a single query and then closes the connection.   This is used
  # both to talk to the vendor and also to talk to mirrors
  if type(serverlocation) != str and type(serverlocation) != unicode:
    raise TypeError("Server location must be a string, not "+str(type(serverlocation)))

  # now let's split it and ensure there are 0 or 1 colons
  splitlocationlist = serverlocation.split(':')
  
  if len(splitlocationlist) >2:
    raise TypeError("Server location may not contain more than one colon")


  # now either set the port or use the default
  if len(splitlocationlist) == 2:
    serverport = int(splitlocationlist[1])
  else: 
    serverport = defaultserverport

  # check that this port is in the right range
  if serverport <= 0 or serverport > 65535:
    raise TypeError("Server location's port is not in the allowed range")

  serverhostname = splitlocationlist[0]


  # now we actually download the information...
  
  # first open the socket
  serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  serversocket.connect((serverhostname, serverport))

  # then issue the relevant command
  session.sendmessage(serversocket, command)

  # and return the answer
  rawanswer = session.recvmessage(serversocket)

  serversocket.close()

  return rawanswer







def parse_manifest(rawmanifestdata):
  """
  <Purpose>
    Given raw manifest data, returns a dictionary containing a manifest 
    dictionary.

  <Arguments>
    rawmanifestdata: a string containing the raw manifest data as is produced
                     by the json module.
                     
  <Exceptions>
    TypeError or ValueError if the manifest data is corrupt

  <Side Effects>
    None

  <Returns>
    A dictionary containing the manifest.   
  """

  if type(rawmanifestdata) != str:
    raise TypeError("Raw manifest data must be a string")

  manifestdict = json.loads(rawmanifestdata)

  _validate_manifest(manifestdict)
  
  return manifestdict





def populate_xordatastore(manifestdict, xordatastore, rootdir="."):
  """
  <Purpose>
    Adds the files listed in the manifestdict to the datastore

  <Arguments>
    manifestdict: a manifest dictionary.

    xordatastore: the XOR datastore that we should populate.

    rootdir: The location to look for the files mentioned in the manifest
                     
  <Exceptions>
    TypeError if the manifest is corrupt or the rootdir is the wrong type.   
    
    FileNotFound if the rootdir does not contain a manifest file.

    IncorrectFileContents if the file listed in the manifest file has the 
                          wrong size or hash

  <Side Effects>
    None

  <Returns>
    None
  """

  if type(manifestdict) != dict:
    raise TypeError("Manifest dict must be a string")

  if type(rootdir) != str and type(rootdir) != unicode:
    raise TypeError("Mirror root must be a string")

  _add_data_to_datastore(xordatastore,manifestdict['fileinfolist'],rootdir, manifestdict['hashalgorithm'])

  hashlist = _compute_block_hashlist(xordatastore, manifestdict['blockcount'], manifestdict['blocksize'], manifestdict['hashalgorithm'])
  
  for blocknum in range(manifestdict['blockcount']):
 
    if hashlist[blocknum] != manifestdict['blockhashlist'][blocknum]:
      raise TypeError("Despite matching file hashes, block '"+str(blocknum)+"' has an invalid hash.\nCorrupt manifest or dirty xordatastore")

  # We're done!


def _add_data_to_datastore(xordatastore, fileinfolist, rootdir, hashalgorithm):
  # Private helper to populate the datastore

  # go through the files one at a time and populate the xordatastore
  for thisfiledict in fileinfolist:
    
    thisrelativefilename = thisfiledict['filename']
    thisfilehash = thisfiledict['hash']
    thisoffset = thisfiledict['offset']
    thisfilelength = thisfiledict['length']

    
    thisfilename = os.path.join(rootdir, thisrelativefilename)

    # read in the files and populate the xordatastore
    if not os.path.exists(thisfilename):
      raise FileNotFound("File '"+thisrelativefilename+"' listed in manifest cannot be found in manifest root: '"+rootdir+"'.")

    # can't go above the root!
    # JAC: I would use relpath, but it's 2.6 and on
    if not os.path.normpath(os.path.abspath(thisfilename)).startswith(os.path.abspath(rootdir)):
      raise TypeError("File in manifest cannot go back from the root dir!!!")

    # get the relevant data
    thisfilecontents = open(thisfilename).read()
    
    # let's see if this has the right size
    if len(thisfilecontents) != thisfilelength:
      raise IncorrectFileContents("File '"+thisrelativefilename+"' has the wrong size")
    
    # let's see if this has the right hash
    if thisfilehash != find_hash(thisfilecontents, hashalgorithm):
      raise IncorrectFileContents("File '"+thisrelativefilename+"' has the wrong hash")


    # and add it to the datastore
    xordatastore.set_data(thisoffset, thisfilecontents)
      


def _compute_block_hashlist(xordatastore, blockcount, blocksize, hashalgorithm):
  # private helper, used both the compute and check hashes

  currenthashlist = []
  
  # Now I'll check the blocks have the right hash...
  for blocknum in range(blockcount):
    # read the block ...
    thisblock = xordatastore.get_data(blocksize*blocknum, blocksize)
    
    # ... and check its hash
    currenthashlist.append(find_hash(thisblock, hashalgorithm))
    
  return currenthashlist
    




def nogaps_offset_assignment_function(fileinfolist, rootdir, blocksize):
  """
  <Purpose>
    Specifies how to map a set of files into offsets in an xordatastore.
    This simple function just adds them linearly.

  <Arguments>
    fileinfolist: a list of dictionaries with file information

    rootdir: the root directory where the files live

    block_size: The size of a block of data.   

  <Exceptions>
    TypeError, IndexError, or KeyError if the arguements are incorrect
    
  <Side Effects>
    Modifies the fileinfolist to add offset elements to each dict

  <Returns>
    None
  """

  # Note, this algorithm doesn't use the blocksize.   Most of algorithms will.
  # We also don't use the rootdir.   I think this is typical

  currentoffset = 0

  for thisfileinfo in fileinfolist:
    thisfileinfo['offset'] = currentoffset
    currentoffset = currentoffset + thisfileinfo['length']




def _find_blockloc_from_offset(offset, sizeofblocks):
  # Private helper function that translates an offset into (block, offset)
  assert(offset >=0)

  return (offset / sizeofblocks, offset % sizeofblocks)



def extract_file_from_blockdict(filename, manifestdict, blockdict):
  """
  <Purpose>
    Reconstitutes a file from a block dict

  <Arguments>
    filename: the file within the release we are asking about

    manifestdict: the manifest for the release

    blockdict: a dictionary of blocknum -> blockcontents

  <Exceptions>
    TypeError, IndexError, or KeyError if the args are incorrect
    
  <Side Effects>
    None

  <Returns>
    A string containing the file contents
  """
 
  blocksize = manifestdict['blocksize']

  for fileinfo in manifestdict['fileinfolist']:
    if filename == fileinfo['filename']:

      offset = fileinfo['offset']
      quantity = fileinfo['length']

      # Let's get the block information 
      (startblock,startoffset) = _find_blockloc_from_offset(offset, blocksize)
      (endblock, endoffset) = _find_blockloc_from_offset(offset+quantity, blocksize)

      # Case 1: this does not cross blocks
      if startblock == endblock:
        return blockdict[startblock][startoffset:endoffset]

      # Case 2: this crosses blocks

      # we'll build up the string starting with the first block...
      currentstring = blockdict[startblock][startoffset:]

      # now add in the 'middle' blocks.   This is all of the blocks 
      # after the start and before the end
      for currentblock in range(startblock+1, endblock):
        currentstring += blockdict[currentblock]

      # this check is needed because we might be past the last block.
      if endoffset > 0:
        # finally, add the end block. 
        currentstring += blockdict[endblock][:endoffset]

      # and return the result
      return currentstring

      

 






def get_blocklist_for_file(filename, manifestdict):
  """
  <Purpose>
    Get the list of blocks needed to reconstruct a file

  <Arguments>
    filename: the file within the release we are asking about

    manifestdict: the manifest for the release

  <Exceptions>
    TypeError, IndexError, or KeyError if the manifestdict / filename are
    corrupt
    
  <Side Effects>
    None

  <Returns>
    A list of blocks numbers
  """
 
  for fileinfo in manifestdict['fileinfolist']:
    if filename == fileinfo['filename']:
      # it's the starting offset / blocksize until the 
      # ending offset -1 divided by the blocksize
      # I do + 1 because range will otherwise omit the last block
      return range(fileinfo['offset'] / manifestdict['blocksize'], (fileinfo['offset'] + fileinfo['length'] - 1) / manifestdict['blocksize'] + 1)

  raise TypeError("File is not in manifest")
 






def get_filenames_in_release(manifestdict):
  """
  <Purpose>
    Get the list of files in a manifest

  <Arguments>
    manifestdict: the manifest for the release

  <Exceptions>
    TypeError, IndexError, or KeyError if the manifestdict is corrupt
    
  <Side Effects>
    None

  <Returns>
    A list of file names
  """
 
  filenamelist = []

  for fileinfo in manifestdict['fileinfolist']:
    filenamelist.append(fileinfo['filename'])
 
  return filenamelist




def _generate_fileinfolist(startdirectory, hashalgorithm="sha1-base64"):
  # private helper.   Generates a list of file information dictionaries for
  # all files under startdirectory.

  fileinfo_list = []

  # let's walk through the directories and add the files + sizes
  for parentdir, junkchilddirectories, filelist in os.walk(startdirectory):
    for filename in filelist:
      thisfiledict = {}
      # we want the relative name in the manifest, not the actual path / name
      thisfiledict['filename'] = filename
      fullfilename = os.path.join(parentdir, filename)

      thisfiledict['length'] = os.path.getsize(fullfilename)

      # get the hash
      filecontents = open(fullfilename).read()
      thisfiledict['hash'] = find_hash(filecontents, hashalgorithm)

      fileinfo_list.append(thisfiledict)
      

  return fileinfo_list
  

def compute_bitstring_length(num_blocks):
  # quick function to compute bitstring length
  return int(math.ceil(num_blocks/8.0))

def set_bitstring_bit(bitstring, bitnum,valuetoset):
  # quick function to set a bit in a bitstring...
  bytepos = bitnum / 8
  bitpos = 7-(bitnum % 8)
  
  bytevalue = ord(bitstring[bytepos])
  # if setting to 1...
  if valuetoset:
    if bytevalue & (2**bitpos):
      # nothing to do, it's set.
      return bitstring
    else:
      return bitstring[:bytepos]+ chr(bytevalue + (2**bitpos)) +bitstring[bytepos+1:]

  else: # I'm setting it to 0...
   
    if bytevalue & (2**bitpos):
      return bitstring[:bytepos]+ chr(bytevalue - (2**bitpos)) +bitstring[bytepos+1:]
    else:
      # nothing to do, it's not set.
      return bitstring
    

def get_bitstring_bit(bitstring, bitnum):
  # returns a bit...
  bytepos = bitnum / 8
  bitpos = 7-(bitnum % 8)

  # we want to return 0 or 1.   I'll AND 2^bitpos and then divide by it
  return (ord(bitstring[bytepos]) & (2**bitpos)) / (2**bitpos)


def flip_bitstring_bit(bitstring, bitnum):
  # reverses the setting of a bit
  targetbit = get_bitstring_bit(bitstring, bitnum)

  # 0 -> 1, 1 -> 0
  targetbit = 1-targetbit   
  
  return set_bitstring_bit(bitstring, bitnum, targetbit)



def create_manifest(rootdir=".", hashalgorithm="sha1-base64", block_size=1024*1024, offset_assignment_function=nogaps_offset_assignment_function, vendorhostname=None, vendorport=62293):
  """
  <Purpose>
    Create a manifest  (and an xordatastore ?)

  <Arguments>
    rootdir: The area to walk looking for files to add to the manifest

    hashalgorithm: The hash algorithm to use to validate file contents
                     
    block_size: The size of a block of data.   

    offset_assignment_function: specifies how to lay out the files in blocks.

  <Exceptions>
    TypeError if the arguments are corrupt or of the wrong type
    
    FileNotFound if the rootdir does not contain a manifest file.

    IncorrectFileContents if the file listed in the manifest file has the 
                          wrong size or hash

  <Side Effects>
    This function creates an XORdatastore while processing.   This may use
    a very large amount of memory.   (This is not fundamental, and is done only
    for convenience).

  <Returns>
    The manifest dictionary
  """

  if vendorhostname == None:
    raise TypeError("Must specify vendor server name")

  if ':' in vendorhostname:
    raise TypeError("Vendor server name must not contain ':'")

  # general workflow: 
  #   set the global parameters
  #   build an xordatastore and add file information as you go...
  #   derive hash information from the xordatastore

  manifestdict = {}

  manifestdict['manifestversion'] = "1.0"
  manifestdict['hashalgorithm'] = hashalgorithm
  manifestdict['blocksize'] = block_size
  manifestdict['vendorhostname'] = vendorhostname
  manifestdict['vendorport'] = vendorport


  # first get the file information
  fileinfolist = _generate_fileinfolist(rootdir, manifestdict['hashalgorithm'])

  # now let's assign the files to offsets as the caller requess...
  offset_assignment_function(fileinfolist, rootdir, manifestdict['blocksize'])

  # let's ensure the offsets are valid...

  # build a list of tuples with offset, etc. info...
  offsetlengthtuplelist = []
  for fileinfo in fileinfolist:
    offsetlengthtuplelist.append((fileinfo['offset'], fileinfo['length']))

  # ...sort the tuples so that it's easy to walk down them and check for
  # overlapping entries...
  offsetlengthtuplelist.sort()

  # ...now, we need to ensure the values don't overlap.
  nextfreeoffset = 0
  for offset, length in offsetlengthtuplelist:
    if offset < 0:
      raise TypeError("Offset generation led to negative offset!")
    if length < 0:
      raise TypeError("File lengths must be positive!")

    if nextfreeoffset > offset:
      raise TypeError("Error! Offset generation led to overlapping files!")

    # since this list is sorted by offset, this should ensure the property we
    # want is upheld.
    nextfreeoffset = offset + length

  # great!   The fileinfolist is okay!
  manifestdict['fileinfolist'] = fileinfolist


  # The nextfreeoffset value is the end of the datastore...   Let's see how
  # many blocks we need
  manifestdict['blockcount'] = int(math.ceil(nextfreeoffset * 1.0 / manifestdict['blocksize']))


  # TODO: Improve this.  It really shouldn't use a datastore...
  import fastsimplexordatastore

  xordatastore = fastsimplexordatastore.XORDatastore(manifestdict['blocksize'], manifestdict['blockcount'])

  # now let's put the files in the datastore
  _add_data_to_datastore(xordatastore, manifestdict['fileinfolist'], rootdir, manifestdict['hashalgorithm'])
   
  # and it is time to get the blockhashlist...
  manifestdict['blockhashlist'] = _compute_block_hashlist(xordatastore, manifestdict['blockcount'], manifestdict['blocksize'], manifestdict['hashalgorithm'])

  # let's generate the manifest's hash
  rawmanifest = json.dumps(manifestdict)
  manifestdict['manifesthash'] = find_hash(rawmanifest, manifestdict['hashalgorithm'])

  # we are done!
  return manifestdict
