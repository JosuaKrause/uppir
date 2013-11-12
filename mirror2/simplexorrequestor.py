""" 
<Author>
  Justin Cappos

<Start Date>
  May 21st, 2011

<Description>
  A requestor object that selects mirrors randomly.   For example, if you want 
  3 mirror privacy and there are 5 available mirrors, you will download all
  blocks from 3 randomly selected mirrors.   If one of the mirrors you selected
  fails, you will use a previously non-selected mirror for the remainder of 
  the blocks.

  For more technical explanation, please see the upPIR papers on my website.
  


"""


# I'll use this to XOR the result together
import simplexordatastore


# helper functions that are shared
import uppirlib


# used for locking parallel requests
import threading

# to sleep...
import time

# TODO / BUG: Ask Geremy if I should be using os.urandom
import os
_randomnumberfunction = os.urandom

# used for mirror selection...
import random

########################### XORRequestGenerator ###############################


def _reconstruct_block(blockinfolist):
  # private helper to reconstruct a block
    
  # xor the blocks together
  currentresult = blockinfolist[0]['xorblock']
  for xorblockdict in blockinfolist[1:]:
    currentresult = simplexordatastore.do_xor(currentresult, xorblockdict['xorblock'])

  # and return the answer
  return currentresult



class InsufficientMirrors(Exception):
  """There are insufficient mirrors to handle your request"""


# These provide an easy way for the client XOR request behavior to be 
# modified.   If you wanted to change the policy by which mirrors are selected,
# the failure behavior for offline mirrors, or the way in which blocks
# are selected.   


class RandomXORRequestor:
  """
  <Purpose>
    Basic XORRequestGenerator that just picks some number of random mirrors
    and then retrieves all blocks from them.   If any mirror fails or is 
    offline, the operation fails.
    
    The strategy this uses is very, very simple.   First we randomly choose
    $n$ mirrors we want to retrieve blocks from.   If at any point, we have
    a failure when retrieving a block, we replace that mirror with a 
    mirror we haven't chosen yet.   

  <Side Effects>
    None.

  <Example Use>
    >>> rxgobj = RandomXORRequestor(['mirror1','mirror2','mirror3'], 
             [23, 45], { ...# manifest dict omitted # }, 2) 

    >>> print rxgobj.get_next_xorrequest()
    ('mirror3',23, '...')   # bitstring omitted
    >>> print rxgobj.get_next_xorrequest()
    ('mirror1',23, '...')   # bitstring omitted
    >>> print rxgobj.get_next_xorrequest()
    # this will block because we didn't say either of the others 
    # completed and there are no other mirrors waiting

    >>> rxgobj.notify_success(('mirror1',23,'...'), '...') 
    # the bit string and result were omitted from the previous statement
    >>> print rxgobj.get_next_xorrequest()
    ('mirror1',45, '...')   # bitstring omitted
    >>> rxgobj.notify_success(('mirror3',23, '...'), '...')  
    >>> print rxgobj.get_next_xorrequest()
    ('mirror1',45, '...')   # bitstring omitted
    >>> rxgobj.notify_failure(('mirror1',45, '...'))
    >>> print rxgobj.get_next_xorrequest()
    ('mirror2',45, '...')
    >>> rxgobj.notify_success(('mirror2',45, '...'), '...')  
    >>> print rxgobj.get_next_xorrequest()
    ()

  """




  def __init__(self, mirrorinfolist, blocklist, manifestdict, privacythreshold, pollinginterval = .1):
    """
    <Purpose>
      Get ready to handle requests for XOR block strings, etc.

    <Arguments>
      mirrorinfolist: a list of dictionaries with information about mirrors

      blocklist: the blocks that need to be retrieved

      manifestdict: the manifest with information about the release

      privacythreshold: the number of mirrors that would need to collude to
                       break privacy

      pollinginterval: the amount of time to sleep between checking for
                       the ability to serve a mirror.   

    <Exceptions>
      TypeError may be raised if invalid parameters are given.

      InsufficientMirrors if there are not enough mirrors

    """
    self.blocklist = blocklist
    self.manifestdict = manifestdict
    self.privacythreshold = privacythreshold
    self.pollinginterval = pollinginterval

    if len(mirrorinfolist) < self.privacythreshold:
      raise InsufficientMirrors("Requested the use of "+str(self.privacythreshold)+" mirrors, but only "+str(len(mirrorinfolist))+" were available.")

    # now we do the 'random' part.   I copy the mirrorinfolist to avoid changing
    # the list in place.
    self.fullmirrorinfolist = mirrorinfolist[:]
    random.shuffle(self.fullmirrorinfolist)


    # let's make a list of mirror information (what has been retrieved, etc.)
    self.activemirrorinfolist = []
    for mirrorinfo in self.fullmirrorinfolist[:self.privacythreshold]:
      thisrequestinfo = {}
      thisrequestinfo['mirrorinfo'] = mirrorinfo
      thisrequestinfo['servingrequest'] = False
      thisrequestinfo['blocksneeded'] = blocklist[:]
      thisrequestinfo['blockbitstringlist'] = []
  
      self.activemirrorinfolist.append(thisrequestinfo)
      

    bitstringlength = uppirlib.compute_bitstring_length(manifestdict['blockcount'])
    # let's generate the bitstrings
    for thisrequestinfo in self.activemirrorinfolist[:-1]:

      for block in blocklist:
        # I'll generate random bitstrings for N-1 of the mirrors...
        thisrequestinfo['blockbitstringlist'].append(_randomnumberfunction(bitstringlength))

    # now, let's do the 'derived' ones...
    for blocknum in range(len(blocklist)):
      thisbitstring = '\0'*bitstringlength
      
      # xor the random strings together
      for requestinfo in self.activemirrorinfolist[:-1]:
        thisbitstring = simplexordatastore.do_xor(thisbitstring, requestinfo['blockbitstringlist'][blocknum])
   
      # ...and flip the appropriate bit for the block we want
      thisbitstring = uppirlib.flip_bitstring_bit(thisbitstring, blocklist[blocknum])
      self.activemirrorinfolist[-1]['blockbitstringlist'].append(thisbitstring)
    
    # we're done setting up the bitstrings!


    # want to have a structure for locking
    self.tablelock = threading.Lock()
    
      
      

    # and we'll keep track of the ones that are waiting in the wings...
    self.backupmirrorinfolist = self.fullmirrorinfolist[self.privacythreshold:]

    # the returned blocks are put here...
    self.returnedxorblocksdict = {}
    for blocknum in blocklist:
      # make these all empty lists to start with
      self.returnedxorblocksdict[blocknum] = []
    
    # and here is where they are put when reconstructed
    self.finishedblockdict = {}

    # and we're ready!




  def get_next_xorrequest(self):
    """
    <Purpose>
      Gets the next requesttuple that should be returned

    <Arguments>
      None

    <Exceptions>
      InsufficientMirrors if there are not enough mirrors
 
    <Returns>
      Either a requesttuple (mirrorinfo, blocknumber, bitstring) or ()
      when all strings have been retrieved...

    """

    # Three cases I need to worry about:
    #   1) nothing that still needs to be requested -> return ()
    #   2) requests remain, but all mirrors are busy -> block until ready
    #   3) there is a request ready -> return the tuple
    # 

    # I'll exit via return.   I will loop to sleep while waiting.   
    # I could use a condition variable here, but this should be fine.   There
    # should almost always be < 5 threads.   Also, why would we start more
    # threads than there are mirrors we will contact?   (As such, sleeping
    # should only happen at the very end)
    while True:
      # lock the table...
      self.tablelock.acquire()

      # but always release it
      try:
        stillserving = False
        for requestinfo in self.activemirrorinfolist:
  
          # if this mirror is serving a request, skip it...
          if requestinfo['servingrequest']:
            stillserving = True
            continue
        
          # this mirror is done...
          if len(requestinfo['blocksneeded']) == 0:
            continue
      
          # otherwise set it to be taken...
          requestinfo['servingrequest'] = True
          return (requestinfo['mirrorinfo'], requestinfo['blocksneeded'][0], requestinfo['blockbitstringlist'][0])

        if not stillserving:
          return ()

      finally:
        # I always want someone else to be able to get the lock
        self.tablelock.release()

      # otherwise, I've looked an nothing is ready...   I'll sleep and retry
      time.sleep(self.pollinginterval)
   




  def notify_failure(self, xorrequesttuple):
    """
    <Purpose>
      Handles that a mirror has failed

    <Arguments>
      The XORrequesttuple that was returned by get_next_xorrequest

    <Exceptions>
      InsufficientMirrors if there are not enough mirrors

      An internal error is raised if the XORrequesttuple is bogus
 
    <Returns>
      None

    """
    # I should lock the table...
    self.tablelock.acquire()

    # but *always* release it
    try:
      # if we're out of replacements, quit
      if len(self.backupmirrorinfolist) == 0:
        raise InsufficientMirrors("There are no replacement mirrors")

      nextmirrorinfo = self.backupmirrorinfolist.pop(0)
    
      failedmirrorsinfo = xorrequesttuple[0]
    
      # now, let's find the activemirror this corresponds ro.
      for activemirrorinfo in self.activemirrorinfolist:
        if activemirrorinfo['mirrorinfo'] == failedmirrorsinfo:
      
          # let's mark it as inactive and set up a different mirror
          activemirrorinfo['mirrorinfo'] = nextmirrorinfo
          activemirrorinfo['servingrequest'] = False
          return

      raise Exception("InternalError: Unknown mirror in notify_failure")

    finally:
      # release the lock
      self.tablelock.release()
    



  def notify_success(self, xorrequesttuple, xorblock):
    """
    <Purpose>
      Handles the receipt of an xorblock

    <Arguments>
      xorrequesttuple: The tuple that was returned by get_next_xorrequest

      xorblock: the data returned by the mirror

    <Exceptions>
      Assertions / IndexError / TypeError / InternalError if the 
      XORrequesttuple is bogus
 
    <Returns>
      None

    """

    # acquire the lock...
    self.tablelock.acquire()
    #... but always release it
    try:
      thismirrorsinfo = xorrequesttuple[0]
    
      # now, let's find the activemirror this corresponds ro.
      for activemirrorinfo in self.activemirrorinfolist:
        if activemirrorinfo['mirrorinfo'] == thismirrorsinfo:
        
          # let's mark it as inactive and pop off the blocks, etc.
          activemirrorinfo['servingrequest'] = False
          
          # remove the block and bitstring (asserting they match what we said 
          # before)
          blocknumber = activemirrorinfo['blocksneeded'].pop(0)
          bitstring = activemirrorinfo['blockbitstringlist'].pop(0)
          assert(blocknumber == xorrequesttuple[1])
          assert(bitstring == xorrequesttuple[2])
  
          # add the xorblockinfo to the dict
          xorblockdict = {}
          xorblockdict['bitstring'] = bitstring
          xorblockdict['mirrorinfo'] = thismirrorsinfo
          xorblockdict['xorblock'] = xorblock
          self.returnedxorblocksdict[blocknumber].append(xorblockdict)

          # if we don't have all of the pieces, continue
          if len(self.returnedxorblocksdict[blocknumber]) != self.privacythreshold:
            return

          # if we have all of the pieces, reconstruct it
          resultingblock = _reconstruct_block(self.returnedxorblocksdict[blocknumber])

          # let's check the hash...
          resultingblockhash = uppirlib.find_hash(resultingblock, self.manifestdict['hashalgorithm'])
          if resultingblockhash != self.manifestdict['blockhashlist'][blocknumber]:
            # TODO: We should notify the vendor!
            raise Exception('Should notify vendor that one of the mirrors or manifest is corrupt')

          # otherwise, let's put this in the finishedblockdict
          self.finishedblockdict[blocknumber] = resultingblock
          
          # it should be safe to delete this
          del self.returnedxorblocksdict[blocknumber]

          return
  
      raise Exception("InternalError: Unknown mirror in notify_failure")

    finally:
      # release the lock
      self.tablelock.release()


    

    
  def return_block(self, blocknum):
    """
    <Purpose>
      Delivers a block.  This presumes there is sufficient cached xorblock info

    <Arguments>
      blocknum: the block number to return

    <Exceptions>
      KeyError if the block isn't known
 
    <Returns>
      The block

    """
    return self.finishedblockdict[blocknum]
    
    
